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

    stat_key: 'ted' or 'tap' — determines sort order and displayed stat.
    season_all: current season results to merge into all-time top 200.
    """
    if not data or 'decades' not in data:
        return '', ''

    stat_upper = stat_key.upper()
    decade_order = ['2020s', '2010s', '2000s', '1990s', '1980s', '1970s', '1960s', '1950s']

    suffix = '' if stat_key == 'ted' else f'-{stat_key}'

    # Build decade nav links (only from TED pass — shared nav)
    nav_links = ''.join(
        f'<a href="#decade-{d}" data-decade="{d}">{d[:-1]}<span class="decade-s">s</span></a>' for d in decade_order if d in data['decades']
    )
    nav_links += '<a href="#" data-goat="true">GOAT</a>'

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

            # Re-sort players by the chosen stat and re-rank
            players_sorted = sorted(
                [p for p in year_data['players'] if p.get('player')],
                key=lambda p: p.get(stat_key, 0),
                reverse=True
            )

            # Build table rows with fresh ranks
            rows = ''
            for rank, p in enumerate(players_sorted, 1):
                name_html = format_player_name(p['player'])
                player_attr = html_module.escape(p['player'], quote=True)
                team = p['team'] if p['team'] else '&mdash;'
                val_str = f'{p[stat_key]:.1f}'
                rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="team">{team}</td><td class="num stat">{val_str}</td></tr>\n'

            year_tables.append(f"""      <div class="year-table" data-year="{year_data['year']}">
        <div class="table-header"><h2>{season_label} SEASON &mdash; {stat_upper} TOP {top_n}</h2></div>
        <table>
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="team">Team</th><th class="num stat">{stat_upper}</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
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
{year_tables[i]}      <div class="year-table"><div class="table-header"><h2>&nbsp;</h2></div></div>
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

    return nav_links, f"""  <div class="historical-section">
    <div class="historical-header"><h2>Historical {stat_upper} Rankings</h2></div>
    <div class="all-time-table" style="display:none">
{render_all_time_html(data, stat_key, season_all)}    </div>
    <nav class="decade-nav">{nav_links}</nav>
    <div class="goat-table" style="display:none">
{goat_html}    </div>
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

    # Start with historical all-time entries
    all_entries = list(data['all_time_top_200'])

    # Merge current season players
    if season_all:
        season_label = f"{current_year}-{str(current_year + 1)[-2:]}"
        for p in season_all:
            if p.get('ted') is not None and p.get('tap') is not None:
                all_entries.append({
                    'player': p['player'],
                    'team': p.get('team', ''),
                    'year': current_year,
                    'season_label': season_label,
                    'ted': round(p['ted'], 1),
                    'tap': round(p['tap'], 1),
                })

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
        val_str = f'{p[stat_key]:.1f}'
        rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="season">{p["season_label"]}</td><td class="num stat">{val_str}</td></tr>\n'

    return f"""    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2>ALL-TIME {stat_upper} TOP 400</h2></div>
        <table>
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="season">Season</th><th class="num stat">{stat_upper}</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
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

    # Start with historical decade entries
    all_entries = list(decade_data['decade_top_100'])

    # Merge current season for the current decade
    if season_all and decade_start <= current_year <= decade_end:
        season_label = f"{current_year}-{str(current_year + 1)[-2:]}"
        for p in season_all:
            if p.get('ted') is not None and p.get('tap') is not None:
                all_entries.append({
                    'player': p['player'],
                    'team': p.get('team', ''),
                    'year': current_year,
                    'season_label': season_label,
                    'ted': round(p['ted'], 1),
                    'tap': round(p['tap'], 1),
                })

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
        val_str = f'{p[stat_key]:.1f}'
        rows += f'        <tr><td class="rank">{rank}</td><td class="player" data-player="{player_attr}">{name_html}</td><td class="season">{p["season_label"]}</td><td class="num stat">{val_str}</td></tr>\n'

    return f"""    <div class="year-pair single">
      <div class="year-table">
        <div class="table-header"><h2><span class="decade-label">{decade_label[:-1]}<span class="decade-s">s</span></span> {stat_upper} TOP {decade_top_n}</h2></div>
        <table>
          <thead><tr><th class="rank">Rank</th><th class="player">Player</th><th class="season">Season</th><th class="num stat">{stat_upper}</th></tr></thead>
          <tbody>
{rows}          </tbody>
        </table>
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
        stats[str(current_year)] = {
            'top10_ted': round(sum(top10_teds) / len(top10_teds), 1),
            'top10_tap': round(sum(top10_taps) / len(top10_taps), 1),
            'ldr_ted': ted_leader['player'], 'ldr_ted_val': round(ted_leader['ted'], 1),
            'ldr_tap': tap_leader['player'], 'ldr_tap_val': round(tap_leader['tap'], 1),
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
        player_name = s.get(f'ldr_{stat_key}', '')
        val = s.get(f'ldr_{stat_key}_val', 0)
        top10 = s.get(f'top10_{stat_key}', 0)
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
    if season_all:
        for r in season_all:
            name = r['player']
            entry = {'y': current_year, 'tm': r['team'], 'ted': round(r['ted'], 1), 'tap': round(r['tap'], 1)}
            if name not in career:
                career[name] = []
            # Avoid duplicate if already present for this year
            if not any(s['y'] == current_year for s in career[name]):
                career[name].append(entry)
                career[name].sort(key=lambda x: x['y'])

        # Add current season to season_stats
        ted_sorted = sorted(season_all, key=lambda r: r['ted'], reverse=True)
        tap_sorted = sorted(season_all, key=lambda r: r['tap'], reverse=True)
        top10_teds = [r['ted'] for r in ted_sorted[:10]]
        top10_taps = [r['tap'] for r in tap_sorted[:10]]
        ted_leader = ted_sorted[0]
        tap_leader = tap_sorted[0]
        season_stats[str(current_year)] = {
            'top10_ted': round(sum(top10_teds) / len(top10_teds), 1),
            'top10_tap': round(sum(top10_taps) / len(top10_taps), 1),
            'ldr_ted': ted_leader['player'], 'ldr_ted_val': round(ted_leader['ted'], 1),
            'ldr_tap': tap_leader['player'], 'ldr_tap_val': round(tap_leader['tap'], 1),
        }

    career_json = json.dumps(career, ensure_ascii=False, separators=(',', ':'))
    stats_json = json.dumps(season_stats, ensure_ascii=False, separators=(',', ':'))
    return f'<script>window.CAREER={career_json};window.SEASON_STATS={stats_json};</script>'


def generate_html(weekly, season, daily, updated_at):
    """Generate the full HTML page — TED only."""
    season_label = f"{config.CURRENT_SEASON_YEAR}-{str(config.CURRENT_SEASON_YEAR + 1)[-2:]}"

    weekly_ted_table = render_table(weekly['ted'], 'ted', 'WEEKLY TED TOP 100')
    season_ted_table = render_table(season['ted'], 'ted', 'SEASON-TO-DATE TED TOP 100')
    weekly_tap_table = render_table(weekly['tap'], 'tap', 'WEEKLY TAP TOP 100')
    season_tap_table = render_table(season['tap'], 'tap', 'SEASON-TO-DATE TAP TOP 100')
    daily_ted_table = render_table(daily['ted'], 'ted', 'DAILY TED TOP 40')
    daily_tap_table = render_table(daily['tap'], 'tap', 'DAILY TAP TOP 40')

    # Build career popup data
    career_js = build_career_js(
        load_historical_rankings(),
        season.get('all', [])
    )

    historical = load_historical_rankings()
    season_all = season.get('all', [])
    if historical:
        decade_nav_links, historical_ted_html = render_historical_section(historical, 'ted', season_all)
        _, historical_tap_html = render_historical_section(historical, 'tap', season_all)
        decade_nav_html = ''  # now embedded inside historical sections
        historical_html = f"""<div class="view-ted" style="display:none">
{historical_ted_html}</div>
<div class="view-tap">
{historical_tap_html}</div>"""
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
    }}

    .season-header h3 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1.1em;
      font-weight: 900;
      letter-spacing: 0.1em;
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
      -webkit-transform: translateZ(0);
      transform: translateZ(0);
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
      border-bottom: 1px solid #fff;
      background: #000;
    }}

    tbody tr {{
      border-bottom: 1px solid #fff;
    }}

    tbody tr:last-child {{
      border-bottom: none;
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
    .goat-table .table-header {{
      background: #fff;
      cursor: pointer;
    }}

    .all-time-table .year-table .table-header h2,
    .decade-top100 .year-table .table-header h2,
    .goat-table .year-table .table-header h2 {{
      color: #ee7623;
    }}

    .all-time-table .table-header:hover,
    .decade-top100 .table-header:hover,
    .goat-table .table-header:hover {{
      background: #eee;
    }}

    td.num.goat-avg,
    thead th.num.goat-avg {{
      text-align: center !important;
      padding-left: 0;
      padding-right: 0;
    }}

    .goat-table td.num:last-child,
    .goat-table thead th.num:last-child {{
      padding-left: 2px;
    }}

    thead th.num.goat-avg {{
      white-space: nowrap;
      font-size: 0.78em;
    }}

    .goat-sort-diff {{
      color: #ee7623;
      cursor: pointer;
    }}

    .goat-sort-val,
    .goat-sort-yr,
    .goat-sort-player {{
      cursor: pointer;
    }}


    .goat-table .player {{
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
    .goat-table table {{
      width: 100%;
    }}

    .all-time-table .year-pair > :first-child,
    .decade-top100 .year-pair > :first-child {{
      border-right: 2px solid #fff;
    }}

    .all-time-table .player,
    .decade-top100 .player {{
      max-width: 160px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}

    .historical-header h2 {{
      font-family: Georgia, 'Times New Roman', serif;
      font-size: 1.2em;
      font-weight: 900;
      letter-spacing: 0.08em;
      text-transform: uppercase;
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
      .year-pair {{
        grid-template-columns: 1fr;
      }}
      .year-pair > :first-child {{
        border-right: none;
        border-bottom: 2px solid #fff;
      }}
      .year-table table {{
        max-width: 100%;
      }}
      .year-table .player .fname,
      .year-table .player .lname {{
        display: inline;
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
    <div class="season-header"><h3>{season_label} Season</h3></div>
    <div class="view-ted" style="display:none">
      <div class="tables-grid">
        <div class="weekly-daily-slot">
          <div class="weekly-table">{weekly_ted_table}</div>
          <div class="daily-table" style="display:none">{daily_ted_table}</div>
        </div>
{season_ted_table}
      </div>
    </div>
    <div class="view-tap">
      <div class="tables-grid">
        <div class="weekly-daily-slot">
          <div class="weekly-table">{weekly_tap_table}</div>
          <div class="daily-table" style="display:none">{daily_tap_table}</div>
        </div>
{season_tap_table}
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
            <th class="cp-avg">TOP 10</th>
            <th class="cp-leader">High</th>
          </tr>
        </thead>
        <tbody id="career-popup-body">
        </tbody>
      </table>
    </div>
  </div>
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
      var anchor = findScrollAnchor();
      var savedScroll = window.scrollY;
      /* Capture weekly/daily state from old view before switching */
      var oldView = stat === 'ted' ? '.view-ted' : '.view-tap';
      var oldSlot = document.querySelector(oldView + ' .weekly-daily-slot');
      var showingDaily = oldSlot && oldSlot.querySelector('.daily-table').style.display !== 'none';
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
        if (typeof goatApplySort === 'function') goatApplySort();
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
    document.querySelectorAll('.decade-nav a[data-decade]').forEach(function(a) {{
      a.addEventListener('click', function(e) {{
        e.preventDefault();
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

    function showCareer(name, contextYear) {{
      var career = window.CAREER[name];
      if (!career || career.length === 0) return;
      var s = stat;
      var su = s.toUpperCase();
      var hlYear = contextYear || null;
      popupName.textContent = name;
      popupStatHeader.textContent = su;
      var html = '';
      for (var i = career.length - 1; i >= 0; i--) {{
        var c = career[i];
        var sl = c.y + '-' + String(c.y + 1).slice(-2);
        var tm = c.tm || '\\u2014';
        var val = c[s] !== null && c[s] !== undefined ? c[s].toFixed(1) : '\\u2014';
        var ss = window.SEASON_STATS[String(c.y)];
        var ldrVal = '', avgVal = '';
        if (ss) {{
          var lv = ss['ldr_' + s + '_val'];
          ldrVal = lv !== undefined ? lv.toFixed(1) : '';
          var av = ss['top10_' + s];
          avgVal = av !== undefined ? av.toFixed(1) : '';
        }}
        var ldrCell = ldrVal || '\\u2014';
        var rc = c.y === hlYear ? ' class="cp-current"' : '';
        html += '<tr' + rc + '>'
          + '<td class="cp-season">' + sl + '</td>'
          + '<td class="cp-team">' + tm + '</td>'
          + '<td class="cp-stat">' + val + '</td>'
          + '<td class="cp-avg">' + (avgVal || '\\u2014') + '</td>'
          + '<td class="cp-leader">' + ldrCell + '</td>'
          + '</tr>';
      }}
      popupBody.innerHTML = html;
      overlay.classList.add('active');
    }}

    function closeCareer() {{
      overlay.classList.remove('active');
      popupBody.innerHTML = '';
    }}

    document.querySelector('.container').addEventListener('click', function(e) {{
      var td = e.target.closest('td.player[data-player]');
      if (td) {{
        e.stopPropagation();
        var yearDiv = td.closest('.year-table[data-year]');
        var ctxYear = yearDiv ? parseInt(yearDiv.getAttribute('data-year')) : currentYear;
        showCareer(td.getAttribute('data-player'), ctxYear);
      }}
    }});

    document.getElementById('career-popup-close').addEventListener('click', closeCareer);
    overlay.addEventListener('click', function(e) {{
      if (e.target === overlay) closeCareer();
    }});
    document.addEventListener('keydown', function(e) {{
      if (e.key === 'Escape') closeCareer();
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

    /* Historical / All-Time toggle — click header to show/hide */
    document.querySelectorAll('.historical-section').forEach(function(sec) {{
      var header = sec.querySelector('.historical-header');
      var allTime = sec.querySelector('.all-time-table');
      if (!header || !allTime) return;
      header.addEventListener('click', function() {{
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
        var viewClass = stat === 'ted' ? '.view-ted' : '.view-tap';
        var goatDiv = document.querySelector(viewClass + ' .goat-table');
        if (!goatDiv) return;
        if (goatDiv.style.display !== 'none') {{
          goatDiv.style.display = 'none';
        }} else {{
          goatDiv.style.display = '';
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
                     top 30, tiebreak DIFF; rows 31+ hidden, orange line visible */
    var goatSortMode = 'year';
    function goatSort(table, mode) {{
      var tbody = table.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll('tr'));
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
      var showOrange = (mode === 'diff' || mode === 'diff-player');
      rows.forEach(function(r, i) {{
        var bdrTop = (showOrange && mode !== 'diff-player' && i === 30) ? '2px solid #ee7623' : '';
        var bdrBot = (mode === 'diff-player' && i === 29) ? '2px solid #ee7623' : '';
        var hide = (mode === 'diff-player' && i >= 30);
        r.style.display = hide ? 'none' : '';
        for (var c = 0; c < r.cells.length; c++) {{
          r.cells[c].style.borderTop = bdrTop;
          r.cells[c].style.borderBottom = bdrBot;
        }}
        tbody.appendChild(r);
      }});
    }}
    function goatApplySort() {{
      document.querySelectorAll('.goat-table table').forEach(function(t) {{
        if (t.style.visibility === 'hidden') return;
        goatSort(t, goatSortMode);
      }});
    }}
    document.querySelectorAll('.goat-sort-diff').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        goatSortMode = goatSortMode === 'diff' ? 'year' : 'diff';
        goatApplySort();
      }});
    }});
    document.querySelectorAll('.goat-sort-val').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        goatSortMode = goatSortMode === 'val' ? 'year' : 'val';
        goatApplySort();
      }});
    }});
    document.querySelectorAll('.goat-sort-yr').forEach(function(th) {{
      th.addEventListener('click', function(e) {{
        e.stopPropagation();
        goatSortMode = 'year';
        goatApplySort();
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
      }});
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

    # Daily rankings = most recent game day (top 40)
    last_game_date = db.get_last_game_date(config.CURRENT_SEASON_YEAR)
    if last_game_date:
        daily_full = calculate_weekly_rankings(last_game_date, last_game_date)
        daily = {
            'ted': daily_full['ted'][:40],
            'tap': daily_full['tap'][:40],
        }
        print(f"  Daily ({last_game_date}): TED {len(daily['ted'])}, TAP {len(daily['tap'])} players")
    else:
        daily = {'ted': [], 'tap': []}
        print(f"  Daily: no games in DB")

    season = calculate_season_rankings()
    print(f"  Season TED: {len(season['ted'])} players")
    print(f"  Season TAP: {len(season['tap'])} players")

    # Generate HTML
    updated_at = date.today().strftime("%B %d, %Y")
    html = generate_html(weekly, season, daily, updated_at)

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
