# AI Sports Analytics & Match Prediction

A football (soccer) analytics platform that estimates match-outcome
probabilities from real data, evaluates itself honestly, and explains its
reasoning. Predictions are estimates with uncertainty, never guarantees.

**Status:** Phase 1 (architecture) done; the statistical core is implemented and
tested. No real data has been ingested yet. See
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the plan, data sources,
risks and acceptance tests.

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
