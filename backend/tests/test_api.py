import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.config import Settings, get_settings
from app.data.provider import NormMatch, ProviderError, ProviderRestricted, normalise_match
from app.db import Base, make_engine, make_session_factory
from app.main import app, get_provider, get_session
from app.models import Fixture, MatchResult, Prediction
from app.fixtures import resolve_fixture
from .helpers import league_payload

LOCAL = ("127.0.0.1", 5000)


class FakeProvider:
    name = "football-data.org"
    def __init__(self, payload=None, fail=False):
        self.payload, self.fail = payload or league_payload(), fail
    def get_matches(self, code, season=None):
        if self.fail: raise ProviderError("boom")
        if season is not None and season < 2023: raise ProviderRestricted("plan")
        return [normalise_match(r, code) for r in self.payload["matches"]]


@pytest.fixture()
def env():
    eng = make_engine("sqlite://"); Base.metadata.create_all(eng)
    sf = make_session_factory(eng)
    cfg = Settings(access_token="", football_data_api_key="k", enabled_leagues="PL")
    holder = {"provider": FakeProvider(), "cfg": cfg}
    def sess():
        s = sf()
        try: yield s
        finally: s.close()
    app.dependency_overrides[get_session] = sess
    app.dependency_overrides[get_settings] = lambda: holder["cfg"]
    app.dependency_overrides[get_provider] = lambda: holder["provider"]
    holder["sf"] = sf
    yield holder
    app.dependency_overrides.clear()


def local():
    return TestClient(app, client=LOCAL)


def seed(c):
    assert c.post("/api/sync", json={}).status_code == 200
    assert c.post("/api/train/PL").status_code == 200


def test_end_to_end_sync_train_search_predict_history(env):
    c = local()
    r = c.post("/api/sync", json={"seasons": [2020, 2025, 2026]}).json()["PL"]
    assert r["results_recorded"] == 90 and r["new_fixtures"] == 92
    assert any("not available" in n for n in r["notes"])        # restricted season -> disclosed
    t = c.post("/api/train/PL").json()
    assert t["n_matches"] == 90
    s = c.post("/api/fixtures/search", json={"home": "man city", "away": "Burnley"}).json()
    assert s["status"] == "found"
    fid = s["fixtures"][0]["fixture_id"]
    p = c.post(f"/api/predict/{fid}").json()
    assert sum(p["result"].values()) == pytest.approx(1.0)
    assert p["result"]["home"] > p["result"]["away"]
    assert p["home_team"] == "Manchester City FC" and p["model_version"].startswith("football-data.org-PL-dc-v1")
    assert any("goals-only" in w for w in p["warnings"])
    assert p["data_timestamps"]["last_sync"] is not None
    h = c.get("/api/predictions").json()
    assert len(h) == 1 and h[0]["evaluation"] is None


def test_prediction_evaluated_after_result_arrives(env):
    c = local(); seed(c)
    fid = c.post("/api/fixtures/search", json={"home": "Manchester City", "away": "Burnley"}).json()["fixtures"][0]["fixture_id"]
    c.post(f"/api/predict/{fid}")
    with env["sf"]() as s:
        fx = s.get(Fixture, fid); fx.status = "FINISHED"
        s.add(MatchResult(fixture_id=fid, home_goals=2, away_goals=0)); s.commit()
    ev = c.get("/api/predictions").json()[0]["evaluation"]
    assert ev["score"] == "2-0" and 0 < ev["log_loss"] and 0 <= ev["brier"] <= 2


def test_predict_without_model_is_409(env):
    c = local(); c.post("/api/sync", json={})
    with env["sf"]() as s:
        fid = s.scalar(select(Fixture.id).where(Fixture.status == "TIMED"))
    assert c.post(f"/api/predict/{fid}").status_code == 409


def test_finished_fixture_declined(env):
    c = local(); seed(c)
    with env["sf"]() as s:
        fid = s.scalar(select(Fixture.id).where(Fixture.status == "FINISHED"))
    r = c.post(f"/api/predict/{fid}")
    assert r.status_code == 422 and "declined" in r.json()["detail"]


def test_train_declines_with_too_little_data(env):
    env["provider"] = FakeProvider(league_payload(rounds=1))
    c = local(); c.post("/api/sync", json={})
    assert c.post("/api/train/PL").status_code == 422


def test_unknown_team_and_wrong_order_not_found(env):
    c = local(); seed(c)
    assert c.post("/api/fixtures/search", json={"home": "Atlantis", "away": "Burnley"}).json()["status"] == "not_found"
    assert c.post("/api/fixtures/search", json={"home": "Arsenal", "away": "Chelsea"}).json()["status"] == "not_found"


def test_resolver_aliases(env):
    c = local(); seed(c)
    with env["sf"]() as s:
        assert resolve_fixture(s, "football-data.org", "Man City", "Burnley").status == "found"
        assert resolve_fixture(s, "football-data.org", "burnley", "man city").status == "found"


def test_provider_failure_is_502_not_stale_data(env):
    env["provider"] = FakeProvider(fail=True)
    r = local().post("/api/sync", json={})
    assert r.status_code == 502


def test_not_enabled_competition_rejected(env):
    assert local().post("/api/sync", json={"competitions": ["FL1"]}).status_code == 400


def test_remote_blocked_without_token(env):
    c = TestClient(app, client=("203.0.113.9", 4000))
    assert c.get("/api/predictions").status_code == 403
    assert c.get("/health").status_code == 200


def test_token_required_when_configured(env):
    env["cfg"] = Settings(access_token="s3cret", football_data_api_key="k", enabled_leagues="PL")
    c = TestClient(app, client=("203.0.113.9", 4000))
    assert c.get("/api/predictions").status_code == 401
    assert c.get("/api/predictions", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert c.get("/api/predictions", headers={"Authorization": "Bearer s3cret"}).status_code == 200


def test_input_validation(env):
    assert local().post("/api/fixtures/search", json={"home": "", "away": "x"}).status_code == 422
