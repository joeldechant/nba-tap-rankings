"""Phase 2 Weekly Update Orchestrator.

Ties together scraping, database storage, and calculation into a single
weekly update workflow. Also provides backfill functionality.
"""

from datetime import date, datetime, timedelta
from . import config, database as db, scraper, calculator

# Don't re-scrape season data from BR if it was refreshed within this window
SEASON_DATA_FRESHNESS = timedelta(hours=6)


def run_weekly_update(week_start=None, week_end=None):
    """Run a full weekly update:
    1. Scrape game box scores for the week
    2. Re-scrape season averages + advanced stats + pace
    3. Calculate weekly rankings (TED top 20, TAP top 20)
    4. Calculate season-to-date rankings (TED top 20, TAP top 20)

    Args:
        week_start: Monday of the target week (date object).
        week_end: Sunday of the target week (date object).
        If None, defaults to the most recent completed Mon-Sun week.

    Returns dict with 'weekly' and 'season' rankings plus metadata.
    """
    # Default: previous Mon-Sun week
    if week_start is None:
        today = date.today()
        days_since_monday = today.weekday()  # Monday=0
        week_end = today - timedelta(days=days_since_monday + 1)  # Last Sunday
        week_start = week_end - timedelta(days=6)  # Previous Monday

    br_year = config.CURRENT_SEASON_YEAR + 1  # BR end-year convention

    print("=" * 60)
    print(f"  WEEKLY UPDATE: {week_start} to {week_end}")
    print("=" * 60)

    db.init_db()
    log_id = db.log_update("weekly", week_start.isoformat(), week_end.isoformat())

    session = scraper.create_session()
    try:
        # 1. Scrape game box scores for the week
        print(f"\n  Step 1: Scraping game box scores...")
        already_scraped = db.get_scraped_game_ids(config.CURRENT_SEASON_YEAR)
        games = scraper.scrape_date_range(
            session, week_start, week_end, skip_game_ids=already_scraped
        )

        # 2. Re-scrape season averages + advanced stats + pace (skip if fresh)
        fresh, age = _is_season_data_fresh()
        if fresh:
            hours = age.total_seconds() / 3600
            print(f"\n  Step 2: Season data is fresh ({hours:.1f}h old), skipping re-scrape")
        else:
            print(f"\n  Step 2: Refreshing season-to-date data...")
            _refresh_season_data(session, br_year)

        # 3. Calculate weekly rankings
        print(f"\n  Step 3: Calculating weekly rankings...")
        weekly = calculate_weekly_rankings(week_start, week_end)

        # 4. Calculate season-to-date rankings
        print(f"\n  Step 4: Calculating season-to-date rankings...")
        season = calculate_season_rankings()

        db.complete_update(
            log_id, games=games,
            players=len(weekly.get('ted', [])),
            status="completed"
        )

        # Print results
        print_rankings(weekly['ted'], "WEEKLY TED TOP 100")
        print_rankings(weekly['tap'], "WEEKLY TAP TOP 100")
        print_rankings(season['ted'], "SEASON-TO-DATE TED TOP 100")
        print_rankings(season['tap'], "SEASON-TO-DATE TAP TOP 100")

        return {
            'weekly': weekly,
            'season': season,
            'games_scraped': games,
        }

    except Exception as e:
        db.complete_update(log_id, status="failed", notes=str(e))
        raise


def backfill_season(start_date=None, end_date=None):
    """Backfill game-level data from last scraped date to yesterday.
    Also refreshes season averages and pace data."""
    db.init_db()
    if end_date is None:
        end_date = date.today() - timedelta(days=1)
    if start_date is None:
        last_date = db.get_last_game_date(config.CURRENT_SEASON_YEAR)
        if last_date:
            start_date = last_date
        else:
            start_date = config.SEASON_START_DATE

    br_year = config.CURRENT_SEASON_YEAR + 1

    print("=" * 60)
    print(f"  BACKFILL: {start_date} to {end_date}")
    print("=" * 60)

    log_id = db.log_update("backfill", start_date.isoformat(), end_date.isoformat())

    session = scraper.create_session()
    try:
        already_scraped = db.get_scraped_game_ids(config.CURRENT_SEASON_YEAR)
        print(f"  Already scraped: {len(already_scraped)} games")

        games = scraper.scrape_date_range(
            session, start_date, end_date, skip_game_ids=already_scraped
        )

        # Refresh season averages + advanced + pace (skip if recently refreshed)
        fresh, age = _is_season_data_fresh()
        if fresh:
            hours = age.total_seconds() / 3600
            print(f"\n  Season data is fresh ({hours:.1f}h old), skipping re-scrape")
        else:
            print(f"\n  Refreshing season-to-date data...")
            _refresh_season_data(session, br_year)

        db.complete_update(log_id, games=games, status="completed")
        print(f"\n  Backfill complete: {games} games scraped")
        return games

    except Exception as e:
        db.complete_update(log_id, status="failed", notes=str(e))
        raise


