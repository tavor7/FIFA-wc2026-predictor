-- Run this in Supabase → SQL Editor → New query → Run
-- WC 2026 Predictor schema (Designed by Amit Tavor — research use only)

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    external_fixture_id TEXT UNIQUE NOT NULL,
    date TEXT NOT NULL,
    league TEXT,
    season INTEGER,
    home_team TEXT NOT NULL,
    away_team TEXT NOT NULL,
    home_team_id INTEGER,
    away_team_id INTEGER,
    status TEXT,
    home_goals INTEGER,
    away_goals INTEGER,
    venue TEXT,
    stage TEXT,
    group_name TEXT,
    round_name TEXT,
    referee_name TEXT,
    weather_json TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS team_match_stats (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team TEXT NOT NULL,
    shots INTEGER,
    shots_on_target INTEGER,
    possession REAL,
    passes INTEGER,
    pass_accuracy REAL,
    corners INTEGER,
    fouls INTEGER,
    yellow_cards INTEGER,
    red_cards INTEGER,
    PRIMARY KEY (match_id, team)
);

CREATE TABLE IF NOT EXISTS lineups (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    team TEXT NOT NULL,
    player_id INTEGER,
    player_name TEXT NOT NULL,
    position TEXT,
    is_starting INTEGER DEFAULT 1,
    rating REAL,
    minutes INTEGER,
    PRIMARY KEY (match_id, team, player_name)
);

CREATE TABLE IF NOT EXISTS injuries (
    player_id INTEGER NOT NULL,
    player_name TEXT NOT NULL,
    team TEXT NOT NULL,
    injury_type TEXT,
    reason TEXT,
    expected_return TEXT,
    last_updated TEXT,
    PRIMARY KEY (player_id, team)
);

CREATE TABLE IF NOT EXISTS predictions (
    match_id INTEGER PRIMARY KEY REFERENCES matches(id) ON DELETE CASCADE,
    generated_at TEXT NOT NULL,
    predicted_home_goals REAL,
    predicted_away_goals REAL,
    home_win_prob REAL,
    draw_prob REAL,
    away_win_prob REAL,
    exact_score_prob REAL,
    top_scorelines_json TEXT,
    explanation TEXT,
    confidence_pct REAL,
    data_completeness_pct REAL,
    model_agreement TEXT,
    ensemble_json TEXT,
    factor_breakdown_json TEXT
);

-- Backward-compatible column adds for existing deployments
ALTER TABLE matches ADD COLUMN IF NOT EXISTS stage TEXT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS group_name TEXT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS round_name TEXT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS referee_name TEXT;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS weather_json TEXT;

ALTER TABLE predictions ADD COLUMN IF NOT EXISTS confidence_pct REAL;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS data_completeness_pct REAL;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS model_agreement TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS ensemble_json TEXT;
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS factor_breakdown_json TEXT;

