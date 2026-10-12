from sportsmodel.tune import score


def test_score_on_hand_made_rows():
    # outcome, total goals, pH, pD, pA, p(over 2.5), exp home, exp away  (test-only values)
    rows = [(0, 3, 0.5, 0.3, 0.2, 0.6, 1.6, 1.0), (2, 1, 0.9, 0.05, 0.05, 0.3, 2.5, 0.4)]
    s = score(rows)
    assert s["n"] == 2 and s["share_max_prob_over_85"] == 0.5 and s["min_expected_goals"] == 0.4
    assert s["log_loss"] > 0
