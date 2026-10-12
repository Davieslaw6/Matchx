"""Strict parser for football-data.co.uk historical results CSV files."""
import csv
from datetime import date, datetime, time, timezone
from io import StringIO
from typing import Any

class CsvImportError(ValueError):
    pass

_REQUIRED = {"Div", "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "FTR"}

def _parse_date(raw: str) -> date:
    for fmt in ("%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw.strip(), fmt).date()
        except ValueError:
            continue
    raise CsvImportError(f"Unsupported match date format: {raw!r}")

def parse_results_csv(content: bytes, *, competition_code: str | None = None) -> list[dict[str, Any]]:
    """Parse only rows with complete, internally consistent final-score data."""
    if not content or len(content) > 25 * 1024 * 1024:
        raise CsvImportError("CSV must be non-empty and no larger than 25 MiB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CsvImportError("CSV must be UTF-8 encoded.") from exc
    reader = csv.DictReader(StringIO(text))
    headers = set(reader.fieldnames or [])
    missing = _REQUIRED - headers
    if missing:
        raise CsvImportError(f"Required columns are missing: {', '.join(sorted(missing))}")
    records: list[dict[str, Any]] = []
    for line_number, row in enumerate(reader, start=2):
        if not row or not any((value or "").strip() for value in row.values()):
            continue
        division = (row.get("Div") or "").strip()
        if competition_code and division != competition_code:
            continue
        home = (row.get("HomeTeam") or "").strip()
        away = (row.get("AwayTeam") or "").strip()
        try:
            home_goals = int((row.get("FTHG") or "").strip())
            away_goals = int((row.get("FTAG") or "").strip())
            match_date = _parse_date(row.get("Date") or "")
        except (ValueError, CsvImportError) as exc:
            raise CsvImportError(f"Invalid result row at line {line_number}: {exc}") from exc
        if not home or not away or home.casefold() == away.casefold() or min(home_goals, away_goals) < 0:
            raise CsvImportError(f"Invalid teams or negative score at line {line_number}.")
        expected_result = "H" if home_goals > away_goals else "A" if home_goals < away_goals else "D"
        actual_result = (row.get("FTR") or "").strip().upper()
        if actual_result != expected_result:
            raise CsvImportError(f"FTR conflicts with score at line {line_number}.")
        kickoff = datetime.combine(match_date, time(12, 0), tzinfo=timezone.utc)
        # The CSV's date often lacks kickoff time. Noon UTC is a deterministic placeholder,
        # not a verified kickoff; callers must retain kickoff_precision='date_only'.
        records.append({
            "provider": "football-data.co.uk",
            "provider_fixture_id": f"{division}:{match_date.isoformat()}:{home}:{away}",
            "competition_code": division,
            "home_team_name": home,
            "away_team_name": away,
            "match_date": match_date,
            "kickoff_at": kickoff,
            "kickoff_precision": "date_only",
            "home_goals": home_goals,
            "away_goals": away_goals,
            "result": expected_result,
            "source_line": line_number,
        })
    return records