def refresh_season_data_only():
    """Just refresh season averages, advanced stats, and pace (no game scraping)."""
    br_year = config.CURRENT_SEASON_YEAR + 1
    db.init_db()

    session = scraper.create_session()
    _refresh_season_data(session, br_year)


# ============================================================
# Internal helpers
# ============================================================

def _is_season_data_fresh():
    """Check if season data was refreshed recently enough to skip re-scraping."""
    conn = db.get_connection()
    row = conn.execute(
        "SELECT MAX(updated_at) as last_update FROM season_averages WHERE season_year = ?",
        (config.CURRENT_SEASON_YEAR,)
    ).fetchone()
    conn.close()
    if row and row['last_update']:
        last_update = datetime.fromisoformat(row['last_update'])
        age = datetime.now() - last_update
        return age < SEASON_DATA_FRESHNESS, age
    return False, None


def _refresh_season_data(session, br_year):
    """Scrape and store season averages, advanced stats, and pace."""
    avg_df = scraper.scrape_season_averages(session, br_year)
    adv_df = scraper.scrape_advanced_stats(session, br_year)
    pace_dict = scraper.scrape_pace(session, br_year)

    # Store season averages
    avg_rows = []
    for _, row in avg_df.iterrows():
        avg_rows.append((
            config.CURRENT_SEASON_YEAR, row['Player'], row.get('Team', ''),
            row.get('Age'), row.get('Pos'), row.get('G'), row.get('GS'),
            row.get('MP'), row.get('FG'), row.get('FGA'), row.get('3P'),
            row.get('FT'), row.get('FTA'), row.get('RB'), row.get('AST'),
            row.get('STL'), row.get('BLK'), row.get('Turnovers'), row.get('PTS'),
        ))
    db.upsert_season_averages(avg_rows)
    print(f"      Stored {len(avg_rows)} season averages")

    # Store advanced stats
    adv_rows = []
    for _, row in adv_df.iterrows():
        adv_rows.append((
            config.CURRENT_SEASON_YEAR, row['Player'], row.get('Team', ''),
            row.get('PER'), row.get('OWS'), row.get('DWS'), row.get('WS'),
            row.get('OBPM'), row.get('DBPM'), row.get('BPM'), row.get('VORP'),
        ))
    db.upsert_advanced_stats(adv_rows)
    print(f"      Stored {len(adv_rows)} advanced stats")

    # Store pace
    pace_rows = [(config.CURRENT_SEASON_YEAR, team, pace)
                 for team, pace in pace_dict.items()]
    db.upsert_team_pace(pace_rows)
    print(f"      Stored {len(pace_rows)} team paces")


def _compute_season_op_lookup(season_avgs_list, adv_stats, pace_lookup):
    """Pre-compute season-to-date OP for each player.

    Runs the full calculator on season averages (box score + OBPM/OWS at the
    same time scale) so OP is internally consistent. Returns {player: op_value}.
    Used by weekly/daily rankings so that per-game TAP doesn't suffer from
    the inverse relationship where better box score games get more negative OP.
    """
    op_lookup = {}
    for row in season_avgs_list:
        row = dict(row) if not isinstance(row, dict) else row
        player = row['player']
        team = row.get('team', '')
        mp = row.get('mp')
        g = row.get('g')

        if not mp or mp < 1:
            continue

        pace = pace_lookup.get(team)
        if pace is None:
            if pace_lookup:
                pace = sum(pace_lookup.values()) / len(pace_lookup)
            else:
                continue

        player_data = {
            'player': player, 'team': team,
            'pts': row.get('pts', 0), 'mp': mp,
            'fg': row.get('fg', 0), 'fga': row.get('fga', 0),
            'three_p': row.get('three_p', 0),
            'ft': row.get('ft', 0), 'fta': row.get('fta', 0),
            'rb': row.get('rb', 0), 'ast': row.get('ast', 0),
            'stl': row.get('stl', 0), 'blk': row.get('blk', 0),
            'tov': row.get('tov', 0),
            'g': g,
            'season_year': config.CURRENT_SEASON_YEAR,
        }

        adv = adv_stats.get(player)
        if not adv:
            op_lookup[player] = 0
            continue

        advanced = {
            'dbpm': adv.get('dbpm'),
            'dws': adv.get('dws'),
            'obpm': adv.get('obpm'),
            'ows': adv.get('ows'),
        }

        result = calculator.calculate_stats(
            player_data, pace, advanced=advanced,
            season_g=g, season_mp=mp
        )
        if result:
            op_lookup[player] = result['op']

    return op_lookup


