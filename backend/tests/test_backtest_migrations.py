import os, subprocess, sys
import numpy as np, pandas as pd, pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from app.db import Base
from app import models  # noqa
from app.engine.backtest import backtest
from app.engine.errors import InsufficientDataError
from app.main import app
from .conftest import synth
from .test_api import env, local, seed  # noqa


def test_backtest_is_chronological_and_beats_baseline_on_structured_data():
    df = synth(seed=11, rounds=8)
    r = backtest(df, min_train=120, block_days=20)
    assert r["n_predictions"] > 50
    assert r["model"]["log_loss"] < r["baseline_outcome_frequencies"]["log_loss"]
    assert r["model"]["log_loss"] < r["baseline_uniform"]["log_loss"]
    assert r["verdict"] == "better than frequency baseline"
    assert all(b["n"] > 0 for b in r["calibration"])
    assert pd.Timestamp(r["first_prediction"], tz="UTC") >= df["date"].iloc[119].normalize()


def test_backtest_uses_only_past_data():
    df = synth(seed=5, rounds=8)
    base = backtest(df, min_train=120, block_days=20)
    tampered = df.copy()
    last = tampered["date"].max()
    tampered.loc[tampered["date"] == last, ["home_goals", "away_goals"]] = [9, 0]   # change only the very last match's score
    t = backtest(tampered, min_train=120, block_days=20)
    # only that final match's own outcome may differ; earlier-block metrics must be driven by identical training data
    assert t["n_predictions"] == base["n_predictions"]
    assert abs(t["model"]["log_loss"] - base["model"]["log_loss"]) < 0.2


def test_backtest_declines_when_too_little_data():
    with pytest.raises(InsufficientDataError):
        backtest(synth(rounds=1), min_train=120)


def test_backtest_endpoint_stores_metrics_and_tool_reports_them(env):
    from .helpers import league_payload
    from .test_api import FakeProvider
    env["provider"] = FakeProvider(league_payload(rounds=8))
    c = local(); c.post("/api/sync", json={}); assert c.post("/api/train/PL").status_code == 200
    r = c.post("/api/backtest/PL")
    assert r.status_code == 200 and r.json()["n_predictions"] > 0
    from app.chat import tools
    with env["sf"]() as s:
        e = tools.get_model_evaluation(s, env["cfg"], "football-data.org")
    assert e["backtest"]["n_predictions"] == r.json()["n_predictions"] and "No backtest" not in e.get("warning", "")


def test_alembic_migration_matches_models(tmp_path):
    db = tmp_path / "m.db"
    env_ = {**os.environ, "DATABASE_URL": f"sqlite:///{db}"}
    root = os.path.dirname(os.path.dirname(__file__))
    for cmd in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        r = subprocess.run([sys.executable, "-m", "alembic", *cmd], cwd=root, env=env_, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
    insp = inspect(create_engine(f"sqlite:///{db}"))
    tables = set(insp.get_table_names()) - {"alembic_version"}
    assert tables == set(Base.metadata.tables)
    for t, tbl in Base.metadata.tables.items():
        assert {c["name"] for c in insp.get_columns(t)} == {c.name for c in tbl.columns}


def test_forwarded_remote_client_blocked_without_token(env):
    c = local()
    assert c.get("/api/predictions", headers={"X-Forwarded-For": "198.51.100.7"}).status_code == 403
    assert c.get("/api/predictions", headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 200
