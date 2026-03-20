"""Phase 2 Database — SQLite schema and data access."""

import sqlite3
import os
from datetime import date, datetime
from . import config


def get_connection():
    """Get a database connection, creating the DB file if needed."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create all tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        -- Individual game box scores (append-only, never overwritten)
        CREATE TABLE IF NOT EXISTS game_box_scores (
            game_id TEXT NOT NULL,
            game_date TEXT NOT NULL,
            season_year INTEGER NOT NULL,
            player TEXT NOT NULL,
            team TEXT NOT NULL,
            mp_decimal REAL,
            fg INTEGER,
            fga INTEGER,
            three_p INTEGER,
            ft INTEGER,
            fta INTEGER,
            rb INTEGER,
            ast INTEGER,
            stl INTEGER,
            blk INTEGER,
            tov INTEGER,
            pts INTEGER,
            plus_minus INTEGER,
            PRIMARY KEY (game_id, player, team)
        );

        CREATE INDEX IF NOT EXISTS idx_gbs_date ON game_box_scores(game_date);
        CREATE INDEX IF NOT EXISTS idx_gbs_season ON game_box_scores(season_year);
        CREATE INDEX IF NOT EXISTS idx_gbs_player ON game_box_scores(player);

        -- Season-to-date per-game averages (overwritten each update)
        CREATE TABLE IF NOT EXISTS season_averages (
            season_year INTEGER NOT NULL,
            player TEXT NOT NULL,
            team TEXT,
            age REAL,
            pos TEXT,
            g INTEGER,
            gs INTEGER,
            mp REAL,
            fg REAL,
            fga REAL,
            three_p REAL,
            ft REAL,
            fta REAL,
            rb REAL,
            ast REAL,
            stl REAL,
            blk REAL,
            tov REAL,
            pts REAL,
            updated_at TEXT,
            PRIMARY KEY (season_year, player)
        );

        -- Season-to-date advanced stats (overwritten each update)
        CREATE TABLE IF NOT EXISTS advanced_stats (
            season_year INTEGER NOT NULL,
            player TEXT NOT NULL,
            team TEXT,
            per REAL,
            ows REAL,
            dws REAL,
            ws REAL,
            obpm REAL,
            dbpm REAL,
            bpm REAL,
            vorp REAL,
            updated_at TEXT,
            PRIMARY KEY (season_year, player)
        );

        -- Team pace by season (overwritten each update)
        CREATE TABLE IF NOT EXISTS team_pace (
            season_year INTEGER NOT NULL,
            team TEXT NOT NULL,
            pace REAL,
            updated_at TEXT,
            PRIMARY KEY (season_year, team)
        );

        -- Update tracking log
        CREATE TABLE IF NOT EXISTS update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_type TEXT,
            week_start TEXT,
            week_end TEXT,
            games_scraped INTEGER,
            players_calculated INTEGER,
            started_at TEXT,
            completed_at TEXT,
            status TEXT,
            notes TEXT
        );
        -- Historical PM data (lightweight: only PM + MP per game, for seasons 2000-2024)
        CREATE TABLE IF NOT EXISTS historical_pm (
            game_id TEXT NOT NULL,
            game_date TEXT NOT NULL,
            season_year INTEGER NOT NULL,
            player TEXT NOT NULL,
            team TEXT NOT NULL,
            mp_decimal REAL,
            plus_minus INTEGER,
            PRIMARY KEY (game_id, player, team)
        );

        CREATE INDEX IF NOT EXISTS idx_hpm_season ON historical_pm(season_year);
        CREATE INDEX IF NOT EXISTS idx_hpm_player ON historical_pm(player);
    """)
    # Migration: add plus_minus column if it doesn't exist
    try:
        conn.execute("ALTER TABLE game_box_scores ADD COLUMN plus_minus INTEGER")
    except sqlite3.OperationalError:
        pass  # Column already exists

    conn.commit()
    conn.close()


# ============================================================
# Insert / Upsert Functions
# ============================================================

def insert_game_box_scores(rows):
    """Insert game box score rows. Ignores duplicates (game already scraped).
    rows: list of tuples (game_id, game_date, season_year, player, team,
          mp_decimal, fg, fga, three_p, ft, fta, rb, ast, stl, blk, tov, pts,
          plus_minus)
    Returns number of rows inserted."""
    conn = get_connection()
    before = conn.execute("SELECT COUNT(*) FROM game_box_scores").fetchone()[0]
    conn.executemany("""
        INSERT OR IGNORE INTO game_box_scores
        (game_id, game_date, season_year, player, team, mp_decimal,
         fg, fga, three_p, ft, fta, rb, ast, stl, blk, tov, pts, plus_minus)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM game_box_scores").fetchone()[0]
    inserted = after - before
    conn.close()
    return inserted


def upsert_season_averages(rows):
    """Insert or replace season averages.
    rows: list of tuples (season_year, player, team, age, pos, g, gs, mp,
          fg, fga, three_p, ft, fta, rb, ast, stl, blk, tov, pts)"""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.executemany("""
        INSERT OR REPLACE INTO season_averages
        (season_year, player, team, age, pos, g, gs, mp, fg, fga,
         three_p, ft, fta, rb, ast, stl, blk, tov, pts, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(*r, now) for r in rows])
    conn.commit()
    conn.close()


