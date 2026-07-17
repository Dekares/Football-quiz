"""Canonical SQLite schema used by the Transfermarkt ingestion pipeline."""

SCHEMA_SQL = r"""
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crawl_jobs (
    job_id INTEGER PRIMARY KEY AUTOINCREMENT,
    request_key TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 100,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'retry', 'completed', 'dead')),
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TEXT NOT NULL,
    leased_at TEXT,
    completed_at TEXT,
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_crawl_jobs_ready
    ON crawl_jobs(status, available_at, priority, job_id);

CREATE TABLE IF NOT EXISTS api_snapshots (
    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES crawl_jobs(job_id) ON DELETE SET NULL,
    request_key TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    request_url TEXT NOT NULL,
    http_status INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    parser_version INTEGER NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_snapshots_entity
    ON api_snapshots(entity_type, entity_id, fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_snapshots_hash
    ON api_snapshots(request_key, content_hash);

CREATE TABLE IF NOT EXISTS crawl_errors (
    error_id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER REFERENCES crawl_jobs(job_id) ON DELETE SET NULL,
    request_key TEXT NOT NULL,
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seasons (
    season_id TEXT PRIMARY KEY,
    label TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competitions (
    competition_id TEXT PRIMARY KEY,
    name TEXT,
    country TEXT,
    competition_type TEXT,
    profile_loaded INTEGER NOT NULL DEFAULT 0 CHECK (profile_loaded IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS competition_seasons (
    competition_id TEXT NOT NULL REFERENCES competitions(competition_id),
    season_id TEXT NOT NULL REFERENCES seasons(season_id),
    discovered_at TEXT NOT NULL,
    PRIMARY KEY (competition_id, season_id)
);

CREATE TABLE IF NOT EXISTS clubs (
    club_id INTEGER PRIMARY KEY,
    name TEXT,
    official_name TEXT,
    logo_url TEXT,
    country TEXT,
    current_competition_id TEXT REFERENCES competitions(competition_id),
    is_placeholder INTEGER NOT NULL DEFAULT 0 CHECK (is_placeholder IN (0, 1)),
    profile_loaded INTEGER NOT NULL DEFAULT 0 CHECK (profile_loaded IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS club_aliases (
    club_id INTEGER NOT NULL REFERENCES clubs(club_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    search_alias TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    PRIMARY KEY (club_id, alias)
);

CREATE TABLE IF NOT EXISTS competition_clubs (
    competition_id TEXT NOT NULL,
    season_id TEXT NOT NULL,
    club_id INTEGER NOT NULL REFERENCES clubs(club_id),
    discovered_at TEXT NOT NULL,
    PRIMARY KEY (competition_id, season_id, club_id),
    FOREIGN KEY (competition_id, season_id)
        REFERENCES competition_seasons(competition_id, season_id)
);
CREATE INDEX IF NOT EXISTS idx_competition_clubs_club
    ON competition_clubs(club_id, season_id);

CREATE TABLE IF NOT EXISTS players (
    player_id INTEGER PRIMARY KEY,
    name TEXT,
    full_name TEXT,
    date_of_birth TEXT,
    country_of_birth TEXT,
    city_of_birth TEXT,
    position TEXT,
    sub_position TEXT,
    foot TEXT,
    height_in_cm INTEGER,
    image_url TEXT,
    current_club_id INTEGER REFERENCES clubs(club_id),
    current_market_value INTEGER,
    highest_market_value INTEGER,
    is_retired INTEGER NOT NULL DEFAULT 0 CHECK (is_retired IN (0, 1)),
    retired_since TEXT,
    is_legend INTEGER NOT NULL DEFAULT 0 CHECK (is_legend IN (0, 1)),
    profile_loaded INTEGER NOT NULL DEFAULT 0 CHECK (profile_loaded IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS player_nationalities (
    player_id INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    nationality TEXT NOT NULL,
    ordinal INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (player_id, nationality)
);

CREATE TABLE IF NOT EXISTS club_rosters (
    club_id INTEGER NOT NULL REFERENCES clubs(club_id),
    season_id TEXT NOT NULL REFERENCES seasons(season_id),
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    position TEXT,
    joined_on TEXT,
    contract_until TEXT,
    market_value INTEGER,
    discovered_at TEXT NOT NULL,
    PRIMARY KEY (club_id, season_id, player_id)
);
CREATE INDEX IF NOT EXISTS idx_club_rosters_player
    ON club_rosters(player_id, season_id);

CREATE TABLE IF NOT EXISTS transfers (
    transfer_id TEXT PRIMARY KEY,
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    from_club_id INTEGER REFERENCES clubs(club_id),
    to_club_id INTEGER REFERENCES clubs(club_id),
    transfer_date TEXT NOT NULL,
    season TEXT,
    transfer_type TEXT,
    market_value INTEGER,
    fee INTEGER,
    is_upcoming INTEGER NOT NULL DEFAULT 0 CHECK (is_upcoming IN (0, 1)),
    fetched_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_transfers_player_date
    ON transfers(player_id, transfer_date, transfer_id);

CREATE TABLE IF NOT EXISTS player_market_values (
    market_value_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    value_date TEXT NOT NULL,
    club_id INTEGER REFERENCES clubs(club_id),
    club_name TEXT,
    market_value INTEGER,
    age INTEGER,
    source_key TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    UNIQUE (player_id, value_date, source_key)
);

CREATE TABLE IF NOT EXISTS player_club_periods (
    period_id INTEGER PRIMARY KEY AUTOINCREMENT,
    player_id INTEGER NOT NULL REFERENCES players(player_id) ON DELETE CASCADE,
    club_id INTEGER NOT NULL REFERENCES clubs(club_id),
    date_from TEXT,
    date_to TEXT,
    source TEXT NOT NULL CHECK (source IN ('transfer', 'roster', 'manual')),
    confidence TEXT NOT NULL CHECK (confidence IN ('exact', 'bounded', 'inferred')),
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_player_club_periods_player
    ON player_club_periods(player_id, date_from, date_to);
CREATE INDEX IF NOT EXISTS idx_player_club_periods_club
    ON player_club_periods(club_id, player_id);

CREATE TABLE IF NOT EXISTS daily_challenges (
    challenge_date TEXT PRIMARY KEY,
    day_number INTEGER NOT NULL UNIQUE CHECK (day_number >= 1),
    player_id INTEGER NOT NULL REFERENCES players(player_id),
    recognition_score INTEGER NOT NULL,
    selection_version TEXT NOT NULL,
    scheduled_build_id TEXT NOT NULL,
    scheduled_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_daily_challenges_player
    ON daily_challenges(player_id, challenge_date);

CREATE TABLE IF NOT EXISTS data_issues (
    issue_id INTEGER PRIMARY KEY AUTOINCREMENT,
    build_id TEXT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    issue_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    resolved_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_data_issues_open
    ON data_issues(resolved_at, severity, issue_code);

CREATE TABLE IF NOT EXISTS build_runs (
    build_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('running', 'failed', 'completed')),
    source_db_path TEXT NOT NULL,
    output_path TEXT,
    stats_json TEXT NOT NULL DEFAULT '{}',
    validation_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT NOT NULL,
    completed_at TEXT
);
"""
