# Phase 1 — Architecture & Plan

Status: **proposal** (Phase 1). Written 2026-10-11. Prices, quotas and licences of
third-party providers change often — every figure below must be re-checked on
the provider's own site before we commit to it.

---

## 0. Environment inspection (what was actually found)

| Item | Found | Consequence |
|---|---|---|
| Repo | Empty (README only) | Greenfield; no legacy constraints |
| Node.js / npm / pnpm | 22.22 / 10.9 / 10.28 | Next.js + TypeScript is fine |
| Python / uv | 3.13 / 0.11 | Python modelling is fine; `uv` for deps |
| PostgreSQL | 16 installed (cluster stopped) | Real Postgres for dev & tests, no mocks |
| Docker | 29.8 | Optional; can run Postgres in a container |
| Network | npm + PyPI reachable. **football-data.co.uk, api.football-data.org, api-sports.io, the-odds-api.com blocked** by this cloud environment's network policy | Real data ingestion cannot run here until those domains are allowed (see §8) |

---

## 1. Architecture in plain language

```
                ┌────────────────────────────── scheduled jobs (cron) ─────────────┐
 Data providers │  Python "engine"                                                 │
 (HTTP APIs,    │   1. ingest   → fetch fixtures/results, normalise, store raw+clean│
  CSV files) ──►│   2. rate     → update Elo, fit Dixon–Coles per league           │
                │   3. predict  → freeze a prediction for every upcoming match     │
                │   4. evaluate → once a match finishes, score the frozen forecast │
                └──────────────────────────────┬───────────────────────────────────┘
                                               │ writes
                                         ┌─────▼─────┐
                                         │ PostgreSQL │  single source of truth
                                         └─────▲─────┘
                                               │ reads (server-side only)
                ┌──────────────────────────────┴───────────────────────────────────┐
                │ Next.js (TypeScript) web app                                      │
                │  dashboard · match analysis · comparison · model validation · odds│
                │  AI report endpoint → LLM gets the *computed* numbers as JSON     │
                └───────────────────────────────────────────────────────────────────┘
```

**Two programs, one database.**

* **Python engine** does everything statistical: download data, compute ratings,
  produce probabilities, backtest. Python has mature, well-tested numerical
  libraries (NumPy, SciPy) — a real advantage for fitting models and checking
  calibration. It runs as batch jobs (a few times a day), not as a web server,
  so it costs almost nothing to run.
* **Next.js web app** only *reads* the database and displays it. It never
  calculates a probability itself, so the website can never disagree with the
  model. API keys live in server-side environment variables; the browser
  never talks to a data provider.
* **PostgreSQL** stores fixtures, results, ratings, every prediction (frozen
  with a timestamp *before* kickoff), and evaluation metrics. Every row carries
  `source` and `fetched_at` so freshness is always visible.

### Why this and not something else

