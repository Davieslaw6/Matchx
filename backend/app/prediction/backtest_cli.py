"""Run a real-data walk-forward backtest for one competition and write auditable reports."""
import argparse
import asyncio
import hashlib
import json
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.db import SessionLocal
from app.models import Fixture, MarketOdds, MatchResult, Team
from app.prediction.backtest import walk_forward_backtest
from app.prediction.dixon_coles import MatchObservation, ModelFitError

_OUTCOME_INDEX = {
    "home": 0, "home_win": 0, "h": 0, "1": 0,
    "draw": 1, "d": 1, "x": 1,
    "away": 2, "away_win": 2, "a": 2, "2": 2,
}
_MARKETS = {"1x2", "matchresult", "fulltimeresult"}

def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

async def load_observations(db: AsyncSession, competition_id: str) -> list[MatchObservation]:
    home = aliased(Team)
    away = aliased(Team)
    rows = (await db.execute(
        select(Fixture, MatchResult, home.name.label("home_name"), away.name.label("away_name"))
        .join(MatchResult, MatchResult.fixture_id == Fixture.id)
        .join(home, Fixture.home_team_id == home.id)
        .join(away, Fixture.away_team_id == away.id)
        .where(Fixture.competition_id == competition_id, Fixture.status == "finished")
        .order_by(Fixture.kickoff_at.asc().nulls_last(), Fixture.match_date.asc().nulls_last())
    )).all()
    if not rows:
        raise ModelFitError("Insufficient data: no completed results exist for this competition.")
    fixtures = {fixture.id: fixture for fixture, _, _, _ in rows}
    odds_rows = (await db.scalars(
        select(MarketOdds)
        .where(MarketOdds.fixture_id.in_(list(fixtures)))
        .order_by(MarketOdds.observed_at.desc())
    )).all()
    groups: dict[tuple[str, str, str, str, datetime], dict[int, float]] = {}
    for odds in odds_rows:
        fixture = fixtures.get(odds.fixture_id)
        if fixture is None or fixture.kickoff_at is None or odds.observed_at_precision == "date_only_closing":
            continue
        observed = _as_utc(odds.observed_at)
        kickoff = _as_utc(fixture.kickoff_at)
        if observed > kickoff:
            continue
        market = odds.market.casefold().replace("_", "").replace(" ", "").replace("-", "")
        if market not in _MARKETS:
            continue
        outcome = _OUTCOME_INDEX.get(odds.outcome.casefold().strip())
        if outcome is None or float(odds.decimal_odds) <= 1:
            continue
        key = (odds.fixture_id, odds.provider, odds.bookmaker or "", market, observed)
        groups.setdefault(key, {})[outcome] = float(odds.decimal_odds)
    closing_by_fixture: dict[str, tuple[float, float, float]] = {}
    candidates: dict[str, list[tuple[datetime, str, dict[int, float]]]] = {}
    for (fixture_id, _, bookmaker, _, observed), outcomes in groups.items():
        if set(outcomes) == {0, 1, 2}:
            candidates.setdefault(fixture_id, []).append((observed, bookmaker, outcomes))
    bookmaker_priority = {"Market average": 4, "Pinnacle": 3, "Bet365": 2}
    for fixture_id, snapshots in candidates.items():
        _, _, outcomes = max(snapshots, key=lambda item: (item[0], bookmaker_priority.get(item[1], 0)))
        closing_by_fixture[fixture_id] = (outcomes[0], outcomes[1], outcomes[2])

    observations: list[MatchObservation] = []
    for fixture, result, home_name, away_name in rows:
        if fixture.kickoff_at is not None:
            played_at = _as_utc(fixture.kickoff_at)
        elif fixture.match_date is not None:
            # Date-only source rows use end-of-day UTC solely for chronological training.
            # This is not a claim about actual kickoff time and is never used for market freshness.
            played_at = datetime.combine(fixture.match_date, time.max, tzinfo=timezone.utc)
        else:
            continue
        observations.append(MatchObservation(
            home_team=home_name, away_team=away_name,
            home_goals=result.home_goals, away_goals=result.away_goals,
            played_at=played_at, closing_odds=closing_by_fixture.get(fixture.id),
        ))
    return observations

