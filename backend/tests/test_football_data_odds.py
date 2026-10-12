from app.sports.football_data_csv import parse_results_csv

def test_parses_valid_bookmaker_and_average_1x2_odds():
    source = (
        b"Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A,AvgH,AvgD,AvgA\n"
        b"E0,12/08/25,15:00,Arsenal,Forest,2,1,H,1.80,3.60,4.50,1.75,3.70,4.70\n"
    )
    record = parse_results_csv(source)[0]
    assert len(record["odds"]) == 2
    assert record["odds"][0]["bookmaker"] == "Bet365"
    assert str(record["odds"][0]["home"]) == "1.80"
    assert record["odds_rejected"] == []
    assert len(record["odds_raw_hash"]) == 64

def test_incomplete_odds_triplet_is_reported_not_fabricated():
    source = (
        b"Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A\n"
        b"E0,12/08/25,Arsenal,Forest,2,1,H,1.80,,4.50\n"
    )
    record = parse_results_csv(source)[0]
    assert record["odds"] == []
    assert record["odds_rejected"] == [{"bookmaker":"Bet365","reason":"incomplete_triplet"}]