def upsert_advanced_stats(rows):
    """Insert or replace advanced stats.
    rows: list of tuples (season_year, player, team, per, ows, dws, ws,
          obpm, dbpm, bpm, vorp)"""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.executemany("""
        INSERT OR REPLACE INTO advanced_stats
        (season_year, player, team, per, ows, dws, ws, obpm, dbpm, bpm, vorp, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(*r, now) for r in rows])
    conn.commit()
    conn.close()


def upsert_team_pace(rows):
    """Insert or replace team pace data.
    rows: list of tuples (season_year, team, pace)"""
    conn = get_connection()
    now = datetime.now().isoformat()
    conn.executemany("""
        INSERT OR REPLACE INTO team_pace (season_year, team, pace, updated_at)
        VALUES (?, ?, ?, ?)
    """, [(*r, now) for r in rows])
    conn.commit()
    conn.close()


# ============================================================
# Historical PM Functions
# ============================================================

def insert_historical_pm(rows):
    """Insert historical PM rows. Ignores duplicates (game already scraped).
    rows: list of tuples (game_id, game_date, season_year, player, team,
          mp_decimal, plus_minus)
    Returns number of rows inserted."""
    conn = get_connection()
    before = conn.execute("SELECT COUNT(*) FROM historical_pm").fetchone()[0]
    conn.executemany("""
        INSERT OR IGNORE INTO historical_pm
        (game_id, game_date, season_year, player, team, mp_decimal, plus_minus)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, rows)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM historical_pm").fetchone()[0]
    inserted = after - before
    conn.close()
    return inserted


def get_historical_pm_game_ids(season_year):
    """Get all game IDs already scraped in historical_pm for a season."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT game_id FROM historical_pm
        WHERE season_year = ? ORDER BY game_id
    """, (season_year,)).fetchall()
    conn.close()
    return set(row['game_id'] for row in rows)


def get_historical_pm_seasons():
    """Get list of season_years that have data in historical_pm."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT season_year FROM historical_pm ORDER BY season_year
    """).fetchall()
    conn.close()
    return [row['season_year'] for row in rows]


def get_historical_avg_pm(season_year=None):
    """Get average PM and MP per player per season from historical_pm.
    Returns dict of {(player, season_year): {'avg_pm': float, 'avg_mp': float, 'games': int}}.
    If season_year is provided, filters to that season only."""
    conn = get_connection()
    if season_year is not None:
        rows = conn.execute("""
            SELECT player, season_year,
                   COUNT(*) as games,
                   AVG(mp_decimal) as avg_mp,
                   AVG(plus_minus) as avg_pm
            FROM historical_pm
            WHERE season_year = ? AND plus_minus IS NOT NULL AND mp_decimal > 0
            GROUP BY player, season_year
        """, (season_year,)).fetchall()
    else:
        rows = conn.execute("""
            SELECT player, season_year,
                   COUNT(*) as games,
                   AVG(mp_decimal) as avg_mp,
                   AVG(plus_minus) as avg_pm
            FROM historical_pm
            WHERE plus_minus IS NOT NULL AND mp_decimal > 0
            GROUP BY player, season_year
        """).fetchall()
    conn.close()
    return {
        (row['player'], row['season_year']): {
            'avg_pm': row['avg_pm'],
            'avg_mp': row['avg_mp'],
            'games': row['games'],
        }
        for row in rows
    }


def get_historical_pm_last_date(season_year):
    """Get the most recent game date in historical_pm for a season."""
    conn = get_connection()
    row = conn.execute("""
        SELECT MAX(game_date) as last_date FROM historical_pm
        WHERE season_year = ?
    """, (season_year,)).fetchone()
    conn.close()
    if row and row['last_date']:
        return date.fromisoformat(row['last_date'])
    return None


def get_historical_pm_stats():
    """Get summary stats for historical_pm table."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT season_year,
               COUNT(DISTINCT game_id) as games,
               COUNT(*) as player_games,
               MIN(game_date) as first_date,
               MAX(game_date) as last_date
        FROM historical_pm
        GROUP BY season_year
        ORDER BY season_year
    """).fetchall()
    conn.close()
    return rows


# ============================================================
# Query Functions
# ============================================================

