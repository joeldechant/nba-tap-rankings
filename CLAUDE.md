# TED Claude Project

## IMPORTANT: Scrape Verification Rule

**When the user asks "did the scrape run?" or "did the update work?", do NOT just check that an update exists and report the game count. ALWAYS verify:**
1. Check the **date** of the most recent update — does it match today?
2. Check `db.get_last_game_date()` — does it include yesterday's games?
3. If the Task Scheduler ran but exit code ≠ 0, report it as a **failure**, not a success
4. Cross-check: the most recent git commit timestamp should also be from today if the pipeline succeeded

**Never tell the user "the scrape ran and picked up X games" without confirming the dates are correct.**

## What This Project Is

This project revolves around **TED (Total Earned Differential)** and its companion stat **TAP (Total Adjusted Production)**, basketball statistics created by Joel Dechant (the user). Both estimate player production per game normalized to 36 minutes and 71 possessions, but from complementary angles.

## Key Concepts

- **TED** converts ALL player contributions (scoring, efficiency, rebounds, assists, steals, blocks, turnovers, defense) into a single points-equivalent number using mostly box-score stats (only DBPM and DWS as advanced stats)
- **TAP** uses the same building blocks as TED but adds an offensive advanced stats overlay (OBPM and OWS) to capture residual offensive impact beyond box-score stats
- **MAP** (Marginal Added Production) measures total contribution from advanced stats beyond box score — originally an experimental "TED" variant in v9, renamed to avoid confusion. Produces small values (~-5 to +10), unlike TED/TAP's ~20-55 range
- **DOPM** (Daily Offensive Plus Minus) — alternative daily/weekly OP derivation using raw game PM instead of OBPM/OWS. PM = raw game box score plus/minus (BR column `+/-`). Chain: PM → PM36 → PM36p → subtract DPS36p → DOPM → strip P/Shot, RB, NA → **OPD** (OP Daily) → **TAPD** (TAP Daily). Avoids the inverse relationship where monster box score games get very negative OP from season-level advanced stats. Parallel calculation — does not affect standard TED/TAP values.
- **OPD** (OP Daily) — the OP residual derived from DOPM after stripping P/Shot, RB, NA effects. Previously named OP_DOPM, renamed Mar 2026.
- **TAPD** (TAP Daily) — TAP calculated using OPD instead of standard OP. Previously named TAP_DOPM, renamed Mar 2026. Used for daily, weekly, and monthly TAP views on the website, with season-to-date TAPD available as a third toggle view (TAP → TAPD → Monthly cycle in TAP view). **Not the same as** TAPd (TAP deflated) in the v10 Excel workbook — see naming note under Calculations sheet.
- Unlike PER (which is an arbitrary relative scale centered on 15), TED/TAP are anchored in real basketball meaning — a TED of 45 means ~45 points-equivalent of total production
- The intended design is to use both stats together: overall player rank = average of TAP rank and TED rank
- The original paper is from January 2018 and lives at `TED - Jan 2018.pdf` in the project root

## Key Files

- `TED - Jan 2018.pdf` — Original paper (20 pages, 5 sections)
- `TED Model v9.xlsx` — Master Excel workbook with full calculation engine (historical archive)
- `memory/ted-formula.md` — Full TED formula reference
- `memory/tap-formula.md` — Full TAP formula reference
- `memory/ted-rankings-context.md` — Rankings, TED vs PER divergences, notable findings
- `memory/excel-workbook-guide.md` — Complete guide to the v9 Excel workbook structure
- `memory/new-project-plan.md` — Full project plan with decisions and open items
- `memory/v10-formulas.md` — Complete v10 formula reference (TED, TAP, all variants, coefficients, column map)

## Two Phases

### Phase 1: Excel Model Update (COMPLETE)
- Create TED Model v10.xlsx from v9 (clean sheet structure, carry forward relevant data)
- Scrape Basketball Reference for seasons 2018-2026 (= 2017-18 through 2025-26)
- Add new players who've entered the league since 2017
- Populate both TED and TAP calculations (including OBPM/OWS for TAP)
- Purpose: working Excel model + demonstrate Claude's Excel capabilities
- Data source: Basketball Reference (per-game stats + advanced stats pages)
- And-1 rate: 25% of FTA estimate (kept from v9)
- 2025-26 season included as season-to-date partial data

### Phase 2: Automated Weekly System (COMPLETE)
- cloudscraper + BeautifulSoup scraper for game-level box scores + season-to-date advanced stats from Basketball Reference (originally Selenium, switched due to chronic Chrome renderer timeouts and zombie process issues)
- SQLite database (replaces Excel as the live engine, stores all game-level data)
- Python calculation engine implementing TED/TAP/MAP formulas (validated against v10)
- Static HTML website on GitHub Pages with two weekly auto-refreshing top-100 rankings (TED):
  1. Weekly TED Top 100 (rolling 7-day window ending yesterday)
  2. Season-to-date TED Top 100
- Website displays TED (switched from TAP in Mar 2026). TED/TAP both calculated internally.
- Weekly rankings use rolling 7-day window (not fixed Mon-Sun); refreshes whenever update runs
- **Weekly/daily TAP OP mode** controlled by `config.USE_SEASON_OP_FOR_WEEKLY` (currently **OFF**). When ON, TAP uses pre-computed season-to-date OP (conceptually stronger — avoids inverse relationship where better box score games get more negative OP). When OFF (current default), TAP derives OP per-game from OBPM/OWS, preserving meaningful TED-TAP divergence that reveals player archetypes. All code supports both modes (`override_op` in `calculator.py`, `_compute_season_op_lookup()` in `weekly_update.py`, `compute_season_op()` in `game_breakdown.py`) — just flip the flag. Season-to-date rankings unaffected either way.
- Weekly advanced stats (DBPM/DWS/OBPM/OWS) use season-to-date values from Basketball Reference
- MAP calculated but not displayed on website (future toggle)
- Auto-update runs daily at 6 AM ET via Windows Task Scheduler (with missed-task catch-up, runs on battery)
- Filtering: MP >= 20 everywhere; no min games for weekly; season-to-date uses tiered min games (Mar 1→30, Jan 15→20, Dec 15→10, Nov 15→5)
- All players stored, filter at output time. Temporary exclusion list in `config.py` supports `(player_name, end_date)` tuples — applies to daily, weekly, and season-to-date unless specified otherwise. Player auto-reappears after end_date. Note: BR stores some names with diacritics (e.g., Porziņģis) — exclusion names must match DB exactly.
- Backfill game-level data from start of 2025-26 season
- MCP server with 5 tools for Claude-driven updates and lookups
- Build order: scraper → data store → calc engine → validate against v10 → website → MCP conversion

## Scraping Details

### Phase 1 (cloudscraper — historical bulk scraping)
- **Tool:** `cloudscraper` (bypasses Cloudflare)
- **Per-game stats URL:** `https://www.basketball-reference.com/leagues/NBA_{year}_per_game.html`
- **Advanced stats URL:** `https://www.basketball-reference.com/leagues/NBA_{year}_advanced.html`
- **Pace URL:** `https://www.basketball-reference.com/leagues/NBA_{year}.html` (table index 10)
- **Encoding:** Write to CSV (avoids Windows console Unicode issues with names like Jokić, Dončić)
- **Traded players:** Use combined row (2TM/3TM), filter out individual team rows
- **All TED/TAP input fields confirmed available** from Basketball Reference

### Phase 2 (cloudscraper + BeautifulSoup — weekly game-level scraping)
- **Tool:** `cloudscraper` + `BeautifulSoup` (same as Phase 1; switched from Selenium which suffered chronic Chrome renderer timeouts, zombie processes, and stale lock files)
- **Daily summary URL:** `https://www.basketball-reference.com/boxscores/?month=M&day=D&year=YYYY`
- **Individual box score URL:** `https://www.basketball-reference.com/boxscores/YYYYMMDD0TEAM.html`
- **Season averages URL:** Same as Phase 1 per-game + advanced stats pages (for season-to-date rankings)
- **Approach:** Scrape daily summary page to get game URLs → scrape each game's box score page
- **Box score fields:** MP, FG, FGA, 3P, FT, FTA, TRB, AST, STL, BLK, TOV, PTS, PM (per player per game)

## Year Convention

- **RULE: When the user says a single year (e.g. "2006"), interpret it as the season STARTING in that year.** "2006" = the 2006-07 season = Year=2006 in v9/v10 = NBA_2007 on Basketball Reference.
- **v9/v10 use start-year convention:** Year=2005 = the 2005-06 season (= Basketball Reference NBA_2006)
- **Basketball Reference uses end-year:** NBA_2006 = the 2005-06 season
- **Conversion:** v9_year = basketball_ref_year - 1
- v9's Year=2017 was originally a **partial mid-season snapshot** (paper written Jan 2018), updated Mar 2026 with full-season averages from Basketball Reference
- Scraped data also covers 2017+ with full-season data

## Data Files (Intermediate)

