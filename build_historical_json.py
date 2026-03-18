"""Build historical TED/TAP rankings JSON from scraped season CSVs.

Reads individual season CSVs from scraped_data/ (BR years 1950-2025),
calculates TED/TAP/TAPD for each qualifying player via calculator.py,
groups by decade, outputs phase2/historical_rankings.json.

Usage: python build_historical_json.py
"""

import csv
import json
import os
import sys
import math
from collections import defaultdict

PROJECT_DIR = r"C:\Projects\TED Claude Project"
sys.path.insert(0, PROJECT_DIR)


def fix_encoding(s):
    """Fix double-encoded UTF-8 (UTF-8 bytes misread as Latin-1 then re-encoded).
    e.g. 'JokiÄ\x87' -> 'Jokić', 'DonÄ\x8diÄ\x87' -> 'Dončić'
    """
    try:
        return s.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s

from phase2 import config
from phase2.calculator import calculate_stats


def load_all_seasons():
    """Load all season CSVs from scraped_data/ (BR years 1952-2025 = start-years 1951-2024).

    Starts at 1952 because BR doesn't have MP data before 1951-52 season,
    and TED/TAP require minutes per game for per-36 normalization.
    """
    scraped_dir = os.path.join(PROJECT_DIR, "scraped_data")
    players = []
    non_qualifying = []  # Players active but didn't meet G>=40/MP>=20

    for br_year in range(1952, 2026):
        csv_path = os.path.join(scraped_dir, f"{br_year}_season.csv")
        if not os.path.exists(csv_path):
            continue

        start_year = br_year - 1  # Convert BR end-year to start-year

        def safe_float(val, default=0.0):
            try:
                v = float(val)
                return v if not math.isnan(v) else default
            except (ValueError, TypeError):
                return default

        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            season_count = 0
            for row in reader:
                g = safe_float(row.get('G', 0))
                mp = safe_float(row.get('MP', 0))
                pace = safe_float(row.get('Pace', 0))

                # Skip traded-player individual team rows (keep only combined)
                team = row.get('Team', '').strip()
                if team in ('2TM', '3TM', '4TM', '5TM'):
                    team = 'TOT'

                player_name = fix_encoding(row['Player'].strip())

                # Filter: G >= 40, MP >= 20
                if g < 40 or mp < 20 or pace == 0:
                    # Track non-qualifying appearances for career popup
                    if g > 0 and player_name:
                        non_qualifying.append({
                            'player': player_name,
                            'team': team,
                            'year': start_year,
                        })
                    continue

                players.append({
                    'player': player_name,
                    'team': team,
                    'year': start_year,
                    'pace': pace,
                    'g': int(g),
                    'mp': mp,
                    'fg': safe_float(row.get('FG', 0)),
                    'fga': safe_float(row.get('FGA', 0)),
                    'three_p': safe_float(row.get('3P', 0)),
                    'ft': safe_float(row.get('FT', 0)),
                    'fta': safe_float(row.get('FTA', 0)),
                    'rb': safe_float(row.get('RB', 0)),
                    'ast': safe_float(row.get('AST', 0)),
                    'stl': safe_float(row.get('STL', 0)),
                    'blk': safe_float(row.get('BLK', 0)),
                    'tov': safe_float(row.get('Turnovers', 0)),
                    'pts': safe_float(row.get('PTS', 0)),
                    'dbpm': safe_float(row['DBPM']) if row.get('DBPM', '').strip() else None,
                    'dws': safe_float(row['DWS']) if row.get('DWS', '').strip() else None,
                    'obpm': safe_float(row['OBPM']) if row.get('OBPM', '').strip() else None,
                    'ows': safe_float(row['OWS']) if row.get('OWS', '').strip() else None,
                    'per': safe_float(row.get('PER', 0)),
                })
                season_count += 1

    print(f"  Loaded {len(players)} qualifying players across {br_year - 1949} seasons (1949-2024)")
    print(f"  Non-qualifying appearances: {len(non_qualifying)}")
    return players, non_qualifying