def get_weekly_game_stats(start_date, end_date):
    """Get per-game averages for each player within a date range.
    Groups by player + team (a traded player appears under each team separately)."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            player,
            team,
            COUNT(*) as games,
            AVG(mp_decimal) as mp,
            AVG(fg) as fg,
            AVG(fga) as fga,
            AVG(three_p) as three_p,
            AVG(ft) as ft,
            AVG(fta) as fta,
            AVG(rb) as rb,
            AVG(ast) as ast,
            AVG(stl) as stl,
            AVG(blk) as blk,
            AVG(tov) as tov,
            AVG(pts) as pts,
            AVG(plus_minus) as plus_minus
        FROM game_box_scores
        WHERE game_date >= ? AND game_date <= ?
        GROUP BY player, team
    """, (start_date, end_date)).fetchall()
    conn.close()
    return rows


def get_season_averages(season_year):
    """Get current season-to-date averages."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM season_averages WHERE season_year = ?",
        (season_year,)
    ).fetchall()
    conn.close()
    return rows


def get_advanced_stats(season_year):
    """Get current season-to-date advanced stats."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM advanced_stats WHERE season_year = ?",
        (season_year,)
    ).fetchall()
    conn.close()
    return rows


def get_team_pace(season_year):
    """Get team pace lookup for a season. Returns dict {team_abbrev: pace}."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT team, pace FROM team_pace WHERE season_year = ?",
        (season_year,)
    ).fetchall()
    conn.close()
    return {row['team']: row['pace'] for row in rows}


def get_scraped_game_dates(season_year):
    """Get all dates that have already been scraped for a season."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT game_date FROM game_box_scores
        WHERE season_year = ? ORDER BY game_date
    """, (season_year,)).fetchall()
    conn.close()
    return [row['game_date'] for row in rows]


def get_last_game_date(season_year):
    """Get the most recent game date in the database for a season."""
    conn = get_connection()
    row = conn.execute("""
        SELECT MAX(game_date) as last_date FROM game_box_scores
        WHERE season_year = ?
    """, (season_year,)).fetchone()
    conn.close()
    if row and row['last_date']:
        return date.fromisoformat(row['last_date'])
    return None


def get_scraped_game_ids(season_year):
    """Get all game IDs that have already been scraped for a season."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT DISTINCT game_id FROM game_box_scores
        WHERE season_year = ? ORDER BY game_id
    """, (season_year,)).fetchall()
    conn.close()
    return set(row['game_id'] for row in rows)


def get_game_count(start_date, end_date):
    """Get count of unique games in a date range."""
    conn = get_connection()
    row = conn.execute("""
        SELECT COUNT(DISTINCT game_id) as cnt FROM game_box_scores
        WHERE game_date >= ? AND game_date <= ?
    """, (start_date, end_date)).fetchone()
    conn.close()
    return row['cnt']


def get_player_recent_games(player, n=5, season_year=None):
    """Get the last N games for a player, most recent first.
    Returns list of dicts with game_date, mp_decimal, pts, rb, ast, stl, blk, tov, plus_minus."""
    conn = get_connection()
    if season_year:
        rows = conn.execute("""
            SELECT game_date, mp_decimal, pts, rb, ast, stl, blk, tov, plus_minus
            FROM game_box_scores
            WHERE player = ? AND season_year = ?
            ORDER BY game_date DESC LIMIT ?
        """, (player, season_year, n)).fetchall()
    else:
        rows = conn.execute("""
            SELECT game_date, mp_decimal, pts, rb, ast, stl, blk, tov, plus_minus
            FROM game_box_scores
            WHERE player = ?
            ORDER BY game_date DESC LIMIT ?
        """, (player, n)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ============================================================
# Update Log
# ============================================================

def log_update(run_type, week_start=None, week_end=None, games=0, players=0,
               status="started", notes=""):
    """Log an update run. Returns the log ID."""
    conn = get_connection()
    cursor = conn.execute("""
        INSERT INTO update_log (run_type, week_start, week_end, games_scraped,
                                players_calculated, started_at, status, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (run_type, week_start, week_end, games, players,
          datetime.now().isoformat(), status, notes))
    log_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return log_id


def complete_update(log_id, games=0, players=0, status="completed", notes=""):
    """Mark an update log entry as completed."""
    conn = get_connection()
    conn.execute("""
        UPDATE update_log SET completed_at=?, games_scraped=?, players_calculated=?,
                              status=?, notes=? WHERE id=?
    """, (datetime.now().isoformat(), games, players, status, notes, log_id))
    conn.commit()
    conn.close()


def cleanup_zombie_entries():
    """Mark any 'started' update_log entries as 'failed'.
    These are zombie entries from runs that were killed before completing."""
    conn = get_connection()
    now = datetime.now().isoformat()
    result = conn.execute("""
        UPDATE update_log
        SET completed_at=?, status='failed', notes='Process terminated unexpectedly (zombie cleanup)'
        WHERE status='started' AND completed_at IS NULL
    """, (now,))
    count = result.rowcount
    conn.commit()
    conn.close()
    if count > 0:
        print(f"  Cleaned up {count} zombie update_log entries")
    return count
