-- Core schema. Every fact row records where it came from (source) and when (fetched_at).

CREATE TABLE competitions (
    code         text PRIMARY KEY,           -- football-data.org code, e.g. 'PL'
    name         text NOT NULL,
    csv_division text                         -- football-data.co.uk division, e.g. 'E0'
);

CREATE TABLE teams (
    id   serial PRIMARY KEY,
    name text NOT NULL UNIQUE                -- canonical name (football-data.org spelling)
);

-- Each provider's spelling of a team. Ingestion fails on names missing here.
CREATE TABLE team_aliases (
    source      text NOT NULL,
    source_name text NOT NULL,
    team_id     int  NOT NULL REFERENCES teams(id),
    PRIMARY KEY (source, source_name)
);

CREATE TABLE matches (
    id               bigserial PRIMARY KEY,
    competition_code text NOT NULL REFERENCES competitions(code),
    season           text NOT NULL,          -- '2526' = 2025/26
    home_team_id     int  NOT NULL REFERENCES teams(id),
    away_team_id     int  NOT NULL REFERENCES teams(id),
    played_on        date NOT NULL,
    kickoff_utc      timestamptz,            -- NULL when only the date is known
    status           text NOT NULL,          -- SCHEDULED/TIMED/FINISHED/POSTPONED/...
    home_goals       int,
    away_goals       int,
    home_shots       int,
    away_shots       int,
    home_shots_on_target int,
    away_shots_on_target int,
    fixture_source   text,                   -- who told us about the fixture
    fixture_source_id text,
    fixture_fetched_at timestamptz,
    result_source    text,                   -- who told us the result
    result_fetched_at  timestamptz,
    -- in a league each home/away pairing happens once per season
    UNIQUE (competition_code, season, home_team_id, away_team_id),
    CHECK (home_team_id <> away_team_id),
    CHECK ((home_goals IS NULL) = (away_goals IS NULL))
);
CREATE INDEX matches_played_on ON matches (played_on);

-- Bookmaker odds. Closing odds are used only to benchmark the model.
CREATE TABLE match_odds (
    match_id   bigint NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    source     text   NOT NULL,              -- e.g. 'football-data.co.uk:AvgC'
    kind       text   NOT NULL CHECK (kind IN ('closing', 'pre_match')),
    home       numeric NOT NULL CHECK (home > 1),
    draw       numeric NOT NULL CHECK (draw > 1),
    away       numeric NOT NULL CHECK (away > 1),
    fetched_at timestamptz NOT NULL,
    PRIMARY KEY (match_id, source, kind)
);

CREATE TABLE model_runs (
    id            bigserial PRIMARY KEY,
    model         text NOT NULL,             -- 'dixon_coles', 'elo', 'base_rate'
    model_version text NOT NULL,
    mode          text NOT NULL CHECK (mode IN ('live', 'backtest')),
    competition_code text NOT NULL REFERENCES competitions(code),
    data_cutoff   timestamptz NOT NULL,      -- only matches before this were used
    n_train       int NOT NULL,
    params        jsonb NOT NULL DEFAULT '{}',
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE predictions (
    id           bigserial PRIMARY KEY,
    match_id     bigint NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    model_run_id bigint NOT NULL REFERENCES model_runs(id) ON DELETE CASCADE,
    p_home       double precision NOT NULL CHECK (p_home BETWEEN 0 AND 1),
    p_draw       double precision NOT NULL CHECK (p_draw BETWEEN 0 AND 1),
    p_away       double precision NOT NULL CHECK (p_away BETWEEN 0 AND 1),
    exp_home_goals double precision,
    exp_away_goals double precision,
    p_over_1_5   double precision,
    p_over_2_5   double precision,
    p_over_3_5   double precision,
    p_btts       double precision,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (match_id, model_run_id),
    CHECK (abs(p_home + p_draw + p_away - 1) < 1e-6)
);

-- A prediction must use only information from before the match:
-- the model's data cut-off has to precede kickoff (or the match date),
-- and a live prediction must be stored before kickoff.
CREATE FUNCTION check_prediction_timing() RETURNS trigger AS $$
DECLARE
    m matches%ROWTYPE;
    r model_runs%ROWTYPE;
    starts timestamptz;
BEGIN
    SELECT * INTO m FROM matches WHERE id = NEW.match_id;
    SELECT * INTO r FROM model_runs WHERE id = NEW.model_run_id;
    starts := coalesce(m.kickoff_utc, m.played_on::timestamptz);
    IF r.data_cutoff > starts THEN
        RAISE EXCEPTION 'model run % uses data up to %, after match % starts at %',
            r.id, r.data_cutoff, m.id, starts;
    END IF;
    IF r.mode = 'live' AND NEW.created_at >= starts THEN
        RAISE EXCEPTION 'live prediction for match % created at or after kickoff', m.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER predictions_timing BEFORE INSERT OR UPDATE ON predictions
    FOR EACH ROW EXECUTE FUNCTION check_prediction_timing();

CREATE TABLE schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