def calculate_tap_for_players(players, pm_lookup=None):
    """Run calculator on each player, return list with TAP values added.

    Args:
        players: list of player dicts with raw stats
        pm_lookup: optional dict of {(player_name, season_year): {'avg_pm': float, ...}}
            from historical_pm table. When available, calculator produces TAPD values.
    """
    pm_lookup = pm_lookup or {}
    results = []
    tapd_count = 0
    for p in players:
        player_data = {
            'player': p['player'],
            'team': p['team'] or '',
            'pts': p['pts'],
            'mp': p['mp'],
            'fg': p['fg'],
            'fga': p['fga'],
            'three_p': p['three_p'],
            'ft': p['ft'],
            'fta': p['fta'],
            'rb': p['rb'],
            'ast': p['ast'],
            'stl': p['stl'],
            'blk': p['blk'],
            'tov': p['tov'],
            'g': p['g'],
            'season_year': p['year'],
        }

        advanced = {}
        if p['dbpm'] is not None:
            advanced['dbpm'] = p['dbpm']
        if p['dws'] is not None:
            advanced['dws'] = p['dws']
        if p['obpm'] is not None:
            advanced['obpm'] = p['obpm']
        if p['ows'] is not None:
            advanced['ows'] = p['ows']

        # Look up average PM for this player-season (for TAPD calculation)
        pm_info = pm_lookup.get((p['player'], p['year']))
        game_pm = pm_info['avg_pm'] if pm_info else None

        result = calculate_stats(
            player_data, p['pace'],
            advanced=advanced if advanced else None,
            season_g=p['g'], season_mp=p['mp'],
            game_plus_minus=game_pm
        )

        if result and result.get('tap') is not None:
            entry = {
                'player': p['player'],
                'team': p['team'],
                'year': p['year'],
                'tap': result['tap'],
                'ted': result.get('ted', result['tap']),
            }
            # Add TAPD if calculator produced it (PM data was available)
            if result.get('tapd') is not None:
                entry['tapd'] = result['tapd']
                tapd_count += 1
            results.append(entry)

    if tapd_count:
        print(f"    TAPD calculated for {tapd_count} player-seasons (PM data available)")
    return results


def load_historical_pm():
    """Load average PM per player per season from historical_pm table.
    Returns dict of {(player_name, season_year): {'avg_pm': float, ...}},
    or empty dict if no data available."""
    try:
        from phase2 import database as db
        db.init_db()
        pm_data = db.get_historical_avg_pm()
        if pm_data:
            seasons = len(set(sy for _, sy in pm_data.keys()))
            print(f"  Historical PM: {len(pm_data)} player-seasons across {seasons} seasons")
        return pm_data
    except Exception as e:
        print(f"  Historical PM: not available ({e})")
        return {}


