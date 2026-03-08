"""Build historical TAP rankings JSON from v9 + scraped data.

One-time script that:
1. Reads v9_historical_data.csv (years 1950-2017) and scraped data (2018-2024)
2. Calculates TAP for each qualifying player via calculator.py
3. Groups by decade, outputs phase2/historical_rankings.json

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


def load_v9_data():
    """Load v9 historical data (1950-2017)."""
    path = os.path.join(PROJECT_DIR, "v9_historical_data.csv")
    players = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        # Columns: TAP 2017, Year, Pace, Games, Minutes, FG, FGA, 3P, FT, FTA,
        #          RB, Assists, Steals, Blocks, Turnovers, DBPM, DWS, Points, PER, OBPM, OWS
        for row in reader:
            try:
                year = int(float(row[1]))
            except (ValueError, IndexError):
                continue
            if year < 1950 or year > 2017:
                continue

            def safe_float(val, default=0.0):
                try:
                    v = float(val)
                    return v if not math.isnan(v) else default
                except (ValueError, TypeError):
                    return default

            g = safe_float(row[3])
            mp = safe_float(row[4])
            pace = safe_float(row[2])

            # Filter: G >= 40, MP >= 20
            if g < 40 or mp < 20:
                continue
            if pace == 0:
                continue

            players.append({
                'player': row[0].strip(),
                'team': None,
                'year': year,
                'pace': pace,
                'g': int(g),
                'mp': mp,
                'fg': safe_float(row[5]),
                'fga': safe_float(row[6]),
                'three_p': safe_float(row[7]),
                'ft': safe_float(row[8]),
                'fta': safe_float(row[9]),
                'rb': safe_float(row[10]),
                'ast': safe_float(row[11]),
                'stl': safe_float(row[12]),
                'blk': safe_float(row[13]),
                'tov': safe_float(row[14]),
                'pts': safe_float(row[17]),
                'dbpm': safe_float(row[15]) if row[15].strip() else None,
                'dws': safe_float(row[16]) if row[16].strip() else None,
                'obpm': safe_float(row[19]) if row[19].strip() else None,
                'ows': safe_float(row[20]) if row[20].strip() else None,
                'per': safe_float(row[18]),
            })

    print(f"  v9: loaded {len(players)} qualifying players (1950-2017)")
    return players


def load_scraped_data():
    """Load scraped data (BR years 2019-2025 = start-years 2018-2024)."""
    path = os.path.join(PROJECT_DIR, "scraped_data", "all_seasons_2018_2026.csv")
    players = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                br_year = int(float(row['Year']))
            except (ValueError, KeyError):
                continue
            start_year = br_year - 1  # Convert BR end-year to start-year
            if start_year < 2018 or start_year > 2024:
                continue

            def safe_float(val, default=0.0):
                try:
                    v = float(val)
                    return v if not math.isnan(v) else default
                except (ValueError, TypeError):
                    return default

            g = safe_float(row.get('G', 0))
            mp = safe_float(row.get('MP', 0))
            pace = safe_float(row.get('Pace', 0))

            # Filter: G >= 40, MP >= 20
            if g < 40 or mp < 20:
                continue
            if pace == 0:
                continue

            # Skip traded-player individual team rows (keep only combined)
            team = row.get('Team', '').strip()
            if team in ('2TM', '3TM', '4TM', '5TM'):
                # These are combined rows — keep them but show TOT as team
                team = 'TOT'

            players.append({
                'player': fix_encoding(row['Player'].strip()),
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

    print(f"  Scraped: loaded {len(players)} qualifying players (2018-2024)")
    return players


def calculate_tap_for_players(players):
    """Run calculator on each player, return list with TAP values added."""
    results = []
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

        result = calculate_stats(
            player_data, p['pace'],
            advanced=advanced if advanced else None,
            season_g=p['g'], season_mp=p['mp']
        )

        if result and result.get('tap') is not None:
            results.append({
                'player': p['player'],
                'team': p['team'],
                'year': p['year'],
                'tap': result['tap'],
                'ted': result.get('ted', result['tap']),
            })

    return results


def build_historical_json():
    """Main entry point: build and write historical_rankings.json."""
    print("Building historical TAP rankings JSON...")

    # Load data
    v9_players = load_v9_data()
    scraped_players = load_scraped_data()
    all_players = v9_players + scraped_players

    print(f"  Total qualifying players: {len(all_players)}")

    # Calculate TAP
    print("  Calculating TAP for all players...")
    results = calculate_tap_for_players(all_players)
    print(f"  Calculated TAP for {len(results)} players")

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
    for r in results:
        career_data[r['player']].append({
            'y': r['year'], 'tm': r['team'] or '',
            'ted': round(r['ted'], 1), 'tap': round(r['tap'], 1)
        })
    for name in career_data:
        career_data[name].sort(key=lambda x: x['y'])
    print(f"  Career data: {len(career_data)} unique players")

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
        season_stats[str(year)] = {
            'top10_ted': round(sum(top10_teds) / len(top10_teds), 1),
            'top10_tap': round(sum(top10_taps) / len(top10_taps), 1),
            'ldr_ted': ted_leader['player'], 'ldr_ted_val': round(ted_leader['ted'], 1),
            'ldr_tap': tap_leader['player'], 'ldr_tap_val': round(tap_leader['tap'], 1),
        }
    print(f"  Season stats: {len(season_stats)} years")

    # Sort each year by TAP descending, take top N
    decades = {}
    decade_order = ['2020s', '2010s', '2000s', '1990s', '1980s', '1970s', '1960s', '1950s']

    for decade_label in decade_order:
        decade_start = int(decade_label[:4])
        decade_end = decade_start + 9
        years_data = []

        for year in range(min(decade_end, 2024), decade_start - 1, -1):  # newest first, cap at 2024
            if year < 1950:
                continue

            if year >= 2013:
                top_n = 40
            elif year >= 1984:
                top_n = 30
            elif year >= 1982:
                top_n = 20
            else:
                top_n = 10
            season_label = f"{year}-{str(year + 1)[-2:]}"

            year_players = sorted(by_year.get(year, []), key=lambda x: x['ted'], reverse=True)
            top_players = year_players[:top_n]

            # Build player entries with rank
            player_entries = []
            for i, p in enumerate(top_players, 1):
                player_entries.append({
                    'rank': i,
                    'player': p['player'],
                    'team': p['team'],
                    'ted': round(p['ted'], 1),
                    'tap': round(p['tap'], 1),
                })

            # Pad with empty entries if fewer than top_n
            while len(player_entries) < top_n:
                player_entries.append({
                    'rank': len(player_entries) + 1,
                    'player': None,
                    'team': None,
                    'ted': None,
                    'tap': None,
                })

            years_data.append({
                'year': year,
                'season_label': season_label,
                'top_n': top_n,
                'players': player_entries,
            })

            actual_count = len(top_players)
            if actual_count < top_n:
                print(f"    {season_label}: {actual_count}/{top_n} qualifying players")

        if years_data:
            decades[decade_label] = {'years': years_data}

    # Build all-time top 200 (best individual seasons by TED across all years)
    all_time_sorted = sorted(results, key=lambda x: x['ted'], reverse=True)[:200]
    all_time_top_200 = []
    for i, p in enumerate(all_time_sorted, 1):
        season_label = f"{p['year']}-{str(p['year'] + 1)[-2:]}"
        all_time_top_200.append({
            'rank': i,
            'player': p['player'],
            'team': p['team'],
            'year': p['year'],
            'season_label': season_label,
            'ted': round(p['ted'], 1),
            'tap': round(p['tap'], 1),
        })
    print(f"  All-time top 200: TED range {all_time_top_200[0]['ted']} to {all_time_top_200[-1]['ted']}")

    # Write JSON
    output = {
        'generated': str(__import__('datetime').date.today()),
        'all_time_top_200': all_time_top_200,
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
