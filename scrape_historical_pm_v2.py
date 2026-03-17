"""Scrape historical PM (plus/minus) from BR player game log pages.

Instead of scraping ~30,000 individual box score pages, this scrapes
player game log pages — one page per player-season gives every game's
PM + MP. Only scrapes players who appear in historical rankings.

~870 requests total (vs 30,000 in v1 approach).

Usage:
    python scrape_historical_pm_v2.py              # All ranked players 2000-2024
    python scrape_historical_pm_v2.py --season 2020  # Single season
    python scrape_historical_pm_v2.py --status       # Show progress
"""

import sys
import os
import json
import time
import argparse
from datetime import date
from bs4 import BeautifulSoup

# Force UTF-8 output on Windows to handle player names with accents
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.stderr.reconfigure(encoding='utf-8', errors='replace')

PROJECT_DIR = r"C:\Projects\TED Claude Project"
sys.path.insert(0, PROJECT_DIR)

from phase2 import config, database as db
from phase2.scraper import create_session, _parse_minutes, _clean_player_name

SCRAPE_DELAY = 5  # seconds between requests
RATE_LIMIT_WAIT = 300  # 5 minutes cooldown on 429
MAX_429_RETRIES = 5  # retry up to 5 times on 429 before giving up on a player
REQUEST_TIMEOUT = 30


def _get_page_no429retry(session, url, label="page"):
    """Fetch a URL. Does NOT retry on 429 — lets caller handle rate limits."""
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT)
        resp.encoding = 'utf-8'
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        if '429' in str(e):
            raise  # Let outer loop handle with long backoff
        # Retry once for non-429 errors
        try:
            time.sleep(5)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            resp.encoding = 'utf-8'
            resp.raise_for_status()
            return resp.text
        except Exception:
            raise


def fix_encoding(s):
    """Fix double-encoded UTF-8 (UTF-8 bytes misread as Latin-1 then re-encoded).
    e.g. 'JokiÄ\x87' -> 'Jokić', 'DonÄ\x8diÄ\x87' -> 'Dončić'
    """
    try:
        return s.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


def get_ranked_players(season_year):
    """Get list of player names who appear in historical rankings for a season."""
    json_path = os.path.join(PROJECT_DIR, 'phase2', 'historical_rankings.json')
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    for decade_label, decade in data['decades'].items():
        for year_data in decade['years']:
            if year_data['year'] == season_year:
                return [p['player'] for p in year_data['players']]
    return []


def get_v9_players(season_year):
    """Get list of player names from v9 CSV for a season (2000-2016)."""
    import csv
    csv_path = os.path.join(PROJECT_DIR, 'v9_historical_data.csv')
    players = []
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)  # First column is player name (named "TAP 2017")
        year_idx = header.index('Year')
        for row in reader:
            try:
                yr = int(row[year_idx])
            except (ValueError, IndexError):
                continue  # Skip mid-file year headers
            if yr == season_year:
                name = row[0].strip()
                if name:
                    players.append(name)
    return players


