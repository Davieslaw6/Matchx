import json, pytest, httpx
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.chat.llm import AnthropicLLM, LLMError, LLMResponse, OpenAILLM
from app.chat.orchestrator import unverified_percentages
from app.config import Settings
from app.chat import tools
from app.main import app, get_llm, get_provider
from app.models import Conversation, Fixture, Message
from .helpers import af_payload, league_payload
from .test_api import FakeProvider, env, local, seed  # noqa: F401  (fixtures)
from app.data.provider import normalise_af_fixture


class Scripted:
    """Fake LLM: fn(turns) -> LLMResponse. Records calls."""
    def __init__(self, fn): self.fn, self.calls = fn, []
    def complete(self, system, turns, tools_):
        self.calls.append(turns)
        return self.fn(turns)


def call(i, name, **args): return {"id": f"c{i}", "name": name, "args": args}
def last_tool_json(turns): return json.loads([t for t in turns if t["role"] == "tool"][-1]["results"][0]["content"])


def install(llm): app.dependency_overrides[get_llm] = lambda: llm


def predicting_llm(extra_text=""):
    def fn(turns):
        n = sum(t["role"] == "tool" for t in turns)
        if n == 0:
            return LLMResponse("", [call(1, "search_fixtures", home="Manchester City", away="Burnley")])
        if n == 1:
            fid = last_tool_json(turns)["fixtures"][0]["fixture_id"]
            return LLMResponse("", [call(2, "calculate_match_prediction", fixture_id=fid)])
        p = last_tool_json(turns)
        return LLMResponse(f"Match: {p['home_team']} vs {p['away_team']}. Home win {100*p['result']['home']:.1f}%. {extra_text}")
    return fn


def test_full_prediction_flow_with_verified_figures(env):
    c = local(); seed(c); install(Scripted(predicting_llm()))
    r = c.post("/api/chat", json={"message": "Analyze Man City vs Burnley"}).json()
    assert [t["tool"] for t in r["tools_used"]] == ["search_fixtures", "calculate_match_prediction"]
    assert r["unverified_figures"] == [] and "Home win" in r["reply"] and r["provider"] == "football-data.org"
    assert len(c.get("/api/predictions").json()) == 1       # prediction stored by the engine call


def test_invented_probability_is_flagged(env):
    c = local(); seed(c); install(Scripted(predicting_llm("Over 2.5 is 73.4% likely.")))
    r = c.post("/api/chat", json={"message": "x"}).json()
    assert r["unverified_figures"] == ["73.4%"] and "could not be matched" in r["reply"]


def test_percentage_without_any_tool_call_is_flagged(env):
    local(); install(Scripted(lambda t: LLMResponse("Arsenal win 60% of the time.")))
    r = local().post("/api/chat", json={"message": "who wins?"}).json()
    assert r["unverified_figures"] == ["60%"] and r["tools_used"] == []


def test_declined_prediction_is_reported_not_crashing(env):
    c = local(); c.post("/api/sync", json={})          # synced but NOT trained
    def fn(turns):
        n = sum(t["role"] == "tool" for t in turns)
        if n == 0: return LLMResponse("", [call(1, "search_fixtures", home="Manchester City", away="Burnley")])
        if n == 1: return LLMResponse("", [call(2, "calculate_match_prediction", fixture_id=last_tool_json(turns)["fixtures"][0]["fixture_id"])])
        return LLMResponse("No prediction: " + last_tool_json(turns)["reason"])
    install(Scripted(fn))
    r = c.post("/api/chat", json={"message": "x"}).json()
    assert r["tools_used"][1]["ok"] is False and "No trained model" in r["reply"]


def test_unknown_tool_and_bad_args_handled(env):
    def fn(turns):
        n = sum(t["role"] == "tool" for t in turns)
        if n == 0: return LLMResponse("", [call(1, "place_bet"), call(2, "get_team_form", nonsense=1)])
        return LLMResponse("done")
    install(Scripted(fn))
    r = local().post("/api/chat", json={"message": "x"}).json()
    assert [t["ok"] for t in r["tools_used"]] == [False, False] and r["reply"] == "done"


def test_tool_round_limit(env):
    install(Scripted(lambda t: LLMResponse("", [call(1, "get_model_evaluation")])))
    r = local().post("/api/chat", json={"message": "x"}).json()
    assert "couldn't complete" in r["reply"] and len(r["tools_used"]) == 6


def test_llm_failure_returns_502_and_logs_error(env):
    def boom(turns): raise LLMError("down")
    install(Scripted(boom))
    c = local(); r = c.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 502 and "No answer was generated" in r.json()["detail"]


def test_conversation_history_export_delete(env):
    c = local(); install(Scripted(lambda t: LLMResponse("hi")))
    cid = c.post("/api/chat", json={"message": "one"}).json()["conversation_id"]
    c.post("/api/chat", json={"message": "two", "conversation_id": cid})
    exp = c.get(f"/api/conversations/{cid}/export").json()
    assert [m["role"] for m in exp["messages"]] == ["user", "assistant", "user", "assistant"]
    assert c.delete(f"/api/conversations/{cid}").status_code == 200
    assert c.get(f"/api/conversations/{cid}/export").status_code == 404
    assert c.post("/api/chat", json={"message": "x", "conversation_id": 999}).status_code == 404
    c.post("/api/chat", json={"message": "a"}); assert c.delete("/api/conversations").status_code == 200
    with env["sf"]() as s: assert s.scalar(select(Message)) is None


def test_chat_requires_access(env):
    install(Scripted(lambda t: LLMResponse("x")))
    assert TestClient(app, client=("203.0.113.9", 1)).post("/api/chat", json={"message": "x"}).status_code == 403
    assert local().post("/api/chat", json={"message": ""}).status_code == 422


