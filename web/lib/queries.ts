import "server-only";
import { cacheLife } from "next/cache";
import { db } from "./db";
import type { EvaluationReport, Fixture, Result } from "./types";

// The engine refreshes the database once a day; one hour of caching is plenty.
// Timestamps are returned as ISO strings (to_json(...)#>>'{}') so cached values are plain data.

const LIVE_PREDICTIONS = `
  SELECT DISTINCT ON (p.match_id, r.model) p.match_id, r.model,
         json_build_object('home', p.p_home, 'draw', p.p_draw, 'away', p.p_away,
                           'expHome', p.exp_home_goals, 'expAway', p.exp_away_goals,
                           'over15', p.p_over_1_5, 'over25', p.p_over_2_5, 'over35', p.p_over_3_5,
                           'btts', p.p_btts, 'createdAt', p.created_at, 'dataCutoff', r.data_cutoff,
                           'nTrain', r.n_train, 'version', r.model_version) AS pred
  FROM predictions p JOIN model_runs r ON r.id = p.model_run_id
  WHERE r.mode = 'live'
  ORDER BY p.match_id, r.model, p.created_at DESC`;

const FIXTURE_COLUMNS = `
  m.id::int AS id, m.competition_code AS competition, c.name AS "competitionName", m.season,
  (to_json(m.kickoff_utc) #>> '{}') AS kickoff, m.played_on::text AS "playedOn", m.status,
  m.home_team_id AS "homeId", m.away_team_id AS "awayId", th.name AS home, ta.name AS away,
  m.fixture_source AS "fixtureSource", (to_json(m.fixture_fetched_at) #>> '{}') AS "fixtureFetchedAt",
  coalesce((SELECT json_object_agg(l.model, l.pred) FROM live l WHERE l.match_id = m.id), '{}'::json) AS predictions,
  (SELECT max(x.played_on)::text FROM matches x
    WHERE x.competition_code = m.competition_code AND x.home_goals IS NOT NULL) AS "leagueLatestResult"`;

const FROM_MATCHES = `
  FROM matches m
  JOIN competitions c ON c.code = m.competition_code
  JOIN teams th ON th.id = m.home_team_id
  JOIN teams ta ON ta.id = m.away_team_id`;

export async function getUpcoming(days = 7): Promise<Fixture[]> {
  "use cache";
  cacheLife("hours");
  return (await db().unsafe(
    `WITH live AS (${LIVE_PREDICTIONS})
     SELECT ${FIXTURE_COLUMNS} ${FROM_MATCHES}
     WHERE m.home_goals IS NULL
       AND m.kickoff_utc >= now() - interval '2 hours'
       AND m.kickoff_utc < now() + make_interval(days => $1)
     ORDER BY m.kickoff_utc, m.id`,
    [days],
  )) as unknown as Fixture[];
}

export async function getFixtures(ids: number[]): Promise<Fixture[]> {
  "use cache";
  cacheLife("hours");
  if (!ids.length) return [];
  return (await db().unsafe(
    `WITH live AS (${LIVE_PREDICTIONS})
     SELECT ${FIXTURE_COLUMNS} ${FROM_MATCHES}
     WHERE m.id = ANY($1::bigint[])
     ORDER BY m.kickoff_utc NULLS LAST, m.id`,
    [ids],
  )) as unknown as Fixture[];
}

export interface MatchDetail extends Fixture {
  homeGoals: number | null;
  awayGoals: number | null;
  resultSource: string | null;
  resultFetchedAt: string | null;
}

export async function getMatch(id: number): Promise<MatchDetail | null> {
  "use cache";
  cacheLife("hours");
  const rows = await db().unsafe(
    `WITH live AS (${LIVE_PREDICTIONS})
     SELECT ${FIXTURE_COLUMNS}, m.home_goals AS "homeGoals", m.away_goals AS "awayGoals",
            m.result_source AS "resultSource", (to_json(m.result_fetched_at) #>> '{}') AS "resultFetchedAt"
     ${FROM_MATCHES}
     WHERE m.id = $1`,
    [id],
  );
  return (rows[0] as unknown as MatchDetail) ?? null;
}

