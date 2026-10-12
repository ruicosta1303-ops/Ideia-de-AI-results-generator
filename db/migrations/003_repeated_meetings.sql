-- Leagues with play-off / split phases play the same home-away pairing more than once a
-- season. For those competitions each match is also identified by its date (leg_date);
-- for single-meeting leagues leg_date stays NULL and the old identity is unchanged.
ALTER TABLE matches ADD COLUMN leg_date date;

DO $$
DECLARE c text;
BEGIN
  SELECT conname INTO c FROM pg_constraint
  WHERE conrelid = 'matches'::regclass AND contype = 'u'
    AND pg_get_constraintdef(oid) = 'UNIQUE (competition_code, season, home_team_id, away_team_id)';
  IF c IS NOT NULL THEN
    EXECUTE format('ALTER TABLE matches DROP CONSTRAINT %I', c);
  END IF;
END $$;

ALTER TABLE matches ADD CONSTRAINT matches_identity
  UNIQUE NULLS NOT DISTINCT (competition_code, season, home_team_id, away_team_id, leg_date);

ALTER TABLE competitions ADD COLUMN country text, ADD COLUMN source_kind text;