def build_historical_json():
    """Main entry point: build and write historical_rankings.json."""
    print("Building historical TAP rankings JSON...")

    # Load data from all scraped season CSVs
    all_players, non_qualifying = load_all_seasons()

    print(f"  Total qualifying players: {len(all_players)}")

    # Load historical PM data for TAPD calculation (seasons 1997+)
    pm_lookup = load_historical_pm()

    # Calculate TAP (and TAPD where PM data available)
    print("  Calculating TED/TAP for all players...")
    results = calculate_tap_for_players(all_players, pm_lookup=pm_lookup)
    print(f"  Calculated TED/TAP for {len(results)} players")

    # Safety net dedup by (player, year). The v9 CSV was cleaned (Mar 2026)
    # to remove all duplicate rows, but this guard remains in case any slip
    # back in. Strategy: merge same-player dupes (same G and PTS, keep
    # highest TAP); keep genuinely different players (different G/PTS) separate.
    from collections import defaultdict as dd
    groups = dd(list)
    for r in results:
        groups[(r['player'], r['year'])].append(r)

    deduped = []
    for key, entries in groups.items():
        if len(entries) == 1:
            deduped.append(entries[0])
        else:
            # Check if entries are the same player (same G and PTS) or different
            base = entries[0]
            same_player_group = [base]
            different_players = []
            for e in entries[1:]:
                # Same player if G and PTS match within rounding
                if (abs(e.get('g', 0) - base.get('g', 0)) <= 1 and
                        abs(e.get('pts', 0) - base.get('pts', 0)) < 1.0):
                    same_player_group.append(e)
                else:
                    different_players.append(e)
            # Keep highest TAP from same-player group
            best = max(same_player_group, key=lambda x: x['tap'])
            deduped.append(best)
            # Keep all genuinely different players
            deduped.extend(different_players)

    results = deduped
    print(f"  After dedup: {len(results)} unique player-seasons")

    # Build career_data: all player-seasons grouped by player name
    career_data = defaultdict(list)
    qualifying_years = set()  # Track (player, year) pairs already added
    for r in results:
        entry = {
            'y': r['year'], 'tm': r['team'] or '',
            'ted': round(r['ted'], 1), 'tap': round(r['tap'], 1)
        }
        if 'tapd' in r:
            entry['tapd'] = round(r['tapd'], 1)
        career_data[r['player']].append(entry)
        qualifying_years.add((r['player'], r['year']))

    # Add non-qualifying seasons (dashes) for players who have at least one qualifying season
    nq_added = 0
    for nq in non_qualifying:
        name = nq['player']
        if name in career_data and (name, nq['year']) not in qualifying_years:
            career_data[name].append({
                'y': nq['year'], 'tm': nq['team'] or '',
                'ted': None, 'tap': None
            })
            qualifying_years.add((name, nq['year']))  # Prevent duplicates
            nq_added += 1

    for name in career_data:
        career_data[name].sort(key=lambda x: x['y'])
    print(f"  Career data: {len(career_data)} unique players ({nq_added} non-qualifying seasons added)")

    # Group by year
    by_year = defaultdict(list)
    for r in results:
        by_year[r['year']].append(r)

    # Build season_stats: top-10 avg and leader per year
    season_stats = {}
    for year, players in by_year.items():
        ted_sorted = sorted(players, key=lambda p: p['ted'], reverse=True)
        tap_sorted = sorted(players, key=lambda p: p['tap'], reverse=True)
        top10_teds = [p['ted'] for p in ted_sorted[:10]]
        top10_taps = [p['tap'] for p in tap_sorted[:10]]
        ted_leader = ted_sorted[0]
        tap_leader = tap_sorted[0]
        ted_second = ted_sorted[1] if len(ted_sorted) > 1 else None
        tap_second = tap_sorted[1] if len(tap_sorted) > 1 else None
        ted_third = ted_sorted[2] if len(ted_sorted) > 2 else None
        tap_third = tap_sorted[2] if len(tap_sorted) > 2 else None
        all_teds = [p['ted'] for p in players]
        all_taps = [p['tap'] for p in players]
        stats_entry = {
            'avg_ted': round(sum(all_teds) / len(all_teds), 1),
            'avg_tap': round(sum(all_taps) / len(all_taps), 1),
            'top10_ted': round(sum(top10_teds) / len(top10_teds), 1),
            'top10_tap': round(sum(top10_taps) / len(top10_taps), 1),
            'ldr_ted': ted_leader['player'], 'ldr_ted_val': round(ted_leader['ted'], 1),
            'ldr_tap': tap_leader['player'], 'ldr_tap_val': round(tap_leader['tap'], 1),
            'g2_ted': ted_second['player'] if ted_second else '',
            'g2_ted_val': round(ted_second['ted'], 1) if ted_second else 0,
            'g2_tap': tap_second['player'] if tap_second else '',
            'g2_tap_val': round(tap_second['tap'], 1) if tap_second else 0,
            'g3_ted': ted_third['player'] if ted_third else '',
            'g3_ted_val': round(ted_third['ted'], 1) if ted_third else 0,
            'g3_tap': tap_third['player'] if tap_third else '',
            'g3_tap_val': round(tap_third['tap'], 1) if tap_third else 0,
        }

        # TAPD stats (only for years with PM data, 1997+)
        tapd_players = [p for p in players if 'tapd' in p]
        if tapd_players:
            tapd_sorted = sorted(tapd_players, key=lambda p: p['tapd'], reverse=True)
            top10_tapds = [p['tapd'] for p in tapd_sorted[:10]]
            stats_entry['top10_tapd'] = round(sum(top10_tapds) / len(top10_tapds), 1)
            tapd_leader = tapd_sorted[0]
            stats_entry['ldr_tapd'] = tapd_leader['player']
            stats_entry['ldr_tapd_val'] = round(tapd_leader['tapd'], 1)
            if len(tapd_sorted) > 1:
                stats_entry['g2_tapd'] = tapd_sorted[1]['player']
                stats_entry['g2_tapd_val'] = round(tapd_sorted[1]['tapd'], 1)
            if len(tapd_sorted) > 2:
                stats_entry['g3_tapd'] = tapd_sorted[2]['player']
                stats_entry['g3_tapd_val'] = round(tapd_sorted[2]['tapd'], 1)

        season_stats[str(year)] = stats_entry
    print(f"  Season stats: {len(season_stats)} years")

    # Sort each year by TAP descending, take top N
    decades = {}
    decade_order = ['2020s', '2010s', '2000s', '1990s', '1980s', '1970s', '1960s', '1950s']

    for decade_label in decade_order:
        decade_start = int(decade_label[:4])
        decade_end = decade_start + 9
        years_data = []

        for year in range(min(decade_end, 2024), decade_start - 1, -1):  # newest first, cap at 2024
            if year < 1951:  # BR has no MP data before 1951-52
                continue

            if year >= 1990:
                top_n = 40
            elif year >= 1980:
                top_n = 30
            elif year >= 1960:
                top_n = 20
            else:
                top_n = 10
            season_label = f"{year}-{str(year + 1)[-2:]}"

            all_year_players = by_year.get(year, [])

            def build_year_entries(pool, sort_key, n):
                """Sort pool by sort_key, take top n, build entry dicts."""
                sorted_p = sorted(pool, key=lambda x: x[sort_key], reverse=True)[:n]
                entries = []
                for i, p in enumerate(sorted_p, 1):
                    entry = {
                        'rank': i,
                        'player': p['player'],
                        'team': p['team'],
                        'ted': round(p['ted'], 1),
                        'tap': round(p['tap'], 1),
                    }
                    if 'tapd' in p:
                        entry['tapd'] = round(p['tapd'], 1)
                    entries.append(entry)
                # Pad with empty entries if fewer than n
                while len(entries) < n:
                    entries.append({
                        'rank': len(entries) + 1,
                        'player': None, 'team': None,
                        'ted': None, 'tap': None,
                    })
                return entries

            players_ted = build_year_entries(all_year_players, 'ted', top_n)
            players_tap = build_year_entries(all_year_players, 'tap', top_n)

            # TAPD per-year list (only for years with TAPD data)
            tapd_year_players = [p for p in all_year_players if p.get('tapd') is not None]
            players_tapd = build_year_entries(tapd_year_players, 'tapd', top_n) if tapd_year_players else []

            year_entry = {
                'year': year,
                'season_label': season_label,
                'top_n': top_n,
                'players': players_ted,
                'players_tap': players_tap,
            }
            if players_tapd:
                year_entry['players_tapd'] = players_tapd
            years_data.append(year_entry)

            actual_count = len([p for p in players_ted if p.get('player')])
            if actual_count < top_n:
                print(f"    {season_label}: {actual_count}/{top_n} qualifying players")

        if years_data:
            # Build decade-level top N (best individual seasons in this decade)
            # 200 for 1980s onwards, 100 for earlier decades
            decade_top_n = 200 if decade_start >= 1980 else 100
            decade_players = [r for r in results
                              if decade_start <= r['year'] <= decade_end]
            def build_decade_entries(pool, sort_key, n):
                """Sort pool by sort_key, take top n, build entry dicts."""
                sorted_p = sorted(pool, key=lambda x: x[sort_key], reverse=True)[:n]
                entries = []
                for i, p in enumerate(sorted_p, 1):
                    sl = f"{p['year']}-{str(p['year'] + 1)[-2:]}"
                    entry = {
                        'rank': i,
                        'player': p['player'],
                        'team': p['team'],
                        'year': p['year'],
                        'season_label': sl,
                        'ted': round(p['ted'], 1),
                        'tap': round(p['tap'], 1),
                    }
                    if 'tapd' in p:
                        entry['tapd'] = round(p['tapd'], 1)
                    entries.append(entry)
                return entries

            decade_top_ted = build_decade_entries(decade_players, 'ted', decade_top_n)
            decade_top_tap = build_decade_entries(decade_players, 'tap', decade_top_n)
            print(f"  {decade_label}: {len(decade_top_ted)} entries in decade top {decade_top_n}")

            # Separate TAPD decade list (1990s+ for TAPD, from full TAPD pool)
            # 1990s gets top 100 (only 4 years of PM data: 1996-1999), 2000s+ gets same as TED/TAP
            decade_tapd_entries = []
            if decade_start >= 1990:
                decade_tapd_n = 100 if decade_start == 1990 else decade_top_n
                decade_tapd_pool = [r for r in decade_players if r.get('tapd') is not None]
                decade_tapd_entries = build_decade_entries(decade_tapd_pool, 'tapd', decade_tapd_n)

            decades[decade_label] = {
                'years': years_data,
                'decade_top_100': decade_top_ted,
                'decade_top_tap': decade_top_tap,
                'decade_top_n': decade_top_n,
                'decade_top_tapd': decade_tapd_entries,
            }

    # Build all-time top 400 — independently sorted by TED, TAP, and TAPD
    def build_all_time(pool, sort_key, n):
        sorted_p = sorted(pool, key=lambda x: x[sort_key], reverse=True)[:n]
        entries = []
        for i, p in enumerate(sorted_p, 1):
            season_label = f"{p['year']}-{str(p['year'] + 1)[-2:]}"
            entry = {
                'rank': i,
                'player': p['player'],
                'team': p['team'],
                'year': p['year'],
                'season_label': season_label,
                'ted': round(p['ted'], 1),
                'tap': round(p['tap'], 1),
            }
            if 'tapd' in p:
                entry['tapd'] = round(p['tapd'], 1)
            entries.append(entry)
        return entries

    all_time_ted = build_all_time(results, 'ted', 400)
    all_time_tap = build_all_time(results, 'tap', 400)
    print(f"  All-time top 400: TED range {all_time_ted[0]['ted']} to {all_time_ted[-1]['ted']}")
    print(f"  All-time top 400: TAP range {all_time_tap[0]['tap']} to {all_time_tap[-1]['tap']}")

    tapd_pool = [p for p in results if p.get('tapd') is not None and p['year'] >= 1996]
    all_time_tapd = build_all_time(tapd_pool, 'tapd', 400)
    if all_time_tapd:
        print(f"  All-time TAPD top {len(all_time_tapd)}: TAPD range {all_time_tapd[0]['tapd']} to {all_time_tapd[-1]['tapd']}")

    # Write JSON
    output = {
        'generated': str(__import__('datetime').date.today()),
        'all_time_top_200': all_time_ted,
        'all_time_tap': all_time_tap,
        'all_time_tapd': all_time_tapd,
        'decades': decades,
        'career_data': dict(career_data),
        'season_stats': season_stats,
    }

    output_path = os.path.join(PROJECT_DIR, "phase2", "historical_rankings.json")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\n  Written: {output_path}")

    # Summary
    total_years = sum(len(d['years']) for d in decades.values())
    total_players = sum(
        len([p for p in y['players'] if p['player'] is not None])
        for d in decades.values()
        for y in d['years']
    )
    print(f"  {total_years} years across {len(decades)} decades, {total_players} ranked entries")


if __name__ == "__main__":
    build_historical_json()