CREATE TABLE IF NOT EXISTS teams (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT UNIQUE,
    country_code TEXT,
    api_team_id INTEGER UNIQUE,
    logo_url TEXT,
    attack_strength REAL,
    defense_strength REAL,
    strength_matches INTEGER,
    strength_avg_scored REAL,
    strength_avg_conceded REAL,
    strength_source TEXT,
    strength_updated_at TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id SERIAL PRIMARY KEY,
    api_player_id INTEGER UNIQUE,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    name TEXT NOT NULL,
    position TEXT,
    rating REAL,
    form REAL,
    caps INTEGER,
    club TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS player_match_stats (
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    api_player_id INTEGER,
    player_name TEXT NOT NULL,
    team TEXT NOT NULL,
    goals INTEGER DEFAULT 0,
    assists INTEGER DEFAULT 0,
    yellow_cards INTEGER DEFAULT 0,
    red_cards INTEGER DEFAULT 0,
    minutes INTEGER,
    rating REAL,
    is_motm INTEGER DEFAULT 0,
    PRIMARY KEY (match_id, team, player_name)
);

CREATE TABLE IF NOT EXISTS match_events (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    minute INTEGER,
    extra_minute INTEGER,
    team TEXT,
    player_name TEXT,
    player_id INTEGER,
    event_type TEXT NOT NULL,
    detail TEXT,
    UNIQUE (match_id, minute, extra_minute, event_type, player_name, detail)
);

CREATE TABLE IF NOT EXISTS standings (
    group_name TEXT NOT NULL,
    team TEXT NOT NULL,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    season INTEGER NOT NULL,
    played INTEGER DEFAULT 0,
    won INTEGER DEFAULT 0,
    drawn INTEGER DEFAULT 0,
    lost INTEGER DEFAULT 0,
    goals_for INTEGER DEFAULT 0,
    goals_against INTEGER DEFAULT 0,
    goal_diff INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0,
    rank INTEGER,
    last_updated TEXT,
    PRIMARY KEY (group_name, team, season)
);

CREATE TABLE IF NOT EXISTS bracket_nodes (
    id SERIAL PRIMARY KEY,
    stage TEXT NOT NULL,
    round_name TEXT NOT NULL,
    slot INTEGER NOT NULL,
    match_id INTEGER REFERENCES matches(id) ON DELETE SET NULL,
    home_team TEXT,
    away_team TEXT,
    winner_team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    parent_node_id INTEGER REFERENCES bracket_nodes(id) ON DELETE SET NULL,
    last_updated TEXT,
    UNIQUE (stage, round_name, slot)
);

CREATE TABLE IF NOT EXISTS head_to_head (
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    team_a_id INTEGER,
    team_b_id INTEGER,
    matches_played INTEGER DEFAULT 0,
    team_a_wins INTEGER DEFAULT 0,
    team_b_wins INTEGER DEFAULT 0,
    draws INTEGER DEFAULT 0,
    team_a_goals INTEGER DEFAULT 0,
    team_b_goals INTEGER DEFAULT 0,
    summary_json TEXT,
    last_updated TEXT,
    PRIMARY KEY (team_a, team_b)
);

CREATE TABLE IF NOT EXISTS team_history (
    team TEXT PRIMARY KEY,
    team_id INTEGER REFERENCES teams(id) ON DELETE SET NULL,
    wc_appearances INTEGER DEFAULT 0,
    best_finish TEXT,
    total_wc_goals INTEGER DEFAULT 0,
    history_json TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id SERIAL PRIMARY KEY,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    source TEXT,
    records_affected INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TEXT,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS data_freshness (
    entity TEXT PRIMARY KEY,
    last_updated TEXT,
    completeness_pct REAL,
    source TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS prediction_history (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    generated_at TEXT NOT NULL,
    home_win_prob REAL,
    draw_prob REAL,
    away_win_prob REAL,
    predicted_home_goals REAL,
    predicted_away_goals REAL,
    features_json TEXT,
    reason_changed TEXT,
    UNIQUE (match_id, version)
);

CREATE TABLE IF NOT EXISTS feature_store (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    generated_at TEXT NOT NULL,
    features_json TEXT,
    missing_flags_json TEXT
);

CREATE TABLE IF NOT EXISTS weather_forecasts (
    match_id INTEGER PRIMARY KEY REFERENCES matches(id) ON DELETE CASCADE,
    temp_c REAL,
    humidity_pct REAL,
    wind_kmh REAL,
    rain_mm REAL,
    conditions TEXT,
    forecast_json TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS referees (
    id SERIAL PRIMARY KEY,
    api_referee_id INTEGER UNIQUE,
    name TEXT NOT NULL UNIQUE,
    nationality TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS referee_stats (
    referee_id INTEGER PRIMARY KEY REFERENCES referees(id) ON DELETE CASCADE,
    matches_officiated INTEGER DEFAULT 0,
    avg_yellow_cards REAL,
    avg_red_cards REAL,
    pen_rate REAL,
    stats_json TEXT,
    last_updated TEXT
);

CREATE TABLE IF NOT EXISTS live_prob_history (
    id SERIAL PRIMARY KEY,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    recorded_at TEXT NOT NULL,
    home_win_prob REAL,
    draw_prob REAL,
    away_win_prob REAL,
    match_minute INTEGER
);

CREATE INDEX IF NOT EXISTS idx_live_prob_match ON live_prob_history(match_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);
CREATE INDEX IF NOT EXISTS idx_matches_stage ON matches(stage, group_name, round_name);
CREATE INDEX IF NOT EXISTS idx_teams_slug ON teams(slug);
CREATE INDEX IF NOT EXISTS idx_teams_api_id ON teams(api_team_id);
CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_id);
CREATE INDEX IF NOT EXISTS idx_match_events_match ON match_events(match_id);
CREATE INDEX IF NOT EXISTS idx_standings_group ON standings(group_name, season);
CREATE INDEX IF NOT EXISTS idx_bracket_stage ON bracket_nodes(stage, round_name);
CREATE INDEX IF NOT EXISTS idx_feature_store_match ON feature_store(match_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_prediction_history_match ON prediction_history(match_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_sync_log_job ON sync_log(job_name, finished_at DESC);