def calculate_weekly_rankings(week_start, week_end):
    """Calculate TED and TAP rankings for a specific week.
    Uses weekly game averages for box score stats, season-to-date for advanced stats.
    TAP OP mode controlled by config.USE_SEASON_OP_FOR_WEEKLY."""
    weekly_stats = db.get_weekly_game_stats(
        week_start.isoformat(), week_end.isoformat()
    )
    adv_stats = {
        row['player']: dict(row)
        for row in db.get_advanced_stats(config.CURRENT_SEASON_YEAR)
    }
    season_avgs = {
        row['player']: dict(row)
        for row in db.get_season_averages(config.CURRENT_SEASON_YEAR)
    }
    pace_lookup = db.get_team_pace(config.CURRENT_SEASON_YEAR)

    # Pre-compute season-to-date OP (only used if USE_SEASON_OP_FOR_WEEKLY is True)
    season_op = {}
    if config.USE_SEASON_OP_FOR_WEEKLY:
        season_avgs_list = db.get_season_averages(config.CURRENT_SEASON_YEAR)
        season_op = _compute_season_op_lookup(season_avgs_list, adv_stats, pace_lookup)

    results = []
    for row in weekly_stats:
        player = row['player']
        team = row['team']
        mp = row['mp']

        # Temporary exclusion filter
        if any(player == name and date.today() <= end for name, end in config.EXCLUDED_PLAYERS):
            continue

        # MP filter
        if mp is None or mp < config.MIN_MP_WEEKLY:
            continue

        # Get pace for this team
        pace = pace_lookup.get(team)
        if pace is None:
            continue

        player_data = {
            'player': player, 'team': team,
            'pts': row['pts'], 'mp': mp,
            'fg': row['fg'], 'fga': row['fga'], 'three_p': row['three_p'],
            'ft': row['ft'], 'fta': row['fta'],
            'rb': row['rb'], 'ast': row['ast'], 'stl': row['stl'],
            'blk': row['blk'], 'tov': row['tov'],
            'g': row['games'],
            'season_year': config.CURRENT_SEASON_YEAR,
        }

        # Advanced stats (season-to-date)
        adv = adv_stats.get(player)
        advanced = None
        if adv:
            advanced = {
                'dbpm': adv.get('dbpm'),
                'dws': adv.get('dws'),
                'obpm': adv.get('obpm'),
                'ows': adv.get('ows'),
            }

        # Season G/MP for DWS/OWS normalization
        season_data = season_avgs.get(player)
        season_g = season_data['g'] if season_data else None
        season_mp = season_data['mp'] if season_data else None

        # Season OP override (only if enabled in config)
        player_season_op = season_op.get(player) if config.USE_SEASON_OP_FOR_WEEKLY else None

        # Game PM for alternative OP (None if not available in DB)
        game_pm = row['plus_minus'] if 'plus_minus' in row.keys() and row['plus_minus'] is not None else None

        result = calculator.calculate_stats(
            player_data, pace, advanced=advanced,
            season_g=season_g, season_mp=season_mp,
            override_op=player_season_op,
            game_plus_minus=game_pm
        )
        if result:
            results.append(result)

    # Sort and rank
    ted_ranked = sorted(results, key=lambda x: x['ted'], reverse=True)[:100]
    tap_ranked = sorted(results, key=lambda x: x['tap'], reverse=True)[:100]

    # TAPD ranking (DOPM-based OP) — only if PM data is available
    tapd_results = [r for r in results if r.get('tapd') is not None]
    tapd_ranked = sorted(tapd_results, key=lambda x: x['tapd'], reverse=True)[:100]

    for i, r in enumerate(ted_ranked):
        r['ted_rank'] = i + 1
    for i, r in enumerate(tap_ranked):
        r['tap_rank'] = i + 1
    for i, r in enumerate(tapd_ranked):
        r['tapd_rank'] = i + 1

    return {'ted': ted_ranked, 'tap': tap_ranked, 'tapd': tapd_ranked}


def _compute_avg_pm_lookup():
    """Compute average game PM per player from all box scores this season.

    Returns dict: {player_name: avg_plus_minus}.
    Only includes players with at least one game with PM data.
    """
    conn = db.get_connection()
    rows = conn.execute(
        """SELECT player, AVG(plus_minus) as avg_pm
           FROM game_box_scores
           WHERE season_year = ? AND plus_minus IS NOT NULL
           GROUP BY player""",
        (config.CURRENT_SEASON_YEAR,)
    ).fetchall()
    return {row['player']: row['avg_pm'] for row in rows}