### Extracted from v9
- `v9_historical_data.csv` — 1,964 player-season rows (+ 69 mid-file year headers), years 1948-2017 (start-year convention), 21 columns of raw inputs. Cleaned Mar 2026: removed 9 duplicate rows, fixed Millsap 2011 DBPM/Pace to BR-verified values, renamed Jermaine O'Neal 2002 to "J O'Neal", added first names to all players, updated Year=2017 from partial mid-season to full-season averages. Dick McGuire (1950) removed Mar 2026 as extreme low outlier.
- `v9_coefficients.csv` — All 24 Row 2 constants from TAP v4 (Pace=95, P36=71.25, RB=0.5967, NA=1.6, P/Shot=1.1, etc.)
- `v9_pace_data.csv` — Team pace by year, 69 rows (1950-2017), 45 columns

### Scraped from Basketball Reference
- `scraped_data/2018_season.csv` through `scraped_data/2026_season.csv` — Individual season files
- `scraped_data/all_seasons_2018_2026.csv` — Combined: 4,970 player-season rows, 9 seasons (NBA_2018-NBA_2026), 28 columns
- `scraped_data/pace_2018_2026.csv` — Team pace data, 278 rows across 9 seasons
- Columns: Player, Team, Age, Pos, G, GS, MP, FG, FGA, 3P, FT, FTA, RB, AST, STL, BLK, Turnovers, PTS, PER, OWS, DWS, WS, OBPM, DBPM, BPM, VORP, Year, Pace

### v10 Workbook
- `TED Model v10.xlsx` — New workbook, created with xlwings
  - **Raw Data sheet:** 6,788 player-season rows, 24 columns, years 1948-2025 (start-year convention)
    - 1,819 rows from v9 (1948-2016), 4,970 rows scraped (2017-2025)
    - Sorted by Year desc, then PTS desc within each year
    - Synced with cleaned v9 CSV (Mar 2026): first names, no duplicates, Millsap corrected
    - v9's partial Year=2017 replaced by full scraped 2017-18 season data
  - **Coefficients sheet:** 22 named parameters with values and descriptions + era baseline lookup table (includes DPS_Coeff=2.5 at B25)
  - **Calculations sheet:** 54 formula columns (A-BB), full TED + TAP + MAP chain, era transitions color-marked, DPS36p multiplied by DPS_Coeff in all final stats
    - Final stats: TAP (AU), TAPd (AV), rTAPd (AW), PER (AX), TED (AY), rTED (AZ), MAP (BA), rMAP (BB)
    - **Naming note**: TAPd/rTAPd in the v10 Excel workbook = "TAP deflated" (TAP without OP, pure box-score calculation). In code these are `tap_deflated`/`rtap_deflated`. This is completely separate from **TAPD** (TAP Daily), which is TAP using DOPM-derived OPD instead of standard OP. The Excel TAPd predates the DOPM system.
    - TED uses RB×0.6, TAP uses RB×0.5967 + OP overlay
    - Era-varying P/Shot OP baselines: 1.16 (2020+), 1.13 (2016-2019), 1.10 (1982-2015), 1.08 (1976-81), 1.03 (1962-75), 0.98 (1957-61), 0.93 (1948-56)
    - All intermediates visible and auditable
  - **Rankings sheet:** 3,800 player-seasons (filtered G>=40/MP>=20), ranked by combined TED+TAP rank within each year
  - **All-Time Top 100 sheet:** Best 100 individual seasons ever by combined global rank
  - **Current Season (2025-26) sheet:** 222 players (filtered G>=15/MP>=20), 2025-26 season-to-date
  - **LaMelo Analysis sheet:** 7 tables analyzing LaMelo Ball's inflated TAP ranking — raw stats, per-36, TED/TAP components, OP decomposition, stripping weight sensitivity (0.3/0.45/0.6), top-20 TED vs TAP comparisons
  - **P-Shot Analysis sheet:** Historical P/Shot by season (1970-2026), era baselines, sensitivity analysis (TAP at 1.13/1.16/1.17), formula discussion and rationale for 2020+ baseline update
  - **DOPM Method sheet:** Worked examples for the DOPM alternative OP calculation. Terminology, constants reference, step-by-step formula chain for one game, and multi-game comparison table (standard OP vs DOPM side by side). Built by `build_pm_op_sheet.py`.
  - **DOPM Conceptual sheet:** Full design rationale for DOPM. 7 sections: (1) The time-scale mismatch problem, (2) DOPM as the solution, (3) Complete calculation chain with naming, (4) Why DPS not raw DBPM for subtraction (with player examples), (5) What DOPM captures vs standard OP, (6) Relationship to existing TAP settings (3 modes), (7) Implementation details. Built by `build_pm_op_sheet.py`.
  - Raw Data columns: Player, Year, Team, Age, Pos, Pace, G, MP, FG, FGA, 3P, FT, FTA, RB, AST, STL, BLK, TOV, PTS, PER, OBPM, OWS, DBPM, DWS

### Phase 2 Database
- `phase2/ted_weekly.db` — SQLite database for weekly system
  - **game_box_scores:** Individual game stats (append-only). PK: (game_id, player, team). Includes `plus_minus` column (raw game PM, added Mar 2026).
  - **season_averages:** Season-to-date per-game averages (overwritten each update). PK: (season_year, player)
  - **advanced_stats:** Season-to-date DBPM/DWS/OBPM/OWS/PER (overwritten each update). PK: (season_year, player)
  - **team_pace:** Team pace by season (overwritten each update). PK: (season_year, team)
  - **update_log:** Tracks each scrape/update run with timestamps and status
  - **historical_pm:** Lightweight PM + MP per game for seasons 2000-2024 (for computing season-average TAPD in historical rankings). PK: (game_id, player, team). Columns: game_id, game_date, season_year, player, team, mp_decimal, plus_minus. Populated by `scrape_historical_pm.py`.

### Scripts
- `extract_v9.py` — Extracts raw input data from v9 TAP v4 sheet via xlwings
- `scrape_seasons.py` — Scrapes seasons 2018-2025 from Basketball Reference
- `scrape_2026.py` — Scrapes 2025-26 current season + verified year convention
- `build_v10.py` — Creates v10 workbook, merges v9 + scraped data, writes Raw Data + Coefficients
- `read_v9_formulas.py` — Reads all cell formulas from v9 TAP v4 Row 5 (Harden) for chain mapping
- `build_v10_calcs.py` — Adds Calculations sheet with 52 formula columns
- `build_v10_output.py` — Builds Rankings, All-Time Top 100, Current Season output sheets
- `validate_v10.py` — Validates v10 against v9 known values
- `map_era_baselines.py` — Maps v9's era-varying P/Shot OP baselines from cell formulas
- `update_era_baselines.py` — Updates v10 PShot_Diff_OP with era-varying IFS formula
- `mark_era_transitions.py` — Colors era transition rows in Calculations sheet
- `add_ted_to_v10.py` — Adds TED/rTED columns (AY-AZ) to Calculations sheet
- `add_map_to_v10.py` — Adds MAP/rMAP columns (BA-BB) to Calculations sheet
- `update_map_formula.py` — Rewrites MAP/rMAP formulas to conceptual decomposition
- `rename_v9_ted_to_map.py` — Renames v9 experimental "TED" (col CE) to MAP
- `sensitivity_analysis.py` — Sensitivity analysis script for coefficient comparisons
- `build_lamelo_sheet.py` — Builds LaMelo Analysis worksheet in v10 (7 comparison tables, OP decomposition, sensitivity)
- `update_dps_coeff.py` — Adds DPS_Coeff to Coefficients sheet and updates all formula columns (AU-BB)
- `coeff_analysis.py` — Current season coefficient sensitivity analysis
- `coeff_analysis_hist.py` — Historical coefficient sensitivity analysis (1,773 player-seasons)
- `dps_tap_analysis.py` — DPS coefficient comparison for TAP rankings (top 30 at x1/x2/x2.5/x3)
- `dps_comparison.py` — Clean top-30 side-by-side comparison at x2.0/x2.5/x3.0 (corrected formula)
- `dps_full_analysis.py` — Complete DPS coefficient analysis: component breakdowns, archetypes, distributions, rank changes
- `dps_analysis_detailed.py` — Earlier analysis script (superseded by dps_full_analysis.py)