# ---- tools ----
def run(env, name, **kw):
    with env["sf"]() as s:
        return tools.REGISTRY[name](s, env["cfg"], "football-data.org", **kw)


def test_tools_form_h2h_stats(env):
    c = local(); seed(c)
    f = run(env, "get_team_form", team="Arsenal", n=100)
    assert f["matches_used"] == 20 and f["wins"] + f["draws"] + f["losses"] == 20       # n clamped
    assert run(env, "get_team_form", team="Atlantis")["error"]
    h = run(env, "get_head_to_head", team_a="Arsenal", team_b="Chelsea")
    assert h["matches_used"] == 6
    st = run(env, "get_team_statistics", team="Manchester City")
    assert st["matches_used"] == 30 and st["home"]["played"] == 15 and st["away"]["played"] == 15


def test_search_upcoming_predictions_market_and_ranking(env):
    c = local(); seed(c)
    r = run(env, "search_upcoming_predictions", competition="PL", market="over_1.5", min_probability=0.0)
    ps = [m["probability"] for m in r["matches"]]
    assert len(ps) == 2 and ps == sorted(ps, reverse=True) and "not value" in r["note"]
    assert run(env, "search_upcoming_predictions", competition="PL", market="over_1.5", min_probability=0.999)["matches"] == []
    assert "error" in run(env, "search_upcoming_predictions", competition="PL", market="nonsense")
    assert run(env, "search_fixtures", competition="PL")["fixtures"]


def test_model_evaluation_warns_when_sample_small(env):
    seed(local())
    e = run(env, "get_model_evaluation")
    assert e["evaluated_predictions"] == 0 and "too few" in e["warning"] and e["models"][0]["active"]


def test_guard_helper():
    out = [{"result": {"home": 0.5123}, "win_pct": 60.0}]
    assert unverified_percentages("51.2% and 60% and 99%", out) == ["99%"]


# ---- provider selection + isolation ----
def test_provider_selection_and_data_isolation(env):
    env["cfg"] = Settings(access_token="", football_data_api_key="k", api_football_api_key="k2", enabled_leagues="PL")
    c = local()
    assert c.get("/api/providers").json()["active"] == "football-data.org"
    assert c.put("/api/provider", json={"name": "nope"}).status_code == 400
    seed(c)
    fd_fixture = c.post("/api/fixtures/search", json={"home": "Manchester City", "away": "Burnley"}).json()["fixtures"][0]["fixture_id"]

    class AF(FakeProvider):
        name = "api-football"
        def get_matches(self, code, season=None):
            return [normalise_af_fixture(r, code) for r in af_payload(self.payload)["response"]]
    env["provider"] = AF()
    assert c.put("/api/provider", json={"name": "api-football"}).json()["active"] == "api-football"
    assert c.post("/api/fixtures/search", json={"home": "Manchester City", "away": "Burnley"}).json()["status"] == "not_found"  # no mixing
    assert c.post(f"/api/predict/{fd_fixture}").status_code == 422                                                         # wrong provider
    assert c.post("/api/sync", json={}).json()["PL"]["provider"] == "api-football"
    assert c.post("/api/train/PL").json()["provider"] == "api-football"
    f = c.post("/api/fixtures/search", json={"home": "Manchester City", "away": "Burnley"}).json()["fixtures"][0]["fixture_id"]
    p = c.post(f"/api/predict/{f}").json()
    assert f != fd_fixture and p["provider"] == "api-football" and p["model_version"].startswith("api-football-PL-")
    c.put("/api/provider", json={"name": "football-data.org"})                       # switching back: original data intact
    assert c.post(f"/api/predict/{fd_fixture}").status_code == 200


def test_cannot_select_unconfigured_provider(env):
    assert local().put("/api/provider", json={"name": "api-football"}).status_code == 400


# ---- LLM clients ----
def test_anthropic_client_roundtrip():
    seen = {}
    def h(req):
        seen["body"] = json.loads(req.content); seen["key"] = req.headers["x-api-key"]
        return httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}, {"type": "tool_use", "id": "t1", "name": "get_model_evaluation", "input": {}}]})
    llm = AnthropicLLM("sk", "m", transport=httpx.MockTransport(h))
    turns = [{"role": "user", "text": "q"}, {"role": "assistant", "text": "", "tool_calls": [{"id": "t0", "name": "a", "args": {"x": 1}}]},
             {"role": "tool", "results": [{"id": "t0", "name": "a", "content": "{}"}]}]
    r = llm.complete("sys", turns, tools.TOOL_SPECS)
    assert r.text == "ok" and r.tool_calls == [{"id": "t1", "name": "get_model_evaluation", "args": {}}]
    b = seen["body"]
    assert b["system"] == "sys" and len(b["tools"]) == 8 and b["messages"][2]["content"][0]["type"] == "tool_result"
    assert seen["key"] == "sk"


def test_openai_client_roundtrip_and_errors():
    def h(req):
        body = json.loads(req.content)
        assert body["messages"][0]["role"] == "system" and body["tools"][0]["type"] == "function"
        return httpx.Response(200, json={"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "x", "type": "function", "function": {"name": "get_team_form", "arguments": "{\"team\": \"Arsenal\"}"}}]}}]})
    r = OpenAILLM("k", "m", transport=httpx.MockTransport(h)).complete("s", [{"role": "user", "text": "q"}], tools.TOOL_SPECS)
    assert r.tool_calls[0]["args"] == {"team": "Arsenal"}
    with pytest.raises(LLMError):
        OpenAILLM("k", "m", transport=httpx.MockTransport(lambda q: httpx.Response(500))).complete("s", [], [])
    with pytest.raises(LLMError):
        AnthropicLLM("", "m")
