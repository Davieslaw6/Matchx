import pytest
from app.sports.football_data_csv import CsvImportError, parse_results_csv

CSV = b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR\nE0,12/08/23,Arsenal,Nottingham Forest,2,1,H\n"

def test_parses_real_schema_and_marks_date_only_kickoff():
    records = parse_results_csv(CSV, competition_code="E0")
    assert len(records) == 1
    assert records[0]["home_goals"] == 2
    assert records[0]["kickoff_precision"] == "date_only"
    assert records[0]["kickoff_at"] is None

def test_rejects_result_conflicting_with_score():
    with pytest.raises(CsvImportError, match="conflicts"):
        parse_results_csv(CSV.replace(b",2,1,H", b",2,1,A"))

def test_filters_other_competitions():
    assert parse_results_csv(CSV, competition_code="SP1") == []
