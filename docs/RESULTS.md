# Backtest results — model 0.2.0

## 17 leagues (run of 2026-10-12)

Same walk-forward test (every forecast uses only earlier matches, weekly refits,
every finished match since 2023-07-01 included). Log loss — lower is better.

| League | n | League average | Dixon–Coles | Elo | Market (benchmark) |
|---|---|---|---|---|---|
| **All 17 leagues** | **15,672** | 1.074 | **0.992** | **0.992** | 0.970 |
| Premier League | 1,199 | 1.076 | 0.984 | 0.987 | 0.964 |
| La Liga | 1,219 | 1.066 | 0.972 | 0.967 | 0.952 |
| Bundesliga | 963 | 1.079 | 0.991 | 0.988 | 0.961 |
| Serie A | 1,200 | 1.088 | 0.984 | 0.982 | 0.964 |
| Ligue 1 | 972 | 1.068 | 1.004 | 1.003 | 0.984 |
| Primeira Liga | 988 | 1.080 | 0.937 | 0.930 | 0.914 |
| Eredivisie | 990 | 1.076 | 0.961 | 0.958 | 0.940 |
| Belgian Pro League | 998 | 1.080 | 1.006 | 1.007 | 0.987 |
| Süper Lig | 1,082 | 1.067 | 0.987 | 0.984 | 0.946 |
| Super League Greece | 744 | 1.082 | 0.953 | 0.959 | 0.931 |
| Scottish Premiership | 726 | 1.070 | 0.970 | 0.973 | 0.955 |
| Austrian Bundesliga | 621 | 1.085 | 1.033 | 1.032 | 1.017 |
| Swiss Super League | 740 | 1.071 | 1.038 | 1.040 | 1.022 |
| Danish Superliga | 631 | 1.079 | 1.023 | 1.023 | 1.001 |
| Ekstraklasa | 996 | 1.073 | 1.057 | 1.058 | 1.046 |
| Eliteserien | 803 | 1.046 | 0.983 | 0.987 | 0.952 |
| Allsvenskan | 800 | 1.065 | 1.020 | 1.022 | 0.998 |

* Both models beat league averages in every league and are worse than the closing market
  in every league. The smallest gain is in Poland (1.057 vs 1.073): a more even league.
* The Dixon–Coles shrinkage strength (4) was chosen on the original 7 leagues' 2022/23
  season and applied unchanged to the new leagues — it was not tuned on these results.
* Caveat for the 10 new leagues: their results are published by football-data.co.uk with a
  delay (up to ~3 weeks for the extra leagues), and their fixture files only list the
  next round. The backtest uses complete history, so it does **not** measure the extra
  error from forecasting with delayed data; the website warns when a league's latest
  result is 10+ days old.

## Original 7 leagues (run of 2026-10-11)

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
