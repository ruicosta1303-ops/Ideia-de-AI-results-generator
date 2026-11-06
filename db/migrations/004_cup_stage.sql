-- Cup matches: the stage (LEAGUE_STAGE, PLAYOFFS, ..., FINAL); the final is at a neutral ground.
ALTER TABLE matches ADD COLUMN stage text;
-- cup matches are looked up by the provider's match id
CREATE INDEX matches_fixture_source_id ON matches (fixture_source, fixture_source_id);
