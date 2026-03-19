"""Static HTML site generator for TED Weekly Rankings.

Reads from the SQLite database, calculates rankings, and generates
a single docs/index.html for GitHub Pages deployment.
"""

import os
import sys
import json
import html as html_module
from datetime import date, timedelta
from . import config, database as db
from .weekly_update import calculate_season_rankings, calculate_weekly_rankings

DOCS_DIR = os.path.join(config.PROJECT_DIR, "docs")


def _remap_tapd(tapd_ranked):
    """Remap TAPD results so they look like standard tap results.

    Copies each result dict, sets 'tap' = 'tapd' and re-numbers 'tap_rank'.
    This lets render_table() display TAPD values using the existing 'tap'
    stat_key (column header stays "TAP", no code changes needed downstream).
    """
    remapped = []
    for i, r in enumerate(tapd_ranked):
        rc = dict(r)
        rc['tap'] = rc['tapd']
        rc['tap_rank'] = i + 1
        remapped.append(rc)
    return remapped


def get_rolling_week():
    """Return (start, end) for the rolling 7-day window ending yesterday.

    Always looks at the 7 most recent days of completed games.
    Yesterday is the last day (today's games may not be final yet),
    and 6 days before that is the first day.
    """
    today = date.today()
    end = today - timedelta(days=1)   # yesterday
    start = end - timedelta(days=6)   # 7-day window
    return start, end


def render_table(rankings, stat_key, title, week_label=None):
    """Render a single ranking table as HTML."""
    rows_html = ""
    if not rankings:
        rows_html = '<tr><td colspan="4" class="empty">No data available</td></tr>'
    else:
        for r in rankings:
            rank = r.get(f'{stat_key}_rank', 0)
            name_html = format_player_name(r['player'])
            player_attr = html_module.escape(r['player'], quote=True)
            rows_html += f"""        <tr>
          <td class="rank">{rank}</td>
          <td class="player" data-player="{player_attr}">{name_html}</td>
          <td class="team">{r['team']}</td>
          <td class="num stat">{r[stat_key]:.1f}</td>
        </tr>
"""

    subtitle = f'<span class="week-label">{week_label}</span>' if week_label else ''

    return f"""  <div class="table-section">
    <div class="table-header"><h2>{title}</h2>{subtitle}</div>
    <table>
      <thead>
        <tr>
          <th class="rank">Rank</th>
          <th class="player">Player</th>
          <th class="team">Team</th>
          <th class="num stat">{stat_key.upper()}</th>
        </tr>
      </thead>
      <tbody>
{rows_html}      </tbody>
    </table>
  </div>
"""


def format_player_name(name):
    """Format a player name for HTML display with suffix handling and mobile line breaks."""
    if not name:
        return ''
    if 'Gilgeous-Alexander' in name:
        return '<span class="fname">Shai Gilgeous-</span><span class="lname">Alexander</span>'
    display = (name.replace(' Jr.', '&nbsp;Jr.')
                   .replace(' Sr.', '&nbsp;Sr.')
                   .replace(' III', '&nbsp;III')
                   .replace(' II', '&nbsp;II')
                   .replace(' IV', '&nbsp;IV'))
    parts = display.split(' ', 1)
    if len(parts) == 2:
        return f'<span class="fname">{parts[0]}</span> <span class="lname">{parts[1]}</span>'
    return name


def load_historical_rankings():
    """Load pre-computed historical rankings from JSON."""
    json_path = os.path.join(config.PHASE2_DIR, "historical_rankings.json")
    if not os.path.exists(json_path):
        return None
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def render_historical_section(data, stat_key='ted', season_all=None):
    """Generate full HTML for the historical rankings section.

    stat_key: 'ted', 'tap', or 'tapd' — determines sort order and displayed stat.
    season_all: current season results to merge into all-time top 200.

    For 'tapd': falls back to 'tap' for players/years without TAPD data.
    Column header shows 'TAPD' for years with data, 'TAP' for pre-PM years.
    """
    if not data or 'decades' not in data:
        return '', ''

    stat_upper = stat_key.upper()
    decade_order = ['2020s', '2010s', '2000s', '1990s', '1980s', '1970s', '1960s', '1950s']

    suffix = '' if stat_key == 'ted' else f'-{stat_key}'

    # Build decade nav links (only from TED pass — shared nav)
    # Insert break after 4th decade so mobile shows 4 per row
    available_decades = [d for d in decade_order if d in data['decades']]
    nav_links = ''
    for i, d in enumerate(available_decades):
        nav_links += f'<a href="#decade-{d}" data-decade="{d}">{d[:-1]}<span class="decade-s">s</span></a>'
        if i == 3:
            nav_links += '<div class="nav-break"></div>'
        if i == 5:
            nav_links += '<div class="nav-break desktop-only"></div>'
    nav_links += '<div class="nav-break"></div>'
    nav_links += '<a href="#" data-goat="true" style="color:#ee7623">GOAT</a>'
    nav_links += '<a href="#" data-g2="true" style="color:#ee7623">G2</a>'
    nav_links += '<a href="#" data-g3="true" style="color:#ee7623">G3</a>'
    nav_links += '<a href="#" data-mg="true" style="color:#ee7623">MG</a>'
    nav_links += '<a href="#" data-diff="true" style="color:#ee7623">DIFF</a>'

    # Build decade sections
    decades_html = ''
    for decade_label in decade_order:
        if decade_label not in data['decades']:
            continue
        decade = data['decades'][decade_label]

        year_tables = []
        for year_data in decade['years']:
            season_label = year_data['season_label']
            top_n = year_data['top_n']

            # Use the independently-sorted player pool for this stat
            if stat_key == 'tap':
                player_pool = year_data.get('players_tap', year_data['players'])
            elif stat_key == 'tapd':
                player_pool = year_data.get('players_tapd', year_data.get('players_tap', year_data['players']))
            else:
                player_pool = year_data['players']

            # For TAPD: check if this year has TAPD data; fall back to TAP if not
            effective_key = stat_key
            if stat_key == 'tapd':
                has_tapd = any(p.get('tapd') is not None
                              for p in player_pool if p.get('player'))
                if not has_tapd:
                    effective_key = 'tap'
                    player_pool = year_data.get('players_tap', year_data['players'])
            effective_upper = effective_key.upper()

            # Players are already sorted by the correct stat from JSON
            players_sorted = [p for p in player_pool if p.get('player')]

            # Build table rows with fresh ranks
            rows = ''
            for rank, p in enumerate(players_sorted, 1):
                name_html = format_player_name(p['player'])
                player_attr = html_module.escape(p['player'], quote=True)
                team = p['team'] if p['team'] else '&mdash;'
                val = p.get(effective_key, 0) or 0
                val_str = f'{val:.1f}'
                rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="team">{team}</td><td class="num stat">{val_str}</td></tr>\n'

            # Years 1996+ will have TAPD data — build a hidden TAPD table (may be empty until scraping completes)
            tapd_eligible = (stat_key == 'tap' and year_data['year'] >= 1996)
            stat_cls = 'num stat stat-toggle' if tapd_eligible else 'num stat'

            tapd_table_html = ''
            if tapd_eligible:
                # Use independently-sorted TAPD player pool
                tapd_players = [p for p in year_data.get('players_tapd', [])
                                if p.get('player')]
                tapd_rows = ''
                if tapd_players:
                    for rank, p in enumerate(tapd_players, 1):
                        name_html = format_player_name(p['player'])
                        player_attr = html_module.escape(p['player'], quote=True)
                        team = p['team'] if p['team'] else '&mdash;'
                        val_str = f'{p["tapd"]:.1f}'
                        tapd_rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="team">{team}</td><td class="num stat">{val_str}</td></tr>\n'
                else:
                    # Skeleton rows — show rank numbers but no data yet
                    num_rows = len(year_data['players'])
                    for rank in range(1, num_rows + 1):
                        tapd_rows += f'        <tr><td class="rank">{rank}</td><td class="player"></td><td class="team"></td><td class="num stat"></td></tr>\n'
                tapd_table_html = f"""
        <table class="tapd-year-table" style="display:none">
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="team">Team</th><th class="num stat stat-toggle">TAPD</th></tr></thead>
          <tbody>
{tapd_rows}          </tbody>
        </table>"""

            year_tables.append(f"""      <div class="year-table" data-year="{year_data['year']}">
        <div class="table-header"><h2>{season_label} SEASON &mdash; <span class="year-stat-label">{effective_upper}</span> TOP {top_n}</h2></div>
        <table class="tap-year-table">
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="team">Team</th><th class="{stat_cls}">{effective_upper}</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>{tapd_table_html}
      </div>
""")

        # Pair year tables side by side (2 per row on desktop)
        years_html = ''
        for i in range(0, len(year_tables), 2):
            if i + 1 < len(year_tables):
                years_html += f"""    <div class="year-pair">
{year_tables[i]}{year_tables[i+1]}    </div>
"""
            else:
                years_html += f"""    <div class="year-pair single">
{year_tables[i]}      <div class="year-table"><div class="table-header" style="visibility:hidden"><h2>&nbsp;</h2></div></div>
    </div>
"""

        decade_top100_html = render_decade_top100_html(
            decade_label, decade, stat_key, season_all)

        decades_html += f"""  <div class="decade" id="decade-{decade_label}{suffix}">
    <div class="decade-header"><h3>{decade_label[:-1]}<span class="decade-s">s</span></h3></div>
    <div class="decade-top100" style="display:none">
{decade_top100_html}    </div>
    <div class="decade-years">
{years_html}    </div>
  </div>
"""

    # Build GOAT table from season_stats
    goat_html = render_goat_html(data.get('season_stats', {}), stat_key, season_all)
    # Build G2 table (top 2 players per year) from season_stats
    g2_html = render_g2_html(data.get('season_stats', {}), stat_key, season_all)
    # Build G3 table (top 3 players per year) from season_stats
    g3_html = render_g3_html(data.get('season_stats', {}), stat_key, season_all)

    # Build MG tables (modern era TAPD — always uses 'tapd' internally regardless of stat_key)
    mg1_html = render_mg1_html(data.get('season_stats', {}), season_all)
    mg2_html = render_mg2_html(data.get('season_stats', {}), season_all)
    mg3_html = render_mg3_html(data.get('season_stats', {}), season_all)

    # Build DIFF tables (career avg TED/TAP and DIFF vs top 100)
    diff_data_ted = [dict(d) for d in data.get('diff_data_ted', [])]
    diff_data_tap = [dict(d) for d in data.get('diff_data_tap', [])]
    # Merge current season into diff data (uses tiered min-games filter from season_all)
    if season_all:
        current_year = config.CURRENT_SEASON_YEAR
        yr_key = str(current_year)
        # Compute top100 avg for current season (DIFF baseline)
        ted_sorted_cur = sorted(season_all, key=lambda r: r['ted'], reverse=True)
        tap_sorted_cur = sorted(season_all, key=lambda r: r['tap'], reverse=True)
        top100_ted_cur = sum(r['ted'] for r in ted_sorted_cur[:100]) / min(100, len(ted_sorted_cur))
        top100_tap_cur = sum(r['tap'] for r in tap_sorted_cur[:100]) / min(100, len(tap_sorted_cur))
        # Update each player's career aggregates with current season
        cur_by_name = {r['player']: r for r in season_all}
        # Build lookup of existing diff entries
        ted_lookup = {d['player']: d for d in diff_data_ted}
        tap_lookup = {d['player']: d for d in diff_data_tap}
        for r in season_all:
            name = r['player']
            ted_diff = r['ted'] - top100_ted_cur
            tap_diff = r['tap'] - top100_tap_cur
            if name in ted_lookup:
                d = ted_lookup[name]
                old_n = d['seasons']
                d['ated'] = round((d['ated'] * old_n + r['ted']) / (old_n + 1), 1)
                d['adiff'] = round((d['adiff'] * old_n + ted_diff) / (old_n + 1), 1)
                d['tdiff'] = round(d['tdiff'] + ted_diff, 1)
                d['seasons'] = old_n + 1
            else:
                new_entry = {'player': name, 'seasons': 1, 'ated': round(r['ted'], 1),
                             'adiff': round(ted_diff, 1), 'tdiff': round(ted_diff, 1)}
                diff_data_ted.append(new_entry)
            if name in tap_lookup:
                d = tap_lookup[name]
                old_n = d['seasons']
                d['atap'] = round((d['atap'] * old_n + r['tap']) / (old_n + 1), 1)
                d['adiff'] = round((d['adiff'] * old_n + tap_diff) / (old_n + 1), 1)
                d['tdiff'] = round(d['tdiff'] + tap_diff, 1)
                d['seasons'] = old_n + 1
            else:
                new_entry = {'player': name, 'seasons': 1, 'atap': round(r['tap'], 1),
                             'adiff': round(tap_diff, 1), 'tdiff': round(tap_diff, 1)}
                diff_data_tap.append(new_entry)
        diff_data_ted.sort(key=lambda x: x['ated'], reverse=True)
        diff_data_tap.sort(key=lambda x: x.get('atap', 0), reverse=True)
    diff_tables = render_diff_html(diff_data_ted, diff_data_tap)

    # TAPD view still uses "TAP" in the section header — no separate historical TAPD summary
    header_label = 'TAP' if stat_key in ('tap', 'tapd') else stat_upper
    return nav_links, f"""  <div class="historical-section">
    <div class="historical-header"><h2>Historical {header_label} Rankings</h2></div>
    <div class="all-time-table" style="display:none">
{render_all_time_html(data, stat_key, season_all)}    </div>
    <nav class="decade-nav">{nav_links}</nav>
    <div class="goat-table" style="display:none">
{goat_html}    </div>
    <div class="g2-table" style="display:none">
{g2_html}    </div>
    <div class="g3-table" style="display:none">
{g3_html}    </div>
    <div class="mg-table" style="display:none">
{mg1_html}{mg2_html}{mg3_html}    </div>
    <div class="diff-table" style="display:none">
      <div class="view-ted">{diff_tables['ted']}</div>
      <div class="view-tap" style="display:none">{diff_tables['tap']}</div>
    </div>
{decades_html}  </div>
"""


def get_last_name(name):
    """Extract last name from a full player name, keeping suffixes attached."""
    if not name:
        return ''
    suffixes = {'Jr.', 'Sr.', 'III', 'II', 'IV'}
    parts = name.split()
    if len(parts) <= 1:
        return name
    if parts[-1] in suffixes and len(parts) >= 3:
        return f'{parts[-2]}&nbsp;{parts[-1]}'
    return parts[-1]


def render_all_time_html(data, stat_key='ted', season_all=None):
    """Generate HTML for the all-time top 400 table.

    Merges current season-to-date players into the historical
    all-time list, re-sorts by stat_key, and takes the top 400.
    """
    if not data or 'all_time_top_200' not in data:
        return ''

    stat_upper = stat_key.upper()
    current_year = config.CURRENT_SEASON_YEAR

    # Use independently-sorted pool for each stat
    if stat_key == 'tap':
        all_entries = list(data.get('all_time_tap', data['all_time_top_200']))
    else:
        all_entries = list(data['all_time_top_200'])

    # Merge current season players
    if season_all:
        season_label = f"{current_year}-{str(current_year + 1)[-2:]}"
        for p in season_all:
            if p.get('ted') is not None and p.get('tap') is not None:
                entry = {
                    'player': p['player'],
                    'team': p.get('team', ''),
                    'year': current_year,
                    'season_label': season_label,
                    'ted': round(p['ted'], 1),
                    'tap': round(p['tap'], 1),
                }
                if p.get('tapd') is not None:
                    entry['tapd'] = round(p['tapd'], 1)
                all_entries.append(entry)

    # Re-sort by chosen stat, take top 400, and re-rank
    players_sorted = sorted(
        all_entries,
        key=lambda p: p.get(stat_key, 0),
        reverse=True
    )[:400]

    rows = ''
    for rank, p in enumerate(players_sorted, 1):
        name_html = format_player_name(p['player'])
        player_attr = html_module.escape(p['player'], quote=True)
        val = p.get(stat_key, 0) or 0
        val_str = f'{val:.1f}'
        rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="season">{p["season_label"]}</td><td class="num stat">{val_str}</td></tr>\n'

    # TAPD toggle table for TAP view — uses separate all_time_tapd pool
    tapd_eligible = (stat_key == 'tap')
    stat_cls = 'num stat stat-toggle' if tapd_eligible else 'num stat'

    tapd_table_html = ''
    if tapd_eligible:
        # Build TAPD entries from dedicated pool (all 1996+ players, not just TED/TAP top 400)
        tapd_pool = list(data.get('all_time_tapd', []))
        # Merge current season
        if season_all:
            season_label = f"{current_year}-{str(current_year + 1)[-2:]}"
            for p in season_all:
                if p.get('tapd') is not None:
                    tapd_pool.append({
                        'player': p['player'],
                        'team': p.get('team', ''),
                        'year': current_year,
                        'season_label': season_label,
                        'tapd': round(p['tapd'], 1),
                    })
        tapd_rows = ''
        if tapd_pool:
            tapd_sorted = sorted(tapd_pool, key=lambda p: p.get('tapd', 0) or 0, reverse=True)[:400]
            for rank, p in enumerate(tapd_sorted, 1):
                name_html = format_player_name(p['player'])
                player_attr = html_module.escape(p['player'], quote=True)
                val_str = f'{p["tapd"]:.1f}'
                tapd_rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="season">{p["season_label"]}</td><td class="num stat">{val_str}</td></tr>\n'
        else:
            # Skeleton rows
            for rank in range(1, len(players_sorted) + 1):
                tapd_rows += f'        <tr><td class="rank">{rank}</td><td class="player"></td><td class="season"></td><td class="num stat"></td></tr>\n'
        tapd_table_html = f"""
        <table class="tapd-year-table" style="display:none">
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="season">Season</th><th class="num stat stat-toggle">TAPD</th></tr></thead>
          <tbody>
{tapd_rows}          </tbody>
        </table>"""

    return f"""    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>ALL-TIME <span class="year-stat-label">{stat_upper}</span> TOP 400</h2></div>
        <table class="tap-year-table">
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="season">Season</th><th class="{stat_cls}">{stat_upper}</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>{tapd_table_html}
      </div>
      <div class="year-table">
        <div class="table-header"><h2>&nbsp;</h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
"""


def render_decade_top100_html(decade_label, decade_data, stat_key='ted', season_all=None):
    """Generate HTML for a decade's top N table.

    Merges current season players for the 2020s decade.
    Top N is 200 for 1980s onwards, 100 for earlier decades.
    """
    if not decade_data or 'decade_top_100' not in decade_data:
        return ''

    stat_upper = stat_key.upper()
    current_year = config.CURRENT_SEASON_YEAR
    decade_start = int(decade_label[:4])
    decade_end = decade_start + 9
    decade_top_n = decade_data.get('decade_top_n', 100)

    # Use independently-sorted pool for each stat
    if stat_key == 'tap':
        all_entries = list(decade_data.get('decade_top_tap', decade_data['decade_top_100']))
    else:
        all_entries = list(decade_data['decade_top_100'])

    # Merge current season for the current decade
    if season_all and decade_start <= current_year <= decade_end:
        season_label = f"{current_year}-{str(current_year + 1)[-2:]}"
        for p in season_all:
            if p.get('ted') is not None and p.get('tap') is not None:
                entry = {
                    'player': p['player'],
                    'team': p.get('team', ''),
                    'year': current_year,
                    'season_label': season_label,
                    'ted': round(p['ted'], 1),
                    'tap': round(p['tap'], 1),
                }
                if p.get('tapd') is not None:
                    entry['tapd'] = round(p['tapd'], 1)
                all_entries.append(entry)

    # For TAPD: fall back to TAP for entries without TAPD data
    if stat_key == 'tapd':
        for e in all_entries:
            if e.get('tapd') is None:
                e['tapd'] = e.get('tap', 0)

    # Sort by chosen stat, take top N, re-rank
    players_sorted = sorted(
        all_entries,
        key=lambda p: p.get(stat_key, 0),
        reverse=True
    )[:decade_top_n]

    rows = ''
    for rank, p in enumerate(players_sorted, 1):
        name_html = format_player_name(p['player'])
        player_attr = html_module.escape(p['player'], quote=True)
        val = p.get(stat_key, 0) or 0
        val_str = f'{val:.1f}'
        rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="season">{p["season_label"]}</td><td class="num stat">{val_str}</td></tr>\n'

    # TAPD toggle for 1990s+ decades in TAP view
    tapd_eligible = (stat_key == 'tap' and decade_start >= 1990)
    stat_cls = 'num stat stat-toggle' if tapd_eligible else 'num stat'

    tapd_table_html = ''
    if tapd_eligible:
        # Build TAPD version from dedicated pool (all players with TAPD, not TED-filtered)
        # 1990s gets top 100 (only 4 years of PM data), 2000s+ gets same as TED/TAP
        decade_tapd_n = 100 if decade_start == 1990 else decade_top_n
        tapd_entries = list(decade_data.get('decade_top_tapd', []))
        # Merge current season
        if season_all and decade_start <= current_year <= decade_end:
            season_label = f"{current_year}-{str(current_year + 1)[-2:]}"
            for p in season_all:
                if p.get('tapd') is not None:
                    tapd_entries.append({
                        'player': p['player'],
                        'team': p.get('team', ''),
                        'year': current_year,
                        'season_label': season_label,
                        'tapd': round(p['tapd'], 1),
                    })
        tapd_rows = ''
        if tapd_entries:
            tapd_sorted = sorted(tapd_entries, key=lambda p: p.get('tapd', 0) or 0, reverse=True)[:decade_tapd_n]
            for rank, p in enumerate(tapd_sorted, 1):
                name_html = format_player_name(p['player'])
                player_attr = html_module.escape(p['player'], quote=True)
                val_str = f'{p["tapd"]:.1f}'
                tapd_rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="season">{p["season_label"]}</td><td class="num stat">{val_str}</td></tr>\n'
        else:
            # Skeleton rows
            for rank in range(1, len(players_sorted) + 1):
                tapd_rows += f'        <tr><td class="rank">{rank}</td><td class="player"></td><td class="season"></td><td class="num stat"></td></tr>\n'
        tapd_table_html = f"""
        <table class="tapd-year-table" style="display:none">
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="season">Season</th><th class="num stat stat-toggle">TAPD</th></tr></thead>
          <tbody>
{tapd_rows}          </tbody>
        </table>"""

    return f"""    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header" data-tap-n="{decade_top_n}" data-tapd-n="{decade_tapd_n if tapd_eligible else decade_top_n}" data-tap-label="{decade_label[:-1]}" data-tapd-label="{'LATE 1990s' if decade_start == 1990 and tapd_eligible else decade_label[:-1]}"><h2><span class="decade-label">{decade_label[:-1]}<span class="decade-s">s</span></span> <span class="year-stat-label">{stat_upper}</span> TOP <span class="top-n-label">{decade_top_n}</span></h2></div>
        <table class="tap-year-table">
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="season">Season</th><th class="{stat_cls}">{stat_upper}</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>{tapd_table_html}
      </div>
      <div class="year-table">
        <div class="table-header"><h2><span class="decade-label" style="visibility:hidden">&nbsp;</span></h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
"""