| Decision | Choice | Why | Rejected alternative |
|---|---|---|---|
| Web | Next.js 15 + TypeScript + Tailwind | Your preferred direction; server components keep secrets server-side; free hosting tiers exist | Separate React SPA + API server (more moving parts) |
| Modelling | Python package (`engine/`) | Better numeric/stat tooling, easy to test | All-TypeScript (possible, but we'd re-implement optimisation & calibration tools) |
| Database | PostgreSQL (local in dev; Supabase or Neon free tier in prod) | Relational data, standard SQL, both providers are plain Postgres → no lock-in | SQLite (hard to share between web host and job runner) |
| Schema | Plain SQL migration files in `db/migrations` | Readable, owned by neither language | ORM-owned schema (ties DB to one language) |
| Scheduling | GitHub Actions cron (free) → later a small VM if needed | No server to manage | Always-on worker (costs money) |
| LLM reports | Claude API, called server-side, **only after** numbers exist; template fallback when no key | LLM explains, never computes | Letting the LLM "predict" (forbidden by the spec) |

### Provider abstraction

Each provider is an *adapter* implementing a small interface:

```python
class FixtureProvider(Protocol):
    def fixtures(self, competition: str, date_from: date, date_to: date) -> list[RawFixture]: ...
    def results(self, competition: str, season: str) -> list[RawResult]: ...
```

Adapters convert provider-specific JSON/CSV into our own normalised records.
Swapping provider = writing one new adapter + mapping team IDs. Nothing else
changes.

---

## 2. Data providers — requirements, costs, limitations

> All quotas/prices below are as I understand them and **must be verified** on
> the provider's site; they change frequently.

| Provider | What we'd use it for | Cost (verify) | Limitations |
|---|---|---|---|
| **football-data.co.uk** (CSV files) | Historical results since the 1990s for ~20 European leagues, plus shots, cards and **closing bookmaker odds** | Free | League matches only (no cups → rest-day calc incomplete); updated ~1–2×/week; no xG; no injuries. Odds are used **only to benchmark** the model, never as model input |
| **football-data.org** (REST API) | Upcoming fixtures, kickoff times, live standings for the main competitions | Free tier with registration; ~10 requests/min; limited to the top competitions | Free tier has no injuries, lineups, xG or odds |
| **API-Football** (api-sports.io) | Later: injuries/suspensions, lineups, broader coverage | Free tier ~100 requests/day with season restrictions; paid tiers from roughly US$20/month | Licence terms forbid redistribution of raw data; quota is tight on free tier |
| **The Odds API** (Phase 4, optional) | Current pre-match odds from licensed bookmakers | Free tier ~500 credits/month | Coverage varies by league/region |
| **xG** | Shot-based expected goals | No free, licensed, reliable feed identified | MVP shows **"xG: Data unavailable"**. Our *model-expected goals* (λ) are a different thing and will be labelled as such |

**Recommended MVP sources:** football-data.co.uk (history + benchmark odds) and
football-data.org (upcoming fixtures). Both free. API-Football only when we
decide injuries are worth paying for.

**Not doing:** scraping sites whose terms forbid it (e.g. scraped xG), or
inventing data. Missing fields are stored as `NULL` and displayed as
"Data unavailable" with a note on how it affects the analysis.

**Caching & rate limits:** each adapter has a token-bucket limiter; raw
responses are stored in `raw_payloads` (with hash + timestamp) so we never
re-download unchanged data and can re-parse after bug fixes.

---

## 3. The prediction engine

Start simple, add complexity only if it **beats the simpler model
out-of-sample**.

| # | Model | What it does | Role |
|---|---|---|---|
| M0 | League base rates | "Home teams in this league win 45 %, draw 26 %…" | Floor. Any model that can't beat this is useless |
| M1 | Elo | One strength number per team, updated after every match, with home advantage and goal-margin factor. Elo difference → 1X2 via an ordered-logit fitted on past data | Robust, data-light |
| M2 | Dixon–Coles Poisson | Each team has an attack and a defence rating, plus home advantage; goals ~ Poisson; low-score correction ρ; older matches down-weighted (time decay) | Main model — gives a full scoreline matrix ⇒ 1X2, O/U 1.5/2.5/3.5, BTTS, expected goals |
| M3 | Ensemble / calibrated | Weighted blend of M1+M2, optionally recalibrated | Only adopted if validation shows a gain |
| B | Market (de-vigged closing odds) | What bookmakers implied | **Benchmark only** — tells us honestly how good we are |

**Guarantees built into the code**

* All three 1X2 probabilities come from one normalised scoreline matrix (or a
  normalised logit), so they **always sum to 100 %** — enforced by tests.
* Every prediction is stored with `model_version`, `created_at` and the data
  cut-off. A prediction made after kickoff is rejected at the database level.
* Head-to-head is shown as a fact, but is **not** given extra weight in the
  model unless a backtest shows it helps (historically it rarely does once team
  strength is known; small samples mislead).

**Validation (Phase 3)** — walk-forward backtest: for each match day, fit only
on matches *before* that day, predict, then score. Metrics:

* **Ranked Probability Score (RPS)** — the standard metric for football 1X2 because it respects order (home > draw > away).
* **Log loss** and **Brier score**.
* **Calibration**: reliability diagram + expected calibration error. "When we say 60 %, does it happen ~60 % of the time?"
* Reported per league, per market, per season, **always with n** (number of predictions). All matches count — no cherry-picking.

---

## 4. AI match report

1. Engine produces a JSON "fact sheet": probabilities, expected goals, ratings,
   form, rest days, missing-data list, model's historical calibration for
   similar probabilities.
2. The LLM receives *only* that JSON with instructions to explain it, list
   risks and missing information, and not introduce any number.
3. A validator checks every number in the generated text against the fact
   sheet; reports containing unknown numbers are rejected and regenerated or
   replaced by a template-based report.
4. In the UI the report sits in a visually distinct "AI explanation" panel,
   separate from "Observed facts" and "Model estimates".

---

## 5. Planned files & components

```
engine/                         Python package (uv project)
  src/sportsmodel/
    markets.py                  scoreline matrix → 1X2, O/U, BTTS, exp. goals
    dixon_coles.py              Dixon–Coles fit (time-weighted MLE)
    elo.py                      Elo ratings
    metrics.py                  log loss, Brier, RPS, calibration
    odds.py                     implied prob., overround, de-vig, EV
    providers/                  base.py, football_data_csv.py, football_data_org.py
    ingest.py  predict.py  evaluate.py  backtest.py  db.py  cli.py
  tests/                        pytest, incl. synthetic-parameter recovery tests
db/migrations/                  001_init.sql …
web/                            Next.js app
  app/(dashboard)/page.tsx      today + next 7 days, filters, search, ranking
  app/match/[id]/page.tsx       full analysis
  app/compare/page.tsx          side-by-side comparison
  app/validation/page.tsx       accuracy, log loss, Brier, RPS, calibration
  app/odds/                     Phase 4, behind a feature flag
  app/api/report/[id]/route.ts  server-side LLM call
  components/                   ProbabilityBar, ScoreMatrix, FormStrip,
                                CalibrationChart, DataBadge (fact/model/AI),
                                FreshnessIndicator, DataUnavailable
  lib/db.ts                     server-only DB access
.github/workflows/              ci.yml (tests), jobs.yml (scheduled ingest/predict)
docs/                           ARCHITECTURE.md (this), DATA_SOURCES.md, MODEL.md
```

Core DB tables: `competitions`, `seasons`, `teams`, `team_aliases`,
`matches` (status, kickoff, scores, source, fetched_at), `raw_payloads`,
`team_ratings`, `model_versions`, `predictions` (frozen, one row per
match × model × market), `evaluations`, `odds_snapshots` (Phase 4).

---

## 6. Biggest technical risks

1. **Team identity across providers** — "Man United", "Manchester Utd",
   "Manchester United FC". Wrong matching silently corrupts ratings.
   *Mitigation:* `team_aliases` table, ingestion fails loudly on unknown names.
2. **Look-ahead leakage in backtests** — using information not available
   before kickoff makes results look great and worthless.
   *Mitigation:* walk-forward only; predictions frozen with timestamps; tests
   that assert the fit window ends before the predicted match.
3. **Data gaps** — cup matches missing from league CSVs (rest days wrong),
   promoted teams with little top-flight history, no free xG/injuries.
   *Mitigation:* explicit data-quality score per match; shown in UI.
4. **Free-tier limits and licensing** — quotas, redistribution rules.
   *Mitigation:* caching, raw-payload storage, adapters swappable.
5. **Draw probability calibration** — Poisson models are known to misprice
   draws. *Mitigation:* Dixon–Coles ρ, calibration check, compare to market.
6. **LLM hallucination** — *Mitigation:* JSON-only input + numeric validator + template fallback.
7. **Misleading presentation** — *Mitigation:* always show n, uncertainty
   ranges, and the market benchmark; no "lock"/"sure bet" language anywhere.

---

## 7. Acceptance tests (definition of done for the MVP)

Engine (automated, pytest):
- [ ] For any valid inputs, P(home)+P(draw)+P(away) = 1 (±1e-9); same for every O/U line and BTTS.
- [ ] Poisson outputs match closed-form values (e.g. λ=μ=1 ⇒ P(0-0)=e⁻²).
- [ ] Dixon–Coles recovers known parameters from synthetic simulated seasons (labelled synthetic, test-only).
- [ ] Elo is zero-sum and updates in the expected direction.
- [ ] Metrics match hand-computed values (uniform forecast log loss = ln 3, perfect forecast RPS = 0).
- [ ] Odds: overround and de-vigged probabilities match hand calculations; EV shown only when inputs are valid.
- [ ] Backtest refuses to use any match with kickoff ≥ prediction time.

Data/DB (integration, real Postgres):
- [ ] Re-running ingestion is idempotent (no duplicate matches).
- [ ] Unknown team names fail ingestion with a clear error.
- [ ] A prediction cannot be inserted with `created_at` ≥ kickoff.

Web (Playwright):
- [ ] Dashboard lists real fixtures for today/next 7 days with source + freshness.
- [ ] Missing data shows "Data unavailable" with an explanation, never a fabricated value.
- [ ] Match page shows facts / model estimates / AI explanation in distinct, labelled panels.
- [ ] No API key appears in any client bundle (build output grep).
- [ ] Validation page shows n, log loss, Brier, RPS and a calibration chart computed over **all** evaluated predictions.

---

## 8. What I need from you

1. **Allow network access** for this cloud environment to:
   `www.football-data.co.uk`, `api.football-data.org` (and later
   `v3.football.api-sports.io`, `api.the-odds-api.com`). Change it in the
   environment settings → Network access → Allowed domains.
   Docs: https://code.claude.com/docs/en/cloud-environments#network-access
2. **A free football-data.org API key** (register at football-data.org). Add
   it as an environment variable/secret named `FOOTBALL_DATA_ORG_TOKEN` — never paste it into code.
3. Two quick decisions (defaults in brackets, I'll proceed with them unless told otherwise):
   * Leagues for MVP — [Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Primeira Liga, Eredivisie]
   * Interface language — [English, structured so Portuguese can be added]

Everything else uses the defaults above. Later (not needed now): an Anthropic
API key for AI reports (Phase 4), and a hosting choice (default: Vercel +
Supabase/Neon free tiers + GitHub Actions).
