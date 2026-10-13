import httpx, pytest
from app.data.provider import ApiFootballClient, ProviderError, ProviderRestricted, normalise_af_fixture
from .helpers import af_payload, league_payload


def client(handler, **kw):
    return ApiFootballClient("k", "https://af.test", transport=httpx.MockTransport(handler), sleep=lambda s: None, max_retries=2, **kw)


def test_requires_key():
    with pytest.raises(ProviderError):
        ApiFootballClient("", "https://af.test")


def test_normalise_scheduled_and_finished():
    p = af_payload(league_payload(rounds=1))["response"]
    fin = normalise_af_fixture(p[0], "PL"); sched = normalise_af_fixture(p[-1], "PL")
    assert fin.status == "FINISHED" and fin.home_goals is not None and fin.season == 2025 and fin.matchday == 1
    assert sched.status == "TIMED" and sched.home_goals is None and sched.away_goals is None


def test_status_mapping_and_postponed_has_no_score():
    raw = af_payload(league_payload(rounds=1))["response"][0]
    raw["fixture"]["status"]["short"] = "PST"
    m = normalise_af_fixture(raw, "PL")
    assert m.status == "POSTPONED" and m.home_goals is None


def test_sends_league_id_season_and_key():
    seen = {}
    def h(req):
        seen.update(dict(req.url.params)); seen["key"] = req.headers["x-apisports-key"]
        return httpx.Response(200, json=af_payload(league_payload(rounds=1)))
    ms = client(h).get_matches("PL", 2026)
    assert seen == {"league": "39", "season": "2026", "key": "k"} and len(ms) == 32


def test_plan_error_in_200_body_is_restricted():
    h = lambda r: httpx.Response(200, json={"errors": {"plan": "Free plans do not have access to this season"}, "response": []})
    with pytest.raises(ProviderRestricted):
        client(h).get_matches("PL", 2020)


def test_rate_limit_body_is_retried():
    calls = {"n": 0}
    def h(r):
        calls["n"] += 1
        if calls["n"] < 3: return httpx.Response(200, json={"errors": {"rateLimit": "Too many requests"}, "response": []})
        return httpx.Response(200, json=af_payload(league_payload(rounds=1)))
    assert len(client(h).get_matches("PL", 2026)) == 32 and calls["n"] == 3


@pytest.mark.parametrize("err", [{"token": "Error/Missing application key"}, {"requests": "daily limit reached"}])
def test_auth_and_daily_quota_not_retried(err):
    calls = {"n": 0}
    def h(r): calls["n"] += 1; return httpx.Response(200, json={"errors": err, "response": []})
    with pytest.raises(ProviderError):
        client(h).get_matches("PL", 2026)
    assert calls["n"] == 1


def test_unknown_league_code():
    with pytest.raises(ProviderError):
        client(lambda r: httpx.Response(200, json={})).get_matches("XX", 2026)


def test_errors_as_empty_list_means_ok():
    h = lambda r: httpx.Response(200, json={"errors": [], "response": []})
    assert client(h).get_matches("PL", 2026) == []