### Phase 2 Scripts (in `phase2/` directory)
- `config.py` — Constants, paths, coefficients (matching v10 exactly), team mappings, era baselines, tiered min-games filter, DPS_COEFF_TED=1.5/DPS_COEFF_TAP=2.5
- `database.py` — SQLite schema, insert/upsert/query functions, update logging, zombie entry cleanup, get_last_game_date(). game_box_scores table includes `plus_minus` column (raw game PM).
- `scraper.py` — cloudscraper + BeautifulSoup BR scraping: daily games, box scores, season averages, advanced stats, pace (simple HTTP requests, no browser process management, forces UTF-8 encoding on responses). Box score scraping includes PM (BR column header `+/-`).
- `calculator.py` — Full TED/TAP/MAP formula engine (validated against v10 to 6+ decimal places). Includes DOPM calculation: when `game_plus_minus` is provided, computes PM→PM36→PM36p→DOPM→OPD→TAPD as a parallel path (does NOT affect standard TED/TAP/OP values).
- `weekly_update.py` — Orchestrator: run_weekly_update(), backfill_season(), calculate_*_rankings(). backfill_season() starts from last game date in DB (not season start).
- `site_generator.py` — Static HTML site generator; reads DB, calculates rankings, loads historical JSON, outputs `docs/index.html`. Displays TED rankings (switched from TAP Mar 2026). Includes all-time top 200, decade top 100, historical per-year rankings by decade, decade nav links. Daily/weekly TAP view uses TAPD (via `_remap_tapd()` helper) with automatic fallback to standard TAP when no PM data available. Season-to-date always uses standard TAP.
- `auto_update.py` — End-to-end pipeline: backfill_season() → generate_site() → git commit+push. Used by Task Scheduler and MCP (via background subprocess). Includes file lock (prevents concurrent runs, uses `os.kill(pid, 0)` for stale PID detection), zombie DB entry cleanup on startup, git operation timeouts (30s each), and overall pipeline timeout (180s, disabled for Task Scheduler).
- `mcp_server.py` — MCP server with 5 tools: update_rankings, get_weekly_rankings, get_season_rankings, get_player_stats, get_update_status. Runs via stdio transport. update_rankings launches auto_update as a **background subprocess** (Popen) and returns immediately — NEVER call auto_update() synchronously inside the MCP server, as it blocks the stdio transport and freezes Claude Code.
- `validate_against_v10.py` — Validation script comparing Python calc engine to v10 Excel outputs
- `game_breakdown.py` — Full TED/TAP game breakdown tool. Shows raw box score, per-36/pace-adjusted stats, all component calculations (EP36p, DPS, OP), and final assembly with OP as its own line. When PM data available, shows DOPM section (PM, PM36, PM36p, DOPM, OPD, TAPD) and three-column final assembly (TED, TAP, TAPD). Multi-game table includes TDOPM and PM columns. Three modes: `python -m phase2.game_breakdown "Doncic"` (most recent), `"Jokic" 2026-03-11` (specific date), `"Jokic" last 10` (multi-game summary). **USE THIS when the user asks for a player's game stats.**

