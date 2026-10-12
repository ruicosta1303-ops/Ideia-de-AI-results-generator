import pytest

from sportsmodel.teams import API, CSV, TeamMappingError, historical_only_aliases, load_mapping


def test_real_mapping_file_is_consistent():
    rows = load_mapping()
    api = [r for r in rows if r[0] == API]
    csv = [r for r in rows if r[0] == CSV]
    assert len(api) == len(csv) == 132


def test_unmapped_current_season_team_is_an_error():
    mapping = [(CSV, "Arsenal", "Arsenal FC")]
    with pytest.raises(TeamMappingError, match="Newcomers"):
        historical_only_aliases({"2627": {"Arsenal", "Newcomers"}}, "2627", mapping)


def test_historical_only_team_keeps_its_csv_name():
    mapping = [(CSV, "Arsenal", "Arsenal FC")]
    assert historical_only_aliases({"2122": {"Arsenal", "Old Club"}, "2627": {"Arsenal"}}, "2627", mapping) == [
        (CSV, "Old Club", "Old Club")]


def test_csv_only_teams_keep_their_names():
    from sportsmodel.teams import csv_only_aliases

    out = csv_only_aliases({"AUT": {"Club A", "Club B"}}, {"PL": {"Arsenal"}}, [(CSV, "Arsenal", "Arsenal FC")])
    assert out == [(CSV, "Club A", "Club A"), (CSV, "Club B", "Club B")]


def test_same_name_in_two_leagues_is_an_error():
    from sportsmodel.teams import csv_only_aliases

    with pytest.raises(TeamMappingError, match="both"):
        csv_only_aliases({"AUT": {"Rapid"}, "SWZ": {"Rapid"}}, {}, [])
    with pytest.raises(TeamMappingError, match="both"):
        csv_only_aliases({"AUT": {"Nacional"}}, {"PPL": {"Nacional"}}, [])
