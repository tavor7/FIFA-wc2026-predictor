export interface Scoreline {
  home: number;
  away: number;
  probability: number;
}

export interface Prediction {
  predicted_home_goals: number;
  predicted_away_goals: number;
  home_win_prob: number;
  draw_prob: number;
  away_win_prob: number;
  exact_score_prob: number;
  top_scorelines: Scoreline[];
  explanation: string;
  generated_at: string;
}

export interface Match {
  id: number;
  external_fixture_id: string;
  date: string;
  home_team: string;
  away_team: string;
  status: string;
  home_goals: number | null;
  away_goals: number | null;
  venue: string | null;
  prediction?: Prediction;
  injuries?: Injury[];
  lineups?: Lineup[];
}

export interface Injury {
  player_name: string;
  team: string;
  reason: string | null;
  injury_type: string | null;
}

export interface Lineup {
  team: string;
  player_name: string;
  position: string | null;
  is_starting: number;
}

export interface Stats {
  upcoming: number;
  live: number;
  predictions: number;
}
