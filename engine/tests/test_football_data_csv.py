"""Parsing tests on a hand-written CSV in football-data.co.uk's column layout
(test-only example rows, not real results)."""
from datetime import date

from sportsmodel.providers.football_data_csv import decode, parse_csv, season_code

CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,FTR,HS,AS,HST,AST,B365CH,B365CD,B365CA,AvgCH,AvgCD,AvgCA
XX,09/08/2025,20:00,Home A,Away B,2,1,H,14,9,6,3,1.80,3.60,4.50,1.85,3.55,4.40
XX,10/08/25,15:00,Home C,Away D,0,0,D,,,,,2.10,3.20,3.50,,,
XX,16/08/2025,15:00,Home E,Away F,,,,,,,,,,,,,
,,,,,,,,,,,,,,,,,
"""


def test_parses_played_rows_and_skips_unplayed_and_blank():
    rows = parse_csv(CSV, "XX", "2526")
    assert len(rows) == 2
    a, b = rows
    assert a.played_on == date(2025, 8, 9) and (a.home_goals, a.away_goals) == (2, 1)
    assert a.closing_odds == (1.85, 3.55, 4.40) and a.closing_odds_source == "AvgC"
    assert b.played_on == date(2025, 8, 10) and b.home_shots is None
    assert b.closing_odds == (2.10, 3.20, 3.50) and b.closing_odds_source == "B365C"


def test_season_code_and_decoding():
    assert season_code(2025) == "2526" and season_code(1999) == "9900"
    assert decode("﻿Div".encode("utf-8")) == "Div"
    assert decode("Atl\xe9tico".encode("latin-1")) == "Atlético"
