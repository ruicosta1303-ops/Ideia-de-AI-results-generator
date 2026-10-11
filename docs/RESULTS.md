# Backtest results — model 0.2.0 (run of 2026-10-11)

Walk-forward test: every forecast was made using only matches played before
it (weekly refits). **All 7,529** finished league matches from 2023-07-01 to
2026-10-11 in the 7 leagues are included — none were filtered out.

Data: football-data.co.uk (8 seasons of results and closing odds) and
football-data.org (current-season fixtures and results).

## All leagues (test period 2023-07-01 onwards)

| Model | n | Log loss | Brier | RPS | Accuracy |
|---|---|---|---|---|---|
| Base rate (league averages) | 7529 | 1.076 | 0.651 | 0.2303 | 43.0% |
| Dixon–Coles 0.1.0 (no shrinkage) | 7528 | 0.992 | 0.583 | 0.1971 | 53.1% |
| **Dixon–Coles 0.2.0 (shrinkage = 4)** | 7529 | 0.976 | 0.581 | 0.1963 | 53.2% |
| Elo + ordered logit | 7529 | **0.974** | **0.580** | **0.1958** | 53.0% |
| Market, closing odds (benchmark) | 7467 | 0.954 | 0.567 | 0.1898 | 54.9% |

Lower is better for log loss, Brier and RPS. The market uses closing odds,
which are only known at kickoff, so it is a reference point, not something
that could be used for forecasting.

## Change in 0.2.0: shrinkage for teams with few matches

Dixon–Coles ratings are now pulled towards a prior: the league average for
established teams (≥ 38 matches in the training window) and the average of the
three weakest established teams for newcomers (usually promoted clubs). The
strength (4 ≈ "worth four matches of evidence") was chosen on the **validation
season 2022/23**, which is not part of the test period above:

| Strength | 0 | 1 | 2 | **4** | 8 | 16 |
|---|---|---|---|---|---|---|
| Validation log loss | 0.9984 | 0.9763 | 0.9751 | **0.9742** | 0.9749 | 0.9795 |
| Lowest expected goals | 0.00 | 0.40 | 0.43 | 0.49 | 0.54 | 0.63 |

Effect on the test period: Bundesliga log loss 1.055 → 0.991; example —
Coventry v Newcastle went from 5 % / 21 % / 74 % (0.30 expected home goals)
to 16 % / 24 % / 60 % (0.88).

## What this means

* Both models are clearly better than league averages, in every league.
* Dixon–Coles and Elo are now practically tied on 1X2; Dixon–Coles is the one
  that also gives goals markets (over/under, BTTS, expected goals).
* Both are worse than the betting market in every league. There is **no
  evidence of betting value** in these forecasts.
* Calibration error (ECE) is 1–3 percentage points in every league.

## Known limitations

1. Elo settings (K = 20, home advantage = 60) are defaults, not tuned yet.
2. 62 recent matches have no closing odds (results from football-data.org only),
   so the market benchmark covers 7,467 matches; models are also compared with
   the market on exactly that subset.
3. "Expected goals" here is the **model's** expected goals, not shot-based xG
   (no reliable free xG source).
4. Only league matches are known: cup and European games are missing, so
   rest days and fixture congestion are not modelled yet.
5. The database is temporary (it exists only while the GitHub job runs).