def calculate_season_rankings():
    """Calculate season-to-date TED, TAP, and TAPD rankings.
    Uses re-scraped season averages + advanced stats.
    TAPD uses average game PM from box scores for the DOPM path."""
    season_avgs = db.get_season_averages(config.CURRENT_SEASON_YEAR)
    adv_stats = {
        row['player']: dict(row)
        for row in db.get_advanced_stats(config.CURRENT_SEASON_YEAR)
    }
    pace_lookup = db.get_team_pace(config.CURRENT_SEASON_YEAR)

    # Build average PM lookup from game box scores for TAPD
    avg_pm_lookup = _compute_avg_pm_lookup()

    today = date.today()

    # Determine current minimum games from tiered thresholds
    min_games = 0
    for tier_date, tier_min in config.SEASON_GAMES_TIERS:
        if today >= tier_date:
            min_games = tier_min
            break

    results = []
    for row in season_avgs:
        row = dict(row)
        player = row['player']
        team = row.get('team', '')
        mp = row.get('mp')
        g = row.get('g')

        # Temporary exclusion filter
        if any(player == name and date.today() <= end for name, end in config.EXCLUDED_PLAYERS):
            continue

        # MP filter
        if mp is None or mp < config.MIN_MP_SEASON:
            continue

        # Tiered games filter
        if min_games > 0 and (g is None or g < min_games):
            continue

        # Get pace — handle traded players (2TM/3TM) with league avg fallback
        pace = pace_lookup.get(team)
        if pace is None:
            if pace_lookup:
                pace = sum(pace_lookup.values()) / len(pace_lookup)
            else:
                continue

        player_data = {
            'player': player, 'team': team,
            'pts': row.get('pts', 0), 'mp': mp,
            'fg': row.get('fg', 0), 'fga': row.get('fga', 0),
            'three_p': row.get('three_p', 0),
            'ft': row.get('ft', 0), 'fta': row.get('fta', 0),
            'rb': row.get('rb', 0), 'ast': row.get('ast', 0),
            'stl': row.get('stl', 0), 'blk': row.get('blk', 0),
            'tov': row.get('tov', 0),
            'g': g,
            'season_year': config.CURRENT_SEASON_YEAR,
        }

        adv = adv_stats.get(player)
        advanced = None
        if adv:
            advanced = {
                'dbpm': adv.get('dbpm'),
                'dws': adv.get('dws'),
                'obpm': adv.get('obpm'),
                'ows': adv.get('ows'),
            }

        # Pass average PM for TAPD calculation
        avg_pm = avg_pm_lookup.get(player)

        result = calculator.calculate_stats(
            player_data, pace, advanced=advanced,
            season_g=g, season_mp=mp,
            game_plus_minus=avg_pm
        )
        if result:
            results.append(result)

    # Sort and rank
    ted_ranked = sorted(results, key=lambda x: x['ted'], reverse=True)[:100]
    tap_ranked = sorted(results, key=lambda x: x['tap'], reverse=True)[:100]

    # TAPD ranking (uses average game PM for DOPM-derived OP)
    tapd_results = [r for r in results if r.get('tapd') is not None]
    tapd_ranked = sorted(tapd_results, key=lambda x: x['tapd'], reverse=True)[:100]

    for i, r in enumerate(ted_ranked):
        r['ted_rank'] = i + 1
    for i, r in enumerate(tap_ranked):
        r['tap_rank'] = i + 1
    for i, r in enumerate(tapd_ranked):
        r['tapd_rank'] = i + 1

    return {'ted': ted_ranked, 'tap': tap_ranked, 'tapd': tapd_ranked, 'all': results}


# ============================================================
# Display
# ============================================================

def print_rankings(ranking_list, title):
    """Pretty-print a top-20 ranking list."""
    stat_key = 'ted' if 'ted' in title.lower() else 'tap'

    print(f"\n  {'=' * 55}")
    print(f"  {title}")
    print(f"  {'=' * 55}")
    print(f"  {'Rank':>4}  {'Player':<25} {'Team':>4} {'G':>3} {'MPG':>5} {stat_key.upper():>6}")
    print(f"  {'-'*4}  {'-'*25} {'-'*4} {'-'*3} {'-'*5} {'-'*6}")

    for r in ranking_list:
        rank = r.get(f'{stat_key}_rank', 0)
        print(f"  {rank:>4}  {r['player']:<25} {r['team']:>4} "
              f"{r['g']:>3} {r['mp']:>5.1f} {r[stat_key]:>6.1f}")