def _data_hash(observations: list[MatchObservation]) -> str:
    canonical = [{
        "home_team": item.home_team, "away_team": item.away_team,
        "home_goals": item.home_goals, "away_goals": item.away_goals,
        "played_at": item.played_at.isoformat(), "closing_odds": item.closing_odds,
    } for item in observations]
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def _report_markdown(report: dict[str, Any], *, competition_id: str, data_hash: str) -> str:
    rows = []
    for name, metrics in report["metrics"].items():
        ci = metrics["log_loss_ci95"]
        ci_text = f"[{ci[0]:.4f}, {ci[1]:.4f}]" if ci else "n/a"
        rows.append(
            f"| {name} | {metrics['sample_size']} | {metrics['log_loss'] if metrics['log_loss'] is not None else 'n/a'} "
            f"| {ci_text} | {metrics['brier'] if metrics['brier'] is not None else 'n/a'} "
            f"| {metrics['rps'] if metrics['rps'] is not None else 'n/a'} "
            f"| {metrics['ece'] if metrics['ece'] is not None else 'n/a'} "
            f"| {metrics['sharpness'] if metrics['sharpness'] is not None else 'n/a'} |"
        )
    comparisons = "\n".join(
        f"- **{name}:** mean log-loss difference {value['mean_difference']:.5f}; "
        f"95% bootstrap CI {value['bootstrap_ci95']}; n={value['sample_size']} "
        f"({value['interpretation']})."
        for name, value in report["comparisons"].items()
    ) or "- No paired baseline comparisons were available."
    fold_rows = "\n".join(
        f"| {fold['fold']} | {fold['status']} | {fold.get('training_matches', 0)} "
        f"| {fold.get('test_matches', 0)} | {fold.get('m1_predictions', 0)} "
        f"| {fold.get('selected_time_decay_days', 'n/a')} |"
        for fold in report["folds"]
    )
    return f"""# MATCH X Walk-Forward Model Report

- **Status:** {report['status']}
- **Competition ID:** {competition_id}
- **Data cutoff (exclusive):** {report['data_cutoff']}
- **Eligible completed matches:** {report['eligible_matches']}
- **Dataset SHA-256:** {data_hash}
- **Git SHA:** {os.getenv('GITHUB_SHA', 'not supplied')}
- **Random seed:** {report['seed']}
- **Bootstrap replicates:** {report['bootstrap_replicates']}
- **Market baseline:** {report['market_baseline_status']}

## Out-of-sample metrics

| Model | n | Log loss | 95% bootstrap CI | Brier | RPS | ECE | Sharpness |
|---|---:|---:|---|---:|---:|---:|---:|
{chr(10).join(rows)}

Log loss, Brier and RPS are lower-is-better; ECE measures confidence/accuracy mismatch; sharpness is mean maximum class probability and is not itself an accuracy measure. Confidence intervals are bootstrap intervals over held-out fixtures and do not remove dependence between matches.

## Paired log-loss comparisons

{comparisons}

A negative M1-minus-baseline difference favours M1; a positive difference favours the baseline. Interpret the confidence interval, sample size, calibration and all baselines together.

## Walk-forward folds

| Fold | Status | Training n | Test n | M1 predictions | Selected decay days |
|---:|---|---:|---:|---:|---:|
{fold_rows}

## Skipped cases

{json.dumps(report['skipped'], indent=2)}

## Data and method notes

- Each fold trains only on matches strictly before its earliest test kickoff/cutoff.
- Exponential time decay is selected by an expanding-window validation inside each training window when enough data are available.
- M0 is an independent Poisson model using training-period league home/away scoring averages.
- The league base-rate benchmark uses Laplace-smoothed 1X2 frequencies; the uniform benchmark assigns one third to each outcome.
- Closing-market probabilities are proportional de-vigged implied probabilities from the latest complete 1X2 snapshot observed at or before kickoff. No market benchmark is claimed when such data are absent.
- Date-only source rows use end-of-day UTC only as a chronology convention; this is not an actual kickoff timestamp.
- This report describes historical evaluation, not a guarantee of future performance or profitability.
"""

async def run(args: argparse.Namespace) -> None:
    cutoff = datetime.combine(args.cutoff, time.min, tzinfo=timezone.utc)
    async with SessionLocal() as db:
        observations = await load_observations(db, args.competition_id)
    data_hash = _data_hash(observations)
    report = walk_forward_backtest(
        observations, data_cutoff=cutoff,
        initial_train_matches=args.initial_train_matches,
        test_window_matches=args.test_window_matches,
        tune_time_decay=not args.no_tune_time_decay,
        bootstrap_replicates=args.bootstrap_replicates,
        seed=args.seed,
    )
    report["dataset_sha256"] = data_hash
    report["competition_id"] = args.competition_id
    report["git_sha"] = os.getenv("GITHUB_SHA")
    json_path = args.json_output
    markdown_path = args.markdown_output
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    markdown_path.write_text(_report_markdown(report, competition_id=args.competition_id,
                                              data_hash=data_hash), encoding="utf-8")
    print(json.dumps({"status": report["status"], "dataset_sha256": data_hash,
                      "eligible_matches": report["eligible_matches"],
                      "markdown_report": str(markdown_path), "json_report": str(json_path)}, indent=2))

def main() -> None:
    parser = argparse.ArgumentParser(description="Run a chronological MATCH X model backtest.")
    parser.add_argument("--competition-id", required=True, help="Internal competition UUID from the database.")
    parser.add_argument("--cutoff", type=date.fromisoformat, required=True,
                        help="Exclusive cutoff date; no match on this date is eligible for training or testing.")
    parser.add_argument("--initial-train-matches", type=int, default=100)
    parser.add_argument("--test-window-matches", type=int, default=20)
    parser.add_argument("--bootstrap-replicates", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-tune-time-decay", action="store_true")
    parser.add_argument("--json-output", type=Path, default=Path("../docs/model_backtest_latest.json"))
    parser.add_argument("--markdown-output", type=Path, default=Path("../docs/MODEL_REPORT.md"))
    args = parser.parse_args()
    if args.initial_train_matches < 50 or args.test_window_matches < 1 or args.bootstrap_replicates < 0:
        parser.error("invalid training window, test window or bootstrap replicate count")
    asyncio.run(run(args))

if __name__ == "__main__":
    main()
