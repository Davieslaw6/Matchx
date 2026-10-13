import httpx, pytest
from app.data.provider import FootballDataOrgClient, ProviderError, ProviderRestricted, normalise_match
from app.data.ingest import ingest_matches
from app.db import Base, make_engine, make_session_factory
from app.models import Fixture, MatchResult
from sqlalchemy import select, func
from .helpers import league_payload, raw_match
from datetime import datetime, timezone


def client(handler, **kw):
    return FootballDataOrgClient("k", "https://x.test/v4", transport=httpx.MockTransport(handler),
                                 sleep=lambda s: None, max_retries=2, **kw)


def test_normalise_keeps_missing_scores_as_none():
    m = normalise_match(raw_match(1, datetime(2026, 9, 1, tzinfo=timezone.utc), 0, 1, "TIMED"), "PL")
    assert m.home_goals is None and m.away_goals is None and m.season == 2026


def test_requires_api_key():
    with pytest.raises(ProviderError):
        FootballDataOrgClient("", "https://x.test")


def test_retries_then_succeeds():
    calls = {"n": 0}
    def h(req):
        calls["n"] += 1
        return httpx.Response(500) if calls["n"] < 3 else httpx.Response(200, json=league_payload(rounds=1))
    assert len(client(h).get_matches("PL", 2026)) == 32 and calls["n"] == 3


def test_bounded_retries_then_error():
    calls = {"n": 0}
    def h(req): calls["n"] += 1; return httpx.Response(503)
    with pytest.raises(ProviderError):
        client(h).get_matches("PL")
    assert calls["n"] == 3


def test_timeout_is_bounded():
    calls = {"n": 0}
    def h(req): calls["n"] += 1; raise httpx.ConnectTimeout("t")
    with pytest.raises(ProviderError):
        client(h).get_matches("PL")
    assert calls["n"] == 3


def test_403_is_restricted_not_retried():
    calls = {"n": 0}
    def h(req): calls["n"] += 1; return httpx.Response(403)
    with pytest.raises(ProviderRestricted):
        client(h).get_matches("PL", 2024)
    assert calls["n"] == 1


def test_cache_avoids_second_call():
    calls = {"n": 0}
    def h(req): calls["n"] += 1; return httpx.Response(200, json={"matches": []})
    c = client(h)
    c.get_matches("PL", 2026); c.get_matches("PL", 2026)
    assert calls["n"] == 1


def test_malformed_records_skipped():
    c = client(lambda r: httpx.Response(200, json={"matches": [{"id": 1}, *league_payload(rounds=1)["matches"][:2]]}))
    assert len(c.get_matches("PL")) == 2


def make_session():
    eng = make_engine("sqlite://"); Base.metadata.create_all(eng)
    return make_session_factory(eng)()


def test_ingest_is_idempotent_and_dedupes():
    s = make_session()
    ms = [normalise_match(r, "PL") for r in league_payload(rounds=1)["matches"]]
    r1 = ingest_matches(s, 'football-data.org', ms)
    r2 = ingest_matches(s, 'football-data.org', ms + ms[:5])
    assert r1.fixtures_new == len(ms) and r2.fixtures_new == 0
    assert s.scalar(select(func.count(Fixture.id))) == len(ms)
    assert s.scalar(select(func.count(MatchResult.id))) == r1.results_recorded == 30


def test_finished_without_score_is_skipped_not_zeroed():
    s = make_session()
    bad = raw_match(1, datetime(2026, 9, 1, tzinfo=timezone.utc), 0, 1, "FINISHED", None, None)
    rep = ingest_matches(s, 'football-data.org', [normalise_match(bad, "PL")])
    assert rep.skipped_invalid == 1 and s.scalar(select(func.count(MatchResult.id))) == 0
