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
    explanation TEXT
);

CREATE INDEX IF NOT EXISTS idx_matches_date ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_status ON matches(status);
CREATE INDEX IF NOT EXISTS idx_matches_teams ON matches(home_team, away_team);