const RESULT_COLUMNS = `
  m.id::int AS id, m.played_on::text AS "playedOn", m.competition_code AS competition,
  m.home_team_id AS "homeId", m.away_team_id AS "awayId", th.name AS home, ta.name AS away,
  m.home_goals AS "homeGoals", m.away_goals AS "awayGoals"`;

/** Finished matches of either team before a date (all competitions in the database). */
export async function getRecentResults(teamIds: number[], before: string, limit = 60): Promise<Result[]> {
  "use cache";
  cacheLife("hours");
  return (await db().unsafe(
    `SELECT ${RESULT_COLUMNS} ${FROM_MATCHES}
     WHERE m.home_goals IS NOT NULL AND m.played_on < $2::date
       AND (m.home_team_id = ANY($1::int[]) OR m.away_team_id = ANY($1::int[]))
     ORDER BY m.played_on DESC LIMIT $3`,
    [teamIds, before, limit],
  )) as unknown as Result[];
}

export async function getHeadToHead(a: number, b: number, before: string, limit = 10): Promise<Result[]> {
  "use cache";
  cacheLife("hours");
  return (await db().unsafe(
    `SELECT ${RESULT_COLUMNS} ${FROM_MATCHES}
     WHERE m.home_goals IS NOT NULL AND m.played_on < $3::date
       AND ((m.home_team_id = $1 AND m.away_team_id = $2) OR (m.home_team_id = $2 AND m.away_team_id = $1))
     ORDER BY m.played_on DESC LIMIT $4`,
    [a, b, before, limit],
  )) as unknown as Result[];
}

export async function getSeasonResults(competition: string, season: string, before: string): Promise<Result[]> {
  "use cache";
  cacheLife("hours");
  return (await db().unsafe(
    `SELECT ${RESULT_COLUMNS} ${FROM_MATCHES}
     WHERE m.home_goals IS NOT NULL AND m.competition_code = $1 AND m.season = $2 AND m.played_on < $3::date`,
    [competition, season, before],
  )) as unknown as Result[];
}

export interface Freshness {
  latestFixtureFetch: string | null;
  latestResultFetch: string | null;
  latestForecast: string | null;
  latestResultDate: string | null;
  modelVersion: string | null;
  sources: string[];
}

export async function getFreshness(): Promise<Freshness> {
  "use cache";
  cacheLife("hours");
  const [row] = await db().unsafe(`
    SELECT (SELECT to_json(max(fixture_fetched_at)) #>> '{}' FROM matches) AS "latestFixtureFetch",
           (SELECT to_json(max(result_fetched_at)) #>> '{}' FROM matches) AS "latestResultFetch",
           (SELECT max(played_on)::text FROM matches WHERE home_goals IS NOT NULL) AS "latestResultDate",
           (SELECT to_json(max(created_at)) #>> '{}' FROM model_runs WHERE mode = 'live') AS "latestForecast",
           (SELECT model_version FROM model_runs WHERE mode = 'live' ORDER BY created_at DESC LIMIT 1) AS "modelVersion",
           (SELECT coalesce(array_agg(DISTINCT s), '{}') FROM (
               SELECT fixture_source AS s FROM matches WHERE fixture_source IS NOT NULL
               UNION SELECT result_source FROM matches WHERE result_source IS NOT NULL) x) AS sources`);
  return row as unknown as Freshness;
}

export interface Evaluation {
  createdAt: string;
  modelVersion: string;
  testFrom: string;
  report: EvaluationReport;
}

export async function getLatestEvaluation(): Promise<Evaluation | null> {
  "use cache";
  cacheLife("hours");
  const rows = await db().unsafe(`
    SELECT (to_json(created_at) #>> '{}') AS "createdAt", model_version AS "modelVersion",
           test_from::text AS "testFrom", report
    FROM evaluation_reports ORDER BY created_at DESC LIMIT 1`);
  return (rows[0] as unknown as Evaluation) ?? null;
}

export async function getCompetitions(): Promise<{ code: string; name: string }[]> {
  "use cache";
  cacheLife("hours");
  return (await db().unsafe(`SELECT code, name FROM competitions ORDER BY name`)) as unknown as {
    code: string;
    name: string;
  }[];
}
