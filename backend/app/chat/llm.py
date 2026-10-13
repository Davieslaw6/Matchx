"""Configurable LLM client with structured tool calling (Anthropic or OpenAI-compatible).

Neutral turn format used by the orchestrator:
  {"role":"user","text":str}
  {"role":"assistant","text":str,"tool_calls":[{"id","name","args"}]}
  {"role":"tool","results":[{"id","name","content":str}]}
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
import httpx


class LLMError(Exception):
    pass


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list = field(default_factory=list)


class AnthropicLLM:
    def __init__(self, api_key, model, base_url="", timeout_s=60.0, transport=None):
        if not api_key:
            raise LLMError("LLM_API_KEY is not configured")
        self.model = model
        self.http = httpx.Client(base_url=base_url or "https://api.anthropic.com", timeout=timeout_s, transport=transport,
                                 headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"})

    @staticmethod
    def _convert(turns):
        out = []
        for t in turns:
            if t["role"] == "user":
                out.append({"role": "user", "content": t["text"]})
            elif t["role"] == "assistant":
                blocks = ([{"type": "text", "text": t["text"]}] if t.get("text") else []) + \
                         [{"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]} for c in t.get("tool_calls", [])]
                out.append({"role": "assistant", "content": blocks})
            else:
                out.append({"role": "user", "content": [{"type": "tool_result", "tool_use_id": r["id"], "content": r["content"]}
                                                          for r in t["results"]]})
        return out

    def complete(self, system, turns, tools) -> LLMResponse:
        body = {"model": self.model, "max_tokens": 1500, "system": system, "messages": self._convert(turns),
                "tools": [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tools]}
        try:
            r = self.http.post("/v1/messages", json=body)
        except httpx.TransportError as e:
            raise LLMError(f"LLM provider unreachable: {e}")
        if r.status_code != 200:
            raise LLMError(f"LLM provider error HTTP {r.status_code}")
        resp = LLMResponse()
        for b in r.json().get("content", []):
            if b.get("type") == "text":
                resp.text += b["text"]
            elif b.get("type") == "tool_use":
                resp.tool_calls.append({"id": b["id"], "name": b["name"], "args": b.get("input") or {}})
        return resp


class OpenAILLM:
    def __init__(self, api_key, model, base_url="", timeout_s=60.0, transport=None):
        if not api_key:
            raise LLMError("LLM_API_KEY is not configured")
        self.model = model
        self.http = httpx.Client(base_url=base_url or "https://api.openai.com/v1", timeout=timeout_s, transport=transport,
                                 headers={"Authorization": f"Bearer {api_key}"})

    @staticmethod
    def _convert(system, turns):
        out = [{"role": "system", "content": system}]
        for t in turns:
            if t["role"] == "user":
                out.append({"role": "user", "content": t["text"]})
            elif t["role"] == "assistant":
                m = {"role": "assistant", "content": t.get("text") or None}
                if t.get("tool_calls"):
                    m["tool_calls"] = [{"id": c["id"], "type": "function",
                                        "function": {"name": c["name"], "arguments": json.dumps(c["args"])}} for c in t["tool_calls"]]
                out.append(m)
            else:
                out += [{"role": "tool", "tool_call_id": r["id"], "content": r["content"]} for r in t["results"]]
        return out

    def complete(self, system, turns, tools) -> LLMResponse:
        body = {"model": self.model, "messages": self._convert(system, turns),
                "tools": [{"type": "function", "function": t} for t in tools]}
        try:
            r = self.http.post("/chat/completions", json=body)
        except httpx.TransportError as e:
            raise LLMError(f"LLM provider unreachable: {e}")
        if r.status_code != 200:
            raise LLMError(f"LLM provider error HTTP {r.status_code}")
        msg = r.json()["choices"][0]["message"]
        resp = LLMResponse(text=msg.get("content") or "")
        for c in msg.get("tool_calls") or []:
            try:
                args = json.loads(c["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            resp.tool_calls.append({"id": c["id"], "name": c["function"]["name"], "args": args})
        return resp


def build_llm(cfg, **kw):
    if cfg.llm_provider == "anthropic":
        return AnthropicLLM(cfg.llm_api_key, cfg.llm_model, cfg.llm_base_url, cfg.llm_timeout_s, **kw)
    if cfg.llm_provider == "openai":
        return OpenAILLM(cfg.llm_api_key, cfg.llm_model, cfg.llm_base_url, cfg.llm_timeout_s, **kw)
    raise LLMError(f"Unknown LLM provider '{cfg.llm_provider}'")
