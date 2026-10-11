# Backtest results — model 0.1.0 (run of 2026-10-11)

Walk-forward test: every forecast was made using only matches played before
it (weekly refits). **All 7,528** finished league matches from 2023-07-01 to
2026-10-11 in the 7 leagues are included — none were filtered out.

Data: football-data.co.uk (8 seasons of results and closing odds) and
football-data.org (current-season fixtures and results).

## All leagues

| Model | n | Log loss | Brier | RPS | Accuracy |
|---|---|---|---|---|---|
| Base rate (league averages) | 7528 | 1.076 | 0.651 | 0.2303 | 43.1% |
| Dixon–Coles | 7528 | 0.992 | 0.583 | 0.1971 | 53.1% |
| Elo + ordered logit | 7528 | **0.974** | **0.580** | **0.1959** | 52.9% |
| Market, closing odds (benchmark) | 7467 | 0.954 | 0.567 | 0.1898 | 54.9% |

Lower is better for log loss, Brier and RPS. The market uses closing odds,
which are only known at kickoff, so it is a reference point, not a competitor
that could be used for forecasting.

## What this means

* Both models are clearly better than league averages, in every league.
* Both are worse than the betting market in every league. That is normal for
  models that only use scores; it means there is **no evidence of betting
  value** in these forecasts.
* Elo is slightly better than Dixon–Coles on 1X2 overall. Dixon–Coles is
  still needed for goals markets (over/under, BTTS, expected goals).
* Calibration error (ECE) is 1–3 percentage points in every league.

## Known problems (to fix before showing forecasts in the app)

1. **Overconfidence for teams with few matches.** Dixon–Coles gives extreme
   numbers for recently promoted teams with only a handful of games, e.g.
   Coventry City at home against Newcastle: 0.30 expected goals, 5 % home win.
   This is also why Dixon–Coles has a much worse log loss in the Bundesliga
   (1.055 vs 0.988 for Elo). Planned fix: shrink ratings towards a prior
   (regularisation), with the strength chosen by backtest.
2. Elo settings (K = 20, home advantage = 60) are defaults, not tuned yet.
3. 61 recent matches have no closing odds (results from football-data.org only),
   so the market benchmark covers 7,467 instead of 7,528 matches. Models are
   also compared with the market on exactly the same subset.
4. "Expected goals" here is the **model's** expected goals, not shot-based xG
   (no reliable free xG source).
5. The database is temporary (it exists only while the GitHub job runs).
