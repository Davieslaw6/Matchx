from __future__ import annotations
import json, logging, re
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..models import Conversation, Message
from .llm import LLMError
from .tools import REGISTRY, TOOL_SPECS

log = logging.getLogger(__name__)
MAX_ROUNDS = 6

SYSTEM = """You are the explanation layer of a private football prediction app.
RULES:
- Every probability, expected-goals value and scoreline you state MUST come from a tool result in this conversation. Never estimate, adjust, round differently, or invent probabilities. Never use your own football knowledge for numbers or current facts.
- For a prediction request: call search_fixtures to find the verified fixture, then calculate_match_prediction. If several fixtures match or none, ask the user to clarify.
- If a tool returns an error or declined=true, say so plainly and explain what is missing. Do not substitute guesses.
- Probability is not confidence and not betting value; never call anything guaranteed or safe; no odds are available unless a tool returns them.
- Use this layout when presenting a prediction (omit sections with no data): Match; Expected goals; Match result; Requested market; Most probable scorelines; Analysis (form, home/away, historical, supporting factors, factors that could make it wrong); Data quality (provider, timestamps, model version, warnings).
- Copy percentages exactly as 100*probability from tool output, one decimal place."""


def _collect_numbers(obj, acc: set):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                if str(k).endswith("_pct"):
                    acc.add(round(float(v), 1))
                elif 0 <= v <= 1:
                    acc.add(round(100 * float(v), 1))
            else:
                _collect_numbers(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_numbers(v, acc)


def unverified_percentages(text: str, tool_outputs: list) -> list[str]:
    allowed: set = set()
    for o in tool_outputs:
        _collect_numbers(o, allowed)
    bad = []
    for m in re.finditer(r"(\d+(?:\.\d+)?)\s*%", text):
        x = float(m.group(1))
        if not any(abs(x - a) <= 0.51 for a in allowed):
            bad.append(m.group(0))
    return bad


def run_chat(s: Session, cfg, llm, provider: str, user_text: str, conversation_id: int | None = None) -> dict:
    conv = s.get(Conversation, conversation_id) if conversation_id else None
    if conversation_id and conv is None:
        raise KeyError("conversation not found")
    if conv is None:
        conv = Conversation(); s.add(conv); s.flush()
    history = s.scalars(select(Message).where(Message.conversation_id == conv.id).order_by(Message.id.desc()).limit(20)).all()[::-1]
    turns = [{"role": m.role, "text": m.content} for m in history if m.role in ("user", "assistant")]
    turns.append({"role": "user", "text": user_text})
    s.add(Message(conversation_id=conv.id, role="user", content=user_text)); s.commit()

    outputs, trace, final = [], [], ""
    system = SYSTEM + f"\nSelected data provider: {provider}."
    try:
        for _ in range(MAX_ROUNDS):
            resp = llm.complete(system, turns, TOOL_SPECS)
            if not resp.tool_calls:
                final = resp.text
                break
            turns.append({"role": "assistant", "text": resp.text, "tool_calls": resp.tool_calls})
            results = []
            for c in resp.tool_calls:
                fn = REGISTRY.get(c["name"])
                if fn is None:
                    out = {"error": f"Unknown tool {c['name']}"}
                else:
                    try:
                        out = fn(s, cfg, provider, **(c["args"] or {}))
                    except TypeError as e:
                        out = {"error": f"Bad tool arguments: {e}"}
                    except Exception:   # tool failure must not crash the chat
                        log.exception("tool %s failed", c["name"])
                        out = {"error": "Internal tool error"}
                outputs.append(out)
                trace.append({"tool": c["name"], "args": c["args"], "ok": "error" not in out and not out.get("declined")})
                results.append({"id": c["id"], "name": c["name"], "content": json.dumps(out, default=str)})
            turns.append({"role": "tool", "results": results})
        else:
            final = "I couldn't complete that request within the allowed number of steps. Please try a more specific question."
    except LLMError as e:
        s.add(Message(conversation_id=conv.id, role="assistant", content=f"[error] {e}")); s.commit()
        raise

    bad = unverified_percentages(final, outputs)
    if bad:
        final += ("\n\n⚠ Some figures above could not be matched to the prediction engine's output and should be "
                  f"ignored: {', '.join(sorted(set(bad)))}.")
    s.add(Message(conversation_id=conv.id, role="assistant", content=final)); s.commit()
    return {"conversation_id": conv.id, "reply": final, "tools_used": trace, "unverified_figures": sorted(set(bad)), "provider": provider}
