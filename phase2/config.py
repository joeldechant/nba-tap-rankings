"""Phase 2 Configuration — constants, paths, and coefficients matching v10 exactly."""

import os
from datetime import date

# === Paths ===
PROJECT_DIR = r"C:\Projects\TED Claude Project"
PHASE2_DIR = os.path.join(PROJECT_DIR, "phase2")
DB_PATH = os.path.join(PHASE2_DIR, "ted_weekly.db")

# === Season Configuration ===
CURRENT_SEASON_YEAR = 2025  # start-year convention (2025 = 2025-26 season)
SEASON_START_DATE = date(2025, 10, 22)  # 2025-26 NBA season opening night

# === Scraping ===
BR_BASE_URL = "https://www.basketball-reference.com"
SCRAPE_DELAY = 3  # seconds between requests (be polite to BR)

# === Filtering ===
MIN_MP_WEEKLY = 20          # minimum average MPG for weekly rankings
MIN_MP_SEASON = 20          # minimum average MPG for season-to-date

# Temporary player exclusions — (player_name, end_date)
# Player is excluded until end_date (inclusive). After that date, they reappear automatically.
EXCLUDED_PLAYERS = [
]

# Tiered minimum games for season-to-date rankings
# (date_threshold, min_games) — checked in order, first match wins
SEASON_GAMES_TIERS = [
    (date(2026, 1, 15), 20),   # Jan 15+ → 20 games min (~40 team games played)
    (date(2025, 12, 15), 10),  # Dec 15+ → 10 games min (~26 team games played)
    (date(2025, 11, 15), 5),   # Nov 15+ → 5 games min (~12 team games played)
]
# Before Nov 15: no minimum games requirement

# === TED/TAP/MAP Coefficients (matching v10 exactly) ===
BASE_PACE = 95
BASE_POSS_36 = 71.25       # = 95 / 48 * 36
AND1_RATE = 0.25
PSHOT_BASELINE = 1.1       # for EP36 efficiency calculation

# Rebound coefficients
RB_COEFF_TED = 0.6         # TED uses round number from paper
RB_COEFF_TAP = 0.5967      # TAP uses derived value: (10-4.9)*0.9*1.3/10

# Net Assists
AST_WEIGHT = 1.0
STL_WEIGHT = 0.85
BLK_WEIGHT = 0.85
TOV_WEIGHT = 0.85
NA_COEFF = 1.6

# Defense (DPS)
DPS_COEFF = 2.5            # DPS multiplier in final TED/TAP/MAP formulas (history: 1.0 → 2.0 → 2.5 → 3.0 → 2.75 → 2.0 → 2.5)
DWS_BASELINE = 3.8
WS_DPS_MULTIPLIER = 1.3

# Offense (OP) — TAP only
OBPM_MULTIPLIER = 1.0
OWS_BASELINE = 3.5         # NOTE: different from DWS baseline of 3.8
WS_OPS_MULTIPLIER = 0.65

# OP extraction
RB_DIFF_WEIGHT = 0.45
RB_AVG_BASELINE = 7.5
NA_DIFF_WEIGHT = 0.3
NA_AVG_BASELINE = 3.5
OP_MULTIPLIER = 1.0

# Era-varying P/Shot OP baselines (for OP extraction, not EP36)
ERA_PSHOT_BASELINES = [
    (2020, 1.16),   # 2020+ (updated Mar 2026 — league avg P/Shot rose ~0.03-0.06 above 1.13)
    (2016, 1.13),   # 2016-2019
    (1982, 1.10),   # 1982-2015
    (1976, 1.08),   # 1976-1981
    (1962, 1.03),   # 1962-1975
    (1957, 0.98),   # 1957-1961
    (0,    0.93),   # pre-1957
]


def get_era_pshot_baseline(year):
    """Get the P/Shot OP baseline for a given season year."""
    for threshold, baseline in ERA_PSHOT_BASELINES:
        if year >= threshold:
            return baseline
    return 0.93


# === Team Abbreviation Mappings ===
TEAM_ABBREV_TO_FULL = {
    "ATL": "Atlanta Hawks",
    "BOS": "Boston Celtics",
    "BRK": "Brooklyn Nets",
    "CHI": "Chicago Bulls",
    "CHO": "Charlotte Hornets",
    "CHA": "Charlotte Hornets",
    "CLE": "Cleveland Cavaliers",
    "DAL": "Dallas Mavericks",
    "DEN": "Denver Nuggets",
    "DET": "Detroit Pistons",
    "GSW": "Golden State Warriors",
    "HOU": "Houston Rockets",
    "IND": "Indiana Pacers",
    "LAC": "Los Angeles Clippers",
    "LAL": "Los Angeles Lakers",
    "MEM": "Memphis Grizzlies",
    "MIA": "Miami Heat",
    "MIL": "Milwaukee Bucks",
    "MIN": "Minnesota Timberwolves",
    "NOP": "New Orleans Pelicans",
    "NYK": "New York Knicks",
    "OKC": "Oklahoma City Thunder",
    "ORL": "Orlando Magic",
    "PHI": "Philadelphia 76ers",
    "PHO": "Phoenix Suns",
    "PHX": "Phoenix Suns",
    "POR": "Portland Trail Blazers",
    "SAC": "Sacramento Kings",
    "SAS": "San Antonio Spurs",
    "TOR": "Toronto Raptors",
    "UTA": "Utah Jazz",
    "WAS": "Washington Wizards",
}

# Build reverse lookup (full name → abbreviation)
TEAM_FULL_TO_ABBREV = {}
for abbr, full in TEAM_ABBREV_TO_FULL.items():
    if full not in TEAM_FULL_TO_ABBREV:
        TEAM_FULL_TO_ABBREV[full] = abbr
# Prefer standard abbreviations for teams with multiple codes
TEAM_FULL_TO_ABBREV["Phoenix Suns"] = "PHO"
TEAM_FULL_TO_ABBREV["Charlotte Hornets"] = "CHO"


def season_year_from_date(d):
    """Determine season start-year from a game date.
    Oct-Dec = same year, Jan-Sep = year - 1."""
    if d.month >= 10:
        return d.year
    return d.year - 1