def render_goat_html(season_stats, stat_key='ted', season_all=None):
    """Generate HTML for the GOAT table — #1 player by season.

    season_stats: dict from historical_rankings.json['season_stats'],
                  keyed by year string, each with ldr_ted/ldr_tap/top10_ted/etc.
    season_all:   current season results to merge (adds current year).
    """
    stat_upper = stat_key.upper()
    current_year = config.CURRENT_SEASON_YEAR

    # Copy and merge current season if needed
    stats = dict(season_stats) if season_stats else {}
    if season_all and str(current_year) not in stats:
        ted_sorted = sorted(season_all, key=lambda r: r['ted'], reverse=True)
        tap_sorted = sorted(season_all, key=lambda r: r['tap'], reverse=True)
        top10_teds = [r['ted'] for r in ted_sorted[:10]]
        top10_taps = [r['tap'] for r in tap_sorted[:10]]
        ted_leader = ted_sorted[0]
        tap_leader = tap_sorted[0]
        ted_second = ted_sorted[1] if len(ted_sorted) > 1 else None
        tap_second = tap_sorted[1] if len(tap_sorted) > 1 else None
        ted_third = ted_sorted[2] if len(ted_sorted) > 2 else None
        tap_third = tap_sorted[2] if len(tap_sorted) > 2 else None
        stats[str(current_year)] = {
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

    # Sort years descending, exclude pre-1960 (small player pools skew DIFF)
    years_sorted = sorted(
        [y for y in stats.keys() if int(y) >= 1960],
        key=lambda y: int(y), reverse=True)

    rows = ''
    for yr_str in years_sorted:
        s = stats[yr_str]
        yr = int(yr_str)
        season_label = f"'{str(yr + 1)[-2:]}"
        # For TAPD: fall back to TAP if TAPD leader data not available for this year
        eff_key = stat_key
        if stat_key == 'tapd' and f'ldr_tapd' not in s:
            eff_key = 'tap'
        player_name = s.get(f'ldr_{eff_key}', '')
        val = s.get(f'ldr_{eff_key}_val', 0)
        top10 = s.get(f'top10_{eff_key}', 0)
        # GOAT table uses "top 9" avg: standard top 10 minus the #1 player,
        # divided by 9. This isolates how far above the field the leader is,
        # without the leader inflating the comparison baseline.
        top9 = round((top10 * 10 - val) / 9, 1) if top10 else 0
        diff = round(val - top9, 1)
        diff_str = f'+{diff:.1f}' if diff >= 0 else f'{diff:.1f}'

        name_html = format_player_name(player_name)
        player_attr = html_module.escape(player_name, quote=True)
        rows += (f'        <tr>'
                 f'<td class="season">{season_label}</td>'
                 f'<td class="player" data-player="{player_attr}">{name_html}</td>'
                 f'<td class="num stat">{val:.1f}</td>'
                 f'<td class="num goat-avg">{round(top9)}</td>'
                 f'<td class="num">{diff_str}</td>'
                 f'</tr>\n')

    return f"""    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>TOP {stat_upper} BY SEASON</h2></div>
        <table>
          <thead><tr><th class="season goat-sort-yr">Yr</th><th class="player goat-sort-player">Player</th><th class="num stat goat-sort-val">{stat_upper}</th><th class="num goat-avg">TOP 9*</th><th class="num goat-sort-diff">DIFF</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
      </div>
      <div class="year-table">
        <div class="table-header"><h2>&nbsp;</h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
"""


def render_g2_html(season_stats, stat_key='ted', season_all=None):
    """Generate HTML for the G2 table — top 2 players by season.

    Same structure as GOAT but with two rows per year (#1 and #2).
    season_stats: dict from historical_rankings.json['season_stats'],
                  keyed by year string, each with ldr/g2 fields.
    season_all:   current season results to merge (adds current year).
    """
    stat_upper = stat_key.upper()
    current_year = config.CURRENT_SEASON_YEAR

    # Copy and merge current season if needed
    stats = dict(season_stats) if season_stats else {}
    if season_all and str(current_year) not in stats:
        ted_sorted = sorted(season_all, key=lambda r: r['ted'], reverse=True)
        tap_sorted = sorted(season_all, key=lambda r: r['tap'], reverse=True)
        top10_teds = [r['ted'] for r in ted_sorted[:10]]
        top10_taps = [r['tap'] for r in tap_sorted[:10]]
        ted_leader = ted_sorted[0]
        tap_leader = tap_sorted[0]
        ted_second = ted_sorted[1] if len(ted_sorted) > 1 else None
        tap_second = tap_sorted[1] if len(tap_sorted) > 1 else None
        ted_third = ted_sorted[2] if len(ted_sorted) > 2 else None
        tap_third = tap_sorted[2] if len(tap_sorted) > 2 else None
        stats[str(current_year)] = {
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

    # Sort years descending, exclude pre-1960 (small player pools skew DIFF)
    years_sorted = sorted(
        [y for y in stats.keys() if int(y) >= 1960],
        key=lambda y: int(y), reverse=True)

    rows = ''
    for yr_str in years_sorted:
        s = stats[yr_str]
        yr = int(yr_str)
        season_label = f"'{str(yr + 1)[-2:]}"
        # For TAPD: fall back to TAP if TAPD data not available for this year
        eff_key = stat_key
        if stat_key == 'tapd' and f'ldr_tapd' not in s:
            eff_key = 'tap'
        # #1 player
        player1 = s.get(f'ldr_{eff_key}', '')
        val1 = s.get(f'ldr_{eff_key}_val', 0)
        # #2 player
        player2 = s.get(f'g2_{eff_key}', '')
        val2 = s.get(f'g2_{eff_key}_val', 0)
        top10 = s.get(f'top10_{eff_key}', 0)
        # TOP 9* = (top10 * 10 - #1 value) / 9 — same as GOAT
        top9 = round((top10 * 10 - val1) / 9, 1) if top10 else 0
        diff1 = round(val1 - top9, 1)
        diff1_str = f'+{diff1:.1f}' if diff1 >= 0 else f'{diff1:.1f}'
        diff2 = round(val2 - top9, 1) if val2 else 0
        diff2_str = f'+{diff2:.1f}' if diff2 >= 0 else f'{diff2:.1f}'

        name1_html = format_player_name(player1)
        player1_attr = html_module.escape(player1, quote=True)
        rows += (f'        <tr data-rank="1">'
                 f'<td class="season">{season_label}</td>'
                 f'<td class="player" data-player="{player1_attr}">{name1_html}</td>'
                 f'<td class="num stat">{val1:.1f}</td>'
                 f'<td class="num g2-avg">{round(top9)}</td>'
                 f'<td class="num">{diff1_str}</td>'
                 f'</tr>\n')
        if player2:
            name2_html = format_player_name(player2)
            player2_attr = html_module.escape(player2, quote=True)
            rows += (f'        <tr data-rank="2">'
                     f'<td class="season">{season_label}</td>'
                     f'<td class="player" data-player="{player2_attr}">{name2_html}</td>'
                     f'<td class="num stat">{val2:.1f}</td>'
                     f'<td class="num g2-avg">{round(top9)}</td>'
                     f'<td class="num">{diff2_str}</td>'
                     f'</tr>\n')

    return f"""    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>TOP 2 {stat_upper} BY SEASON</h2></div>
        <table>
          <thead><tr><th class="season g2-sort-yr">Yr</th><th class="player g2-sort-player">Player</th><th class="num stat g2-sort-val">{stat_upper}</th><th class="num g2-avg">TOP 9*</th><th class="num g2-sort-diff">DIFF</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
      </div>
      <div class="year-table">
        <div class="table-header"><h2>&nbsp;</h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
"""


def render_g3_html(season_stats, stat_key='ted', season_all=None):
    """Generate HTML for the G3 table — top 3 players by season.

    Same structure as G2 but with three rows per year (#1, #2, #3).
    """
    stat_upper = stat_key.upper()
    current_year = config.CURRENT_SEASON_YEAR

    # Copy and merge current season if needed
    stats = dict(season_stats) if season_stats else {}
    if season_all and str(current_year) not in stats:
        ted_sorted = sorted(season_all, key=lambda r: r['ted'], reverse=True)
        tap_sorted = sorted(season_all, key=lambda r: r['tap'], reverse=True)
        top10_teds = [r['ted'] for r in ted_sorted[:10]]
        top10_taps = [r['tap'] for r in tap_sorted[:10]]
        ted_leader = ted_sorted[0]
        tap_leader = tap_sorted[0]
        ted_second = ted_sorted[1] if len(ted_sorted) > 1 else None
        tap_second = tap_sorted[1] if len(tap_sorted) > 1 else None
        ted_third = ted_sorted[2] if len(ted_sorted) > 2 else None
        tap_third = tap_sorted[2] if len(tap_sorted) > 2 else None
        stats[str(current_year)] = {
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

    # Sort years descending, exclude pre-1960 (small player pools skew DIFF)
    years_sorted = sorted(
        [y for y in stats.keys() if int(y) >= 1960],
        key=lambda y: int(y), reverse=True)

    rows = ''
    for yr_str in years_sorted:
        s = stats[yr_str]
        yr = int(yr_str)
        season_label = f"'{str(yr + 1)[-2:]}"
        # For TAPD: fall back to TAP if TAPD data not available for this year
        eff_key = stat_key
        if stat_key == 'tapd' and f'ldr_tapd' not in s:
            eff_key = 'tap'
        # #1 player
        player1 = s.get(f'ldr_{eff_key}', '')
        val1 = s.get(f'ldr_{eff_key}_val', 0)
        # #2 player
        player2 = s.get(f'g2_{eff_key}', '')
        val2 = s.get(f'g2_{eff_key}_val', 0)
        # #3 player
        player3 = s.get(f'g3_{eff_key}', '')
        val3 = s.get(f'g3_{eff_key}_val', 0)
        top10 = s.get(f'top10_{eff_key}', 0)
        # TOP 9* = (top10 * 10 - #1 value) / 9 — same as GOAT
        top9 = round((top10 * 10 - val1) / 9, 1) if top10 else 0
        diff1 = round(val1 - top9, 1)
        diff1_str = f'+{diff1:.1f}' if diff1 >= 0 else f'{diff1:.1f}'
        diff2 = round(val2 - top9, 1) if val2 else 0
        diff2_str = f'+{diff2:.1f}' if diff2 >= 0 else f'{diff2:.1f}'
        diff3 = round(val3 - top9, 1) if val3 else 0
        diff3_str = f'+{diff3:.1f}' if diff3 >= 0 else f'{diff3:.1f}'

        name1_html = format_player_name(player1)
        player1_attr = html_module.escape(player1, quote=True)
        rows += (f'        <tr data-rank="1">'
                 f'<td class="season">{season_label}</td>'
                 f'<td class="player" data-player="{player1_attr}">{name1_html}</td>'
                 f'<td class="num stat">{val1:.1f}</td>'
                 f'<td class="num g3-avg">{round(top9)}</td>'
                 f'<td class="num">{diff1_str}</td>'
                 f'</tr>\n')
        if player2:
            name2_html = format_player_name(player2)
            player2_attr = html_module.escape(player2, quote=True)
            rows += (f'        <tr data-rank="2">'
                     f'<td class="season">{season_label}</td>'
                     f'<td class="player" data-player="{player2_attr}">{name2_html}</td>'
                     f'<td class="num stat">{val2:.1f}</td>'
                     f'<td class="num g3-avg">{round(top9)}</td>'
                     f'<td class="num">{diff2_str}</td>'
                     f'</tr>\n')
        if player3:
            name3_html = format_player_name(player3)
            player3_attr = html_module.escape(player3, quote=True)
            rows += (f'        <tr data-rank="3">'
                     f'<td class="season">{season_label}</td>'
                     f'<td class="player" data-player="{player3_attr}">{name3_html}</td>'
                     f'<td class="num stat">{val3:.1f}</td>'
                     f'<td class="num g3-avg">{round(top9)}</td>'
                     f'<td class="num">{diff3_str}</td>'
                     f'</tr>\n')

    return f"""    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>TOP 3 {stat_upper} BY SEASON</h2></div>
        <table>
          <thead><tr><th class="season g3-sort-yr">Yr</th><th class="player g3-sort-player">Player</th><th class="num stat g3-sort-val">{stat_upper}</th><th class="num g3-avg">TOP 9*</th><th class="num g3-sort-diff">DIFF</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
      </div>
      <div class="year-table">
        <div class="table-header"><h2>&nbsp;</h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
"""


def render_mg1_html(season_stats, season_all=None):
    """Generate HTML for the MG GOAT table — #1 TAPD player by season (1996+ only).

    Always uses stat_key='tapd' internally. Falls back to TAP when TAPD
    data is not available for a given year.
    """
    stat_upper = 'TAPD'
    current_year = config.CURRENT_SEASON_YEAR

    # Copy and merge current season if needed
    stats = dict(season_stats) if season_stats else {}
    if season_all and str(current_year) not in stats:
        tapd_players = [r for r in season_all if r.get('tapd') is not None]
        if tapd_players:
            tapd_sorted = sorted(tapd_players, key=lambda r: r['tapd'], reverse=True)
            top10_tapds = [r['tapd'] for r in tapd_sorted[:10]]
            tapd_leader = tapd_sorted[0]
            tapd_second = tapd_sorted[1] if len(tapd_sorted) > 1 else None
            tapd_third = tapd_sorted[2] if len(tapd_sorted) > 2 else None
            stats[str(current_year)] = {
                'top10_tapd': round(sum(top10_tapds) / len(top10_tapds), 1),
                'ldr_tapd': tapd_leader['player'], 'ldr_tapd_val': round(tapd_leader['tapd'], 1),
                'g2_tapd': tapd_second['player'] if tapd_second else '',
                'g2_tapd_val': round(tapd_second['tapd'], 1) if tapd_second else 0,
                'g3_tapd': tapd_third['player'] if tapd_third else '',
                'g3_tapd_val': round(tapd_third['tapd'], 1) if tapd_third else 0,
            }
    # Also ensure existing current year entry gets TAPD fields if missing
    if season_all and str(current_year) in stats and 'ldr_tapd' not in stats[str(current_year)]:
        tapd_players = [r for r in season_all if r.get('tapd') is not None]
        if tapd_players:
            tapd_sorted = sorted(tapd_players, key=lambda r: r['tapd'], reverse=True)
            top10_tapds = [r['tapd'] for r in tapd_sorted[:10]]
            tapd_leader = tapd_sorted[0]
            tapd_second = tapd_sorted[1] if len(tapd_sorted) > 1 else None
            tapd_third = tapd_sorted[2] if len(tapd_sorted) > 2 else None
            stats[str(current_year)].update({
                'top10_tapd': round(sum(top10_tapds) / len(top10_tapds), 1),
                'ldr_tapd': tapd_leader['player'], 'ldr_tapd_val': round(tapd_leader['tapd'], 1),
                'g2_tapd': tapd_second['player'] if tapd_second else '',
                'g2_tapd_val': round(tapd_second['tapd'], 1) if tapd_second else 0,
                'g3_tapd': tapd_third['player'] if tapd_third else '',
                'g3_tapd_val': round(tapd_third['tapd'], 1) if tapd_third else 0,
            })

    # Sort years descending, only 1996+ (PM data available from 1996-97)
    years_sorted = sorted(
        [y for y in stats.keys() if int(y) >= 1996],
        key=lambda y: int(y), reverse=True)

    rows = ''
    for yr_str in years_sorted:
        s = stats[yr_str]
        yr = int(yr_str)
        season_label = f"'{str(yr + 1)[-2:]}"
        # Fall back to TAP if TAPD leader data not available
        if 'ldr_tapd' in s:
            player_name = s.get('ldr_tapd', '')
            val = s.get('ldr_tapd_val', 0)
            top10 = s.get('top10_tapd', 0)
        else:
            player_name = s.get('ldr_tap', '')
            val = s.get('ldr_tap_val', 0)
            top10 = s.get('top10_tap', 0)
        top9 = round((top10 * 10 - val) / 9, 1) if top10 else 0
        diff = round(val - top9, 1)
        diff_str = f'+{diff:.1f}' if diff >= 0 else f'{diff:.1f}'

        name_html = format_player_name(player_name)
        player_attr = html_module.escape(player_name, quote=True)
        rows += (f'        <tr>'
                 f'<td class="season">{season_label}</td>'
                 f'<td class="player" data-player="{player_attr}">{name_html}</td>'
                 f'<td class="num stat">{val:.1f}</td>'
                 f'<td class="num mg1-avg">{round(top9)}</td>'
                 f'<td class="num">{diff_str}</td>'
                 f'</tr>\n')

    return f"""  <div class="mg-goat-view">
    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>MODERN ERA TOP {stat_upper} BY SEASON</h2></div>
        <table>
          <thead><tr><th class="season mg1-sort-yr">Yr</th><th class="player mg1-sort-player">Player</th><th class="num stat mg1-sort-val">{stat_upper}</th><th class="num mg1-avg">TOP 9*</th><th class="num mg1-sort-diff">DIFF</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
      </div>
      <div class="year-table">
        <div class="table-header"><h2>&nbsp;</h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
  </div>
"""


def render_mg2_html(season_stats, season_all=None):
    """Generate HTML for the MG G2 table — top 2 TAPD players by season (1996+ only)."""
    stat_upper = 'TAPD'
    current_year = config.CURRENT_SEASON_YEAR

    # Copy and merge current season if needed
    stats = dict(season_stats) if season_stats else {}
    if season_all and str(current_year) not in stats:
        tapd_players = [r for r in season_all if r.get('tapd') is not None]
        if tapd_players:
            tapd_sorted = sorted(tapd_players, key=lambda r: r['tapd'], reverse=True)
            top10_tapds = [r['tapd'] for r in tapd_sorted[:10]]
            tapd_leader = tapd_sorted[0]
            tapd_second = tapd_sorted[1] if len(tapd_sorted) > 1 else None
            tapd_third = tapd_sorted[2] if len(tapd_sorted) > 2 else None
            stats[str(current_year)] = {
                'top10_tapd': round(sum(top10_tapds) / len(top10_tapds), 1),
                'ldr_tapd': tapd_leader['player'], 'ldr_tapd_val': round(tapd_leader['tapd'], 1),
                'g2_tapd': tapd_second['player'] if tapd_second else '',
                'g2_tapd_val': round(tapd_second['tapd'], 1) if tapd_second else 0,
                'g3_tapd': tapd_third['player'] if tapd_third else '',
                'g3_tapd_val': round(tapd_third['tapd'], 1) if tapd_third else 0,
            }
    if season_all and str(current_year) in stats and 'ldr_tapd' not in stats[str(current_year)]:
        tapd_players = [r for r in season_all if r.get('tapd') is not None]
        if tapd_players:
            tapd_sorted = sorted(tapd_players, key=lambda r: r['tapd'], reverse=True)
            top10_tapds = [r['tapd'] for r in tapd_sorted[:10]]
            tapd_leader = tapd_sorted[0]
            tapd_second = tapd_sorted[1] if len(tapd_sorted) > 1 else None
            tapd_third = tapd_sorted[2] if len(tapd_sorted) > 2 else None
            stats[str(current_year)].update({
                'top10_tapd': round(sum(top10_tapds) / len(top10_tapds), 1),
                'ldr_tapd': tapd_leader['player'], 'ldr_tapd_val': round(tapd_leader['tapd'], 1),
                'g2_tapd': tapd_second['player'] if tapd_second else '',
                'g2_tapd_val': round(tapd_second['tapd'], 1) if tapd_second else 0,
                'g3_tapd': tapd_third['player'] if tapd_third else '',
                'g3_tapd_val': round(tapd_third['tapd'], 1) if tapd_third else 0,
            })

    years_sorted = sorted(
        [y for y in stats.keys() if int(y) >= 1996],
        key=lambda y: int(y), reverse=True)

    rows = ''
    for yr_str in years_sorted:
        s = stats[yr_str]
        yr = int(yr_str)
        season_label = f"'{str(yr + 1)[-2:]}"
        if 'ldr_tapd' in s:
            player1 = s.get('ldr_tapd', '')
            val1 = s.get('ldr_tapd_val', 0)
            player2 = s.get('g2_tapd', '')
            val2 = s.get('g2_tapd_val', 0)
            top10 = s.get('top10_tapd', 0)
        else:
            player1 = s.get('ldr_tap', '')
            val1 = s.get('ldr_tap_val', 0)
            player2 = s.get('g2_tap', '')
            val2 = s.get('g2_tap_val', 0)
            top10 = s.get('top10_tap', 0)
        top9 = round((top10 * 10 - val1) / 9, 1) if top10 else 0
        diff1 = round(val1 - top9, 1)
        diff1_str = f'+{diff1:.1f}' if diff1 >= 0 else f'{diff1:.1f}'
        diff2 = round(val2 - top9, 1) if val2 else 0
        diff2_str = f'+{diff2:.1f}' if diff2 >= 0 else f'{diff2:.1f}'

        name1_html = format_player_name(player1)
        player1_attr = html_module.escape(player1, quote=True)
        rows += (f'        <tr data-rank="1">'
                 f'<td class="season">{season_label}</td>'
                 f'<td class="player" data-player="{player1_attr}">{name1_html}</td>'
                 f'<td class="num stat">{val1:.1f}</td>'
                 f'<td class="num mg2-avg">{round(top9)}</td>'
                 f'<td class="num">{diff1_str}</td>'
                 f'</tr>\n')
        if player2:
            name2_html = format_player_name(player2)
            player2_attr = html_module.escape(player2, quote=True)
            rows += (f'        <tr data-rank="2">'
                     f'<td class="season">{season_label}</td>'
                     f'<td class="player" data-player="{player2_attr}">{name2_html}</td>'
                     f'<td class="num stat">{val2:.1f}</td>'
                     f'<td class="num mg2-avg">{round(top9)}</td>'
                     f'<td class="num">{diff2_str}</td>'
                     f'</tr>\n')

    return f"""  <div class="mg-g2-view" style="display:none">
    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>MODERN TOP 2 {stat_upper} BY SEASON</h2></div>
        <table>
          <thead><tr><th class="season mg2-sort-yr">Yr</th><th class="player mg2-sort-player">Player</th><th class="num stat mg2-sort-val">{stat_upper}</th><th class="num mg2-avg">TOP 9*</th><th class="num mg2-sort-diff">DIFF</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
      </div>
      <div class="year-table">
        <div class="table-header"><h2>&nbsp;</h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
  </div>
"""


def render_mg3_html(season_stats, season_all=None):
    """Generate HTML for the MG G3 table — top 3 TAPD players by season (1996+ only)."""
    stat_upper = 'TAPD'
    current_year = config.CURRENT_SEASON_YEAR

    # Copy and merge current season if needed
    stats = dict(season_stats) if season_stats else {}
    if season_all and str(current_year) not in stats:
        tapd_players = [r for r in season_all if r.get('tapd') is not None]
        if tapd_players:
            tapd_sorted = sorted(tapd_players, key=lambda r: r['tapd'], reverse=True)
            top10_tapds = [r['tapd'] for r in tapd_sorted[:10]]
            tapd_leader = tapd_sorted[0]
            tapd_second = tapd_sorted[1] if len(tapd_sorted) > 1 else None
            tapd_third = tapd_sorted[2] if len(tapd_sorted) > 2 else None
            stats[str(current_year)] = {
                'top10_tapd': round(sum(top10_tapds) / len(top10_tapds), 1),
                'ldr_tapd': tapd_leader['player'], 'ldr_tapd_val': round(tapd_leader['tapd'], 1),
                'g2_tapd': tapd_second['player'] if tapd_second else '',
                'g2_tapd_val': round(tapd_second['tapd'], 1) if tapd_second else 0,
                'g3_tapd': tapd_third['player'] if tapd_third else '',
                'g3_tapd_val': round(tapd_third['tapd'], 1) if tapd_third else 0,
            }
    if season_all and str(current_year) in stats and 'ldr_tapd' not in stats[str(current_year)]:
        tapd_players = [r for r in season_all if r.get('tapd') is not None]
        if tapd_players:
            tapd_sorted = sorted(tapd_players, key=lambda r: r['tapd'], reverse=True)
            top10_tapds = [r['tapd'] for r in tapd_sorted[:10]]
            tapd_leader = tapd_sorted[0]
            tapd_second = tapd_sorted[1] if len(tapd_sorted) > 1 else None
            tapd_third = tapd_sorted[2] if len(tapd_sorted) > 2 else None
            stats[str(current_year)].update({
                'top10_tapd': round(sum(top10_tapds) / len(top10_tapds), 1),
                'ldr_tapd': tapd_leader['player'], 'ldr_tapd_val': round(tapd_leader['tapd'], 1),
                'g2_tapd': tapd_second['player'] if tapd_second else '',
                'g2_tapd_val': round(tapd_second['tapd'], 1) if tapd_second else 0,
                'g3_tapd': tapd_third['player'] if tapd_third else '',
                'g3_tapd_val': round(tapd_third['tapd'], 1) if tapd_third else 0,
            })

    years_sorted = sorted(
        [y for y in stats.keys() if int(y) >= 1996],
        key=lambda y: int(y), reverse=True)

    rows = ''
    for yr_str in years_sorted:
        s = stats[yr_str]
        yr = int(yr_str)
        season_label = f"'{str(yr + 1)[-2:]}"
        if 'ldr_tapd' in s:
            player1 = s.get('ldr_tapd', '')
            val1 = s.get('ldr_tapd_val', 0)
            player2 = s.get('g2_tapd', '')
            val2 = s.get('g2_tapd_val', 0)
            player3 = s.get('g3_tapd', '')
            val3 = s.get('g3_tapd_val', 0)
            top10 = s.get('top10_tapd', 0)
        else:
            player1 = s.get('ldr_tap', '')
            val1 = s.get('ldr_tap_val', 0)
            player2 = s.get('g2_tap', '')
            val2 = s.get('g2_tap_val', 0)
            player3 = s.get('g3_tap', '')
            val3 = s.get('g3_tap_val', 0)
            top10 = s.get('top10_tap', 0)
        top9 = round((top10 * 10 - val1) / 9, 1) if top10 else 0
        diff1 = round(val1 - top9, 1)
        diff1_str = f'+{diff1:.1f}' if diff1 >= 0 else f'{diff1:.1f}'
        diff2 = round(val2 - top9, 1) if val2 else 0
        diff2_str = f'+{diff2:.1f}' if diff2 >= 0 else f'{diff2:.1f}'
        diff3 = round(val3 - top9, 1) if val3 else 0
        diff3_str = f'+{diff3:.1f}' if diff3 >= 0 else f'{diff3:.1f}'

        name1_html = format_player_name(player1)
        player1_attr = html_module.escape(player1, quote=True)
        rows += (f'        <tr data-rank="1">'
                 f'<td class="season">{season_label}</td>'
                 f'<td class="player" data-player="{player1_attr}">{name1_html}</td>'
                 f'<td class="num stat">{val1:.1f}</td>'
                 f'<td class="num mg3-avg">{round(top9)}</td>'
                 f'<td class="num">{diff1_str}</td>'
                 f'</tr>\n')
        if player2:
            name2_html = format_player_name(player2)
            player2_attr = html_module.escape(player2, quote=True)
            rows += (f'        <tr data-rank="2">'
                     f'<td class="season">{season_label}</td>'
                     f'<td class="player" data-player="{player2_attr}">{name2_html}</td>'
                     f'<td class="num stat">{val2:.1f}</td>'
                     f'<td class="num mg3-avg">{round(top9)}</td>'
                     f'<td class="num">{diff2_str}</td>'
                     f'</tr>\n')
        if player3:
            name3_html = format_player_name(player3)
            player3_attr = html_module.escape(player3, quote=True)
            rows += (f'        <tr data-rank="3">'
                     f'<td class="season">{season_label}</td>'
                     f'<td class="player" data-player="{player3_attr}">{name3_html}</td>'
                     f'<td class="num stat">{val3:.1f}</td>'
                     f'<td class="num mg3-avg">{round(top9)}</td>'
                     f'<td class="num">{diff3_str}</td>'
                     f'</tr>\n')

    return f"""  <div class="mg-g3-view" style="display:none">
    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>MODERN TOP 3 {stat_upper} BY SEASON</h2></div>
        <table>
          <thead><tr><th class="season mg3-sort-yr">Yr</th><th class="player mg3-sort-player">Player</th><th class="num stat mg3-sort-val">{stat_upper}</th><th class="num mg3-avg">TOP 9*</th><th class="num mg3-sort-diff">DIFF</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
      </div>
      <div class="year-table">
        <div class="table-header"><h2>&nbsp;</h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
  </div>
"""


def render_diff_html(diff_data_ted, diff_data_tap):
    """Generate HTML for the DIFF table — career averages and DIFF vs top 100.

    Two table sets (view-ted/view-tap), each with Rank, Player, aTED/aTAP, aDIFF, tDIFF.
    """
    def build_rows(data, stat_key):
        rows = ''
        val_col = 'ated' if stat_key == 'ted' else 'atap'
        data = sorted(data, key=lambda x: x[val_col], reverse=True)[:400]
        data = sorted(data, key=lambda x: x['adiff'], reverse=True)[:200]
        data.sort(key=lambda x: x[val_col], reverse=True)
        for i, p in enumerate(data, 1):
            name_html = format_player_name(p['player'])
            player_attr = html_module.escape(p['player'], quote=True)
            val = p[val_col]
            adiff = p['adiff']
            tdiff = p['tdiff']
            adiff_str = f'+{abs(adiff):.1f}' if adiff >= 0 else f'-{abs(adiff):.1f}'
            tdiff_str = f'+{abs(tdiff):.0f}' if tdiff >= 0 else f'-{abs(tdiff):.0f}'
            rows += (f'        <tr>'
                     f'<td class="rank">{i}</td>'
                     f'<td class="player" data-player="{player_attr}">{name_html}</td>'
                     f'<td class="num diff-val">{val:.1f}</td>'
                     f'<td class="num diff-adiff">{adiff_str}</td>'
                     f'<td class="num diff-tdiff">{tdiff_str}</td>'
                     f'</tr>\n')
        return rows

    stat_labels = {'ted': 'aTED', 'tap': 'aTAP'}
    results = {}
    for stat_key, data in [('ted', diff_data_ted), ('tap', diff_data_tap)]:
        label = stat_labels[stat_key]
        rows = build_rows(data, stat_key)
        results[stat_key] = f"""    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>CAREER AVG / TOTAL {stat_key.upper()} DIFF</h2></div>
        <table>
          <thead><tr><th class="rank diff-sort-rank">Rank</th><th class="player diff-sort-player">Player</th><th class="num diff-sort-val">{label}</th><th class="num diff-sort-adiff">aDIFF</th><th class="num diff-sort-tdiff">tDIFF</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
      </div>
      <div class="year-table">
        <div class="table-header"><h2>&nbsp;</h2></div>
        <table style="visibility:hidden"><thead><tr><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th><th>&nbsp;</th></tr></thead></table>
      </div>
    </div>
"""
    return results


def build_career_js(historical, season_all):
    """Build JS career data from historical JSON + current season results.

    Returns a <script> tag string with window.CAREER and window.SEASON_STATS.
    """
    career = {}
    season_stats = {}

    if historical:
        career = historical.get('career_data', {})
        season_stats = historical.get('season_stats', {})

    # Merge current-season players into career data
    current_year = config.CURRENT_SEASON_YEAR
    qualifying_names = set()
    if season_all:
        for r in season_all:
            name = r['player']
            qualifying_names.add(name)
            entry = {'y': current_year, 'tm': r['team'], 'ted': round(r['ted'], 1), 'tap': round(r['tap'], 1)}
            if r.get('tapd') is not None:
                entry['tapd'] = round(r['tapd'], 1)
            if name not in career:
                career[name] = []
            # Avoid duplicate if already present for this year
            if not any(s['y'] == current_year for s in career[name]):
                career[name].append(entry)
                career[name].sort(key=lambda x: x['y'])

    # Add non-qualifying current-season players as dash rows
    # (active this season but haven't met G/MP thresholds)
    all_season_players = db.get_season_averages(current_year)
    for row in all_season_players:
        name = row['player']
        if name in qualifying_names:
            continue
        if name not in career:
            continue  # only add dash rows for players with existing career data
        if not any(s['y'] == current_year for s in career[name]):
            team = row['team'] if 'team' in row.keys() else ''
            career[name].append({
                'y': current_year, 'tm': team,
                'ted': None, 'tap': None
            })
            career[name].sort(key=lambda x: x['y'])

        # Add current season to season_stats
        ted_sorted = sorted(season_all, key=lambda r: r['ted'], reverse=True)
        tap_sorted = sorted(season_all, key=lambda r: r['tap'], reverse=True)
        top10_teds = [r['ted'] for r in ted_sorted[:10]]
        top10_taps = [r['tap'] for r in tap_sorted[:10]]
        ted_leader = ted_sorted[0]
        tap_leader = tap_sorted[0]
        ted_second = ted_sorted[1] if len(ted_sorted) > 1 else None
        tap_second = tap_sorted[1] if len(tap_sorted) > 1 else None
        ted_third = ted_sorted[2] if len(ted_sorted) > 2 else None
        tap_third = tap_sorted[2] if len(tap_sorted) > 2 else None
        all_teds = [r['ted'] for r in season_all]
        all_taps = [r['tap'] for r in season_all]
        season_stats[str(current_year)] = {
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

    career_json = json.dumps(career, ensure_ascii=False, separators=(',', ':'))
    stats_json = json.dumps(season_stats, ensure_ascii=False, separators=(',', ':'))
    return f'<script>window.CAREER={career_json};window.SEASON_STATS={stats_json};</script>'


def generate_html(weekly, season, daily, monthly, month_label, month_winners, updated_at):
    """Generate the full HTML page — TED only."""
    season_label = f"{config.CURRENT_SEASON_YEAR}-{str(config.CURRENT_SEASON_YEAR + 1)[-2:]}"

    weekly_ted_table = render_table(weekly['ted'], 'ted', 'WEEKLY TED TOP 100')
    season_ted_table = render_table(season['ted'], 'ted', 'SEASON-TO-DATE TED TOP 100')
    weekly_tap_table = render_table(weekly['tap'], 'tap', 'WEEKLY TAP TOP 100')
    season_tap_table = render_table(season['tap'], 'tap', 'SEASON-TO-DATE TAP TOP 100')
    season_tapd_table = render_table(season.get('tapd', []), 'tapd', 'SEASON-TO-DATE TAPD TOP 100')
    daily_ted_table = render_table(daily['ted'], 'ted', 'DAILY TED TOP 40')
    daily_tap_table = render_table(daily['tap'], 'tap', 'DAILY TAP TOP 40')
    monthly_ted_table = render_table(monthly['ted'], 'ted', 'PLAYER OF THE MONTH - TED')
    monthly_tap_table = render_table(monthly['tap'], 'tap', 'PLAYER OF THE MONTH - TAP')

    # Build career popup data
    career_js = build_career_js(
        load_historical_rankings(),
        season.get('all', [])
    )

    # Embed month winners for POTM popup
    month_winners_json = json.dumps(month_winners, ensure_ascii=False, separators=(',', ':'))
    potm_js = f'<script>window.MONTH_WINNERS={month_winners_json};</script>'

    historical = load_historical_rankings()
    season_all = season.get('all', [])
    if historical:
        decade_nav_links, historical_ted_html = render_historical_section(historical, 'ted', season_all)
        _, historical_tap_html = render_historical_section(historical, 'tap', season_all)
        decade_nav_html = ''  # now embedded inside historical sections
        historical_html = f"""<div class="view-ted" style="display:none">
{historical_ted_html}</div>
<div class="view-tap">
{historical_tap_html}
</div>"""
    else:
        decade_nav_html = ''
        historical_html = ''

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NBA TAP Rankings &mdash; {season_label} Season</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      font-family: 'Courier New', Courier, monospace;
      font-weight: 700;
      background: #000;
      color: #fff;
      line-height: 1.4;
      padding: 20px;
    }}

    .container {{
      max-width: 880px;
      margin: 0 auto;
      border: 3px solid #fff;
      padding: 0;
      overflow: visible;
    }}

    header {{
      text-align: center;
      padding: 25px 20px 15px;
      background: #fff;
      color: #000;
    }}

    header h1 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 3em;
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      margin-bottom: 2px;
    }}

    .basketball {{
      display: block;
      margin: 8px auto 0;
      cursor: pointer;
    }}

    .toggle-link {{
      display: block;
      text-align: center;
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 0.75em;
      color: #ee7623;
      cursor: pointer;
      margin-top: 2px;
      letter-spacing: 0.03em;
    }}
    .toggle-link:hover {{
      text-decoration: underline;
    }}

    .float-toggle {{
      position: fixed;
      bottom: 20px;
      right: 20px;
      z-index: 100;
      cursor: pointer;
      user-select: none;
      -webkit-tap-highlight-color: transparent;
      width: 40px;
      height: 40px;
    }}
    .float-toggle svg {{
      width: 40px;
      height: 40px;
    }}

    .season-header {{
      background: #000;
      padding: 10px 16px;
      text-align: center;
      cursor: pointer;
    }}

    .season-header h3 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1.1em;
      font-weight: 900;
      letter-spacing: 0.1em;
      color: #ee7623;
      margin: 0;
    }}

    .season-click-hint {{
      font-size: 0.68em;
      font-weight: 400;
      letter-spacing: 0.03em;
    }}

    .season-hint {{
      background: #000;
      text-align: center;
      padding: 0 16px;
      max-height: 0;
      overflow: hidden;
      transition: max-height 0.3s ease, padding 0.3s ease;
      cursor: pointer;
    }}

    .season-hint.open {{
      max-height: 110px;
      padding: 10px 16px 10px;
    }}

    .season-hint p {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 0.85em;
      font-style: italic;
      color: #ee7623;
      margin: 0;
    }}

    .description {{
      display: grid;
      justify-items: center;
      padding: 16px 24px;
      border-bottom: 2px solid #fff;
    }}

    .stat-desc {{
      max-width: 620px;
      grid-row: 1;
      grid-column: 1;
    }}

    .stat-desc.desc-hidden {{
      visibility: hidden;
    }}

    .stat-desc h3 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1em;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 4px;
      color: #fff;
      text-align: center;
    }}

    .stat-desc p {{
      font-size: 0.85em;
      color: #fff;
      line-height: 1.5;
      text-align: justify;
    }}

    .tables-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      margin-bottom: 0;
    }}

    .tables-grid > :first-child {{
      border-right: 2px solid #fff;
    }}

    .table-section {{
      overflow: visible;
    }}

    .table-header {{
      background: #fff;
      border: 2px solid #000;
      padding: 10px 12px;
      text-align: center;
      position: -webkit-sticky;
      position: sticky;
      top: 0;
      z-index: 20;
      -webkit-transform: translateZ(0);
      transform: translateZ(0);
    }}

    .weekly-daily-slot .table-header {{
      cursor: pointer;
    }}

    .weekly-daily-slot .table-header:hover {{
      background: #eee;
    }}

    .table-section h2 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1em;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: #000;
      text-align: center;
      margin: 0;
      padding: 0;
      border: none;
      background: none;
      display: inline;
    }}

    .weekly-daily-slot .table-section h2 {{
      color: #ee7623;
    }}

    .season-monthly-slot .season-table .table-header,
    .season-monthly-slot .monthly-table .table-header {{
      cursor: pointer;
    }}

    .season-monthly-slot .season-table .table-header:hover,
    .season-monthly-slot .monthly-table .table-header:hover {{
      background: #eee;
    }}

    .season-monthly-slot .season-table .table-section h2,
    .season-monthly-slot .monthly-table .table-section h2 {{
      color: #ee7623;
    }}

    .monthly-table th.rank {{
      color: #ee7623;
      cursor: pointer;
    }}

    /* TAP sub-header in season-to-date TAP and TAPD tables: orange + clickable */
    .view-tap .season-monthly-slot .season-table th.stat,
    .view-tap .season-monthly-slot .tapd-table th.stat {{
      color: #ee7623;
      cursor: pointer;
    }}
    /* TAPD table header text: orange + clickable (goes back to TAP) */
    .tapd-table .table-header h2 {{
      color: #ee7623;
    }}
    .tapd-table .table-header {{
      cursor: pointer;
    }}
    .view-tap .season-monthly-slot .season-table th.stat:hover,
    .view-tap .season-monthly-slot .season-table th.stat:active,
    .view-tap .season-monthly-slot .tapd-table th.stat:hover,
    .view-tap .season-monthly-slot .tapd-table th.stat:active {{
      color: #ee7623;
      opacity: 1;
    }}
    /* Historical TAP/TAPD toggle: orange clickable sub-header only for years with TAPD data */
    .view-tap th.stat-toggle {{
      color: #ee7623;
      cursor: pointer;
    }}
    .view-tap th.stat-toggle:hover,
    .view-tap th.stat-toggle:active {{
      color: #ee7623;
      opacity: 1;
    }}

    .potm-overlay {{
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.75);
      z-index: 1000;
      justify-content: center;
      align-items: center;
    }}
    .potm-overlay.active {{
      display: flex;
    }}
    body.potm-open .container {{
      pointer-events: none;
    }}
    body.potm-open .potm-overlay {{
      pointer-events: auto;
    }}

    .potm-popup {{
      background: #111;
      border: 2px solid #fff;
      max-width: 500px;
      width: 92%;
      max-height: 80vh;
      overflow-y: auto;
      padding: 0;
      position: relative;
    }}

    .potm-popup-header {{
      background: #fff;
      color: #000;
      padding: 12px 16px;
      text-align: center;
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1.1em;
      font-weight: 900;
      letter-spacing: 0.05em;
      position: sticky;
      top: 0;
      z-index: 1;
    }}

    .potm-popup-close {{
      position: absolute;
      top: 8px;
      right: 12px;
      cursor: pointer;
      font-size: 1.4em;
      font-weight: 900;
      color: #000;
      background: none;
      border: none;
      font-family: 'Courier New', monospace;
      line-height: 1;
    }}

    .potm-popup table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88em;
    }}

    .potm-popup thead {{
      position: sticky;
      top: 42px;
      z-index: 1;
    }}

    .potm-popup thead th {{
      font-family: Georgia, 'Times New Roman', serif;
      text-align: center;
      padding: 6px 8px;
      font-weight: 900;
      font-size: 0.85em;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #fff;
      border-bottom: 1px solid #fff;
      background: #111;
    }}

    .potm-popup tbody tr {{
      border-bottom: 1px solid #333;
    }}

    .potm-popup td {{
      padding: 12px 8px;
      color: #fff;
      text-align: center;
      vertical-align: middle;
      height: 2.8em;
    }}

    .potm-popup .pm-month {{ width: 120px; }}
    .potm-popup .pm-player {{ width: 160px; }}
    .potm-popup .pm-stat {{ width: 52px; font-weight: 900; }}

    .potm-popup tbody tr:first-child td {{
      color: #ee7623;
      font-weight: 900;
    }}

    .week-label {{
      font-family: Georgia, 'Times New Roman', serif;
      font-weight: 400;
      font-style: italic;
      text-transform: none;
      letter-spacing: 0;
      color: #000;
      font-size: 0.9em;
      margin-left: 6px;
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95em;
    }}

    thead {{
      position: -webkit-sticky;
      position: sticky;
      top: 44px;
      z-index: 19;
    }}

    thead th {{
      font-family: Georgia, 'Times New Roman', serif;
      text-align: left;
      padding: 6px 10px;
      font-weight: 900;
      font-size: 0.95em;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #fff;
      background: #000;
      overflow: hidden;
    }}

    thead tr {{
      border-bottom: 1px solid #fff;
    }}

    tbody tr {{
      border-bottom: 1px solid #fff;
    }}

    tbody tr:last-child {{
      border-bottom: none;
    }}

    .all-time-table .year-pair,
    .decade-top100 .year-pair {{
      border-bottom: 3px solid #fff;
    }}

    td {{
      padding: 5px 10px;
    }}

    .rank {{
      width: 32px;
      text-align: center;
      font-weight: 700;
    }}

    .player {{
      min-width: 130px;
      white-space: nowrap;
    }}

    .team {{
      width: 40px;
      text-align: center;
      font-size: 0.9em;
    }}

    .season {{
      width: 68px;
      text-align: center;
      font-size: 0.85em;
    }}

    thead th.season {{
      text-align: center;
    }}

    .num {{
      width: 52px;
      text-align: right;
      font-variant-numeric: tabular-nums;
    }}

    .stat {{
      font-weight: 900;
      font-size: 1.15em;
      letter-spacing: -0.5px;
    }}
    /* Lock stat column width in tables that toggle TAP/TAPD (prevents column jump on toggle).
       GOAT/G2/G3 excluded — they don't toggle and need narrower .num width (52px) to fit mobile. */
    .decade-years .year-table .stat,
    .decade-top100 .year-table .stat,
    .all-time-table .year-table .stat,
    .season-table .stat,
    .tapd-table .stat,
    .monthly-table .stat,
    .tables-grid .year-table .stat {{
      width: 62px;
      min-width: 62px;
      max-width: 62px;
    }}

    thead th.num {{
      text-align: right;
    }}

    thead th.rank {{
      text-align: center;
    }}

    thead th.team {{
      text-align: center;
    }}

    thead th.stat {{
      text-align: right;
    }}
    /* Match stat width lock for headers in TAP/TAPD toggle tables only */
    .decade-years thead th.stat,
    .decade-top100 thead th.stat,
    .all-time-table thead th.stat,
    .season-table thead th.stat,
    .tapd-table thead th.stat,
    .monthly-table thead th.stat,
    .tables-grid thead th.stat {{
      min-width: 62px;
    }}

    .tapd-year-table thead th.stat,
    .tapd-table thead th.stat {{
      text-indent: -4px;
    }}

    .empty {{
      text-align: center;
      color: #fff;
      padding: 30px;
      font-style: italic;
    }}

    footer {{
      text-align: center;
      padding: 14px 0;
      border-top: 2px solid #fff;
      font-size: 0.82em;
      color: #fff;
      background: #000;
    }}

    footer .updated {{
      margin-bottom: 3px;
    }}

    .historical-section {{
      border-top: 2px solid #fff;
    }}

    .historical-header {{
      background: #fff;
      color: #000;
      text-align: center;
      padding: 16px 12px;
      cursor: pointer;
    }}

    .historical-header:hover {{
      background: #eee;
    }}

    .all-time-table .table-header,
    .decade-top100 .table-header,
    .goat-table .table-header,
    .g2-table .table-header,
    .g3-table .table-header,
    .mg-table .table-header,
    .diff-table .table-header {{
      background: #fff;
      cursor: pointer;
    }}

    .all-time-table .year-table .table-header h2,
    .decade-top100 .year-table .table-header h2,
    .goat-table .year-table .table-header h2,
    .g2-table .year-table .table-header h2,
    .g3-table .year-table .table-header h2,
    .mg-table .year-table .table-header h2,
    .diff-table .year-table .table-header h2 {{
      color: #ee7623;
    }}

    .all-time-table .table-header:hover,
    .decade-top100 .table-header:hover,
    .goat-table .table-header:hover,
    .g2-table .table-header:hover,
    .g3-table .table-header:hover,
    .mg-table .table-header:hover,
    .diff-table .table-header:hover {{
      background: #eee;
    }}

    td.num.goat-avg,
    thead th.num.goat-avg,
    td.num.g2-avg,
    thead th.num.g2-avg,
    td.num.g3-avg,
    thead th.num.g3-avg,
    td.num.mg1-avg,
    thead th.num.mg1-avg,
    td.num.mg2-avg,
    thead th.num.mg2-avg,
    td.num.mg3-avg,
    thead th.num.mg3-avg {{
      text-align: center !important;
      padding-left: 0;
      padding-right: 0;
    }}

    .goat-table thead,
    .g2-table thead,
    .g3-table thead,
    .mg-table thead {{
      box-shadow: 3px 0 0 #fff;
    }}
    .diff-table thead {{
      box-shadow: none;
    }}
    .goat-table thead tr,
    .g2-table thead tr,
    .g3-table thead tr,
    .mg-table thead tr,
    .diff-table thead tr {{
      border-bottom: 2px solid #fff;
    }}

    .goat-table td.num:last-child,
    .goat-table thead th.num:last-child,
    .g2-table td.num:last-child,
    .g2-table thead th.num:last-child,
    .g3-table td.num:last-child,
    .g3-table thead th.num:last-child,
    .mg-table td.num:last-child,
    .mg-table thead th.num:last-child {{
      padding-left: 2px;
    }}

    thead th.num.goat-avg,
    thead th.num.g2-avg,
    thead th.num.g3-avg,
    thead th.num.mg1-avg,
    thead th.num.mg2-avg,
    thead th.num.mg3-avg {{
      white-space: nowrap;
      font-size: 0.78em;
      cursor: pointer;
      text-indent: 7px;
    }}

    .goat-avg-tooltip {{
      display: none;
      position: fixed;
      z-index: 9999;
      background: #222;
      color: #fff;
      border: 1px solid #fff;
      border-radius: 6px;
      padding: 10px 14px;
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 0.82em;
      font-style: italic;
      max-width: 220px;
      text-align: center;
      box-shadow: 0 2px 8px rgba(0,0,0,0.5);
    }}
    .goat-avg-tooltip.active {{
      display: block;
    }}

    tr.goat-orange-sep td,
    tr.g2-orange-sep td,
    tr.g3-orange-sep td,
    tr.mg1-orange-sep td,
    tr.mg2-orange-sep td,
    tr.mg3-orange-sep td {{
      height: 6px;
      font-size: 1px;
      line-height: 6px;
      color: #ee7623;
      padding: 0;
      background: #ee7623;
      cursor: pointer;
      border: none;
      border-top: 1px solid #fff;
      overflow: hidden;
    }}

    .goat-sort-diff,
    .g2-sort-diff,
    .g3-sort-diff,
    .mg1-sort-diff,
    .mg2-sort-diff,
    .mg3-sort-diff {{
      color: #ee7623;
      cursor: pointer;
    }}

    .goat-sort-val,
    .goat-sort-yr,
    .g2-sort-val,
    .g2-sort-yr,
    .g3-sort-val,
    .g3-sort-yr,
    .mg1-sort-val,
    .mg1-sort-yr,
    .mg2-sort-val,
    .mg2-sort-yr,
    .mg3-sort-val,
    .mg3-sort-yr {{
      cursor: pointer;
    }}

    .goat-sort-player,
    .g2-sort-player,
    .g3-sort-player,
    .mg1-sort-player,
    .mg2-sort-player,
    .mg3-sort-player {{
      cursor: pointer;
      color: #ee7623;
    }}



    .mg-table th.stat,
    .mg-table td.stat {{
      width: 46px;
      min-width: 46px;
      max-width: 46px;
    }}
    .goat-table th.stat,
    .goat-table td.stat,
    .g2-table th.stat,
    .g2-table td.stat,
    .g3-table th.stat,
    .g3-table td.stat,
    .mg-table th.stat,
    .mg-table td.stat {{
      width: 46px;
      min-width: 46px;
      max-width: 46px;
    }}
    .goat-table thead th,
    .g2-table thead th,
    .g3-table thead th,
    .mg-table thead th,
    .diff-table thead th,
    .goat-table thead th.player,
    .g2-table thead th.player,
    .g3-table thead th.player,
    .mg-table thead th.player,
    .diff-table thead th.player {{
      overflow: visible;
    }}
    .mg-table thead th.stat {{
      text-indent: -4px;
    }}
    .mg-table thead th[class*="avg"] {{
      padding-left: 8px;
    }}

    .goat-table .player,
    .g2-table .player,
    .g3-table .player,
    .mg-table .player,
    .diff-table .player {{
      max-width: 160px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .decade-top100 .year-table .table-header h2 .decade-label {{
      font-size: 1.22em;
      font-weight: 700;
    }}

    .all-time-table table,
    .decade-top100 table,
    .goat-table table,
    .g2-table table,
    .g3-table table,
    .mg-table table,
    .diff-table table {{
      width: 100%;
    }}

    .all-time-table .player,
    .decade-top100 .player {{
      max-width: 160px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    /* DIFF table styles */
    .diff-table thead th.diff-sort-val,
    .diff-table thead th.diff-sort-adiff,
    .diff-table thead th.diff-sort-tdiff {{
      cursor: pointer;
      color: #ee7623;
      font-size: 0.95em;
      white-space: nowrap;
      text-transform: none;
    }}
    .diff-table td.diff-val,
    .diff-table td.diff-adiff,
    .diff-table td.diff-tdiff {{
      font-size: 0.92em;
    }}
    .diff-table td.diff-tdiff {{
      padding-right: 8px;
    }}
    .diff-table td.rank {{
      text-align: center;
      width: 30px;
    }}
    .diff-table thead th.rank {{
      text-align: center;
      width: 30px;
    }}
    .diff-table .view-ted,
    .diff-table .view-tap {{
      width: 100%;
    }}

    .historical-header h2 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1.2em;
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #ee7623;
      margin: 0;
    }}

    .decade-nav {{
      display: flex;
      justify-content: center;
      gap: 10px;
      padding: 22px 16px;
      border-bottom: 2px solid #fff;
      flex-wrap: wrap;
    }}

    .decade-nav .nav-break {{
      display: none;
      width: 100%;
      height: 0;
    }}

    .decade-nav .nav-break.desktop-only {{
      display: block;
    }}

    .decade-nav a {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 0.95em;
      font-weight: 700;
      color: #fff;
      text-decoration: none;
      padding: 4px 12px;
      border: 1px solid #fff;
      transition: background 0.2s, color 0.2s;
    }}

    .decade-nav a:hover {{
      background: #fff;
      color: #000;
    }}

    .decade {{
      border-top: 2px solid #fff;
    }}

    .decade-header {{
      background: #222;
      padding: 10px 16px;
      text-align: center;
      cursor: pointer;
    }}

    .decade-header:hover {{
      background: #333;
    }}

    .decade-header h3 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1.22em;
      font-weight: 900;
      letter-spacing: 0.1em;
      color: #ee7623;
      margin: 0;
    }}

    .decade-s {{
      font-size: 0.75em;
      vertical-align: baseline;
    }}

    .year-pair {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      border-top: 1px solid #555;
    }}

    .year-pair > :first-child {{
      border-right: 2px solid #fff;
    }}

    .year-table {{
      min-width: 0;
    }}

    .year-table table {{
      max-width: 100%;
      margin: 0 auto;
    }}

    #decade-all-time .year-table table {{
      max-width: 780px;
      table-layout: fixed;
    }}

    #decade-all-time .rank {{
      width: 50px;
    }}

    #decade-all-time .player {{
      width: auto;
    }}

    #decade-all-time .team {{
      width: 50px;
    }}

    #decade-all-time .season {{
      width: 80px;
    }}

    #decade-all-time .num {{
      width: 58px;
    }}

    .year-table .table-header {{
      background: #fff;
      border: 2px solid #000;
      padding: 10px 12px;
      text-align: center;
    }}


    .year-table .table-header h2 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1em;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: #000;
      text-align: center;
      margin: 0;
      padding: 0;
      border: none;
      background: none;
      display: inline;
    }}

    .empty-row td {{
      height: 28px;
    }}

    td.player[data-player] {{
      cursor: pointer;
    }}
    td.player[data-player]:hover {{
      opacity: 0.7;
    }}

    .career-overlay {{
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: rgba(0, 0, 0, 0.75);
      z-index: 1000;
      justify-content: center;
      align-items: center;
    }}
    .career-overlay.active {{
      display: flex;
    }}
    body.career-open .container {{
      pointer-events: none;
    }}
    body.career-open .career-overlay {{
      pointer-events: auto;
    }}

    .career-popup {{
      background: #111;
      border: 2px solid #fff;
      max-width: 600px;
      width: 92%;
      max-height: 80vh;
      overflow-y: auto;
      padding: 0;
      position: relative;
    }}

    .career-popup-header {{
      background: #fff;
      color: #000;
      padding: 12px 16px;
      text-align: center;
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1.1em;
      font-weight: 900;
      letter-spacing: 0.05em;
      position: sticky;
      top: 0;
      z-index: 1;
    }}

    .career-popup-close {{
      position: absolute;
      top: 8px;
      right: 12px;
      cursor: pointer;
      font-size: 1.4em;
      font-weight: 900;
      color: #000;
      background: none;
      border: none;
      font-family: 'Courier New', monospace;
      line-height: 1;
    }}

    .career-popup table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88em;
    }}

    .career-popup thead {{
      position: sticky;
      top: 42px;
      z-index: 1;
    }}

    .career-popup thead th {{
      font-family: Georgia, 'Times New Roman', serif;
      text-align: left;
      padding: 6px 8px;
      font-weight: 900;
      font-size: 0.85em;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: #fff;
      border-bottom: 1px solid #fff;
      background: #111;
    }}

    .career-popup tbody tr {{
      border-bottom: 1px solid #333;
    }}

    .career-popup td {{
      padding: 4px 8px;
      color: #fff;
    }}

    .career-popup .cp-season {{ width: 68px; text-align: center; }}
    .career-popup .cp-team {{ width: 40px; text-align: center; }}
    .career-popup .cp-stat {{ width: 52px; text-align: center; font-weight: 900; }}
    .career-popup .cp-avg {{ width: 48px; text-align: center; }}
    .career-popup .cp-leader {{ width: 52px; text-align: center; font-weight: 900; }}

    .career-popup thead th {{ text-align: center; }}

    .career-popup tr.cp-current td {{
      color: #ee7623;
      font-weight: 900;
    }}

    @media (max-width: 900px) {{
      .tables-grid {{
        grid-template-columns: 1fr;
      }}
      .tables-grid > :first-child {{
        border-right: none;
        border-bottom: 2px solid #fff;
      }}
      .table-section h2 {{
        display: block;
      }}
      .week-label {{
        display: block;
        margin-left: 0;
        margin-top: 4px;
        font-size: 0.8em;
      }}
      .player .fname,
      .player .lname {{
        display: inline;
      }}
      td, thead th {{
        padding: 4px 6px;
      }}
      .player {{
        min-width: 0;
        max-width: 140px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }}
      .stat-desc p {{
        text-align: center;
      }}
      .decade-nav {{
        gap: 4px;
        padding: 10px 8px;
      }}
      .decade-nav a {{
        font-size: 0.85em;
        padding: 4px 8px;
      }}
      .decade-nav .nav-break {{
        display: block;
        width: 100%;
        height: 0;
      }}
      .decade-nav .nav-break.desktop-only {{
        display: none;
      }}
      .year-pair {{
        grid-template-columns: 1fr;
      }}
      .year-pair > :first-child {{
        border-right: none;
        border-bottom: 2px solid #fff;
      }}
      .all-time-table .year-pair > :first-child,
      .decade-top100 .year-pair > :first-child,
      .goat-table .year-pair > :first-child,
      .g2-table .year-pair > :first-child,
      .g3-table .year-pair > :first-child,
      .mg-table .year-pair > :first-child,
      .diff-table .year-pair > :first-child {{
        border-bottom: none;
      }}
      .year-pair.single > :last-child,
      .all-time-table .year-pair > :last-child,
      .decade-top100 .year-pair > :last-child,
      .goat-table .year-pair > :last-child,
      .g2-table .year-pair > :last-child,
      .g3-table .year-pair > :last-child,
      .mg-table .year-pair > :last-child,
      .diff-table .year-pair > :last-child {{
        display: none;
      }}
      .goat-table td,
      .goat-table thead th,
      .g2-table td,
      .g2-table thead th,
      .g3-table td,
      .g3-table thead th,
      .mg-table td,
      .mg-table thead th,
      .diff-table td,
      .diff-table thead th {{
        padding-left: 3px;
        padding-right: 3px;
      }}
      .mg-table thead th[class*="avg"] {{
        padding-left: 0;
        padding-right: 0;
      }}
      .diff-table thead th {{
        padding-top: 6px;
        padding-bottom: 6px;
      }}
      .diff-table thead th.diff-sort-val,
      .diff-table thead th.diff-sort-adiff,
      .diff-table thead th.diff-sort-tdiff {{
        font-size: 0.85em;
      }}
      .diff-table td.diff-val,
      .diff-table td.diff-adiff,
      .diff-table td.diff-tdiff {{
        font-size: 0.85em;
      }}
      .diff-table td.diff-tdiff {{
        padding-right: 8px;
      }}
      .diff-table td.rank,
      .diff-table thead th.rank {{
        font-size: 0.85em;
      }}
      .diff-table .player {{
        max-width: 120px;
      }}
      .diff-table td.rank,
      .diff-table thead th.rank {{
        padding-left: 2px;
        padding-right: 2px;
      }}
      .mg-table .table-header h2 {{
        white-space: nowrap;
        letter-spacing: 0.5px;
      }}
      .mg-table .table-header {{
        padding-left: 6px;
      }}
      .all-time-table .player,
      .decade-top100 .player {{
        max-width: 120px;
      }}
      .all-time-table td,
      .all-time-table th,
      .decade-top100 td,
      .decade-top100 th {{
        padding-left: 6px;
        padding-right: 6px;
      }}
      .year-table table {{
        max-width: 100%;
      }}
      .year-table .player .fname,
      .year-table .player .lname {{
        display: inline;
      }}
      .potm-popup-header {{
        font-size: 1.05em;
        padding: 10px 14px;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1 data-ted-text="NBA TED Rankings" data-tap-text="NBA TAP Rankings">NBA TAP Rankings</h1>
      <svg class="basketball" width="36" height="36" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <circle cx="50" cy="50" r="46" fill="#ee7623" stroke="#000" stroke-width="3"/>
        <path d="M4 50 C4 50 96 50 96 50" stroke="#000" stroke-width="2.5"/>
        <path d="M50 4 C50 4 50 96 50 96" stroke="#000" stroke-width="2.5"/>
        <path d="M10 18 C30 38 30 62 10 82" stroke="#000" stroke-width="2.5" fill="none"/>
        <path d="M90 18 C70 38 70 62 90 82" stroke="#000" stroke-width="2.5" fill="none"/>
      </svg>
      <div class="toggle-link" id="toggle-link">TED Click Here</div>
    </header>

    <div class="description">
      <div class="stat-desc desc-ted desc-hidden">
        <h3>TED &mdash; Total Earned Differential</h3>
        <p>TED estimates total player production per game as a single points-equivalent number. It relies primarily on box score stats, converting all box-score contributions &mdash; points scored, scoring efficiency, rebounds, assists, steals, turnovers, blocks &mdash; along with a defensive adjustment (using DBPM and DWS) into one value. TED is meant to capture a player&rsquo;s full impact on points scored in a game, both directly and indirectly &mdash; his Total Earned Differential. For example, if a player scored 30 points with a TED of 52 in last night&rsquo;s game &mdash; he actually contributed 52 points worth of total offensive/defensive production across all facets of the game, not 30. TED is normalized to per 36 minutes and 71 possessions for cleaner cross-player and cross-era comparisons.</p>
      </div>
      <div class="stat-desc desc-tap">
        <h3>TAP &mdash; Total Adjusted Production</h3>
        <p>TAP estimates total player production per game as a single points-equivalent number. It builds on TED (Total Earned Differential), which converts all box-score contributions &mdash; points scored, scoring efficiency, rebounds, assists, steals, turnovers, blocks &mdash; plus a defensive adjustment (using DBPM and DWS) into one value. TAP takes this approach one step further, overlaying an additional offensive adjustment (using OBPM and OWS) to capture the residual offensive impact that box-score stats miss &mdash; for example, shooting gravity that warps defenses, or anti-gravity. TAP is normalized to per 36 minutes and 71 possessions for cleaner cross-player and cross-era comparisons. Players must meet a 20 minutes per game and 40 games per season threshold for inclusion in the rankings.</p>
      </div>
    </div>

{decade_nav_html}
    <div class="season-header" id="season-header"><h3>{season_label} Season <span class="season-click-hint">Click here</span></h3></div>
    <div class="season-hint" id="season-hint"><p>Everything you see in ORANGE is CLICKABLE for added functionality!</p><p>&nbsp;</p></div>
    <div class="view-ted" style="display:none">
      <div class="tables-grid">
        <div class="weekly-daily-slot">
          <div class="weekly-table">{weekly_ted_table}</div>
          <div class="daily-table" style="display:none">{daily_ted_table}</div>
        </div>
        <div class="season-monthly-slot">
          <div class="season-table">{season_ted_table}</div>
          <div class="monthly-table" style="display:none">{monthly_ted_table}</div>
        </div>
      </div>
    </div>
    <div class="view-tap">
      <div class="tables-grid">
        <div class="weekly-daily-slot">
          <div class="weekly-table">{weekly_tap_table}</div>
          <div class="daily-table" style="display:none">{daily_tap_table}</div>
        </div>
        <div class="season-monthly-slot">
          <div class="season-table">{season_tap_table}</div>
          <div class="tapd-table" style="display:none">{season_tapd_table}</div>
          <div class="monthly-table" style="display:none">{monthly_tap_table}</div>
        </div>
      </div>
    </div>

{historical_html}
    <footer>
      <div class="updated">Last updated: {updated_at}</div>
      <div>TED and TAP created by Joel Dechant</div>
    </footer>
  </div>
  <div class="float-toggle" id="float-toggle">
    <svg width="40" height="40" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <circle cx="50" cy="50" r="46" fill="#ee7623" stroke="#000" stroke-width="3"/>
      <path d="M4 50 C4 50 96 50 96 50" stroke="#000" stroke-width="2.5"/>
      <path d="M50 4 C50 4 50 96 50 96" stroke="#000" stroke-width="2.5"/>
      <path d="M10 18 C30 38 30 62 10 82" stroke="#000" stroke-width="2.5" fill="none"/>
      <path d="M90 18 C70 38 70 62 90 82" stroke="#000" stroke-width="2.5" fill="none"/>
    </svg>
  </div>
  <div class="goat-avg-tooltip" id="goat-avg-tooltip"></div>
  <div class="career-overlay" id="career-overlay">
    <div class="career-popup" id="career-popup">
      <div class="career-popup-header">
        <span id="career-popup-name"></span>
        <button class="career-popup-close" id="career-popup-close">&times;</button>
      </div>
      <table>
        <thead>
          <tr>
            <th class="cp-season">Season</th>
            <th class="cp-team">Team</th>
            <th class="cp-stat" id="career-stat-header">TED</th>
            <th class="cp-avg" id="career-avg-header">AVG</th>
            <th class="cp-leader" id="career-top10-header">TOP 10</th>
          </tr>
        </thead>
        <tbody id="career-popup-body">
        </tbody>
      </table>
    </div>
  </div>
  <div class="potm-overlay" id="potm-overlay">
    <div class="potm-popup" id="potm-popup">
      <div class="potm-popup-header">
        <span id="potm-popup-title">PLAYER OF THE MONTH</span>
        <button class="potm-popup-close" id="potm-popup-close">&times;</button>
      </div>
      <table>
        <thead>
          <tr>
            <th class="pm-month">Month</th>
            <th class="pm-player">Player</th>
            <th class="pm-stat" id="potm-stat-header">TED</th>
          </tr>
        </thead>
        <tbody id="potm-popup-body">
        </tbody>
      </table>
    </div>
  </div>
{potm_js}
{career_js}
  <script>
  (function() {{
    var stat = 'tap';
    var toggleLink = document.getElementById('toggle-link');
    var floatToggle = document.getElementById('float-toggle');

    /* Find the nearest visible anchor element for scroll preservation.
       Returns {{selector, offset}} where selector can find the matching
       element in the other view, and offset is the viewport-top distance. */
    function findScrollAnchor() {{
      var viewClass = stat === 'ted' ? '.view-ted' : '.view-tap';
      var candidates = [];
      /* Year tables (data-year) */
      document.querySelectorAll(viewClass + ' .year-table[data-year]').forEach(function(el) {{
        if (el.offsetParent !== null) candidates.push({{el: el, sel: '.year-table[data-year="' + el.getAttribute('data-year') + '"]'}});
      }});
      /* Decade headers (not sticky — safe anchors with stable DOM positions) */
      document.querySelectorAll(viewClass + ' .decade').forEach(function(dec) {{
        var decId = dec.id;
        var otherId = decId.endsWith('-tap') ? decId.slice(0, -4) : decId + '-tap';
        var h = dec.querySelector('.decade-header');
        if (h && h.offsetParent !== null) {{
          candidates.push({{el: h, sel: '#' + otherId + ' .decade-header'}});
        }}
      }});
      /* Historical section header (not sticky — safe anchor) */
      var hh = document.querySelector(viewClass + ' .historical-header');
      if (hh && hh.offsetParent !== null) candidates.push({{el: hh, sel: '.historical-header'}});
      var best = null, bestDist = Infinity;
      var vh = window.innerHeight;
      for (var i = 0; i < candidates.length; i++) {{
        var rect = candidates[i].el.getBoundingClientRect();
        /* Only consider elements at least partially visible in viewport */
        if (rect.bottom < 0 || rect.top > vh) continue;
        var dist = Math.abs(rect.top);
        if (dist < bestDist) {{ bestDist = dist; best = {{sel: candidates[i].sel, offset: rect.top}}; }}
      }}
      return best;
    }}

    function doToggle() {{
      closeCareer();
      closePotm();
      var anchor = findScrollAnchor();
      var savedScroll = window.scrollY;
      /* Capture weekly/daily and season/monthly state from old view before switching */
      var oldView = stat === 'ted' ? '.view-ted' : '.view-tap';
      var oldSlot = document.querySelector(oldView + ' .weekly-daily-slot');
      var showingDaily = oldSlot && oldSlot.querySelector('.daily-table').style.display !== 'none';
      var oldSeasonSlot = document.querySelector(oldView + ' .season-monthly-slot');
      var showingMonthly = oldSeasonSlot && oldSeasonSlot.querySelector('.monthly-table').style.display !== 'none';
      var oldTapdDiv = oldSeasonSlot && oldSeasonSlot.querySelector('.tapd-table');
      var showingTapd = oldTapdDiv && oldTapdDiv.style.display !== 'none';
      stat = stat === 'ted' ? 'tap' : 'ted';
      document.querySelectorAll('.view-ted').forEach(function(el) {{
        el.style.display = stat === 'ted' ? '' : 'none';
      }});
      document.querySelectorAll('.view-tap').forEach(function(el) {{
        el.style.display = stat === 'tap' ? '' : 'none';
      }});
      /* Sync weekly/daily state to new view */
      var newView = stat === 'ted' ? '.view-ted' : '.view-tap';
      var newSlot = document.querySelector(newView + ' .weekly-daily-slot');
      if (newSlot) {{
        newSlot.querySelector('.weekly-table').style.display = showingDaily ? 'none' : '';
        newSlot.querySelector('.daily-table').style.display = showingDaily ? '' : 'none';
      }}
      /* Sync season/monthly state to new view */
      var newSeasonSlot = document.querySelector(newView + ' .season-monthly-slot');
      if (newSeasonSlot) {{
        newSeasonSlot.querySelector('.season-table').style.display = showingMonthly ? 'none' : '';
        newSeasonSlot.querySelector('.monthly-table').style.display = showingMonthly ? '' : 'none';
        var newTapdDiv = newSeasonSlot.querySelector('.tapd-table');
        if (newTapdDiv) newTapdDiv.style.display = 'none';
      }}
      /* Reset per-year TAPD toggles back to TAP on switch */
      document.querySelectorAll('.view-tap .tapd-year-table').forEach(function(t) {{ t.style.display = 'none'; }});
      document.querySelectorAll('.view-tap .tap-year-table').forEach(function(t) {{ t.style.display = ''; }});
      document.querySelectorAll('.view-tap .year-stat-label').forEach(function(l) {{ l.textContent = 'TAP'; }});
      /* Reset all-time header text back to TAP (first year-table only, skip placeholder) */
      var atH2 = document.querySelector('.view-tap .all-time-table .year-pair > .year-table:first-child .table-header h2');
      if (atH2) atH2.innerHTML = 'ALL-TIME <span class="year-stat-label">TAP</span> TOP 400';
      /* Sync all-time and decade top 100 expand/collapse state */
      var oldSec = document.querySelector(oldView + ' .historical-section');
      var newSec = document.querySelector(newView + ' .historical-section');
      if (oldSec && newSec) {{
        var oldAT = oldSec.querySelector('.all-time-table');
        var newAT = newSec.querySelector('.all-time-table');
        if (oldAT && newAT) newAT.style.display = oldAT.style.display;
        var oldGoat = oldSec.querySelector('.goat-table');
        var newGoat = newSec.querySelector('.goat-table');
        if (oldGoat && newGoat) newGoat.style.display = oldGoat.style.display;
        if (newGoat && newGoat.style.display !== 'none' && typeof goatApplySort === 'function') goatApplySort();
        var oldG2 = oldSec.querySelector('.g2-table');
        var newG2 = newSec.querySelector('.g2-table');
        if (oldG2 && newG2) newG2.style.display = oldG2.style.display;
        if (newG2 && newG2.style.display !== 'none' && typeof g2ApplySort === 'function') g2ApplySort();
        var oldG3 = oldSec.querySelector('.g3-table');
        var newG3 = newSec.querySelector('.g3-table');
        if (oldG3 && newG3) newG3.style.display = oldG3.style.display;
        if (newG3 && newG3.style.display !== 'none' && typeof g3ApplySort === 'function') g3ApplySort();
        var oldMg = oldSec.querySelector('.mg-table');
        var newMg = newSec.querySelector('.mg-table');
        if (oldMg && newMg) {{
          newMg.style.display = oldMg.style.display;
          ['mg-goat-view', 'mg-g2-view', 'mg-g3-view'].forEach(function(cls) {{
            var oldV = oldMg.querySelector('.' + cls);
            var newV = newMg.querySelector('.' + cls);
            if (oldV && newV) newV.style.display = oldV.style.display;
          }});
          if (newMg.style.display !== 'none') {{
            if (typeof mg1ApplySort === 'function') mg1ApplySort();
            if (typeof mg2ApplySort === 'function') mg2ApplySort();
            if (typeof mg3ApplySort === 'function') mg3ApplySort();
          }}
        }}
        var oldDiff = oldSec.querySelector('.diff-table');
        var newDiff = newSec.querySelector('.diff-table');
        if (oldDiff && newDiff) {{
          newDiff.style.display = oldDiff.style.display;
          /* Sync internal TED/TAP views */
          var dTed = newDiff.querySelector('.view-ted');
          var dTap = newDiff.querySelector('.view-tap');
          if (dTed) dTed.style.display = tapVisible ? 'none' : '';
          if (dTap) dTap.style.display = tapVisible ? '' : 'none';
        }}
        var oldDecs = oldSec.querySelectorAll('.decade');
        var newDecs = newSec.querySelectorAll('.decade');
        for (var di = 0; di < oldDecs.length && di < newDecs.length; di++) {{
          var oldD100 = oldDecs[di].querySelector('.decade-top100');
          var newD100 = newDecs[di].querySelector('.decade-top100');
          var oldYears = oldDecs[di].querySelector('.decade-years');
          var newYears = newDecs[di].querySelector('.decade-years');
          if (oldD100 && newD100) newD100.style.display = oldD100.style.display;
          if (oldYears && newYears) newYears.style.display = oldYears.style.display;
        }}
      }}
      document.querySelector('.desc-ted').classList.toggle('desc-hidden', stat !== 'ted');
      document.querySelector('.desc-tap').classList.toggle('desc-hidden', stat !== 'tap');
      toggleLink.textContent = stat === 'ted' ? 'TAP Click Here' : 'TED Click Here';
      document.querySelectorAll('[data-ted-text]').forEach(function(el) {{
        el.textContent = el.getAttribute('data-' + stat + '-text');
      }});
      /* Compute desired scroll position, then only scrollTo if it actually
         changed — avoids unnecessary scrollTo calls that cause visual jiggle
         on mobile browsers during DOM reflow */
      var desiredScroll = savedScroll;
      if (anchor) {{
        var viewClass = stat === 'ted' ? '.view-ted' : '.view-tap';
        var target = document.querySelector(viewClass + ' ' + anchor.sel);
        if (target) {{
          desiredScroll = target.getBoundingClientRect().top + window.scrollY - anchor.offset;
        }}
      }}
      if (Math.abs(desiredScroll - window.scrollY) > 2) {{
        window.scrollTo(0, desiredScroll);
      }}
    }}

    document.querySelector('.basketball').addEventListener('click', doToggle);
    toggleLink.addEventListener('click', doToggle);
    floatToggle.addEventListener('click', doToggle);
    document.getElementById('season-header').addEventListener('click', function() {{
      document.getElementById('season-hint').classList.toggle('open');
    }});
    document.getElementById('season-hint').addEventListener('click', function() {{
      this.classList.remove('open');
    }});
    document.querySelectorAll('.decade-nav a[data-decade]').forEach(function(a) {{
      a.addEventListener('click', function(e) {{
        e.preventDefault();
        var tip = document.getElementById('goat-avg-tooltip');
        if (tip && tip.classList.contains('active')) return;
        var decade = this.getAttribute('data-decade');
        var suffix = stat === 'ted' ? '' : '-tap';
        var target = document.getElementById('decade-' + decade + suffix);
        if (target) target.scrollIntoView({{behavior: 'smooth'}});
      }});
    }});

    // === Career Popup ===
    var overlay = document.getElementById('career-overlay');
    var popupBody = document.getElementById('career-popup-body');
    var popupName = document.getElementById('career-popup-name');
    var popupStatHeader = document.getElementById('career-stat-header');
    var currentYear = {config.CURRENT_SEASON_YEAR};

    function showCareer(name, contextYear, statOverride) {{
      var career = window.CAREER[name];
      if (!career || career.length === 0) return;
      var s = statOverride || stat;
      var su = s.toUpperCase();
      var hlYear = contextYear || null;
      popupName.textContent = name;
      popupStatHeader.textContent = su;
      var avgH = document.getElementById('career-avg-header');
      var t10H = document.getElementById('career-top10-header');
      avgH.textContent = 'AVG';
      t10H.textContent = 'TOP 10';
      var html = '';
      for (var i = career.length - 1; i >= 0; i--) {{
        var c = career[i];
        var sl = c.y + '-' + String(c.y + 1).slice(-2);
        var tm = c.tm || '\\u2014';
        var val = c[s] !== null && c[s] !== undefined ? c[s].toFixed(1) : '\\u2014';
        var ss = window.SEASON_STATS[String(c.y)];
        var avgVal = '', top10Val = '';
        if (ss) {{
          var av = ss['avg_' + s];
          avgVal = av !== undefined ? av.toFixed(1) : '';
          var t10 = ss['top10_' + s];
          top10Val = t10 !== undefined ? t10.toFixed(1) : '';
        }}
        var rc = c.y === hlYear ? ' class="cp-current"' : '';
        html += '<tr' + rc + '>'
          + '<td class="cp-season">' + sl + '</td>'
          + '<td class="cp-team">' + tm + '</td>'
          + '<td class="cp-stat">' + val + '</td>'
          + '<td class="cp-avg">' + (avgVal || '\\u2014') + '</td>'
          + '<td class="cp-leader">' + (top10Val || '\\u2014') + '</td>'
          + '</tr>';
      }}
      popupBody.innerHTML = html;
      overlay.classList.add('active');
      document.body.classList.add('career-open');
    }}

    function closeCareer() {{
      overlay.classList.remove('active');
      document.body.classList.remove('career-open');
      popupBody.innerHTML = '';
    }}

    document.querySelector('.container').addEventListener('click', function(e) {{
      if (overlay.classList.contains('active')) {{
        closeCareer();
        return;
      }}
      var tip = document.getElementById('goat-avg-tooltip');
      if (tip && tip.classList.contains('active')) {{
        tip.classList.remove('active');
        return;
      }}
      var td = e.target.closest('td.player[data-player]');
      if (td) {{
        e.stopPropagation();
        var yearDiv = td.closest('.year-table[data-year]');
        var ctxYear = yearDiv ? parseInt(yearDiv.getAttribute('data-year')) : currentYear;
        var so = null;
        if (td.closest('.tapd-year-table') || td.closest('.tapd-table')) so = 'tapd';
        showCareer(td.getAttribute('data-player'), ctxYear, so);
      }}
    }});

    document.getElementById('career-popup-close').addEventListener('click', closeCareer);
    overlay.addEventListener('click', function(e) {{
      closeCareer();
    }});
    document.addEventListener('keydown', function(e) {{
      if (e.key === 'Escape') closeCareer();
      if (e.key === 'Escape') closePotm();
    }});

    /* POTM (Player of the Month) popup — click RANK header in monthly table */
    var potmOverlay = document.getElementById('potm-overlay');
    var potmBody = document.getElementById('potm-popup-body');
    var potmTitle = document.getElementById('potm-popup-title');
    var potmStatHeader = document.getElementById('potm-stat-header');

    function showPotm() {{
      var winners = window.MONTH_WINNERS;
      if (!winners || winners.length === 0) return;
      var s = stat;
      var su = s.toUpperCase();
      potmTitle.textContent = 'PLAYER OF THE MONTH - ' + su;
      potmStatHeader.textContent = su;
      var html = '';
      for (var i = winners.length - 1; i >= 0; i--) {{
        var w = winners[i];
        var player = s === 'ted' ? w.ted_player : w.tap_player;
        var val = s === 'ted' ? w.ted_val : w.tap_val;
        html += '<tr>'
          + '<td class="pm-month">' + w.month + '</td>'
          + '<td class="pm-player">' + player + '</td>'
          + '<td class="pm-stat">' + val.toFixed(1) + '</td>'
          + '</tr>';
      }}
      potmBody.innerHTML = html;
      potmOverlay.classList.add('active');
      document.body.classList.add('potm-open');
    }}

    function closePotm() {{
      potmOverlay.classList.remove('active');
      document.body.classList.remove('potm-open');
      potmBody.innerHTML = '';
    }}

    /* Click RANK header in monthly tables to open POTM popup */
    document.querySelectorAll('.monthly-table th.rank').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        showPotm();
      }});
    }});

    document.getElementById('potm-popup-close').addEventListener('click', closePotm);
    potmOverlay.addEventListener('click', function(e) {{
      closePotm();
    }});

    /* Weekly / Daily toggle — click header to swap */
    document.querySelectorAll('.weekly-daily-slot').forEach(function(slot) {{
      slot.addEventListener('click', function(e) {{
        var header = e.target.closest('.table-header');
        if (!header) return;
        var weekly = slot.querySelector('.weekly-table');
        var daily = slot.querySelector('.daily-table');
        if (weekly.style.display === 'none') {{
          weekly.style.display = '';
          daily.style.display = 'none';
        }} else {{
          weekly.style.display = 'none';
          daily.style.display = '';
        }}
      }});
    }});

    /* Season ↔ Monthly toggle via title bar click (both TED and TAP views). */
    document.querySelectorAll('.season-monthly-slot').forEach(function(slot) {{
      slot.addEventListener('click', function(e) {{
        var header = e.target.closest('.table-header');
        if (!header) return;
        /* Handle season-table, monthly-table, or tapd-table title bars */
        var inSeason = !!header.closest('.season-table');
        var inMonthly = !!header.closest('.monthly-table');
        var inTapd = !!header.closest('.tapd-table');
        if (!inSeason && !inMonthly && !inTapd) return;
        var seasonDiv = slot.querySelector('.season-table');
        var monthlyDiv = slot.querySelector('.monthly-table');
        var tapdDiv = slot.querySelector('.tapd-table');
        if (inTapd) {{
          /* TAPD header click: go back to TAP */
          if (tapdDiv) tapdDiv.style.display = 'none';
          if (seasonDiv) seasonDiv.style.display = '';
          if (monthlyDiv) monthlyDiv.style.display = 'none';
          return;
        }}
        var seasonVisible = seasonDiv.style.display !== 'none';
        seasonDiv.style.display = seasonVisible ? 'none' : '';
        monthlyDiv.style.display = seasonVisible ? '' : 'none';
        if (tapdDiv) tapdDiv.style.display = 'none';
      }});
    }});

    /* TAP view: clicking the "TAP"/"TAPD" column sub-header toggles TAP ↔ TAPD */
    document.querySelectorAll('.view-tap .season-monthly-slot').forEach(function(slot) {{
      var seasonDiv = slot.querySelector('.season-table');
      var tapdDiv = slot.querySelector('.tapd-table');
      var monthlyDiv = slot.querySelector('.monthly-table');
      if (!seasonDiv || !tapdDiv) return;
      slot.addEventListener('click', function(e) {{
        var th = e.target.closest('th.stat');
        if (!th) return;
        /* Only respond to stat column header clicks inside season or tapd tables */
        var inSeason = !!th.closest('.season-table');
        var inTapd = !!th.closest('.tapd-table');
        if (!inSeason && !inTapd) return;
        var seasonVisible = seasonDiv.style.display !== 'none';
        seasonDiv.style.display = seasonVisible ? 'none' : '';
        tapdDiv.style.display = seasonVisible ? '' : 'none';
        /* Hide monthly when entering TAPD mode */
        if (monthlyDiv) monthlyDiv.style.display = 'none';
      }});
    }});

    /* Historical TAP/TAPD toggle: per-year toggle — clicking th.stat-toggle swaps tables within that year only */
    document.querySelectorAll('.view-tap').forEach(function(vt) {{ vt.addEventListener('click', function(e) {{
      var th = e.target.closest('th.stat-toggle');
      if (!th) return;
      var yearDiv = th.closest('.year-table');
      if (!yearDiv) return;
      /* Only handle historical year tables (not current-season tables) */
      if (yearDiv.closest('.season-monthly-slot')) return;
      var tapTable = yearDiv.querySelector('.tap-year-table');
      var tapdTable = yearDiv.querySelector('.tapd-year-table');
      if (!tapTable || !tapdTable) return;
      var tapVisible = tapTable.style.display !== 'none';
      tapTable.style.display = tapVisible ? 'none' : '';
      tapdTable.style.display = tapVisible ? '' : 'none';
      /* Update the header label */
      var label = yearDiv.querySelector('.year-stat-label');
      if (label) {{
        var isAllTime = yearDiv.closest('.all-time-table');
        if (isAllTime) {{
          var h2 = yearDiv.querySelector('.table-header h2');
          if (h2) h2.innerHTML = tapVisible
            ? 'MODERN ERA <span class="year-stat-label">TAPD</span> TOP 400'
            : 'ALL-TIME <span class="year-stat-label">TAP</span> TOP 400';
        }} else {{
          label.textContent = tapVisible ? 'TAPD' : 'TAP';
          /* Update TOP N and decade label for decade lists (e.g., 1990s TAP TOP 200 → LATE 1990s TAPD TOP 100) */
          var header = yearDiv.querySelector('.table-header');
          if (header && header.dataset.tapN) {{
            var topNLabel = header.querySelector('.top-n-label');
            if (topNLabel) topNLabel.textContent = tapVisible ? header.dataset.tapdN : header.dataset.tapN;
            var decLabel = header.querySelector('.decade-label');
            if (decLabel && header.dataset.tapLabel && header.dataset.tapdLabel) {{
              var isLate90s = (header.dataset.tapdLabel === 'LATE 1990s');
              var latePrefix = decLabel.parentNode.querySelector('.late-prefix');
              if (isLate90s && tapVisible) {{
                if (!latePrefix) {{
                  latePrefix = document.createElement('span');
                  latePrefix.className = 'late-prefix';
                  latePrefix.textContent = 'LATE ';
                  decLabel.parentNode.insertBefore(latePrefix, decLabel);
                }}
                latePrefix.style.display = '';
              }} else {{
                if (latePrefix) latePrefix.style.display = 'none';
                var newLabel = tapVisible ? header.dataset.tapdLabel : header.dataset.tapLabel;
                var decS = decLabel.querySelector('.decade-s');
                decLabel.childNodes[0].textContent = newLabel;
                if (decS) decS.style.display = (newLabel === header.dataset.tapLabel) ? '' : 'none';
              }}
            }}
          }}
        }}
      }}
    }}); }});

    /* Historical / All-Time toggle — click header to show/hide */
    document.querySelectorAll('.historical-section').forEach(function(sec) {{
      var header = sec.querySelector('.historical-header');
      var allTime = sec.querySelector('.all-time-table');
      if (!header || !allTime) return;
      header.addEventListener('click', function() {{
        var tip = document.getElementById('goat-avg-tooltip');
        if (tip && tip.classList.contains('active')) return;
        if (allTime.style.display !== 'none') {{
          allTime.style.display = 'none';
          /* Only scroll back if header is near viewport top (scrolled past it) */
          if (header.getBoundingClientRect().top <= 5) {{
            header.scrollIntoView({{block: 'start'}});
          }}
        }} else {{
          allTime.style.display = '';
        }}
      }});
      /* Also collapse via the table's own sticky header */
      var tableHeader = allTime.querySelector('.table-header');
      if (tableHeader) tableHeader.addEventListener('click', function() {{
        /* table-header is sticky; only scroll if it's stuck at viewport top */
        var isStuck = tableHeader.getBoundingClientRect().top <= 5;
        allTime.style.display = 'none';
        if (isStuck) {{
          header.scrollIntoView({{block: 'start'}});
        }}
      }});
    }});

    /* GOAT table toggle — click nav link or sticky header to show/hide */
    document.querySelectorAll('.decade-nav a[data-goat]').forEach(function(a) {{
      a.addEventListener('click', function(e) {{
        e.preventDefault();
        var tip = document.getElementById('goat-avg-tooltip');
        if (tip && tip.classList.contains('active')) return;
        var viewClass = stat === 'ted' ? '.view-ted' : '.view-tap';
        var goatDiv = document.querySelector(viewClass + ' .goat-table');
        var g2Div = document.querySelector(viewClass + ' .g2-table');
        var g3Div = document.querySelector(viewClass + ' .g3-table');
        var mgDiv = document.querySelector(viewClass + ' .mg-table');
        var diffDiv = document.querySelector(viewClass + ' .diff-table');
        if (!goatDiv) return;
        if (goatDiv.style.display !== 'none') {{
          goatDiv.style.display = 'none';
        }} else {{
          goatDiv.style.display = '';
          if (g2Div) g2Div.style.display = 'none';
          if (g3Div) g3Div.style.display = 'none';
          if (mgDiv) mgDiv.style.display = 'none';
          if (diffDiv) diffDiv.style.display = 'none';
        }}
      }});
    }});
    document.querySelectorAll('.goat-table').forEach(function(goat) {{
      var tableHeader = goat.querySelector('.table-header');
      if (tableHeader) tableHeader.addEventListener('click', function() {{
        var isStuck = tableHeader.getBoundingClientRect().top <= 5;
        goat.style.display = 'none';
        if (isStuck) {{
          var nav = goat.closest('.historical-section').querySelector('.decade-nav');
          if (nav) nav.scrollIntoView({{block: 'start'}});
        }}
      }});
    }});

    /* GOAT table sort modes:
       year        — default, sorted by year desc
       diff        — sorted by DIFF desc, orange line after row 30
       val         — sorted by TED/TAP value desc
       player      — sorted by appearance count (full list), tiebreak DIFF
       diff-player — top 30 DIFF only, sorted by appearance count within
                     top 30, tiebreak DIFF; rows 31+ hidden
       goatTextOpen — independent boolean: when true, shows cutoff message
                      text instead of orange separator line */
    var goatSortMode = 'year';
    var goatTextOpen = false;
    function goatSort(table, mode) {{
      var tbody = table.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll('tr:not(.goat-orange-sep):not(.goat-text-row)'));
      /* Helper: sort by DIFF desc */
      function sortByDiff(arr) {{
        arr.sort(function(a, b) {{
          return (parseFloat(b.cells[4].textContent) || 0) -
                 (parseFloat(a.cells[4].textContent) || 0);
        }});
      }}
      /* Helper: sort by appearance count desc, group by player.
         intraCol = column index for within-player sort (2=TED/TAP, 4=DIFF) */
      function sortByCount(arr, countMap, intraCol) {{
        /* Find each player's best DIFF for inter-player ordering */
        var bestDiff = {{}};
        arr.forEach(function(r) {{
          var n = r.cells[1].textContent.trim();
          var d = parseFloat(r.cells[4].textContent) || 0;
          if (bestDiff[n] === undefined || d > bestDiff[n]) bestDiff[n] = d;
        }});
        arr.sort(function(a, b) {{
          var na = a.cells[1].textContent.trim();
          var nb = b.cells[1].textContent.trim();
          var ca = countMap[na] || 0, cb = countMap[nb] || 0;
          if (cb !== ca) return cb - ca;
          /* Same count: group by player (higher best-DIFF player first) */
          if (na !== nb) return (bestDiff[nb] || 0) - (bestDiff[na] || 0);
          /* Same player: sort by intraCol desc */
          return (parseFloat(b.cells[intraCol].textContent) || 0) -
                 (parseFloat(a.cells[intraCol].textContent) || 0);
        }});
      }}
      if (mode === 'diff') {{
        sortByDiff(rows);
      }} else if (mode === 'val') {{
        rows.sort(function(a, b) {{
          return (parseFloat(b.cells[2].textContent) || 0) -
                 (parseFloat(a.cells[2].textContent) || 0);
        }});
      }} else if (mode === 'player') {{
        /* Count appearances across ALL rows */
        var counts = {{}};
        rows.forEach(function(r) {{
          var n = r.cells[1].textContent.trim();
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(rows, counts, 2); /* within player: sort by TED/TAP value */
      }} else if (mode === 'diff-player') {{
        /* Sort by DIFF first to identify top 30 */
        sortByDiff(rows);
        var top30 = rows.slice(0, 30);
        var rest = rows.slice(30);
        /* Count appearances within top 30 only */
        var counts = {{}};
        top30.forEach(function(r) {{
          var n = r.cells[1].textContent.trim();
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(top30, counts, 4); /* within player: sort by DIFF */
        rows = top30.concat(rest);
      }} else {{
        /* year sort */
        rows.sort(function(a, b) {{
          var ay = parseInt(a.cells[0].textContent.replace("'", '')) || 0;
          var by = parseInt(b.cells[0].textContent.replace("'", '')) || 0;
          ay = ay >= 60 ? 1900 + ay : 2000 + ay;
          by = by >= 60 ? 1900 + by : 2000 + by;
          return by - ay;
        }});
      }}
      /* Remove any previously inserted orange separator or text row */
      var oldSep = tbody.querySelector('.goat-orange-sep');
      if (oldSep) oldSep.remove();
      var oldTextRow = tbody.querySelector('.goat-text-row');
      if (oldTextRow) oldTextRow.remove();
      var truncate = (mode === 'diff-player');
      rows.forEach(function(r, i) {{
        var hide = (truncate && i >= 30);
        r.style.display = hide ? 'none' : '';
        for (var c = 0; c < r.cells.length; c++) {{
          r.cells[c].style.borderTop = '';
          r.cells[c].style.borderBottom = '';
          r.cells[c].style.paddingBottom = '';
        }}
        tbody.appendChild(r);
      }});
      /* Insert inline element at cutoff position in diff modes */
      if (mode === 'diff' || mode === 'diff-player') {{
        if (goatTextOpen) {{
          /* Insert text row inline at the cutoff position */
          var textRow = document.createElement('tr');
          textRow.className = 'goat-text-row';
          if (mode === 'diff-player') {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;min-height:2.4em;display:flex;align-items:center;justify-content:center">Watch out for the herd of GOATs above!</p></td>';
          }} else {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;max-width:23em;display:inline-block">Click <span style="font-weight:700;font-style:normal;color:#ee7623">PLAYER</span> above to sort the top 30 DIFF seasons and see your GOAT candidates!</p></td>';
          }}
          if (mode === 'diff') {{
            tbody.insertBefore(textRow, tbody.children[30]);
          }} else {{
            tbody.appendChild(textRow);
          }}
          textRow.addEventListener('click', function() {{
            goatTextOpen = false;
            goatApplySort();
          }});
        }} else {{
          /* Insert clickable orange separator line */
          var sep = document.createElement('tr');
          sep.className = 'goat-orange-sep';
          sep.innerHTML = '<td colspan="5">\\u00a0</td>';
          if (mode === 'diff') {{
            tbody.insertBefore(sep, tbody.children[30]);
          }} else {{
            tbody.appendChild(sep);
          }}
          sep.addEventListener('click', function() {{
            goatTextOpen = true;
            goatApplySort();
          }});
        }}
      }}
    }}
    function goatApplySort() {{
      document.querySelectorAll('.goat-table table').forEach(function(t) {{
        if (t.style.visibility === 'hidden') return;
        goatSort(t, goatSortMode);
      }});
      /* Hide/show placeholder year-table when rows are truncated */
      var hidePlaceholder = (goatSortMode === 'diff-player');
      document.querySelectorAll('.goat-table table[style*="visibility:hidden"]').forEach(function(t) {{
        t.closest('.year-table').style.display = hidePlaceholder ? 'none' : '';
      }});
    }}
    /* Scroll to top of GOAT table only when the sticky header is floating
       (user is deep in the list). If header is in natural position, stay put.
       Uses the non-sticky .goat-table container as scroll target because
       scrollIntoView() on sticky elements is unreliable (browser considers
       them "already visible" when stuck). */
    function goatScrollIfStuck(el) {{
      var hdr = el.closest('.year-table').querySelector('.table-header');
      if (hdr && hdr.getBoundingClientRect().top <= 5) {{
        el.closest('.goat-table').scrollIntoView({{block: 'start'}});
      }}
    }}
    document.querySelectorAll('.goat-sort-diff').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (goatSortMode === 'diff' || goatSortMode === 'diff-player') {{ goatSortMode = 'year'; goatTextOpen = false; }}
        else goatSortMode = 'diff';
        goatApplySort();
        goatScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.goat-sort-val').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        goatSortMode = goatSortMode === 'val' ? 'year' : 'val';
        goatTextOpen = false;
        goatApplySort();
        goatScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.goat-sort-yr').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        goatSortMode = 'year';
        goatTextOpen = false;
        goatApplySort();
        goatScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.goat-sort-player').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (goatSortMode === 'player') goatSortMode = 'year';
        else if (goatSortMode === 'diff-player') goatSortMode = 'diff';
        else if (goatSortMode === 'diff') goatSortMode = 'diff-player';
        else goatSortMode = 'player';
        goatApplySort();
        goatScrollIfStuck(th);
      }});
    }});
    /* TOP 9* tooltip */
    var avgTooltip = document.getElementById('goat-avg-tooltip');
    var statLabel = document.querySelector('.view-ted') &&
      window.getComputedStyle(document.querySelector('.view-ted')).display !== 'none' ? 'TED' : 'TAP';
    document.querySelectorAll('thead th.goat-avg').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        var isActive = avgTooltip.classList.contains('active');
        avgTooltip.classList.remove('active');
        if (isActive) return;
        var activeStat = 'TAP';
        document.querySelectorAll('.view-ted').forEach(function(v) {{
          if (window.getComputedStyle(v).display !== 'none' && v.querySelector('.goat-table')) activeStat = 'TED';
        }});
        avgTooltip.textContent = '* average of the top 9 ' + activeStat + ' scores that season excluding the winner (ie. avg of rank #2\u201310)';
        var rect = th.getBoundingClientRect();
        avgTooltip.style.left = Math.max(8, rect.left + rect.width / 2 - 130) + 'px';
        avgTooltip.style.top = (rect.bottom + 6) + 'px';
        avgTooltip.classList.add('active');
      }});
    }});
    document.addEventListener('click', function(e) {{
      if (avgTooltip.classList.contains('active')) {{
        avgTooltip.classList.remove('active');
        e.stopImmediatePropagation();
        e.preventDefault();
      }}
    }}, true);

    /* === G2 table toggle — click nav link or sticky header to show/hide === */
    document.querySelectorAll('.decade-nav a[data-g2]').forEach(function(a) {{
      a.addEventListener('click', function(e) {{
        e.preventDefault();
        var tip = document.getElementById('goat-avg-tooltip');
        if (tip && tip.classList.contains('active')) return;
        var viewClass = stat === 'ted' ? '.view-ted' : '.view-tap';
        var g2Div = document.querySelector(viewClass + ' .g2-table');
        var goatDiv = document.querySelector(viewClass + ' .goat-table');
        var g3Div = document.querySelector(viewClass + ' .g3-table');
        var mgDiv = document.querySelector(viewClass + ' .mg-table');
        var diffDiv = document.querySelector(viewClass + ' .diff-table');
        if (!g2Div) return;
        if (g2Div.style.display !== 'none') {{
          g2Div.style.display = 'none';
        }} else {{
          g2Div.style.display = '';
          if (goatDiv) goatDiv.style.display = 'none';
          if (g3Div) g3Div.style.display = 'none';
          if (mgDiv) mgDiv.style.display = 'none';
          if (diffDiv) diffDiv.style.display = 'none';
        }}
      }});
    }});
    document.querySelectorAll('.g2-table').forEach(function(g2) {{
      var tableHeader = g2.querySelector('.table-header');
      if (tableHeader) tableHeader.addEventListener('click', function() {{
        var isStuck = tableHeader.getBoundingClientRect().top <= 5;
        g2.style.display = 'none';
        if (isStuck) {{
          var nav = g2.closest('.historical-section').querySelector('.decade-nav');
          if (nav) nav.scrollIntoView({{block: 'start'}});
        }}
      }});
    }});

    /* G2 table sort modes — same as GOAT but independent state */
    var g2SortMode = 'year';
    var g2TextOpen = false;
    function g2Sort(table, mode) {{
      var tbody = table.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll('tr:not(.g2-orange-sep):not(.g2-text-row)'));
      /* Helper: get clean player name from data-player attribute */
      function getName(row) {{
        var td = row.cells[1];
        return td ? (td.getAttribute('data-player') || td.textContent.trim()) : '';
      }}
      function sortByDiff(arr) {{
        arr.sort(function(a, b) {{
          return (parseFloat(b.cells[4].textContent) || 0) -
                 (parseFloat(a.cells[4].textContent) || 0);
        }});
      }}
      function sortByCount(arr, countMap, intraCol) {{
        /* Build average DIFF per player for tiebreaking */
        var totalDiff = {{}};
        arr.forEach(function(r) {{
          var n = getName(r);
          var d = parseFloat(r.cells[4].textContent) || 0;
          totalDiff[n] = (totalDiff[n] || 0) + d;
        }});
        var avgDiff = {{}};
        for (var p in totalDiff) {{
          avgDiff[p] = totalDiff[p] / (countMap[p] || 1);
        }}
        arr.sort(function(a, b) {{
          var na = getName(a);
          var nb = getName(b);
          var ca = countMap[na] || 0, cb = countMap[nb] || 0;
          if (cb !== ca) return cb - ca;
          /* Same count: group by player (higher avg DIFF first) */
          if (na !== nb) return (avgDiff[nb] || 0) - (avgDiff[na] || 0);
          /* Same player: sort by intraCol desc */
          return (parseFloat(b.cells[intraCol].textContent) || 0) -
                 (parseFloat(a.cells[intraCol].textContent) || 0);
        }});
      }}
      if (mode === 'diff') {{
        sortByDiff(rows);
      }} else if (mode === 'val') {{
        rows.sort(function(a, b) {{
          return (parseFloat(b.cells[2].textContent) || 0) -
                 (parseFloat(a.cells[2].textContent) || 0);
        }});
      }} else if (mode === 'player') {{
        var counts = {{}};
        rows.forEach(function(r) {{
          var n = getName(r);
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(rows, counts, 2);
      }} else if (mode === 'diff-player') {{
        sortByDiff(rows);
        var top40 = rows.slice(0, 40);
        var rest = rows.slice(40);
        var counts = {{}};
        top40.forEach(function(r) {{
          var n = getName(r);
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(top40, counts, 4);
        rows = top40.concat(rest);
      }} else {{
        /* year sort — for G2 (two rows per year), sort by year desc then rank asc */
        rows.sort(function(a, b) {{
          var ayr = a.cells[0].textContent.replace("'", '').trim();
          var byr = b.cells[0].textContent.replace("'", '').trim();
          var ay = ayr ? parseInt(ayr) : -1;
          var by = byr ? parseInt(byr) : -1;
          if (ay === -1) ay = parseInt(a.getAttribute('data-sort-year') || '0');
          if (by === -1) by = parseInt(b.getAttribute('data-sort-year') || '0');
          ay = ay >= 60 ? 1900 + ay : 2000 + ay;
          by = by >= 60 ? 1900 + by : 2000 + by;
          if (by !== ay) return by - ay;
          var ra = parseInt(a.getAttribute('data-rank') || '1');
          var rb = parseInt(b.getAttribute('data-rank') || '1');
          return ra - rb;
        }});
      }}
      var oldSep = tbody.querySelector('.g2-orange-sep');
      if (oldSep) oldSep.remove();
      var oldTextRow = tbody.querySelector('.g2-text-row');
      if (oldTextRow) oldTextRow.remove();
      var truncate = (mode === 'diff-player');
      rows.forEach(function(r, i) {{
        var hide = (truncate && i >= 40);
        r.style.display = hide ? 'none' : '';
        for (var c = 0; c < r.cells.length; c++) {{
          r.cells[c].style.borderTop = '';
          r.cells[c].style.borderBottom = '';
          r.cells[c].style.paddingBottom = '';
        }}
        tbody.appendChild(r);
      }});
      if (mode === 'diff' || mode === 'diff-player') {{
        if (g2TextOpen) {{
          var textRow = document.createElement('tr');
          textRow.className = 'g2-text-row';
          if (mode === 'diff-player') {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;min-height:2.4em;display:flex;align-items:center;justify-content:center">Watch out for the herd of GOATs above!</p></td>';
          }} else {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;max-width:23em;display:inline-block">Click <span style="font-weight:700;font-style:normal;color:#ee7623">PLAYER</span> above to sort the top 40 DIFF seasons and see your GOAT candidates!</p></td>';
          }}
          if (mode === 'diff') {{
            tbody.insertBefore(textRow, tbody.children[40]);
          }} else {{
            tbody.appendChild(textRow);
          }}
          textRow.addEventListener('click', function() {{
            g2TextOpen = false;
            g2ApplySort();
          }});
        }} else {{
          var sep = document.createElement('tr');
          sep.className = 'g2-orange-sep';
          sep.innerHTML = '<td colspan="5">\\u00a0</td>';
          if (mode === 'diff') {{
            tbody.insertBefore(sep, tbody.children[40]);
          }} else {{
            tbody.appendChild(sep);
          }}
          sep.addEventListener('click', function() {{
            g2TextOpen = true;
            g2ApplySort();
          }});
        }}
      }}
    }}
    function g2ApplySort() {{
      document.querySelectorAll('.g2-table table').forEach(function(t) {{
        if (t.style.visibility === 'hidden') return;
        g2Sort(t, g2SortMode);
      }});
      var hidePlaceholder = (g2SortMode === 'diff-player');
      document.querySelectorAll('.g2-table table[style*="visibility:hidden"]').forEach(function(t) {{
        t.closest('.year-table').style.display = hidePlaceholder ? 'none' : '';
      }});
    }}
    function g2ScrollIfStuck(el) {{
      var hdr = el.closest('.year-table').querySelector('.table-header');
      if (hdr && hdr.getBoundingClientRect().top <= 5) {{
        el.closest('.g2-table').scrollIntoView({{block: 'start'}});
      }}
    }}
    document.querySelectorAll('.g2-sort-diff').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (g2SortMode === 'diff' || g2SortMode === 'diff-player') {{ g2SortMode = 'year'; g2TextOpen = false; }}
        else g2SortMode = 'diff';
        g2ApplySort();
        g2ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.g2-sort-val').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        g2SortMode = g2SortMode === 'val' ? 'year' : 'val';
        g2TextOpen = false;
        g2ApplySort();
        g2ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.g2-sort-yr').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        g2SortMode = 'year';
        g2TextOpen = false;
        g2ApplySort();
        g2ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.g2-sort-player').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (g2SortMode === 'player') g2SortMode = 'year';
        else if (g2SortMode === 'diff-player') g2SortMode = 'diff';
        else if (g2SortMode === 'diff') g2SortMode = 'diff-player';
        else g2SortMode = 'player';
        g2ApplySort();
        g2ScrollIfStuck(th);
      }});
    }});
    /* G2 TOP 9* tooltip — reuse same tooltip element */
    document.querySelectorAll('thead th.g2-avg').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        var isActive = avgTooltip.classList.contains('active');
        avgTooltip.classList.remove('active');
        if (isActive) return;
        var activeStat = 'TAP';
        document.querySelectorAll('.view-ted').forEach(function(v) {{
          if (window.getComputedStyle(v).display !== 'none' && v.querySelector('.g2-table')) activeStat = 'TED';
        }});
        avgTooltip.textContent = '* average of the top 9 ' + activeStat + ' scores that season excluding the winner (ie. avg of rank #2\u201310)';
        var rect = th.getBoundingClientRect();
        avgTooltip.style.left = Math.max(8, rect.left + rect.width / 2 - 130) + 'px';
        avgTooltip.style.top = (rect.bottom + 6) + 'px';
        avgTooltip.classList.add('active');
      }});
    }});

    /* Assign sort-year to G2 rank-2 rows (they have empty year cells) */
    document.querySelectorAll('.g2-table tbody').forEach(function(tbody) {{
      var lastYear = '';
      Array.from(tbody.children).forEach(function(tr) {{
        var yrCell = tr.cells && tr.cells[0] ? tr.cells[0].textContent.trim() : '';
        if (yrCell) lastYear = yrCell.replace("'", '');
        tr.setAttribute('data-sort-year', lastYear);
      }});
    }});

    /* === G3 table toggle — click nav link or sticky header to show/hide === */
    document.querySelectorAll('.decade-nav a[data-g3]').forEach(function(a) {{
      a.addEventListener('click', function(e) {{
        e.preventDefault();
        var tip = document.getElementById('goat-avg-tooltip');
        if (tip && tip.classList.contains('active')) return;
        var viewClass = stat === 'ted' ? '.view-ted' : '.view-tap';
        var g3Div = document.querySelector(viewClass + ' .g3-table');
        var goatDiv = document.querySelector(viewClass + ' .goat-table');
        var g2Div = document.querySelector(viewClass + ' .g2-table');
        var mgDiv = document.querySelector(viewClass + ' .mg-table');
        var diffDiv = document.querySelector(viewClass + ' .diff-table');
        if (!g3Div) return;
        if (g3Div.style.display !== 'none') {{
          g3Div.style.display = 'none';
        }} else {{
          g3Div.style.display = '';
          if (goatDiv) goatDiv.style.display = 'none';
          if (g2Div) g2Div.style.display = 'none';
          if (mgDiv) mgDiv.style.display = 'none';
          if (diffDiv) diffDiv.style.display = 'none';
        }}
      }});
    }});
    document.querySelectorAll('.g3-table').forEach(function(g3) {{
      var tableHeader = g3.querySelector('.table-header');
      if (tableHeader) tableHeader.addEventListener('click', function() {{
        var isStuck = tableHeader.getBoundingClientRect().top <= 5;
        g3.style.display = 'none';
        if (isStuck) {{
          var nav = g3.closest('.historical-section').querySelector('.decade-nav');
          if (nav) nav.scrollIntoView({{block: 'start'}});
        }}
      }});
    }});

    /* G3 table sort modes — same as G2 but independent state */
    var g3SortMode = 'year';
    var g3TextOpen = false;
    function g3Sort(table, mode) {{
      var tbody = table.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll('tr:not(.g3-orange-sep):not(.g3-text-row)'));
      function getName(row) {{
        var td = row.cells[1];
        return td ? (td.getAttribute('data-player') || td.textContent.trim()) : '';
      }}
      function sortByDiff(arr) {{
        arr.sort(function(a, b) {{
          return (parseFloat(b.cells[4].textContent) || 0) -
                 (parseFloat(a.cells[4].textContent) || 0);
        }});
      }}
      function sortByCount(arr, countMap, intraCol) {{
        var totalDiff = {{}};
        arr.forEach(function(r) {{
          var n = getName(r);
          var d = parseFloat(r.cells[4].textContent) || 0;
          totalDiff[n] = (totalDiff[n] || 0) + d;
        }});
        var avgDiff = {{}};
        for (var p in totalDiff) {{
          avgDiff[p] = totalDiff[p] / (countMap[p] || 1);
        }}
        arr.sort(function(a, b) {{
          var na = getName(a);
          var nb = getName(b);
          var ca = countMap[na] || 0, cb = countMap[nb] || 0;
          if (cb !== ca) return cb - ca;
          if (na !== nb) return (avgDiff[nb] || 0) - (avgDiff[na] || 0);
          return (parseFloat(b.cells[intraCol].textContent) || 0) -
                 (parseFloat(a.cells[intraCol].textContent) || 0);
        }});
      }}
      if (mode === 'diff') {{
        sortByDiff(rows);
      }} else if (mode === 'val') {{
        rows.sort(function(a, b) {{
          return (parseFloat(b.cells[2].textContent) || 0) -
                 (parseFloat(a.cells[2].textContent) || 0);
        }});
      }} else if (mode === 'player') {{
        var counts = {{}};
        rows.forEach(function(r) {{
          var n = getName(r);
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(rows, counts, 2);
      }} else if (mode === 'diff-player') {{
        sortByDiff(rows);
        var top50 = rows.slice(0, 50);
        var rest = rows.slice(50);
        var counts = {{}};
        top50.forEach(function(r) {{
          var n = getName(r);
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(top50, counts, 4);
        rows = top50.concat(rest);
      }} else {{
        rows.sort(function(a, b) {{
          var ayr = a.cells[0].textContent.replace("'", '').trim();
          var byr = b.cells[0].textContent.replace("'", '').trim();
          var ay = ayr ? parseInt(ayr) : -1;
          var by = byr ? parseInt(byr) : -1;
          if (ay === -1) ay = parseInt(a.getAttribute('data-sort-year') || '0');
          if (by === -1) by = parseInt(b.getAttribute('data-sort-year') || '0');
          ay = ay >= 60 ? 1900 + ay : 2000 + ay;
          by = by >= 60 ? 1900 + by : 2000 + by;
          if (by !== ay) return by - ay;
          var ra = parseInt(a.getAttribute('data-rank') || '1');
          var rb = parseInt(b.getAttribute('data-rank') || '1');
          return ra - rb;
        }});
      }}
      var oldSep = tbody.querySelector('.g3-orange-sep');
      if (oldSep) oldSep.remove();
      var oldTextRow = tbody.querySelector('.g3-text-row');
      if (oldTextRow) oldTextRow.remove();
      var truncate = (mode === 'diff-player');
      rows.forEach(function(r, i) {{
        var hide = (truncate && i >= 50);
        r.style.display = hide ? 'none' : '';
        for (var c = 0; c < r.cells.length; c++) {{
          r.cells[c].style.borderTop = '';
          r.cells[c].style.borderBottom = '';
          r.cells[c].style.paddingBottom = '';
        }}
        tbody.appendChild(r);
      }});
      if (mode === 'diff' || mode === 'diff-player') {{
        if (g3TextOpen) {{
          var textRow = document.createElement('tr');
          textRow.className = 'g3-text-row';
          if (mode === 'diff-player') {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;min-height:2.4em;display:flex;align-items:center;justify-content:center">Watch out for the herd of GOATs above!</p></td>';
          }} else {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;max-width:23em;display:inline-block">Click <span style="font-weight:700;font-style:normal;color:#ee7623">PLAYER</span> above to sort the top 50 DIFF seasons and see your GOAT candidates!</p></td>';
          }}
          if (mode === 'diff') {{
            tbody.insertBefore(textRow, tbody.children[50]);
          }} else {{
            tbody.appendChild(textRow);
          }}
          textRow.addEventListener('click', function() {{
            g3TextOpen = false;
            g3ApplySort();
          }});
        }} else {{
          var sep = document.createElement('tr');
          sep.className = 'g3-orange-sep';
          sep.innerHTML = '<td colspan="5">\\u00a0</td>';
          if (mode === 'diff') {{
            tbody.insertBefore(sep, tbody.children[50]);
          }} else {{
            tbody.appendChild(sep);
          }}
          sep.addEventListener('click', function() {{
            g3TextOpen = true;
            g3ApplySort();
          }});
        }}
      }}
    }}
    function g3ApplySort() {{
      document.querySelectorAll('.g3-table table').forEach(function(t) {{
        if (t.style.visibility === 'hidden') return;
        g3Sort(t, g3SortMode);
      }});
      var hidePlaceholder = (g3SortMode === 'diff-player');
      document.querySelectorAll('.g3-table table[style*="visibility:hidden"]').forEach(function(t) {{
        t.closest('.year-table').style.display = hidePlaceholder ? 'none' : '';
      }});
    }}
    function g3ScrollIfStuck(el) {{
      var hdr = el.closest('.year-table').querySelector('.table-header');
      if (hdr && hdr.getBoundingClientRect().top <= 5) {{
        el.closest('.g3-table').scrollIntoView({{block: 'start'}});
      }}
    }}
    document.querySelectorAll('.g3-sort-diff').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (g3SortMode === 'diff' || g3SortMode === 'diff-player') {{ g3SortMode = 'year'; g3TextOpen = false; }}
        else g3SortMode = 'diff';
        g3ApplySort();
        g3ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.g3-sort-val').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        g3SortMode = g3SortMode === 'val' ? 'year' : 'val';
        g3TextOpen = false;
        g3ApplySort();
        g3ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.g3-sort-yr').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        g3SortMode = 'year';
        g3TextOpen = false;
        g3ApplySort();
        g3ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.g3-sort-player').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (g3SortMode === 'player') g3SortMode = 'year';
        else if (g3SortMode === 'diff-player') g3SortMode = 'diff';
        else if (g3SortMode === 'diff') g3SortMode = 'diff-player';
        else g3SortMode = 'player';
        g3ApplySort();
        g3ScrollIfStuck(th);
      }});
    }});
    /* G3 TOP 9* tooltip — reuse same tooltip element */
    document.querySelectorAll('thead th.g3-avg').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        var isActive = avgTooltip.classList.contains('active');
        avgTooltip.classList.remove('active');
        if (isActive) return;
        var activeStat = 'TAP';
        document.querySelectorAll('.view-ted').forEach(function(v) {{
          if (window.getComputedStyle(v).display !== 'none' && v.querySelector('.g3-table')) activeStat = 'TED';
        }});
        avgTooltip.textContent = '* average of the top 9 ' + activeStat + ' scores that season excluding the winner (ie. avg of rank #2\u201310)';
        var rect = th.getBoundingClientRect();
        avgTooltip.style.left = Math.max(8, rect.left + rect.width / 2 - 130) + 'px';
        avgTooltip.style.top = (rect.bottom + 6) + 'px';
        avgTooltip.classList.add('active');
      }});
    }});

    /* Assign sort-year to G3 rows */
    document.querySelectorAll('.g3-table tbody').forEach(function(tbody) {{
      var lastYear = '';
      Array.from(tbody.children).forEach(function(tr) {{
        var yrCell = tr.cells && tr.cells[0] ? tr.cells[0].textContent.trim() : '';
        if (yrCell) lastYear = yrCell.replace("'", '');
        tr.setAttribute('data-sort-year', lastYear);
      }});
    }});

    /* === MG (Modern GOAT) table toggle — click nav link to show/hide, header to cycle sub-views === */
    document.querySelectorAll('.decade-nav a[data-mg]').forEach(function(a) {{
      a.addEventListener('click', function(e) {{
        e.preventDefault();
        var tip = document.getElementById('goat-avg-tooltip');
        if (tip && tip.classList.contains('active')) return;
        var viewClass = stat === 'ted' ? '.view-ted' : '.view-tap';
        var mgDiv = document.querySelector(viewClass + ' .mg-table');
        var goatDiv = document.querySelector(viewClass + ' .goat-table');
        var g2Div = document.querySelector(viewClass + ' .g2-table');
        var g3Div = document.querySelector(viewClass + ' .g3-table');
        if (!mgDiv) return;
        if (mgDiv.style.display !== 'none') {{
          mgDiv.style.display = 'none';
        }} else {{
          mgDiv.style.display = '';
          /* Show first sub-view, hide others */
          var v1 = mgDiv.querySelector('.mg-goat-view');
          var v2 = mgDiv.querySelector('.mg-g2-view');
          var v3 = mgDiv.querySelector('.mg-g3-view');
          if (v1) v1.style.display = '';
          if (v2) v2.style.display = 'none';
          if (v3) v3.style.display = 'none';
          var diffDiv = document.querySelector(viewClass + ' .diff-table');
          if (goatDiv) goatDiv.style.display = 'none';
          if (g2Div) g2Div.style.display = 'none';
          if (g3Div) g3Div.style.display = 'none';
          if (diffDiv) diffDiv.style.display = 'none';
        }}
      }});
    }});

    /* MG header cycling: click header to cycle mg-goat-view → mg-g2-view → mg-g3-view → mg-goat-view */
    document.querySelectorAll('.mg-table').forEach(function(mg) {{
      mg.addEventListener('click', function(e) {{
        var header = e.target.closest('.table-header');
        if (!header) return;
        var view = header.closest('.mg-goat-view') || header.closest('.mg-g2-view') || header.closest('.mg-g3-view');
        if (!view) return;
        var v1 = mg.querySelector('.mg-goat-view');
        var v2 = mg.querySelector('.mg-g2-view');
        var v3 = mg.querySelector('.mg-g3-view');
        var isStuck = header.getBoundingClientRect().top <= 5;
        if (view.classList.contains('mg-goat-view')) {{
          v1.style.display = 'none';
          v2.style.display = '';
          v3.style.display = 'none';
        }} else if (view.classList.contains('mg-g2-view')) {{
          v1.style.display = 'none';
          v2.style.display = 'none';
          v3.style.display = '';
        }} else {{
          v1.style.display = '';
          v2.style.display = 'none';
          v3.style.display = 'none';
        }}
        if (isStuck) {{
          mg.scrollIntoView({{block: 'start'}});
        }}
      }});
    }});

    /* MG1 (Modern GOAT) sort modes — same pattern as GOAT, cutoff 20 */
    var mg1SortMode = 'year';
    var mg1TextOpen = false;
    function mg1Sort(table, mode) {{
      var tbody = table.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll('tr:not(.mg1-orange-sep):not(.mg1-text-row)'));
      function sortByDiff(arr) {{
        arr.sort(function(a, b) {{
          return (parseFloat(b.cells[4].textContent) || 0) -
                 (parseFloat(a.cells[4].textContent) || 0);
        }});
      }}
      function sortByCount(arr, countMap, intraCol) {{
        var bestDiff = {{}};
        arr.forEach(function(r) {{
          var n = r.cells[1].textContent.trim();
          var d = parseFloat(r.cells[4].textContent) || 0;
          if (bestDiff[n] === undefined || d > bestDiff[n]) bestDiff[n] = d;
        }});
        arr.sort(function(a, b) {{
          var na = a.cells[1].textContent.trim();
          var nb = b.cells[1].textContent.trim();
          var ca = countMap[na] || 0, cb = countMap[nb] || 0;
          if (cb !== ca) return cb - ca;
          if (na !== nb) {{
            var da = bestDiff[na] || 0, db = bestDiff[nb] || 0;
            if (db !== da) return db - da;
            return na < nb ? -1 : 1;
          }}
          return (parseFloat(b.cells[intraCol].textContent) || 0) -
                 (parseFloat(a.cells[intraCol].textContent) || 0);
        }});
      }}
      if (mode === 'diff') {{
        sortByDiff(rows);
      }} else if (mode === 'val') {{
        rows.sort(function(a, b) {{
          return (parseFloat(b.cells[2].textContent) || 0) -
                 (parseFloat(a.cells[2].textContent) || 0);
        }});
      }} else if (mode === 'player') {{
        var counts = {{}};
        rows.forEach(function(r) {{
          var n = r.cells[1].textContent.trim();
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(rows, counts, 2);
      }} else if (mode === 'diff-player') {{
        sortByDiff(rows);
        var top20 = rows.slice(0, 20);
        var rest = rows.slice(20);
        var counts = {{}};
        top20.forEach(function(r) {{
          var n = r.cells[1].textContent.trim();
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(top20, counts, 4);
        rows = top20.concat(rest);
      }} else {{
        rows.sort(function(a, b) {{
          var ay = parseInt(a.cells[0].textContent.replace("'", '')) || 0;
          var by = parseInt(b.cells[0].textContent.replace("'", '')) || 0;
          ay = ay >= 60 ? 1900 + ay : 2000 + ay;
          by = by >= 60 ? 1900 + by : 2000 + by;
          return by - ay;
        }});
      }}
      var oldSep = tbody.querySelector('.mg1-orange-sep');
      if (oldSep) oldSep.remove();
      var oldTextRow = tbody.querySelector('.mg1-text-row');
      if (oldTextRow) oldTextRow.remove();
      var truncate = (mode === 'diff-player');
      rows.forEach(function(r, i) {{
        var hide = (truncate && i >= 20);
        r.style.display = hide ? 'none' : '';
        for (var c = 0; c < r.cells.length; c++) {{
          r.cells[c].style.borderTop = '';
          r.cells[c].style.borderBottom = '';
          r.cells[c].style.paddingBottom = '';
        }}
        tbody.appendChild(r);
      }});
      if (mode === 'diff' || mode === 'diff-player') {{
        if (mg1TextOpen) {{
          var textRow = document.createElement('tr');
          textRow.className = 'mg1-text-row';
          if (mode === 'diff-player') {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;min-height:2.4em;display:flex;align-items:center;justify-content:center">Watch out for the herd of GOATs above!</p></td>';
          }} else {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 4px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;display:inline-block">Click <span style="font-weight:700;font-style:normal;color:#ee7623">PLAYER</span> above to sort the top 20 DIFF seasons and see your modern GOAT candidates!</p></td>';
          }}
          if (mode === 'diff') {{
            tbody.insertBefore(textRow, tbody.children[20]);
          }} else {{
            tbody.appendChild(textRow);
          }}
          textRow.addEventListener('click', function() {{
            mg1TextOpen = false;
            mg1ApplySort();
          }});
        }} else {{
          var sep = document.createElement('tr');
          sep.className = 'mg1-orange-sep';
          sep.innerHTML = '<td colspan="5">\\u00a0</td>';
          if (mode === 'diff') {{
            tbody.insertBefore(sep, tbody.children[20]);
          }} else {{
            tbody.appendChild(sep);
          }}
          sep.addEventListener('click', function() {{
            mg1TextOpen = true;
            mg1ApplySort();
          }});
        }}
      }}
    }}
    function mg1ApplySort() {{
      document.querySelectorAll('.mg-table .mg-goat-view table').forEach(function(t) {{
        if (t.style.visibility === 'hidden') return;
        mg1Sort(t, mg1SortMode);
      }});
      var hidePlaceholder = (mg1SortMode === 'diff-player');
      document.querySelectorAll('.mg-table .mg-goat-view table[style*="visibility:hidden"]').forEach(function(t) {{
        t.closest('.year-table').style.display = hidePlaceholder ? 'none' : '';
      }});
    }}
    function mg1ScrollIfStuck(el) {{
      var hdr = el.closest('.year-table').querySelector('.table-header');
      if (hdr && hdr.getBoundingClientRect().top <= 5) {{
        el.closest('.mg-table').scrollIntoView({{block: 'start'}});
      }}
    }}
    document.querySelectorAll('.mg1-sort-diff').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (mg1SortMode === 'diff' || mg1SortMode === 'diff-player') {{ mg1SortMode = 'year'; mg1TextOpen = false; }}
        else mg1SortMode = 'diff';
        mg1ApplySort();
        mg1ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg1-sort-val').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        mg1SortMode = mg1SortMode === 'val' ? 'year' : 'val';
        mg1TextOpen = false;
        mg1ApplySort();
        mg1ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg1-sort-yr').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        mg1SortMode = 'year';
        mg1TextOpen = false;
        mg1ApplySort();
        mg1ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg1-sort-player').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (mg1SortMode === 'player') mg1SortMode = 'year';
        else if (mg1SortMode === 'diff-player') mg1SortMode = 'diff';
        else if (mg1SortMode === 'diff') mg1SortMode = 'diff-player';
        else mg1SortMode = 'player';
        mg1ApplySort();
        mg1ScrollIfStuck(th);
      }});
    }});
    /* MG1 TOP 9* tooltip — always shows 'TAPD' */
    document.querySelectorAll('thead th.mg1-avg').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        var isActive = avgTooltip.classList.contains('active');
        avgTooltip.classList.remove('active');
        if (isActive) return;
        avgTooltip.textContent = '* average of the top 9 TAPD scores that season excluding the winner (ie. avg of rank #2\u201310)';
        var rect = th.getBoundingClientRect();
        avgTooltip.style.left = Math.max(8, rect.left + rect.width / 2 - 130) + 'px';
        avgTooltip.style.top = (rect.bottom + 6) + 'px';
        avgTooltip.classList.add('active');
      }});
    }});

    /* MG2 sort modes — same as G2 but cutoff 30 */
    var mg2SortMode = 'year';
    var mg2TextOpen = false;
    function mg2Sort(table, mode) {{
      var tbody = table.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll('tr:not(.mg2-orange-sep):not(.mg2-text-row)'));
      function getName(row) {{
        var td = row.cells[1];
        return td ? (td.getAttribute('data-player') || td.textContent.trim()) : '';
      }}
      function sortByDiff(arr) {{
        arr.sort(function(a, b) {{
          return (parseFloat(b.cells[4].textContent) || 0) -
                 (parseFloat(a.cells[4].textContent) || 0);
        }});
      }}
      function sortByCount(arr, countMap, intraCol) {{
        var totalDiff = {{}};
        arr.forEach(function(r) {{
          var n = getName(r);
          var d = parseFloat(r.cells[4].textContent) || 0;
          totalDiff[n] = (totalDiff[n] || 0) + d;
        }});
        var avgDiff = {{}};
        for (var p in totalDiff) {{
          avgDiff[p] = totalDiff[p] / (countMap[p] || 1);
        }}
        arr.sort(function(a, b) {{
          var na = getName(a);
          var nb = getName(b);
          var ca = countMap[na] || 0, cb = countMap[nb] || 0;
          if (cb !== ca) return cb - ca;
          if (na !== nb) {{
            var da = avgDiff[na] || 0, db = avgDiff[nb] || 0;
            if (db !== da) return db - da;
            return na < nb ? -1 : 1;
          }}
          return (parseFloat(b.cells[intraCol].textContent) || 0) -
                 (parseFloat(a.cells[intraCol].textContent) || 0);
        }});
      }}
      if (mode === 'diff') {{
        sortByDiff(rows);
      }} else if (mode === 'val') {{
        rows.sort(function(a, b) {{
          return (parseFloat(b.cells[2].textContent) || 0) -
                 (parseFloat(a.cells[2].textContent) || 0);
        }});
      }} else if (mode === 'player') {{
        var counts = {{}};
        rows.forEach(function(r) {{
          var n = getName(r);
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(rows, counts, 2);
      }} else if (mode === 'diff-player') {{
        sortByDiff(rows);
        var top30 = rows.slice(0, 30);
        var rest = rows.slice(30);
        var counts = {{}};
        top30.forEach(function(r) {{
          var n = getName(r);
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(top30, counts, 4);
        rows = top30.concat(rest);
      }} else {{
        rows.sort(function(a, b) {{
          var ayr = a.cells[0].textContent.replace("'", '').trim();
          var byr = b.cells[0].textContent.replace("'", '').trim();
          var ay = ayr ? parseInt(ayr) : -1;
          var by = byr ? parseInt(byr) : -1;
          if (ay === -1) ay = parseInt(a.getAttribute('data-sort-year') || '0');
          if (by === -1) by = parseInt(b.getAttribute('data-sort-year') || '0');
          ay = ay >= 60 ? 1900 + ay : 2000 + ay;
          by = by >= 60 ? 1900 + by : 2000 + by;
          if (by !== ay) return by - ay;
          var ra = parseInt(a.getAttribute('data-rank') || '1');
          var rb = parseInt(b.getAttribute('data-rank') || '1');
          return ra - rb;
        }});
      }}
      var oldSep = tbody.querySelector('.mg2-orange-sep');
      if (oldSep) oldSep.remove();
      var oldTextRow = tbody.querySelector('.mg2-text-row');
      if (oldTextRow) oldTextRow.remove();
      var truncate = (mode === 'diff-player');
      rows.forEach(function(r, i) {{
        var hide = (truncate && i >= 30);
        r.style.display = hide ? 'none' : '';
        for (var c = 0; c < r.cells.length; c++) {{
          r.cells[c].style.borderTop = '';
          r.cells[c].style.borderBottom = '';
          r.cells[c].style.paddingBottom = '';
        }}
        tbody.appendChild(r);
      }});
      if (mode === 'diff' || mode === 'diff-player') {{
        if (mg2TextOpen) {{
          var textRow = document.createElement('tr');
          textRow.className = 'mg2-text-row';
          if (mode === 'diff-player') {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;min-height:2.4em;display:flex;align-items:center;justify-content:center">Watch out for the herd of GOATs above!</p></td>';
          }} else {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 4px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;max-width:28em;display:inline-block">Click <span style="font-weight:700;font-style:normal;color:#ee7623">PLAYER</span> above to sort the top 30 DIFF seasons and see your modern GOAT candidates!</p></td>';
          }}
          if (mode === 'diff') {{
            tbody.insertBefore(textRow, tbody.children[30]);
          }} else {{
            tbody.appendChild(textRow);
          }}
          textRow.addEventListener('click', function() {{
            mg2TextOpen = false;
            mg2ApplySort();
          }});
        }} else {{
          var sep = document.createElement('tr');
          sep.className = 'mg2-orange-sep';
          sep.innerHTML = '<td colspan="5">\\u00a0</td>';
          if (mode === 'diff') {{
            tbody.insertBefore(sep, tbody.children[30]);
          }} else {{
            tbody.appendChild(sep);
          }}
          sep.addEventListener('click', function() {{
            mg2TextOpen = true;
            mg2ApplySort();
          }});
        }}
      }}
    }}
    function mg2ApplySort() {{
      document.querySelectorAll('.mg-table .mg-g2-view table').forEach(function(t) {{
        if (t.style.visibility === 'hidden') return;
        mg2Sort(t, mg2SortMode);
      }});
      var hidePlaceholder = (mg2SortMode === 'diff-player');
      document.querySelectorAll('.mg-table .mg-g2-view table[style*="visibility:hidden"]').forEach(function(t) {{
        t.closest('.year-table').style.display = hidePlaceholder ? 'none' : '';
      }});
    }}
    function mg2ScrollIfStuck(el) {{
      var hdr = el.closest('.year-table').querySelector('.table-header');
      if (hdr && hdr.getBoundingClientRect().top <= 5) {{
        el.closest('.mg-table').scrollIntoView({{block: 'start'}});
      }}
    }}
    document.querySelectorAll('.mg2-sort-diff').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (mg2SortMode === 'diff' || mg2SortMode === 'diff-player') {{ mg2SortMode = 'year'; mg2TextOpen = false; }}
        else mg2SortMode = 'diff';
        mg2ApplySort();
        mg2ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg2-sort-val').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        mg2SortMode = mg2SortMode === 'val' ? 'year' : 'val';
        mg2TextOpen = false;
        mg2ApplySort();
        mg2ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg2-sort-yr').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        mg2SortMode = 'year';
        mg2TextOpen = false;
        mg2ApplySort();
        mg2ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg2-sort-player').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (mg2SortMode === 'player') mg2SortMode = 'year';
        else if (mg2SortMode === 'diff-player') mg2SortMode = 'diff';
        else if (mg2SortMode === 'diff') mg2SortMode = 'diff-player';
        else mg2SortMode = 'player';
        mg2ApplySort();
        mg2ScrollIfStuck(th);
      }});
    }});
    /* MG2 TOP 9* tooltip — always shows 'TAPD' */
    document.querySelectorAll('thead th.mg2-avg').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        var isActive = avgTooltip.classList.contains('active');
        avgTooltip.classList.remove('active');
        if (isActive) return;
        avgTooltip.textContent = '* average of the top 9 TAPD scores that season excluding the winner (ie. avg of rank #2\u201310)';
        var rect = th.getBoundingClientRect();
        avgTooltip.style.left = Math.max(8, rect.left + rect.width / 2 - 130) + 'px';
        avgTooltip.style.top = (rect.bottom + 6) + 'px';
        avgTooltip.classList.add('active');
      }});
    }});
    /* Assign sort-year to MG2 rows */
    document.querySelectorAll('.mg-table .mg-g2-view tbody').forEach(function(tbody) {{
      var lastYear = '';
      Array.from(tbody.children).forEach(function(tr) {{
        var yrCell = tr.cells && tr.cells[0] ? tr.cells[0].textContent.trim() : '';
        if (yrCell) lastYear = yrCell.replace("'", '');
        tr.setAttribute('data-sort-year', lastYear);
      }});
    }});

    /* MG3 sort modes — same as G3 but cutoff 40 */
    var mg3SortMode = 'year';
    var mg3TextOpen = false;
    function mg3Sort(table, mode) {{
      var tbody = table.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll('tr:not(.mg3-orange-sep):not(.mg3-text-row)'));
      function getName(row) {{
        var td = row.cells[1];
        return td ? (td.getAttribute('data-player') || td.textContent.trim()) : '';
      }}
      function sortByDiff(arr) {{
        arr.sort(function(a, b) {{
          return (parseFloat(b.cells[4].textContent) || 0) -
                 (parseFloat(a.cells[4].textContent) || 0);
        }});
      }}
      function sortByCount(arr, countMap, intraCol) {{
        var totalDiff = {{}};
        arr.forEach(function(r) {{
          var n = getName(r);
          var d = parseFloat(r.cells[4].textContent) || 0;
          totalDiff[n] = (totalDiff[n] || 0) + d;
        }});
        var avgDiff = {{}};
        for (var p in totalDiff) {{
          avgDiff[p] = totalDiff[p] / (countMap[p] || 1);
        }}
        arr.sort(function(a, b) {{
          var na = getName(a);
          var nb = getName(b);
          var ca = countMap[na] || 0, cb = countMap[nb] || 0;
          if (cb !== ca) return cb - ca;
          if (na !== nb) {{
            var da = avgDiff[na] || 0, db = avgDiff[nb] || 0;
            if (db !== da) return db - da;
            return na < nb ? -1 : 1;
          }}
          return (parseFloat(b.cells[intraCol].textContent) || 0) -
                 (parseFloat(a.cells[intraCol].textContent) || 0);
        }});
      }}
      if (mode === 'diff') {{
        sortByDiff(rows);
      }} else if (mode === 'val') {{
        rows.sort(function(a, b) {{
          return (parseFloat(b.cells[2].textContent) || 0) -
                 (parseFloat(a.cells[2].textContent) || 0);
        }});
      }} else if (mode === 'player') {{
        var counts = {{}};
        rows.forEach(function(r) {{
          var n = getName(r);
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(rows, counts, 2);
      }} else if (mode === 'diff-player') {{
        sortByDiff(rows);
        var top40 = rows.slice(0, 40);
        var rest = rows.slice(40);
        var counts = {{}};
        top40.forEach(function(r) {{
          var n = getName(r);
          counts[n] = (counts[n] || 0) + 1;
        }});
        sortByCount(top40, counts, 4);
        rows = top40.concat(rest);
      }} else {{
        rows.sort(function(a, b) {{
          var ayr = a.cells[0].textContent.replace("'", '').trim();
          var byr = b.cells[0].textContent.replace("'", '').trim();
          var ay = ayr ? parseInt(ayr) : -1;
          var by = byr ? parseInt(byr) : -1;
          if (ay === -1) ay = parseInt(a.getAttribute('data-sort-year') || '0');
          if (by === -1) by = parseInt(b.getAttribute('data-sort-year') || '0');
          ay = ay >= 60 ? 1900 + ay : 2000 + ay;
          by = by >= 60 ? 1900 + by : 2000 + by;
          if (by !== ay) return by - ay;
          var ra = parseInt(a.getAttribute('data-rank') || '1');
          var rb = parseInt(b.getAttribute('data-rank') || '1');
          return ra - rb;
        }});
      }}
      var oldSep = tbody.querySelector('.mg3-orange-sep');
      if (oldSep) oldSep.remove();
      var oldTextRow = tbody.querySelector('.mg3-text-row');
      if (oldTextRow) oldTextRow.remove();
      var truncate = (mode === 'diff-player');
      rows.forEach(function(r, i) {{
        var hide = (truncate && i >= 40);
        r.style.display = hide ? 'none' : '';
        for (var c = 0; c < r.cells.length; c++) {{
          r.cells[c].style.borderTop = '';
          r.cells[c].style.borderBottom = '';
          r.cells[c].style.paddingBottom = '';
        }}
        tbody.appendChild(r);
      }});
      if (mode === 'diff' || mode === 'diff-player') {{
        if (mg3TextOpen) {{
          var textRow = document.createElement('tr');
          textRow.className = 'mg3-text-row';
          if (mode === 'diff-player') {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 16px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;min-height:2.4em;display:flex;align-items:center;justify-content:center">Watch out for the herd of GOATs above!</p></td>';
          }} else {{
            textRow.innerHTML = '<td colspan="5" style="text-align:center;padding:12px 4px;cursor:pointer;border:none;background:#000"><p style="font-family:Georgia,serif;font-size:0.85em;font-style:italic;color:#ee7623;margin:0;max-width:28em;display:inline-block">Click <span style="font-weight:700;font-style:normal;color:#ee7623">PLAYER</span> above to sort the top 40 DIFF seasons and see your modern GOAT candidates!</p></td>';
          }}
          if (mode === 'diff') {{
            tbody.insertBefore(textRow, tbody.children[40]);
          }} else {{
            tbody.appendChild(textRow);
          }}
          textRow.addEventListener('click', function() {{
            mg3TextOpen = false;
            mg3ApplySort();
          }});
        }} else {{
          var sep = document.createElement('tr');
          sep.className = 'mg3-orange-sep';
          sep.innerHTML = '<td colspan="5">\\u00a0</td>';
          if (mode === 'diff') {{
            tbody.insertBefore(sep, tbody.children[40]);
          }} else {{
            tbody.appendChild(sep);
          }}
          sep.addEventListener('click', function() {{
            mg3TextOpen = true;
            mg3ApplySort();
          }});
        }}
      }}
    }}
    function mg3ApplySort() {{
      document.querySelectorAll('.mg-table .mg-g3-view table').forEach(function(t) {{
        if (t.style.visibility === 'hidden') return;
        mg3Sort(t, mg3SortMode);
      }});
      var hidePlaceholder = (mg3SortMode === 'diff-player');
      document.querySelectorAll('.mg-table .mg-g3-view table[style*="visibility:hidden"]').forEach(function(t) {{
        t.closest('.year-table').style.display = hidePlaceholder ? 'none' : '';
      }});
    }}
    function mg3ScrollIfStuck(el) {{
      var hdr = el.closest('.year-table').querySelector('.table-header');
      if (hdr && hdr.getBoundingClientRect().top <= 5) {{
        el.closest('.mg-table').scrollIntoView({{block: 'start'}});
      }}
    }}
    document.querySelectorAll('.mg3-sort-diff').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (mg3SortMode === 'diff' || mg3SortMode === 'diff-player') {{ mg3SortMode = 'year'; mg3TextOpen = false; }}
        else mg3SortMode = 'diff';
        mg3ApplySort();
        mg3ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg3-sort-val').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        mg3SortMode = mg3SortMode === 'val' ? 'year' : 'val';
        mg3TextOpen = false;
        mg3ApplySort();
        mg3ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg3-sort-yr').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        mg3SortMode = 'year';
        mg3TextOpen = false;
        mg3ApplySort();
        mg3ScrollIfStuck(th);
      }});
    }});
    document.querySelectorAll('.mg3-sort-player').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        if (mg3SortMode === 'player') mg3SortMode = 'year';
        else if (mg3SortMode === 'diff-player') mg3SortMode = 'diff';
        else if (mg3SortMode === 'diff') mg3SortMode = 'diff-player';
        else mg3SortMode = 'player';
        mg3ApplySort();
        mg3ScrollIfStuck(th);
      }});
    }});
    /* MG3 TOP 9* tooltip — always shows 'TAPD' */
    document.querySelectorAll('thead th.mg3-avg').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        var isActive = avgTooltip.classList.contains('active');
        avgTooltip.classList.remove('active');
        if (isActive) return;
        avgTooltip.textContent = '* average of the top 9 TAPD scores that season excluding the winner (ie. avg of rank #2\u201310)';
        var rect = th.getBoundingClientRect();
        avgTooltip.style.left = Math.max(8, rect.left + rect.width / 2 - 130) + 'px';
        avgTooltip.style.top = (rect.bottom + 6) + 'px';
        avgTooltip.classList.add('active');
      }});
    }});
    /* Assign sort-year to MG3 rows */
    document.querySelectorAll('.mg-table .mg-g3-view tbody').forEach(function(tbody) {{
      var lastYear = '';
      Array.from(tbody.children).forEach(function(tr) {{
        var yrCell = tr.cells && tr.cells[0] ? tr.cells[0].textContent.trim() : '';
        if (yrCell) lastYear = yrCell.replace("'", '');
        tr.setAttribute('data-sort-year', lastYear);
      }});
    }});

    /* === DIFF table toggle — click nav link to show/hide === */
    document.querySelectorAll('.decade-nav a[data-diff]').forEach(function(a) {{
      a.addEventListener('click', function(e) {{
        e.preventDefault();
        var tip = document.getElementById('goat-avg-tooltip');
        if (tip && tip.classList.contains('active')) return;
        var viewClass = stat === 'ted' ? '.view-ted' : '.view-tap';
        var diffDiv = document.querySelector(viewClass + ' .diff-table');
        var goatDiv = document.querySelector(viewClass + ' .goat-table');
        var g2Div = document.querySelector(viewClass + ' .g2-table');
        var g3Div = document.querySelector(viewClass + ' .g3-table');
        var mgDiv = document.querySelector(viewClass + ' .mg-table');
        if (!diffDiv) return;
        if (diffDiv.style.display !== 'none') {{
          diffDiv.style.display = 'none';
        }} else {{
          diffDiv.style.display = '';
          /* Show correct internal view */
          var tedV = diffDiv.querySelector('.view-ted');
          var tapV = diffDiv.querySelector('.view-tap');
          if (tedV) tedV.style.display = (stat === 'ted') ? '' : 'none';
          if (tapV) tapV.style.display = (stat === 'tap') ? '' : 'none';
          if (goatDiv) goatDiv.style.display = 'none';
          if (g2Div) g2Div.style.display = 'none';
          if (g3Div) g3Div.style.display = 'none';
          if (mgDiv) mgDiv.style.display = 'none';
        }}
      }});
    }});
    /* DIFF header click — collapse */
    document.querySelectorAll('.diff-table').forEach(function(diffDiv) {{
      diffDiv.querySelectorAll('.table-header').forEach(function(tableHeader) {{
        tableHeader.addEventListener('click', function() {{
          var isStuck = tableHeader.getBoundingClientRect().top <= 5;
          diffDiv.style.display = 'none';
          if (isStuck) {{
            var nav = diffDiv.closest('.historical-section').querySelector('.decade-nav');
            if (nav) nav.scrollIntoView({{block: 'start'}});
          }}
        }});
      }});
    }});
    /* DIFF sort — click aTED/aTAP, aDIFF, tDIFF headers to sort */
    document.querySelectorAll('.diff-table table').forEach(function(table) {{
      if (table.style.visibility === 'hidden') return;
      var thead = table.querySelector('thead');
      var tbody = table.querySelector('tbody');
      if (!thead || !tbody) return;
      var currentSort = 'val'; /* default sort by aTED/aTAP desc */
      function diffSort(mode) {{
        var rows = Array.from(tbody.querySelectorAll('tr'));
        var colIdx = mode === 'val' ? 2 : mode === 'adiff' ? 3 : 4;
        rows.sort(function(a, b) {{
          var av = parseFloat(a.cells[colIdx].textContent.replace('+','')) || 0;
          var bv = parseFloat(b.cells[colIdx].textContent.replace('+','')) || 0;
          return bv - av;
        }});
        rows.forEach(function(r, i) {{
          r.cells[0].textContent = i + 1;
          tbody.appendChild(r);
        }});
        currentSort = mode;
      }}
      var valTh = thead.querySelector('.diff-sort-val');
      var adiffTh = thead.querySelector('.diff-sort-adiff');
      var tdiffTh = thead.querySelector('.diff-sort-tdiff');
      if (valTh) valTh.addEventListener('click', function() {{ diffSort('val'); }});
      if (adiffTh) adiffTh.addEventListener('click', function() {{ diffSort('adiff'); }});
      if (tdiffTh) tdiffTh.addEventListener('click', function() {{ diffSort('tdiff'); }});
    }});

    /* Scroll helper — only scrolls when the sticky header is floating.
       When the header is in its natural DOM position (not stuck), the user
       can see where they are, so scrolling would be confusing. When the
       header IS stuck at viewport top (getBoundingClientRect().top ≈ 0),
       the user is deep in the list and needs to be scrolled back. */
    function collapseAndScroll(toHide, toShow, stickyEl) {{
      var isStuck = stickyEl.getBoundingClientRect().top <= 5;
      toHide.style.display = 'none';
      toShow.style.display = '';
      if (isStuck) {{
        stickyEl.closest('.decade').scrollIntoView({{block: 'start'}});
      }}
    }}
    document.querySelectorAll('.decade').forEach(function(dec) {{
      var header = dec.querySelector('.decade-header');
      var top100 = dec.querySelector('.decade-top100');
      var years = dec.querySelector('.decade-years');
      if (!header || !top100 || !years) return;
      header.addEventListener('click', function() {{
        if (top100.style.display !== 'none') {{
          /* Collapse: hide top100, show years, scroll to header */
          collapseAndScroll(top100, years, header);
        }} else {{
          /* Expand: show top100, hide years */
          top100.style.display = '';
          years.style.display = 'none';
        }}
      }});
      /* Also collapse via the table's own sticky header */
      var tableHeader = top100.querySelector('.table-header');
      if (tableHeader) tableHeader.addEventListener('click', function() {{
        collapseAndScroll(top100, years, header);
      }});
    }});
  }})();
  </script>
