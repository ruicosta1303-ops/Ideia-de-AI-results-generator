-- One row per evaluation run: metrics over ALL finished matches in the test window.
CREATE TABLE evaluation_reports (
    id            bigserial PRIMARY KEY,
    created_at    timestamptz NOT NULL DEFAULT now(),
    model_version text NOT NULL,
    test_from     date NOT NULL,
    report        jsonb NOT NULL
);
