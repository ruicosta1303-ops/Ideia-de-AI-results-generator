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


# Test-only example rows in the extra-league and fixtures-file layouts (not real results).
EXTRA = """Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA,AvgCH,AvgCD,AvgCA
Austria,Bundesliga,2025/2026,03/08/2025,16:00,Club A,Club B,2,2,D,2.10,3.40,3.30,2.05,3.35,3.25
Austria,Bundesliga,2026/2027,02/08/2026,16:00,Club B,Club A,1,0,H,2.20,3.30,3.10,,,
Austria,Bundesliga,2026/2027,09/08/2026,16:00,Club A,Club C,,,,,,,,,
Austria,Bundesliga,2019/2020,04/08/2019,16:00,Old A,Old B,1,0,H,,,,,,
"""


def test_extra_league_file_seasons_odds_and_filtering():
    from sportsmodel.providers.football_data_csv import parse_extra_csv

    rows = parse_extra_csv(EXTRA, "AUT", min_start_year=2020)
    assert [(r.season, r.home_team, r.home_goals, r.away_goals) for r in rows] == [
        ("2526", "Club A", 2, 2), ("2627", "Club B", 1, 0)]
    assert rows[0].closing_odds == (2.05, 3.35, 3.25) and rows[0].closing_odds_source == "AvgC"
    assert rows[1].closing_odds == (2.20, 3.30, 3.10) and rows[1].closing_odds_source == "PSC"


def test_calendar_year_season_label():
    from sportsmodel.providers.football_data_csv import parse_extra_csv

    text = "Country,League,Season,Date,Time,Home,Away,HG,AG\nNorway,Eliteserien,2026,12/04/2026,18:00,X,Y,1,1\n"
    assert parse_extra_csv(text, "NOR", 2020)[0].season == "2026"


def test_fixture_files_convert_uk_time_to_utc():
    from datetime import date, datetime, timezone

    from sportsmodel.providers.football_data_csv import parse_fixtures

    fetched = datetime(2026, 10, 12, tzinfo=timezone.utc)
    main = "Div,Date,Time,HomeTeam,AwayTeam,B365H\nB1,17/10/2026,19:45,Club A,Club B,2.1\nE0,17/10/2026,15:00,X,Y,2\n"
    [f] = parse_fixtures(main, {"B1": "B1"}, "Div", fetched)
    assert f.kickoff_utc == datetime(2026, 10, 17, 18, 45, tzinfo=timezone.utc)  # BST = UTC+1
    assert f.leg_date == date(2026, 10, 17) and f.status == "TIMED" and f.source == "football-data.co.uk"
    extra = "Country,League,Date,Time,Home,Away\nAustria,Bundesliga,07/11/2026,14:00,Club C,Club A\n"
    [g] = parse_fixtures(extra, {"Austria": "AUT"}, "Country", fetched)
    assert g.kickoff_utc == datetime(2026, 11, 7, 14, 0, tzinfo=timezone.utc)  # GMT = UTC
    assert g.competition_code == "AUT" and (g.home_team, g.away_team) == ("Club C", "Club A")