</body>
</html>
"""


def generate_site():
    """Main entry point: calculate rankings and generate docs/index.html."""
    print("Generating TED Weekly Rankings site...")

    db.init_db()

    # Calculate rankings
    week_start, week_end = get_rolling_week()
    print(f"  Weekly (rolling 7-day): {week_start} to {week_end}")

    weekly = calculate_weekly_rankings(week_start, week_end)
    print(f"  Weekly TED: {len(weekly['ted'])} players")
    print(f"  Weekly TAP: {len(weekly['tap'])} players")

    # For daily/weekly TAP view, use TAPD (game-level PM-derived OP) instead of
    # standard TAP (season-level OBPM/OWS-derived OP). Remap tapd → tap so the
    # existing render_table code works unchanged (column header stays "TAP").
    # Falls back to standard TAP if no TAPD data available.
    weekly_tapd = weekly.get('tapd', [])
    if weekly_tapd:
        weekly['tap'] = _remap_tapd(weekly_tapd)
        print(f"  Weekly TAP using TAPD: {len(weekly['tap'])} players")
    else:
        print(f"  Weekly TAP using standard OP (no PM data)")

    # Daily rankings = most recent game day (top 40)
    last_game_date = db.get_last_game_date(config.CURRENT_SEASON_YEAR)
    if last_game_date:
        daily_full = calculate_weekly_rankings(last_game_date, last_game_date)
        daily_tapd = daily_full.get('tapd', [])
        if daily_tapd:
            daily_tap = _remap_tapd(daily_tapd)[:40]
        else:
            daily_tap = daily_full['tap'][:40]
        daily = {
            'ted': daily_full['ted'][:40],
            'tap': daily_tap,
        }
        print(f"  Daily ({last_game_date}): TED {len(daily['ted'])}, TAP {len(daily['tap'])} players")
    else:
        daily = {'ted': [], 'tap': []}
        print(f"  Daily: no games in DB")

    # Monthly rankings = current calendar month (top 100 by avg TED/TAP_DOPM)
    # Min games filter: October = 3 games, all other months = 8 games
    def _monthly_min_games(month_num):
        return 3 if month_num == 10 else 8

    def _filter_min_games(rankings, min_g):
        return [r for r in rankings if r.get('g', 0) >= min_g]

    if last_game_date:
        month_start = last_game_date.replace(day=1)
        monthly_full = calculate_weekly_rankings(month_start, last_game_date)
        # Min 3 games for monthly inclusion after the 15th (except October)
        past_midmonth = last_game_date.day >= 15
        min_monthly_games = 3 if (past_midmonth and month_start.month != 10) else 0
        if min_monthly_games:
            monthly_full['ted'] = [r for r in monthly_full['ted'] if r.get('g', 0) >= min_monthly_games]
            monthly_full['tap'] = [r for r in monthly_full['tap'] if r.get('g', 0) >= min_monthly_games]
            if 'tapd' in monthly_full:
                monthly_full['tapd'] = [r for r in monthly_full['tapd'] if r.get('g', 0) >= min_monthly_games]
        monthly_tapd = monthly_full.get('tapd', [])
        if monthly_tapd:
            monthly_tap = _remap_tapd(monthly_tapd)[:100]
        else:
            monthly_tap = monthly_full['tap'][:100]
        monthly = {
            'ted': monthly_full['ted'][:100],
            'tap': monthly_tap,
        }
        month_label = last_game_date.strftime("%B %Y").upper()
        print(f"  Monthly ({month_start} to {last_game_date}): TED {len(monthly['ted'])}, TAP {len(monthly['tap'])} players")
    else:
        monthly = {'ted': [], 'tap': []}
        month_label = ""
        print(f"  Monthly: no games in DB")

    season = calculate_season_rankings()
    print(f"  Season TED: {len(season['ted'])} players")
    print(f"  Season TAP: {len(season['tap'])} players")

    # Compute month-by-month leaders for POTM popup
    month_winners = []
    if last_game_date:
        # Season starts in October of CURRENT_SEASON_YEAR
        season_start_month = 10  # October
        season_start_year = config.CURRENT_SEASON_YEAR
        # Build list of (year, month) pairs from Oct through current month
        ym_pairs = []
        y, m = season_start_year, season_start_month
        while (y, m) <= (last_game_date.year, last_game_date.month):
            ym_pairs.append((y, m))
            m += 1
            if m > 12:
                m = 1
                y += 1
        import calendar
        for y, m in ym_pairs:
            m_start = date(y, m, 1)
            if y == last_game_date.year and m == last_game_date.month:
                m_end = last_game_date
            else:
                m_end = date(y, m, calendar.monthrange(y, m)[1])
            try:
                m_rankings = calculate_weekly_rankings(m_start, m_end)
            except Exception:
                continue
            month_name = m_start.strftime("%B %Y").upper()
            # Apply min games filter only to completed months, not the current month
            is_current_month = (y == last_game_date.year and m == last_game_date.month)
            min_g = _monthly_min_games(m)
            if is_current_month:
                ted_filtered = m_rankings['ted']
            else:
                ted_filtered = _filter_min_games(m_rankings['ted'], min_g)
            ted_leader = ted_filtered[0] if ted_filtered else None
            # Use TAPD if available, else standard TAP
            tapd_list = m_rankings.get('tapd', [])
            if tapd_list:
                tap_filtered = tapd_list if is_current_month else _filter_min_games(tapd_list, min_g)
                tap_leader_data = tap_filtered[0] if tap_filtered else None
                tap_val = round(tap_leader_data.get('tapd', tap_leader_data.get('tap', 0)), 1) if tap_leader_data else 0
                tap_leader_name = tap_leader_data['player'] if tap_leader_data else ''
            elif m_rankings['tap']:
                tap_filtered = m_rankings['tap'] if is_current_month else _filter_min_games(m_rankings['tap'], min_g)
                tap_leader_data = tap_filtered[0] if tap_filtered else None
                tap_val = round(tap_leader_data['tap'], 1) if tap_leader_data else 0
                tap_leader_name = tap_leader_data['player'] if tap_leader_data else ''
            else:
                tap_val = 0
                tap_leader_name = ''
            winner = {
                'month': month_name,
                'ted_player': ted_leader['player'] if ted_leader else '',
                'ted_val': round(ted_leader['ted'], 1) if ted_leader else 0,
                'tap_player': tap_leader_name,
                'tap_val': tap_val,
            }
            month_winners.append(winner)
        print(f"  Month winners computed: {len(month_winners)} months")

    # Generate HTML
    updated_at = date.today().strftime("%B %d, %Y")
    html = generate_html(weekly, season, daily, monthly, month_label, month_winners, updated_at)

    # Write output
    os.makedirs(DOCS_DIR, exist_ok=True)
    output_path = os.path.join(DOCS_DIR, "index.html")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n  Generated: {output_path}")
    print(f"  Open in browser to preview.")


if __name__ == "__main__":
    sys.path.insert(0, config.PROJECT_DIR)
    generate_site()
