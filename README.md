# AI Sports Analytics & Match Prediction

A football (soccer) analytics platform that estimates match-outcome
probabilities from real data, evaluates itself honestly, and explains its
reasoning. Predictions are estimates with uncertainty, never guarantees.

**Status:** Phase 2 in progress. Real data is ingested, three models are
backtested walk-forward on 7,528 matches, and upcoming fixtures are forecast by
a GitHub Actions job. No website yet. See [`docs/RESULTS.md`](docs/RESULTS.md)
for the current results and known problems, and
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the plan.

Run it: GitHub → Actions → **Pipeline** → *Run workflow*. It needs the
repository secret `FOOTBALL_DATA_ORG_TOKEN`.

## What exists today

`engine/` is a Python package with:

| Module | What it does |
|---|---|
| `markets.py` | Expected goals → scoreline matrix → 1X2, over/under 1.5/2.5/3.5, BTTS (always sums to 100 %) |
| `dixon_coles.py` | Dixon–Coles Poisson model with time decay, fitted only on matches before a cut-off date |
| `elo.py` | Elo ratings with home advantage + goal-margin factor; ordered-logit mapping to 1X2 |
| `metrics.py` | Log loss, Brier, ranked probability score, accuracy, calibration bins / ECE |
| `odds.py` | Implied probabilities, overround, margin, de-vigging, expected value |

```bash
cd engine
uv sync
uv run pytest -q
```

The test-suite uses **synthetic simulated matches** only to check that the
model recovers known parameters; no synthetic data is ever used for real
predictions.