def get_scraped_players(season_year):
    """Get list of player names from scraped CSV for a season (2017-2024)."""
    import csv
    br_year = season_year + 1
    csv_path = os.path.join(PROJECT_DIR, 'scraped_data', f'{br_year}_season.csv')
    if not os.path.exists(csv_path):
        return []
    players = []
    with open(csv_path, encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = fix_encoding(row.get('Player', '').strip())
            if name:
                players.append(name)
    return players


def get_all_players(season_year):
    """Get ALL players we have data for in a season (v9 for 2000-2016, scraped for 2017+)."""
    if season_year <= 2016:
        return get_v9_players(season_year)
    else:
        return get_scraped_players(season_year)


def get_player_slugs(session, br_year):
    """Scrape the season per-game page to build a name -> BR slug mapping.

    BR per-game page has links like: /players/j/jokicni01.html
    Returns dict: {'Nikola Jokić': 'jokicni01', ...}
    """
    url = f"{config.BR_BASE_URL}/leagues/NBA_{br_year}_per_game.html"
    print(f"  Fetching player slugs from NBA_{br_year} per-game page...")
    html = _get_page_no429retry(session, url, f"per-game NBA_{br_year}")
    time.sleep(SCRAPE_DELAY)

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', id='per_game_stats')
    if not table:
        # Try inside comments (BR sometimes hides tables in comments)
        for comment in soup.find_all(string=lambda t: isinstance(t, type(soup.new_string(''))) and 'per_game_stats' in str(t)):
            comment_soup = BeautifulSoup(str(comment), 'html.parser')
            table = comment_soup.find('table', id='per_game_stats')
            if table:
                break

    if not table:
        print(f"    WARNING: Could not find per_game_stats table for NBA_{br_year}")
        return {}

    slugs = {}
    tbody = table.find('tbody')
    if not tbody:
        return slugs

    for row in tbody.find_all('tr'):
        if row.get('class') and 'thead' in row['class']:
            continue
        player_cell = row.find('td', {'data-stat': 'name_display'})
        if not player_cell:
            continue
        link = player_cell.find('a')
        if not link or not link.get('href'):
            continue
        name = _clean_player_name(link.text)
        # Extract slug from href like /players/j/jokicni01.html
        href = link['href']
        slug = href.split('/')[-1].replace('.html', '')
        if name and slug:
            slugs[name] = slug

    print(f"    Found {len(slugs)} player slugs")
    return slugs


def scrape_player_gamelog_pm(session, slug, br_year):
    """Scrape a player's game log page for PM data.

    Returns list of (mp_decimal, plus_minus) tuples for games where both exist.
    """
    url = f"{config.BR_BASE_URL}/players/{slug[0]}/{slug}/gamelog/{br_year}"
    html = _get_page_no429retry(session, url, f"gamelog {slug}/{br_year}")

    soup = BeautifulSoup(html, 'html.parser')
    table = soup.find('table', id='player_game_log_reg')
    if not table:
        return []

    tbody = table.find('tbody')
    if not tbody:
        return []

    games = []
    for row in tbody.find_all('tr'):
        if row.get('class') and 'thead' in row['class']:
            continue
        # Skip inactive/DNP rows
        reason = row.find('td', {'data-stat': 'reason'})
        if reason and reason.text.strip():
            continue

        mp_cell = row.find('td', {'data-stat': 'mp'})
        pm_cell = row.find('td', {'data-stat': 'plus_minus'})

        if not mp_cell or not pm_cell:
            continue

        mp = _parse_minutes(mp_cell.text)
        pm_text = pm_cell.text.strip()
        if mp is None or not pm_text:
            continue

        try:
            pm = int(pm_text)
        except ValueError:
            try:
                pm = int(float(pm_text))
            except ValueError:
                continue

        if mp > 0:
            games.append((mp, pm))

    return games


def compute_avg_pm(games):
    """Compute season-average PM from game log data.

    Uses season-level normalization: sum(PM) / sum(MP) * 36
    Consistent with how all other stats are normalized.
    """
    if not games:
        return None
    total_mp = sum(mp for mp, pm in games)
    total_pm = sum(pm for mp, pm in games)
    if total_mp == 0:
        return None
    # Return raw average PM per game (not per-36) — the calculator handles normalization
    return total_pm / len(games)


def name_match(ranked_name, slug_name):
    """Fuzzy match player names (handles accents, suffixes, etc.)."""
    import unicodedata

    def normalize(n):
        # Remove accents
        n = unicodedata.normalize('NFD', n)
        n = ''.join(c for c in n if unicodedata.category(c) != 'Mn')
        # Lowercase, strip suffixes
        n = n.lower().strip()
        for suffix in [' jr.', ' sr.', ' iii', ' ii', ' iv', ' jr', ' sr']:
            n = n.replace(suffix, '')
        return n.strip()

    return normalize(ranked_name) == normalize(slug_name)


# Manual name mappings for BR retroactive name changes
NAME_ALIASES = {
    'Enes Kanter': 'Enes Freedom',
}


def find_slug(player_name, slugs):
    """Find BR slug for a player name, with fuzzy matching."""
    # Exact match
    if player_name in slugs:
        return slugs[player_name]

    # Check aliases
    alias = NAME_ALIASES.get(player_name)
    if alias and alias in slugs:
        return slugs[alias]

    # Fuzzy match
    for slug_name, slug in slugs.items():
        if name_match(player_name, slug_name):
            return slug

    return None


def scrape_season_pm(session, season_year, full=False):
    """Scrape PM data for players in a season.

    season_year: start-year convention (2020 = 2020-21 season)
    full: if True, scrape ALL players from the per-game page (not just ranked)
    """
    br_year = season_year + 1
    season_label = f"{season_year}-{str(season_year + 1)[-2:]}"

    print(f"\n{'='*60}")
    print(f"  Season {season_label} (BR year {br_year}){' [FULL]' if full else ''}")
    print(f"{'='*60}")

    # Get player slugs from per-game page (need this for both modes)
    slugs = None
    for slug_retry in range(MAX_429_RETRIES):
        try:
            slugs = get_player_slugs(session, br_year)
            break
        except Exception as e:
            if '429' in str(e) and slug_retry < MAX_429_RETRIES - 1:
                wait = RATE_LIMIT_WAIT * (slug_retry + 1)
                print(f"  429 on slug page, waiting {wait}s...")
                time.sleep(wait)
            else:
                print(f"  ERROR getting slugs: {e}")
                break
    if not slugs:
        print(f"  ERROR: Could not get player slugs")
        return 0

    if full:
        # Scrape all players we have data for (v9 for 2000-2016, scraped for 2017+)
        target_players = get_all_players(season_year)
        print(f"  All players in dataset: {len(target_players)}")
    else:
        # Scrape only ranked players
        target_players = get_ranked_players(season_year)
        if not target_players:
            print(f"  No ranked players found for {season_label}")
            return 0
        print(f"  Ranked players: {len(target_players)}")

    # Check which players already have PM data
    existing_raw = db.get_historical_avg_pm(season_year)
    existing = {player: data for (player, sy), data in existing_raw.items() if sy == season_year}
    already_done = set()
    for name in target_players:
        if name in existing and existing[name] is not None:
            already_done.add(name)

    remaining = [n for n in target_players if n not in already_done]
    print(f"  Already have PM data: {len(already_done)}")
    print(f"  Need to scrape: {len(remaining)}")

    if not remaining:
        print(f"  All done for {season_label}!")
        return 0

    scraped = 0
    failed = []

    for i, player_name in enumerate(remaining):
        slug = find_slug(player_name, slugs)
        if not slug:
            print(f"    [{i+1}/{len(remaining)}] {player_name}: NO SLUG FOUND")
            failed.append(player_name)
            continue

        print(f"    [{i+1}/{len(remaining)}] {player_name} ({slug})...", end=' ')
        success = False
        for retry_429 in range(MAX_429_RETRIES):
            try:
                games = scrape_player_gamelog_pm(session, slug, br_year)
                if games:
                    avg_pm = compute_avg_pm(games)
                    # Store in historical_pm as a summary row (tuple format)
                    pm_rows = [(
                        f'avg_{season_year}_{slug}',
                        f'{season_year + 1}-07-01',  # placeholder date
                        season_year,
                        player_name,
                        'AVG',
                        sum(mp for mp, _ in games) / len(games),
                        avg_pm or 0,
                    )]
                    db.insert_historical_pm(pm_rows)
                    print(f"{len(games)} games, avg PM = {avg_pm:+.1f}")
                    scraped += 1
                else:
                    print("no game data")
                    failed.append(player_name)
                success = True
                break
            except Exception as e:
                if '429' in str(e) and retry_429 < MAX_429_RETRIES - 1:
                    wait = RATE_LIMIT_WAIT * (retry_429 + 1)
                    print(f"429 rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    print(f"    [{i+1}/{len(remaining)}] {player_name} ({slug}) retry...", end=' ')
                else:
                    print(f"ERROR: {e}")
                    failed.append(player_name)
                    success = True  # don't retry non-429 errors
                    break

        time.sleep(SCRAPE_DELAY)

    print(f"\n  Season {season_label}: scraped {scraped}/{len(remaining)}")
    if failed:
        print(f"  Failed ({len(failed)}): {', '.join(failed[:10])}{'...' if len(failed) > 10 else ''}")
    return scraped


def show_status(full=False):
    """Show scraping progress."""
    if full:
        # Full mode: compare players in dataset vs players with PM in DB
        print(f"{'Season':<16} {'Dataset':>8} {'Have PM':>8} {'Missing':>8}")
        print('-' * 50)
        total_ds = 0
        total_have = 0
        for season_year in range(2024, 1999, -1):
            all_players = get_all_players(season_year)
            existing_raw = db.get_historical_avg_pm(season_year)
            existing = {player: data for (player, sy), data in existing_raw.items() if sy == season_year}
            have_pm = sum(1 for n in all_players if n in existing and existing[n] is not None)
            missing = len(all_players) - have_pm
            label = f"{season_year}-{str(season_year + 1)[-2:]}"
            status = "DONE" if missing == 0 else ""
            print(f"{label:<16} {len(all_players):>8} {have_pm:>8} {missing:>8} {status}")
            total_ds += len(all_players)
            total_have += have_pm
        print('-' * 50)
        print(f"{'TOTAL':<16} {total_ds:>8} {total_have:>8} {total_ds - total_have:>8}")
    else:
        json_path = os.path.join(PROJECT_DIR, 'phase2', 'historical_rankings.json')
        with open(json_path, encoding='utf-8') as f:
            data = json.load(f)

        print(f"{'Season':<16} {'Ranked':>7} {'Have PM':>8} {'Missing':>8}")
        print('-' * 45)

        total_ranked = 0
        total_have = 0

        for season_year in range(2024, 1999, -1):
            ranked = get_ranked_players(season_year)
            if not ranked:
                continue
            existing_raw = db.get_historical_avg_pm(season_year)
            existing = {player: data for (player, sy), data in existing_raw.items() if sy == season_year}
            have_pm = sum(1 for n in ranked if n in existing and existing[n] is not None)
            missing = len(ranked) - have_pm
            label = f"{season_year}-{str(season_year + 1)[-2:]}"
            status = "DONE" if missing == 0 else ""
            print(f"{label:<16} {len(ranked):>7} {have_pm:>8} {missing:>8} {status}")
            total_ranked += len(ranked)
            total_have += have_pm

        print('-' * 45)
        print(f"{'TOTAL':<16} {total_ranked:>7} {total_have:>8} {total_ranked - total_have:>8}")


# Seasons with player data (v9: 2000-2016, scraped: 2017-2024)
FULL_SEASONS = list(range(2024, 1999, -1))  # 2000-2024 (start-year)


def main():
    parser = argparse.ArgumentParser(description='Scrape historical PM from BR player game logs')
    parser.add_argument('--season', type=int, help='Single season year (start-year, e.g. 2020)')
    parser.add_argument('--full', action='store_true', help='Scrape ALL players (not just ranked) for seasons 2017-2024')
    parser.add_argument('--status', action='store_true', help='Show progress')
    args = parser.parse_args()

    if args.status:
        show_status(full=args.full)
        return

    session = create_session()

    if args.full:
        # Full mode: all players for scraped seasons (2017-2024)
        seasons = [args.season] if args.season else FULL_SEASONS
        for season_year in seasons:
            scrape_season_pm(session, season_year, full=True)
    elif args.season:
        scrape_season_pm(session, args.season)
    else:
        # Ranked-only for all seasons 2000-2024
        for season_year in range(2024, 1999, -1):
            scrape_season_pm(session, season_year)

    print("\nDone!")


if __name__ == '__main__':
    main()
