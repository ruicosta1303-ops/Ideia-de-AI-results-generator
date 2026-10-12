export type ModelName = "dixon_coles" | "elo" | "base_rate";

export interface Prediction {
  home: number;
  draw: number;
  away: number;
  expHome: number | null;
  expAway: number | null;
  over15: number | null;
  over25: number | null;
  over35: number | null;
  btts: number | null;
  createdAt: string;
  dataCutoff: string;
  nTrain: number;
  version: string;
}

export interface Fixture {
  id: number;
  competition: string;
  competitionName: string;
  season: string;
  kickoff: string | null;
  playedOn: string;
  status: string;
  homeId: number;
  awayId: number;
  home: string;
  away: string;
  fixtureSource: string | null;
  fixtureFetchedAt: string | null;
  predictions: Partial<Record<ModelName, Prediction>>;
  leagueLatestResult: string | null;
}

export interface Result {
  id: number;
  playedOn: string;
  competition: string;
  homeId: number;
  awayId: number;
  home: string;
  away: string;
  homeGoals: number;
  awayGoals: number;
}

export interface CalibrationBin {
  lower: number;
  upper: number;
  count: number;
  mean_predicted: number | null;
  observed_rate: number | null;
}

export interface ModelMetrics {
  n: number;
  log_loss: number;
  brier: number;
  rps: number;
  accuracy: number;
  ece_1x2: number;
  calibration_1x2: CalibrationBin[];
  observed: { home: number; draw: number; away: number };
  mean_predicted: { home: number; draw: number; away: number };
  over_2_5?: { log_loss: number; brier: number; ece: number; observed_rate: number; mean_predicted: number };
  btts?: { log_loss: number; brier: number; ece: number; observed_rate: number; mean_predicted: number };
  on_market_subset?: { n: number; log_loss: number; rps: number };
}

export type EvaluationReport = Record<string, Record<string, ModelMetrics>>;