### Standalone Scripts (project root)
- `run_backfill.py` — Runs season backfill (Oct 22 → present); safe to restart (skips already-scraped games)
- `scrape_last_week.py` — One-off script to scrape a specific week's games (used for Feb 16-22 testing)
- `build_historical_json.py` — One-time script to generate `phase2/historical_rankings.json` from v9 (1950-2017) + scraped (2018-2024) CSVs. Calculates TED, TAP, and TAPD (when historical PM data available, seasons 2000+) for all qualifying players (G>=40, MP>=20) across 1950-2024, groups by decade, includes all-time top 200 and decade top 100 (both ranked by TED). Tiered per-year top_n: 40 (2013+), 30 (1984-2012), 20 (1982-1983), 10 (1950-1981). Includes `fix_encoding()` for double-encoded UTF-8 names in scraped CSV. Has safety-net dedup logic. TAPD computed by averaging game-level PM from `historical_pm` table and passing as `game_plus_minus` to calculator.
- `update_rankings.bat` — Batch file wrapper for Task Scheduler (also at `C:\Projects\tap_update.bat`). Uses full Python path (Microsoft Store alias doesn't work from Task Scheduler).
- `build_pm_op_sheet.py` — Creates "DOPM Method" and "DOPM Conceptual" worksheets in TED Model v10.xlsx. DOPM Method: worked examples, terminology, constants, multi-game comparison table. DOPM Conceptual: 7-section design rationale (time-scale mismatch, DPS subtraction rationale, 3 TAP modes, implementation details).
- `backfill_plus_minus.py` — Re-scrapes historical game box scores to populate the `plus_minus` column (safe to restart, skips rows that already have PM data)
- `scrape_historical_pm.py` — Scrapes historical PM + MP from BR box scores for seasons 2000-2024 (lightweight, only 7 columns per row). Stores in `historical_pm` table for computing season-average TAPD. Restartable (skips scraped games, resumes from last date). CLI: `--status`, `--season YEAR`, `--oldest-first`. Scrapes newest seasons first by default. **Superseded by v2** for new scraping — v1 scrapes individual box score pages (~30K requests), v2 scrapes player game log pages (~870 ranked, ~3,350 full).
- `scrape_historical_pm_v2.py` — Scrapes season-average PM from BR player game log pages (one page per player-season). Much more efficient than v1 (~870 requests for ranked players, ~3,350 for full dataset vs ~30K box score pages). Stores summary rows in `historical_pm` table with `team='AVG'`. CLI: `--status`, `--season YEAR`, `--full` (all players in dataset, not just ranked). Includes `fix_encoding()` for double-encoded UTF-8 names in scraped CSVs.
- `add_first_names.py` — Cross-matches v9 last-name-only players with Basketball Reference full names. Scrapes ~69 BR per-game stats pages via pd.read_html. 96 manual name mappings for edge cases. Run with `--apply` to modify CSV.
- `update_v9_2017.py` — Updates v9 Year=2017 partial-season entries with full-season averages from scraped data. Matches 146 players, handles double-encoded UTF-8 and Kanter→Freedom name change. Run with `--apply` to modify CSV.
- `update_v10_data.py` — Syncs v10 workbook with cleaned v9 CSV. Rebuilds Raw Data (v9 Year<=2016 + scraped 2017-2025), handles Calculations row count, regenerates Rankings/All-Time Top 100/Current Season output sheets. Run after any v9 CSV changes.

### Configuration Files
- `.mcp.json` — MCP server configuration; tells Claude Code how to launch the TAP Rankings MCP server

## v9 Formula Chain (mapped from TAP v4 Row 5)

Full calculation chain traced from v9's actual cell formulas. This is the reference for building the v10 Calculations sheet.

### Calculation Flow (83 columns, A-CE)
1. **Pace**: E = Pace * 36/48 (possessions per 36 min)
2. **And-1s / Shots**: M = FTA*0.25, N = (FTA-And1s)/2, AK = FGA+FTOP
3. **Per-36 stats**: P (RB36), V-W (NA36), AP (Shots36), etc. — all `stat / MP * 36`
4. **Pace-adjusted**: Q (RB36p), X (NA36p), etc. — all `stat36 * Base_Pace / Pace`
5. **Defense (DPS)**: Two paths averaged:
   - DBPM path: Z→AA→AB (DBPM * possessions normalization)
   - DWS path: AD→AE→AF→AG→AH (DWS normalized for G/MP/pace, minus 3.8 baseline, * 1.3)
   - AI/AJ = average of both paths
6. **Scoring efficiency**: AN (P/Shot), AO-AZ (avg_Shots, S_Created, P_Created, EP36, EP36p)
7. **Offensive Production (OP)**: Two paths averaged then decomposed:
   - OBPM path: BD→BE→BF (OBPM * possessions normalization)
   - OWS path: BI→BJ→BK→BL (OWS normalized, minus 3.8 baseline, * 0.65)
   - BM = average of both paths
   - Strip out P/Shot effect (BN-BQ) and RB/NA diffs (BS-BU)
   - BV = OP (residual)
8. **Final stats**: BW (EP36pop = EP36p + OP), BX (TAP), BB-BC (rTAPd, TAPd), BY-CE (MAP decomposition: PMSEp, RB_adj, NA_adj, DPS36p, rMAP, OP, MAP)

### Key v9 Validation Values (Harden 2017, original partial season)
- TAP = 51.46, EP36p = 35.09, OP = 2.58, DPS36p = -0.16
- rTAPd = 51.04, TAPd = 48.88
- Note: These were from the original partial 2017 season (35 games) used for v10 validation. v9 CSV now has full-season data.

## Project Status

- Jan 2018 PDF has been fully read and understood
- TED Model v9.xlsx has been reviewed and understood (23 sheets, 551 players, 1948-2017)
- Known data gaps: incomplete OBPM/OWS data, P/Shot baseline issue across eras
- **Scraping COMPLETE** — All 9 seasons (2018-2026) scraped successfully (4,970 players total)
- **v9 extraction COMPLETE** — 2,043 historical player-season rows + coefficients + pace data
- **Year convention CONFIRMED** — v9 uses start-year (Year=2016 = 2016-17 season)
- **v10 workbook CREATED** — Raw Data (6,798 rows) + Coefficients sheets populated
- **v9 formula chain MAPPED** — All 83 columns traced from actual cell formulas
- **v10 Calculations sheet BUILT** — 54 columns (A-BB), all formulas filled for 6,798 rows
- **TED + TAP both implemented** — TED (paper's original, RB×0.6) and TAP (with OP, RB×0.5967)
- **Key finding:** Paper's TED was in TED Pace v3E (not TAP v4). TAP v4's "TED" col was experimental variant.
- **v9 experimental "TED" renamed to MAP** (Marginal Added Production) — now implemented in v10 (cols BA-BB)
- **v10 VALIDATED against v9** — ALL stats match perfectly (0.000000 diff) including TAP/OP, after implementing era-varying P/Shot OP baselines matching v9. Only remaining diff: Curry 2016 DPS (v9 manual override). Details in v10-formulas.md.
- **Output sheets BUILT** — Rankings (3,810 filtered rows), All-Time Top 100, Current Season (2025-26)
- **PHASE 1 COMPLETE** — v10 workbook has 11 sheets (6 original + LaMelo Analysis + P-Shot Analysis + DOPM Method + DOPM Conceptual), full TED+TAP calculations, validated, formatted output
- **Phase 2 COMPLETE** — Full autonomous weekly system operational (scraper, DB, calc engine, website, MCP server, Task Scheduler)
- **Phase 2 calc engine VALIDATED** — Perfect match against v10 across all eras (SGA/Jokic 2024, Jordan 1996, Bird 1986, Wilt 1964)
- **Phase 2 scraper TESTED** — Successfully scrapes game box scores, season averages, advanced stats, and pace from BR
- **Phase 2 season rankings WORKING** — Season-to-date TED/TAP top 20 producing reasonable results (Jokic #1)
- **Season backfill COMPLETE** — 889 games scraped (Oct 22, 2025 → Feb 28, 2026), full 2025-26 season through present. Run `python run_backfill.py` to add new games (safe to restart, skips already-scraped).
- **Scraper rewritten: Selenium → cloudscraper + BeautifulSoup** — Selenium suffered chronic Chrome renderer timeouts, zombie process accumulation, and stale lock files. Switched to cloudscraper (same tool used successfully in Phase 1 bulk scraping). No browser process management needed. Tested and working (daily games, season averages, advanced stats, pace all verified).
- **UTF-8 encoding fix applied** — cloudscraper detects BR responses as ISO-8859-1 (incorrect) but content is UTF-8. This caused double-encoding of accented characters (č, ć, é, ü, Ş → garbled). Fixed by setting `resp.encoding = 'utf-8'` in `_get_page()` before accessing `resp.text`. 9 corrupted player names from initial cloudscraper scrape (Dončić, Şengün, Diabaté, Bogdanović, Matković, Jakučionis, Traoré, Niederhäuser, Dёmin) fixed in DB.
- **BR posting lag** — Basketball Reference posts box scores overnight/early morning after games are played. Uses SportRadar data feed with corrections within 24 hours. **5 AM was too early** — Mar 1 games returned 0 results at 5 AM but 11 games later that morning. Moved to 6 AM. BR daily summary pages can also return next-day game IDs (e.g., Feb 28 page showing March 1 game links).
- **Website BUILT** — `phase2/site_generator.py` generates `docs/index.html` (static HTML, TED-only). Two tables: Weekly TED Top 100 (left/first) + Season-to-date TED Top 100 (right/second). Black background, white text, Courier New + Georgia serif fonts. Basketball SVG in header colored orange (#ee7623). Season header banner (black background, orange text, styled like decade headers) sits between decade nav and current-season tables.
- **Website POLISHED** — Mobile-responsive CSS refined: header centering (text-align + inline/block display toggle), reduced cell padding for mobile fit, `@media` block at end of CSS for correct specificity. TED stat numbers use `letter-spacing: -0.5px`. TED description: justify on desktop, center on mobile. Shai Gilgeous-Alexander special-cased to display as "Shai Gilgeous-" / "Alexander" on mobile (avoids 3-line wrap). Name suffixes (Jr., Sr., III, II, IV) use `&nbsp;` to stay attached. Player names on mobile use `overflow: hidden; text-overflow: ellipsis` to clip instead of wrapping.
- **DPS coefficients SPLIT: TED ×1.5, TAP ×2.5** — Defense amplified differently for TED vs TAP (history: 1.0 → 2.0 → 2.5 → 3.0 → 2.75 → 2.0 → 2.5 → 2.0 → split TED ×1.5 / TAP ×2.5). Split because TED double-counts the defensive component of turnovers and defensive rebounds (see future-analysis-items.md #10, #11), while TAP's OP residual corrects for this. MAP uses TAP coefficient. Config: `DPS_COEFF_TED`, `DPS_COEFF_TAP`, `DPS_COEFF` (backward compat alias = TAP value).
- **GitHub Pages LIVE** — https://joeldechant.github.io/nba-ted-rankings/ (repo: github.com/joeldechant/nba-ted-rankings, deploys from `docs/` on `main` branch). Renamed from nba-tap-rankings in Mar 2026.
- **Project cleanup DONE** — Removed 24 stale files (12 temp artifacts from file-generation workarounds, 8 one-time debug scripts, 3 test CSVs, `__pycache__/`). All Phase 1/Phase 2 scripts and data files retained.
- **MCP server BUILT** — `phase2/mcp_server.py` with 5 tools (update_rankings, get_weekly_rankings, get_season_rankings, get_player_stats, get_update_status). FastMCP SDK, stdio transport. Configured in `.mcp.json`. Tested: all tools register, player lookup works (accent-insensitive search), status tool returns live DB stats.
- **MCP config hot-reload** — The MCP server calls `importlib.reload(config)` at the top of every lookup tool, so changes to `config.py` (exclusion list, coefficients, era baselines) take effect immediately without restarting. Changes to `calculator.py` or `weekly_update.py` (formula/logic rewrites) still require an MCP server restart, but those are rare. The `update_rankings` tool, website, and Task Scheduler are never affected (fresh processes).
- **Auto-update pipeline BUILT** — `phase2/auto_update.py` runs backfill → site generate → git push. Used by both MCP `update_rankings` tool and Task Scheduler.
- **Windows Task Scheduler CONFIGURED** — Task "TAPRankingsUpdate" runs daily at 6:00 AM via `C:\Projects\tap_update.bat`. Logs to `logs/auto_update.log`. Runs on battery, catches up on missed runs.
- **MCP stdout fix** — Original problem: `auto_update()` prints progress to stdout, corrupting the MCP stdio JSON-RPC protocol. First fix (redirect_stdout to stderr) still blocked the MCP server synchronously, causing Claude Code to freeze for minutes. **Final fix:** `update_rankings` now launches `python -m phase2.auto_update` as a detached background subprocess (Popen) and returns immediately. The MCP server is never blocked. Use `get_update_status` to check completion.
- **Backfill optimization** — `backfill_season()` was scanning from `SEASON_START_DATE` (Oct 22) every run, making ~130 HTTP requests just to skip already-scraped dates. Added `db.get_last_game_date()` so it starts from the last game date in the DB instead (1-2 requests for a typical weekly update).
- **Double-scrape fix** (Mar 2, 2026) — BR daily summary pages can return game IDs from adjacent dates (e.g., Feb 28 page showing March 1 game links). `scrape_date_range()` now adds each scraped game_id to `skip_game_ids` immediately after insertion, preventing duplicate scraping when the same game appears on multiple daily summary pages.
- **Lock file fix** — Replaced `tasklist /FI` process check (broken in Git Bash — `/FI` gets mangled to a file path) with Python-native `os.kill(pid, 0)` for stale PID detection.
- **MCP hang fix** — `update_rankings` tool was calling `auto_update()` synchronously, blocking the MCP stdio server and freezing Claude Code (sometimes for 2+ hours). Root causes: (1) any synchronous work inside an MCP stdio tool handler blocks the entire server, (2) `git push` had no timeout so could hang forever, (3) `_refresh_season_data()` re-scraped BR every run even when data was fresh. Fixes: `update_rankings` now launches the pipeline as a background subprocess (Popen); `auto_update.py` has 30s git timeouts and 180s pipeline timeout; `weekly_update.py` has 6-hour freshness check to skip redundant BR scrapes.
- **MCP file handle bug** (Mar 1, 2026) — `update_rankings` used `with open(log_file, "w") as log:` around the `Popen` call. The `with` block closed the file handle immediately after `Popen` returned, breaking the subprocess's stdout pipe. First `print()` in auto_update hit a broken pipe and the process died silently (empty 0-byte log). **Fix:** Added `--log <path>` argument to `auto_update.py` so the subprocess opens and owns its own log file handle, avoiding Windows file handle inheritance issues entirely. The MCP server passes `--log` to the Popen call.
- **Task Scheduler reconfigured and tested** (Mar 1, 2026) — Original task had never actually run (Last Run Time = "never", error 267011). Settings were wrong: "Interactive only" mode, "No Start On Batteries". Fixed via PowerShell: `StartWhenAvailable = $true` (catch up missed runs), `DisallowStartIfOnBatteries = $false`, `StopIfGoingOnBatteries = $false`, `WakeToRun = $true`. Still "Interactive only" (changing to "run whether logged on or not" requires password via Task Scheduler GUI). Batch file updated to use full Python path (Microsoft Store app alias doesn't work from Task Scheduler). **Successfully tested**: Task fired on schedule, exit code 0, full pipeline completed.
- **TROUBLESHOOTING: Zombie Python processes** — MCP-launched `auto_update` subprocesses can hang (e.g., stuck on git push timeout) and survive as zombie processes that hold `logs/auto_update.log` locked. Symptoms: Task Scheduler runs exit code 1, log file not updated, "file is being used by another process" errors. **Fix:** Check for stale Python processes (`Get-Process python*` in PowerShell), kill any from hours/days ago, remove `phase2/.update.lock` if stale, then re-run. Future improvement: auto_update.py could force-kill child git processes on timeout.
- **v9 historical data cleaned** (Mar 1, 2026) — Found and removed 9 duplicate (player, year) rows in `v9_historical_data.csv`. Root cause: v9 Excel workbook had duplicate entries with different Pace values (for teams not in v9's 16-team pace table) or data entry errors. Each duplicate resolved by keeping the row with BR-verified correct values:
  - Marion 2000 (wrong DWS=5.3 removed, correct=6.4), 2001 (exact duplicate), 2003 (wrong Pace=89.9 removed, correct=92.6), 2004 (wrong Pace=91.1 removed, correct=95.9)
  - Camby 2000 (wrong Pace=91.0 removed, correct=86.7)
  - Mullin 1987 (wrong Pace=99.9 removed, correct=101.6)
  - Smith 2009 (wrong Pace=93.2 removed, correct=90.1), 2010 (wrong 3P=0.0 removed, correct=0.7)
  - Millsap 2011 (bad row with DBPM=-1.9/DWS=0.3 removed; remaining row corrected: DBPM 2.1→1.3, Pace 90.2→91.4, both BR-verified)
  - Jermaine O'Neal 2002 renamed from "O'Neal" to "J O'Neal" (matching his other 3 entries, distinguishing from Shaquille)
  - CSV went from 2,043 total rows to 2,034 (1,965 player rows + 69 mid-file year headers); original 2,043 count included mid-file headers. Dick McGuire (1950) later removed (Mar 2026), bringing CSV to 2,033 (1,964 player rows + 69 headers).
- **First names added to v9 data** (Mar 1, 2026) — All 1,960 of 1,965 v9 player entries updated from last-name-only to full first+last names. Used `add_first_names.py` to cross-match with Basketball Reference per-game stats pages (pd.read_html, ~69 BR requests). 96 manual name mappings for edge cases (Abdul-Jabbar, Antetokounmpo, misspellings like "Beldsoe"→Bledsoe, "Daughtery"→Daugherty). 5 pre-1960 players left as-is (not used in historical rankings).
- **v9 2017 data updated to full season** (Mar 1, 2026) — v9's Year=2017 was a partial mid-season snapshot (paper written Jan 2018, ~35 games for top players). Updated all 146 Year=2017 entries with full-season averages from scraped Basketball Reference data (e.g., Harden: 35→72 games, Curry: 29→51 games). Used `update_v9_2017.py` to cross-match v9 names with scraped 2017-18 season data, with fix_encoding() for double-encoded UTF-8 names and manual mapping for Enes Kanter→Enes Freedom (BR retroactive name change). `build_historical_json.py` updated to use v9 for 1960-2017 (was 1960-2016) and scraped for 2018-2024 (was 2017-2024), making v9 the single source of truth through 2017.
- **PHASE 2 COMPLETE** — Full autonomous daily system: scraper, DB, calc engine, website, MCP server, Task Scheduler. Site updates automatically every day at 6 AM.
- **Historical TED Rankings ADDED** — Website includes historical sections below the current-season tables:
  1. **Per-Year Rankings by Decade** — Top 40 (2013+), Top 30 (1984-2012), Top 20 (1982-1983), Top 10 (1950-1981) for each year, organized under decade headers (2020s→1950s). Decade header "s" rendered smaller via `.decade-s` span. All players now have full first+last names. v9 data (1950-2017) has no team (shows "—"). Scraped data (2018-2024) has teams. Traded players show "TOT" (Basketball Reference combined row).
  2. **Decade Navigation** — White nav links (2020s, 2010s, ..., 1950s) with anchor scrolling, positioned under TED description.
  3. **Desktop layout** — Year tables displayed two per row (CSS grid `1fr 1fr`), matching weekly/season-to-date side-by-side layout. Falls back to single column on mobile (<900px). Odd years in a decade display as single centered table.
  - Data source: `phase2/historical_rankings.json` (static, generated by `build_historical_json.py`, stores both TED and TAP values, sorted by TED)
  - Historical data is baked into HTML at generation time — no changes needed to auto_update.py pipeline
  - To regenerate historical data: `python build_historical_json.py` then `python -m phase2.site_generator`
- **v10 synced with cleaned v9 CSV** (Mar 2026) — Ran `update_v10_data.py` to apply all v9 CSV fixes to v10: first names for 1,819 pre-2018 players, 9 duplicate rows removed, Millsap 2011 corrected. Raw Data: 6,798→6,788 rows. Rankings: 3,810→3,800. Output sheets (Rankings, All-Time Top 100, Current Season) regenerated. Calculations formulas preserved and recalculated. LaMelo Analysis sheet preserved.
- **IMPORTANT: v9 CSV, v9 Excel, and v10 must stay in sync** — When changes are made to `v9_historical_data.csv` for pre-2017 data, the same changes must also be made in `TED Model v9.xlsx` (TAP v4 sheet). Run `update_v10_data.py` to sync v10. Also update `build_historical_json.py` → JSON → site if historical data changes. See `memory/future-analysis-items.md` item #7 for details.
- **Website switched from TAP to TED** (Mar 2026) — Default display is TED. `build_historical_json.py` stores both TED and TAP values, sorted/ranked by TED. `site_generator.py` displays TED by default with hidden TAP toggle.
- **GitHub repo renamed back** (Mar 2026) — nba-ted-rankings → nba-tap-rankings. URL: https://joeldechant.github.io/nba-tap-rankings/. Git remote updated locally.
- **TED/TAP toggle** (Mar 2026) — Clicking the basketball SVG or the "TAP Click Here" / "TED Click Here" text link under it toggles between TED and TAP views. Orange toggle link text (`#ee7623`, Georgia serif, 0.75em) updates dynamically: shows "TAP Click Here" when on TED view, "TED Click Here" when on TAP view. Implementation in `site_generator.py`:
  - Dual current-season tables: `div.view-ted` (visible) and `div.view-tap` (hidden), each with weekly + season-to-date grids
  - Dual description blocks: `div.desc-ted` and `div.desc-tap` in CSS grid overlay (same cell, `visibility: hidden` to toggle — keeps both in layout so container height = taller description, preventing layout shift)
  - H1 title toggles between "TED Rankings" and "TAP Rankings"
  - Toggle link element: `div.toggle-link#toggle-link` between basketball SVG and season header
  - Season header: `div.season-header` with orange h3 text, positioned between decade nav and current-season tables (replaces old italic subtitle in header)
  - Dual historical per-year tables: fully separate TED-sorted and TAP-sorted table sets wrapped in `view-ted`/`view-tap` divs. Players re-ranked by the active stat so ranks reflect correct sort order. Decade IDs use `-tap` suffix for TAP version to avoid duplicate IDs.
  - All-time top 200: click "Historical TED/TAP Rankings" header to toggle. Current season merged in at site generation time.
  - Decade nav links use JS click handler with `data-decade` attribute to scroll to the correct visible section based on current stat mode
  - JavaScript `doToggle()` function attached to both `.basketball` click and `#toggle-link` click events; uses `querySelectorAll('.view-ted'/'.view-tap')` to toggle all table sets (current-season + historical)
  - TAP description finalized in the generator (describes TAP as building on TED with OBPM/OWS overlay for residual offensive impact like "shooting gravity that warps defenses, or anti-gravity"). Includes inclusion threshold note: "Players must meet a 20 minutes per game and 40 games per season threshold for inclusion."
  - Floating toggle button: fixed-position 40px orange basketball SVG in bottom-right corner (`div.float-toggle#float-toggle`). Allows toggling TED/TAP from anywhere on the page without scrolling to top. No text overlay.
  - Scroll position preservation: `findScrollAnchor()` finds the nearest visible anchor element (year-table, decade header, all-time header, or historical header) within the viewport and records its viewport offset; after toggle, finds the matching element in the new view and restores exact position. Viewport filtering (`rect.bottom < 0 || rect.top > vh`) prevents off-screen elements from being selected as anchors. 2px threshold skips unnecessary `scrollTo` calls that cause mobile jiggle. Sticky table headers excluded as anchor candidates (unreliable `getBoundingClientRect()` during DOM swaps).
  - **Status: LIVE — tested, committed, pushed to GitHub Pages**
- **Player career popup** (Mar 2026) — Click any player name in any table to see a floating popup with their full career TED or TAP history. Respects current TED/TAP toggle state.
  - Data sources: `build_historical_json.py` generates `career_data` (830 players, 3,468 player-seasons, G>=40/MP>=20) and `season_stats` (75 years of top-10 avg + leader) in `historical_rankings.json`. Current season (2025-26) merged at site generation time from `calculate_season_rankings()` full results.
  - `weekly_update.py`: `calculate_season_rankings()` returns `'all': results` in addition to top-100 TED/TAP lists (backward compatible).
  - `site_generator.py`: `build_career_js()` merges historical + current season data, embeds as `window.CAREER` and `window.SEASON_STATS` JS objects (~200KB). All `<td class="player">` elements get `data-player` attribute. Popup HTML (`div.career-overlay` + `div.career-popup`), CSS, and JS added inline.
  - Popup columns: Season | Team | TED/TAP | TOP 10 (avg of top 10 players) | High (season leader value). All centered. Most recent season at top. Context-year highlighting: clicking from a historical year table highlights that year's row in orange (#ee7623); clicking from current-season tables highlights current year.
  - JS: `showCareer(name, contextYear)` builds table rows from `window.CAREER[name]`, `closeCareer()` hides overlay. Click handler extracts `data-year` from nearest `.year-table` ancestor (falls back to `currentYear` for current-season tables). Event delegation on `.container` for clicks on `td.player[data-player]`. Close via X button, click outside, or Escape key. `doToggle()` calls `closeCareer()` on stat switch.
  - Player names: `cursor: pointer` + opacity hover effect, no underline, no color change.
  - **Status: LIVE**
- **P/Shot OP baseline updated** (Mar 4, 2026) — Added 1.16 for 2020+ era (was 1.13 for all 2016+). League-avg P/Shot rose ~0.03-0.06 above 1.13 in the 2020s. Updated in: `config.py` (ERA_PSHOT_BASELINES), v10 Calculations column AM (IFS formula), v10 Coefficients B24, historical JSON, website (pushed to GitHub Pages). v10 now has 9 sheets (added P-Shot Analysis). Era baselines now: 1.16 (2020+), 1.13 (2016-2019), 1.10 (1982-2015), 1.08 (1976-81), 1.03 (1962-75), 0.98 (1957-61), 0.93 (pre-1957).
- **P-Shot Analysis worksheet rebuilt** (Mar 4, 2026) — Comprehensive worksheet with: P/Shot formula, full EP36 + OP extraction formula chains, effect of higher baseline (with practical example), era baselines table, data source caveats (v9 subset +0.009 bias vs full BR), 2017-18 overlap comparison, decision rationale, historical P/Shot table (1970-2026, 57 rows, color-coded by source), sensitivity analysis (top 20 TAP at 1.13/1.16/1.17), rank changes table, P/Shot trend chart.
- **Daily Top 40 toggle** (Mar 2026) — Clicking the "WEEKLY TOP 100" header bar swaps it with a "DAILY TOP 40" table showing the most recent game day's top performers (MP >= 20). Uses `db.get_last_game_date()` to find the most recent day with game data (not hardcoded to yesterday). Clicking the daily header swaps back. Works for both TED and TAP views. If no qualifying players, shows "No data available". Implementation: `generate_site()` calls `calculate_weekly_rankings(last_game_date, last_game_date)` and takes top 40. Weekly and daily tables wrapped in `.weekly-daily-slot` div; JS click handler toggles visibility. Header has `cursor: pointer` and hover effect.
- **All-time top 200 toggle** (Mar 2026) — Click "Historical TED Rankings" or "Historical TAP Rankings" header to reveal the all-time top 200 best individual seasons, sorted by TED or TAP. Click the all-time table header to swap back to decade view. Current 2025-26 season players merged at site generation time. Data from `build_historical_json.py` (`all_time_top_200` key) + current season from `calculate_season_rankings()['all']`. Rendered by `render_all_time_html()` in `site_generator.py`. **Status: LIVE.**
- **Decade top 100 toggle** (Mar 2026) — Click any decade header (2020s, 2010s, ..., 1950s) to reveal the top 100 individual seasons for that decade, sorted by TED or TAP. Click the decade top 100 header to swap back to per-year tables. Data pre-computed in `build_historical_json.py` (`decade_top_100` key per decade). Current season merged into 2020s at site generation time. Decades with fewer than 100 qualifying seasons show all available (1960s: 82, 1950s: 92). Rendered by `render_decade_top100_html()` in `site_generator.py`. HTML structure: `.decade-years` (year tables) + `.decade-top100` (hidden) inside each `.decade` div. **Status: LIVE.**
- **Decade toggle fixed** (Mar 2026) — Two bugs in decade top 100 / all-time top 200 toggle: (1) year-pair tables were not wrapped in a container div, so they stayed visible alongside the decade top 100 (both showed simultaneously, making sections ~7000px longer than intended); (2) scroll-back on collapse didn't work because `scrollIntoView()` on a `position: sticky; top: 0` element is a no-op — browser considers it "already visible." Fix: wrapped year-pairs in `.decade-years` div for proper show/hide toggling. Added `collapseAndScroll(toHide, toShow, scrollTarget)` helper that hides, shows, then calls `.closest('.decade').scrollIntoView()` to scroll to the non-sticky parent container. All-time top 200 collapse also works (`.historical-header` is not sticky, so `scrollIntoView` works directly).
- **Collapse scroll conditional** (Mar 9, 2026) — `collapseAndScroll()` and all-time collapse handlers now check `getBoundingClientRect().top <= 5` before scrolling. If the header is in its natural position (not floating/stuck), collapsing just hides/shows content without scrolling — avoids confusing screen jump when user hasn't scrolled far into the list.
- **All-time/decade header text orange** (Mar 9, 2026) — `.all-time-table .year-table .table-header h2` and `.decade-top100 .year-table .table-header h2` set to `color: #ee7623`. Needed `.year-table` in the selector chain for specificity over `.year-table .table-header h2 { color: #000 }`.
- **TED/TAP toggle scroll preservation improved** (Mar 9, 2026) — Replaced `findVisibleYear()` (only found `data-year` tables) with `findScrollAnchor()` that also detects decade headers, all-time table headers, and historical section headers as scroll anchors. Toggle now preserves scroll position when inside expanded decade top 200 or all-time top 400 lists. Also syncs `.decade-years` display state alongside `.decade-top100` on toggle.
- **Column dividers thickened** (Mar 9, 2026) — All year-pair column dividers changed from `1px solid #555` (thin gray) to `2px solid #fff` (thick white), matching the current-season tables-grid. Applied to per-year tables, all-time, decade lists, and mobile overrides. Border on container div (runs through headers).
- **Decade headers non-sticky** (Mar 9, 2026) — Removed `position: sticky; top: 0; z-index: 10` from `.decade-header`. Decade headers now scroll normally with the page. Only the white `.table-header` elements remain sticky at `top: 0` (same behavior as current-season weekly/season-to-date headers). Previously decade headers and table headers both stuck at top:0, causing overlap and visual gap issues.
- **v9 Excel synced with CSV** (Mar 4, 2026) — `sync_v9_excel.py` applied all CSV cleanup changes to v9 TAP v4 sheet: 1,960 first names added, 9 duplicate rows deleted, Millsap 2011 corrected (DBPM→1.3, Pace→91.4), O'Neal 2002 renamed to J O'Neal. Backup at `TED Model v9 - BACKUP.xlsx`.
- **Dick McGuire removed from all data** (Mar 8, 2026) — Dick McGuire (1950, TED 14.6) removed as extreme low outlier. Deleted from v9 CSV, v9 Excel (TAP v4 row 2233), v10 synced (6789→6788 rows, Rankings 3801→3800), historical JSON rebuilt, site regenerated. No exclusion list — removed at source.
- **Project cleanup #2** (Mar 8, 2026) — Removed 19 files: NUL (Windows artifact), conversation_only.txt, nash_tap_by_season.txt, nash_vs_herro.txt, v9_formula_blueprint.txt (captured in v10-formulas.md), v9_name_mapping.csv (names already applied), 3 Task Scheduler setup scripts (set_schedule.ps1, set_trigger.ps1, task_schedule.xml), 6 test log files, 2 superseded scraped CSVs (all_seasons_2018_2025.csv, pace_2018_2025.csv), 2 __pycache__ directories.
- **GOAT tab IMPLEMENTED** (Mar 10, 2026) — "GOAT" link in decade nav (after 1950s) shows the #1 TED/TAP player for every season from 1960 onward. Columns: Yr | Player | TED/TAP | TOP 9* | DIFF. TOP 9* is a modified average: standard top 10 minus the #1 player, divided by 9 — isolates how far above the field the leader was without the leader inflating the baseline. This calc is GOAT-table-only; career popup and all other contexts use standard top 10 avg. DIFF = leader value minus TOP 9*. Pre-1960 seasons excluded (small player pools skew DIFF). Click orange DIFF header to sort by DIFF descending; click again to return to year sort. Sort mode persists across TED/TAP toggle. Sticky white/orange header + sticky black column headers (at `top: 44px`). Collapse via nav link click or header click. Player names clickable for career popup. Rendered by `render_goat_html()` in `site_generator.py`. Data from `season_stats` in `historical_rankings.json` + current season merge. **Status: LIVE.**
  - **GOAT sort modes** (5 modes + `goatTextOpen` boolean, managed by `goatSortMode` variable in IIFE scope):
    - `year` — default chronological sort (most recent first)
    - `diff` — sorted by DIFF descending. Inserts either an orange separator `<tr class="goat-orange-sep">` or a text `<tr class="goat-text-row">` after row 30, depending on `goatTextOpen`. Separator uses `font-size: 1px; line-height: 6px; color: #ee7623` to force height in `border-collapse: collapse` tables.
    - `val` — sorted by TED/TAP value descending
    - `player` — sorted by appearance count descending, tiebreak by best DIFF, within-player sorted by TED/TAP value
    - `diff-player` — top 30 DIFF only, sorted by appearance count within that top 30, tiebreak by DIFF. Rows 31+ hidden.
  - **`goatTextOpen` boolean** — Independent of sort mode. When true, an inline `<tr class="goat-text-row">` replaces the orange separator at the cutoff position. Clicking the separator opens text; clicking the text closes it. `textOpen` persists across diff↔diff-player transitions (clicking PLAYER does NOT reset it). Resets to false on DIFF header, VAL, or YR clicks.
  - **Conditional cutoff message** — In `diff` mode, text shows "Click PLAYER above to sort the top 30 DIFF seasons and see the GOAT candidates!" (original styling). In `diff-player` mode, text shows "Watch out for the herd of GOATs above!" (with `min-height:2.4em` + flex centering for vertical centering in two-line space).
  - **State transitions**: DIFF header toggles `diff`↔`year` (resets textOpen). PLAYER header toggles `player`↔`year` or `diff-player`↔`diff` (preserves textOpen). YR/VAL always reset textOpen.
  - **IMPORTANT: `goatSort()` must filter separator and text rows** — `tbody.querySelectorAll('tr:not(.goat-orange-sep):not(.goat-text-row)')` prevents these rows from entering sort functions that access `cells[4]`.
  - **TOP 9* tooltip** — Click the "TOP 9*" column header to see a popup: "* average of top 9 TAP/TED scores that season excluding the winner (ie. avg of rank #2–10)". Dynamically detects active stat (TED/TAP). White border, dark background, fixed position below header. Dismisses on any click anywhere on the screen.
  - **Season hint dropdown** — Click "2025-26 Season" header to reveal: "Everything you see in ORANGE is CLICKABLE for added functionality!" Orange italic Georgia serif text, animated max-height transition. "Click here" hint text appended to header in small font. Clicking the hint text itself also closes it.
  - **Orange = clickable convention** — All interactive headers colored orange (#ee7623): weekly/daily table headers, historical header, GOAT nav link text, PLAYER column header in GOAT table. Season-to-date header stays black (not clickable for sort).
- **GOAT sub-header border fixes** (Mar 11, 2026) — Two issues fixed:
  - **Right border**: Sticky `thead` with GPU compositing painted over the container's border. Fixed with `box-shadow: 3px 0 0 #fff` on `.goat-table thead` (renders outside border-collapse model, stays aligned). GOAT-specific because it's the only single-column expandable table where the container border is the sole right edge.
  - **Bottom border variable thickness**: The `.player` th had `overflow: hidden` (from text-overflow: ellipsis) while other th cells didn't. In `border-collapse`, cells with `overflow: hidden` render their portion of shared borders at correct thickness; cells without it render thinner on Retina displays. Fixed by adding `overflow: hidden` to all `thead th` globally. Also moved `border-bottom` from `thead th` to `thead tr` (single continuous line, matching how `tbody tr` borders work). Removed `transform: translateZ(0)` from `thead` (was causing GPU layer boundary artifacts; originally added for mobile sticky rendering after toggle).
  - **TOP 9* header spacing**: `text-indent: 7px` on `thead th.num.goat-avg` pushes the header text right without changing column width.
  - **GOAT mobile padding**: Reduced from 6px to 3px horizontal padding on `.goat-table td, .goat-table thead th` in mobile media query to prevent table overflow on narrow screens (375px).
- **G2 tab IMPLEMENTED** (Mar 11, 2026) — "G2" link in decade nav (after GOAT) shows the **top TWO** TED/TAP players per season (1960 onward), catching edge cases where two players both had GOAT-level DIFFs in the same year (e.g., 2024-25 SGA over Jokic). Same columns as GOAT: Yr | Player | TED/TAP | TOP 9* | DIFF. Every row is self-contained (year and TOP 9* on both #1 and #2 rows). ~130 rows total (2 per year × 65 years). Header text: "TOP 2 TED BY SEASON" / "TOP 2 TAP BY SEASON". CSS class `.g2-table`, thead classes `.g2-sort-yr`, `.g2-sort-player`, `.g2-sort-val`, `.g2-avg`, `.g2-sort-diff`. Data from `g2_ted`/`g2_tap` fields in `season_stats` (added to `build_historical_json.py` and current-season merge in `site_generator.py`). **Status: LIVE.**
  - **Row attributes**: `data-rank="1"` and `data-rank="2"` distinguish finishers. `data-sort-year` assigned via JS on page load for stable year sorting.
  - **GOAT/G2 mutual exclusion** — Clicking GOAT hides G2 and vice versa. Only one can be visible at a time. Toggling is handled in the nav link click handlers.
  - **G2 sort modes** (5 modes + `g2TextOpen` boolean, managed by `g2SortMode` variable, independent from GOAT):
    - `year` — default chronological sort (most recent first), #1 before #2 within same year
    - `diff` — sorted by DIFF descending. Orange separator or text row after row **40** (not 30 like GOAT).
    - `val` — sorted by TED/TAP value descending
    - `player` — sorted by appearance count descending, tiebreak by **average DIFF** (average of all DIFF values in the current list for that player, not best single or career average), within-player sorted by TED/TAP value
    - `diff-player` — top 40 DIFF only, sorted by appearance count within that top 40, tiebreak by average DIFF. Rows 41+ hidden.
  - **`g2TextOpen` boolean** — Same behavior as GOAT: separator↔text toggle, persists across diff↔diff-player, resets on DIFF/VAL/YR. Conditional message: diff → "Click PLAYER..." prompt; diff-player → "Watch out for the herd of GOATs above!"
  - **Name matching**: Uses `getName()` helper that reads `data-player` attribute (not `textContent.trim()`, which can include HTML artifacts from `format_player_name()` — non-breaking spaces, concatenated span text).
  - **Average DIFF tiebreak**: When players have the same appearance count in player sort, compare average of all their DIFF values in the current ranking (not career, not best single). Implemented via `sortByCount()` which computes `totalDiff` and `avgDiff` from the current `arr`.
  - **TED/TAP toggle sync**: `doToggle()` syncs G2 visibility alongside GOAT, calls `g2ApplySort()`.
  - **Mobile**: G2 CSS mirrors GOAT mobile overrides (3px padding, reduced font sizes). `.year-pair.single > :last-child` hidden on mobile to prevent white placeholder bar in odd-year decades (2020s has 5 years).
- **G3 tab IMPLEMENTED** (Mar 11, 2026) — "G3" link in decade nav (after G2) shows the **top THREE** TED/TAP players per season (1960 onward). Same columns as GOAT/G2: Yr | Player | TED/TAP | TOP 9* | DIFF. Every row self-contained. ~195 rows (3 per year × 65 years). Header text: "TOP 3 TED BY SEASON" / "TOP 3 TAP BY SEASON". CSS class `.g3-table`, thead classes `.g3-sort-yr`, `.g3-sort-player`, `.g3-sort-val`, `.g3-avg`, `.g3-sort-diff`. Data from `g3_ted`/`g3_tap` fields in `season_stats` (added to `build_historical_json.py` and current-season merge in `site_generator.py`). **Status: LIVE.**
  - **Row attributes**: `data-rank="1"`, `data-rank="2"`, and `data-rank="3"` distinguish finishers. `data-sort-year` assigned via JS on page load.
  - **GOAT/G2/G3 mutual exclusion** — Only one can be visible at a time. Each nav handler hides the other two when opening.
  - **G3 sort modes** (5 modes + `g3TextOpen` boolean, managed by `g3SortMode` variable, independent from GOAT and G2):
    - `year` — default chronological sort (most recent first), #1 before #2 before #3 within same year
    - `diff` — sorted by DIFF descending. Orange separator or text row after row **50**.
    - `val` — sorted by TED/TAP value descending
    - `player` — sorted by appearance count descending, tiebreak by average DIFF, within-player sorted by TED/TAP value
    - `diff-player` — top 50 DIFF only, sorted by appearance count within that top 50, tiebreak by average DIFF. Rows 51+ hidden.
  - **`g3TextOpen` boolean** — Same behavior as GOAT/G2: separator↔text toggle, persists across diff↔diff-player, resets on DIFF/VAL/YR. Conditional message: diff → "Click PLAYER..." prompt; diff-player → "Watch out for the herd of GOATs above!"
  - **Reuses G2 patterns**: `getName()`, `sortByCount()`, `sortByDiff()` helpers. Average DIFF tiebreak. `doToggle()` syncs G3 visibility and calls `g3ApplySort()`.
  - **CSS**: All G2 selectors extended to include G3 equivalents (20+ selector groups).
  - **Mobile nav layout**: 4 decade icons per row (2020s-1990s, then 1980s-1950s), GOAT/G2/G3 on third row. Uses `.nav-break` divs (hidden on desktop, `display: block; width: 100%; height: 0` on mobile) for flex-wrap line breaks.
- **TOP 9* tooltip fixes** (Mar 11, 2026) — Three related fixes to the TOP 9* tooltip popup (`.goat-avg-tooltip`, shared across GOAT/G2/G3):
  - **Width**: Set to `max-width: 220px` for balanced 3-line display on mobile.
  - **Text**: Updated to `'* average of the top 9 ' + activeStat + ' scores that season excluding the winner (ie. avg of rank #2–10)'` — added "the" before "top 9". Three instances in generator (one per GOAT/G2/G3 IIFE).
  - **Click-blocking fix**: When tooltip is open, clicking anywhere on the page now closes it WITHOUT triggering the clicked element's action (no player popups, no decade navigation, no GOAT/G2/G3 toggling). Implementation: capture-phase document click handler (`addEventListener(..., true)`) checks if tooltip has `.active` class, removes it, then calls `stopImmediatePropagation()` + `preventDefault()` to block all other handlers. `preventDefault()` is critical because GOAT/G2/G3 are `<a href="#">` — without it, the browser follows the `#` anchor and scrolls to the page top. Additional guards added to: container click handler (for player names), decade nav handler, GOAT/G2/G3 nav handlers, historical header handler.
- **Career popup overlay click fix** (Mar 11, 2026) — Overlay click handler changed from `if (e.target === overlay) closeCareer()` to unconditional `closeCareer()` — clicking anywhere on the overlay (including on the popup itself) now closes it. Added `body.career-open` CSS class: `.container { pointer-events: none }` + `.career-overlay { pointer-events: auto }` to prevent clicks from passing through the overlay to elements underneath.
- **DOPM (Daily Offensive Plus Minus) IMPLEMENTED** (Mar 14, 2026) — Alternative daily/weekly TAP using raw game PM instead of OBPM/OWS to derive a game-level OP residual. Avoids the inverse relationship where monster box score games get very negative OP from season-level advanced stats.
  - **Naming**: PM (raw game plus/minus, i.e. Daily Plus Minus), PM36 (per 36 min), PM36p (pace-adjusted), DOPM = PM36p - DPS36p (Daily Offensive Plus Minus — isolates offense by subtracting defense), OPD (DOPM residual after stripping P/Shot, RB, NA), TAPD (TAP using OPD instead of standard OP)
  - **DPS subtraction**: Uses full DPS36p (averaged DBPM+DWS paths), not raw DBPM alone. DWS path normalization (baseline subtraction, ×1.3 multiplier) puts it on the same scale as DBPM. The two paths disagreeing is feature not bug — DPS captures defensive impact better than DBPM alone.
  - **Calculation chain**: PM → PM36 (÷MP×36) → PM36p (×pace_factor) → subtract DPS36p → DOPM → strip P/Shot effect (PMSEp), RB diff, NA diff → OPD → EP36p + OPD + RB + NA + DPS → TAPD
  - **Implementation**: Parallel path in `calculator.py` (triggered by `game_plus_minus` parameter) — does NOT affect standard TED/TAP/OP values. `database.py` has `plus_minus` column in game_box_scores. `scraper.py` captures BR `+/-` column. `weekly_update.py` passes PM through and produces `tapd` rankings. `game_breakdown.py` shows DOPM section and TAPD in output.
  - **Excel**: "DOPM Method" worksheet in v10 with overview, terminology, constants, worked example, and multi-game comparison table (built by `build_pm_op_sheet.py`). "DOPM Conceptual" worksheet with full 7-section design rationale. v10 now has 11 sheets.
  - **Backfill COMPLETE**: `backfill_plus_minus.py` re-scraped all historical box scores to populate PM. All game_box_scores rows now have PM data.
  - **Website integration**: `site_generator.py` uses TAPD for daily/weekly TAP view via `_remap_tapd()` helper (remaps `tapd` → `tap` in result dicts so `render_table()` works unchanged). Falls back to standard TAP when no PM data covers the ranking window. Season-to-date always uses standard TAP. Column header stays "TAP" regardless of source.
  - **3 TAP modes for daily/weekly**: (1) Standard OP from per-game OBPM/OWS (original), (2) Season OP override (`USE_SEASON_OP_FOR_WEEKLY=True`), (3) TAPD from game PM (current default for website). Season-to-date rankings always use mode 1.
  - **Scaling validation DONE** (Mar 14, 2026) — Compared avg PM36p vs BPM36p (OBPM+DBPM) vs ODS36p (OPS+DPS raw, no coefficients) across top 40 players by minutes (all per-36 pace-adjusted). Results: PM36p mean +2.4, BPM36p mean +1.6, ODS36p mean +0.7. PM runs ~0.8 above BPM and ~1.7 above ODS — systematic offset (not scaling mismatch), preserves rank order. Correlation: PM vs BPM 0.51, PM vs ODS 0.65. The WS paths pull ODS lower via 3.8 baseline subtraction (replacement-level anchoring) — DWS36p averages 3.16 vs baseline 3.8, so DWS_adj is negative on average (-0.8), while OWS36p averages 4.73, so OWS_adj is slightly positive (+0.6). Combined WS-adjusted mean ≈ -0.2 (near zero, as expected). Conclusion: DPS subtraction from PM is well-calibrated; PM's higher mean is team-quality noise that ODS strips out via baseline subtraction.
  - **Matched-pair analysis DONE** (Mar 15, 2026) — Same-player same-game comparison across 97 daily qualifying players (MP>=20): TAP - TED = -0.36, TAPD - TAP = +1.04, TAPD - TED = +0.67. Season-to-date: TAP - TED = 0.00. Confirms no scaling issues between any of the three stats.
  - **Daily top-40 selection bias** (Mar 15, 2026) — Key finding: when viewing the top 40 daily players, TED/TAP/TAPD look dramatically different because of selection bias:
    - (1) **No scaling issue** — all three stats are on the same scale across all players.
    - (2) **Standard TAP fades top daily performers** — OP regresses game performance toward season average. Q1 (top TED) players lose 5.6 pts on average from OP; Q4 (bottom TED) gain 2.9. The top 40 only shows the penalty side, making TAP look consistently lower than TED.
    - (3) **TAPD has different top-40 composition** — PM variance reshuffles rankings. Guys like Derrick White (TED #36 → TAPD #7) and Kawhi (TED #6 → TAPD #50) swap in/out. The two top-40 lists share only ~60-70% of players, making side-by-side comparison misleading.
    - (4) **TAPD upside outliers from PM variance** — Single-game PM has enormous variance (swings from -16 to +33 observed), creating fatter tails. The top-40 list disproportionately captures the noisy upside tail of PM, making TAPD look like it's "juicing" stats relative to TED — but the full-population average is only +0.67 higher. The apparent inflation is a selection artifact, not a real scaling difference. Some upside outliers are real signal (off-ball gravity/defense invisible to box scores), some are blowout noise — can't distinguish on a single day. Over a week the noise compresses; over a season it disappears entirely.
- **Player of the Month IMPLEMENTED** (Mar 15, 2026) — Click orange season-to-date header to reveal "PLAYER OF THE MONTH TED/TAP" table (top 100). Click monthly header to swap back. Uses `calculate_weekly_rankings(month_start, last_game_date)` — same function as weekly/daily, just with first-of-month as start date. TAP column uses TAPD (same as daily/weekly). Resets at beginning of each month. Implementation mirrors weekly/daily toggle: `.season-monthly-slot` wrapper div, CSS for orange clickable header, JS click handler, state synced in `doToggle()` across TED/TAP views. Minimal additional computation (~1-2 seconds).
  - **POTM winners popup**: Clicking the orange "Rank" sub-header in the monthly table opens a popup showing all monthly leaders for the season (Month | Player | TED/TAP). Computed by looping through each month (Oct through current) and calling `calculate_weekly_rankings()` per month. Data embedded as `window.MONTH_WINNERS` JS object. Current month row highlighted in orange. Close behavior matches career popup exactly (X button, overlay click, Escape key, `body.potm-open` class). `closePotm()` called in `doToggle()`. Popup respects TED/TAP toggle (shows correct stat and leader).
  - **Monthly min games filter**: October = 3 games minimum, all other months = 8 games minimum. Filter applied ONLY to completed months (in the POTM winners popup). Current month rankings table is unfiltered during the month itself — the filter is purely historical for determining past month winners.
  - **Status: LIVE.**
- **Historical PM scraping** (Mar 15-16, 2026) — Two approaches: v1 (`scrape_historical_pm.py`) scrapes individual box score pages (~30K requests); v2 (`scrape_historical_pm_v2.py`) scrapes player game log pages (~870 ranked, ~3,350 full). **v2 is the preferred approach** — always use player game log pages for historical BR data needing game-level stats. Ranked subset (870 player-seasons) complete; full dataset scrape in progress (2,096/5,206 as of Mar 16). Full scrape captures all players with seasonal data: v9 players for 2000-2016, scraped CSV players for 2017-2024. This data improves TAPD accuracy on the website (more players = better TOP 10 averages) and will be added to v10 Excel (future item #13).
- **Historical TAPD toggle REFACTORED** (Mar 16, 2026) — Per-year toggle (not full-section swap). Clicking orange TAP sub-header (`th.stat-toggle`) on any year >= 2000 toggles that year to TAPD and back independently. Years without TAPD data show skeleton rows (rank numbers, empty cells) that populate as PM scraping completes. Pre-2000 years stay white/non-clickable. Historical header always says "Historical TAP Rankings". `doToggle()` resets all per-year toggles. TAPD header uses `text-indent: -4px` for slight left shift on desktop. TEAM column locked with `width/min-width/max-width: 62px` on `.stat`. Desktop player names use `white-space: nowrap`. Status: 2024-25 populated, others pending scraping.
