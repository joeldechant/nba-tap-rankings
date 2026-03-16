"""Phase 2 Calculator — TED/TAP/MAP formula engine.

Implements the full calculation chain matching v10 Excel exactly.
See memory/v10-formulas.md for complete formula reference.
"""

from . import config


def calculate_stats(player_data, pace, advanced=None, season_g=None, season_mp=None,
                    override_op=None, game_plus_minus=None):
    """Calculate TED, TAP, and MAP for a single player.

    Args:
        player_data: dict with per-game averages:
            pts, mp, fg, fga, three_p, ft, fta, rb, ast, stl, blk, tov, g
            Plus: player, team, season_year (for identification/era baseline)
        pace: team pace (possessions per 48 min)
        advanced: dict with season-to-date: dbpm, dws, obpm, ows
            If None, DPS and OP are set to 0.
        season_g: games played for the season (for DWS/OWS normalization).
            If None, uses player_data['g'].
        season_mp: season-to-date MPG (for DWS/OWS normalization).
            If None, uses player_data['mp'].
        override_op: if provided, use this value for OP instead of deriving
            from OBPM/OWS. Used for weekly/daily TAP where season-to-date OP
            is more appropriate than per-game derivation (avoids the inverse
            relationship where better box score games get more negative OP).
        game_plus_minus: raw game PM (Daily Plus Minus, i.e. box score +/-),
            or average PM over a window. When provided, derives DOPM by:
            1. PM → PM36 (per-36) → PM36p (pace-adjusted)
            2. Subtracting DPS36p (season defense) to isolate offense → DOPM
            3. Running the same OP stripping (P/Shot, RB, NA) → OPD
            The result appears as 'dopm', 'opd', and 'tapd' in output.
            Does NOT affect the standard 'op' or 'tap' values.

    Returns:
        dict with all intermediate and final values, or None if mp == 0.
    """
    # Extract inputs
    pts = float(player_data.get('pts', 0) or 0)
    mp = float(player_data.get('mp', 0) or 0)
    fga = float(player_data.get('fga', 0) or 0)
    fta = float(player_data.get('fta', 0) or 0)
    rb = float(player_data.get('rb', 0) or player_data.get('trb', 0) or 0)
    ast = float(player_data.get('ast', 0) or 0)
    stl = float(player_data.get('stl', 0) or 0)
    blk = float(player_data.get('blk', 0) or 0)
    tov = float(player_data.get('tov', 0) or 0)
    g = int(player_data.get('g', 1) or 1)
    season_year = player_data.get('season_year', config.CURRENT_SEASON_YEAR)

    # For DWS/OWS normalization — use season totals, not weekly
    norm_g = season_g if season_g is not None else g
    norm_mp = season_mp if season_mp is not None else mp

    if mp == 0:
        return None

    # === Pace Factor ===
    poss36 = pace / 48 * 36
    pace_factor = config.BASE_POSS_36 / poss36  # = 95 / pace

    # === And-1s / Shots ===
    and1s = fta * config.AND1_RATE
    ftop = (fta - and1s) / 2
    shots = fga + ftop

    # === Per-36 conversions ===
    p36 = pts / mp * 36
    shots36 = shots / mp * 36
    rb36 = rb / mp * 36
    na_pg = (ast * config.AST_WEIGHT
             + stl * config.STL_WEIGHT
             + blk * config.BLK_WEIGHT
             - tov * config.TOV_WEIGHT)
    na36 = na_pg / mp * 36

    # === Pace-adjusted ===
    p36p = p36 * pace_factor
    shots36p = shots36 * pace_factor
    rb36p = rb36 * pace_factor
    na36p = na36 * pace_factor

    # === P/Shot ===
    p_shot = pts / shots if shots > 0 else 0

    # === EP36 (additive approach — matches v10 spreadsheet) ===
    avg_shots36 = p36 / config.PSHOT_BASELINE
    s_created = avg_shots36 - shots36
    p_created = s_created * config.PSHOT_BASELINE
    ep36 = p36 + p_created

    # Pace-adjusted EP36
    avg_shots36p = p36p / config.PSHOT_BASELINE
    s_created_p = avg_shots36p - shots36p
    p_created_p = s_created_p * config.PSHOT_BASELINE
    ep36p = p36p + p_created_p

    # === Defense (DPS) — average of DBPM and DWS paths ===
    dbpm36 = 0
    dbpm36p = 0
    ws_dps36 = 0
    ws_dps36p = 0
    dps36 = 0
    dps36p = 0

    if advanced:
        dbpm = advanced.get('dbpm')
        dws = advanced.get('dws')

        if dbpm is not None:
            dbpm = float(dbpm)
            # DBPM path: convert per-100-poss to per-36-min, then pace-adjust
            dbpm36 = dbpm / 100 * poss36
            dbpm36p = dbpm36 * pace_factor

        if dws is not None:
            dws = float(dws)
            # DWS path: normalize to full-season 36-min rate
            if norm_g > 0 and norm_mp > 0:
                adj_dws = dws * (82 / norm_g) / norm_mp * 36
            else:
                adj_dws = 0
            dwse = adj_dws - config.DWS_BASELINE
            ws_dps36 = dwse * config.WS_DPS_MULTIPLIER
            ws_dps36p = ws_dps36 * pace_factor

        if dbpm is not None and dws is not None:
            dps36 = (dbpm36 + ws_dps36) / 2
            dps36p = (dbpm36p + ws_dps36p) / 2
        elif dbpm is not None:
            dps36 = dbpm36
            dps36p = dbpm36p
        elif dws is not None:
            dps36 = ws_dps36
            dps36p = ws_dps36p

    # === Offense (OP) — TAP only, from OBPM + OWS ===
    op = 0
    pmse_p = 0
    pm_other = 0
    ops36p = 0

    if advanced:
        obpm = advanced.get('obpm')
        ows = advanced.get('ows')

        pm_op = 0
        ws_ops = 0
        has_obpm = obpm is not None
        has_ows = ows is not None

        if has_obpm:
            obpm = float(obpm)
            opm36p = obpm * (config.BASE_POSS_36 / 100)
            pm_op = opm36p * config.OBPM_MULTIPLIER

        if has_ows:
            ows = float(ows)
            if norm_g > 0 and norm_mp > 0:
                adj_ows_raw = ows * (82 / norm_g) / norm_mp * 36
                adj_ows = adj_ows_raw / poss36 * config.BASE_POSS_36
            else:
                adj_ows = 0
            owse = adj_ows - config.OWS_BASELINE
            ws_ops = owse * config.WS_OPS_MULTIPLIER

        if has_obpm and has_ows:
            ops36p = (pm_op + ws_ops) / 2
        elif has_obpm:
            ops36p = pm_op
        elif has_ows:
            ops36p = ws_ops

        # OP extraction — strip out what box score already explains
        era_baseline = config.get_era_pshot_baseline(season_year)
        pshot_diff_op = p_shot - era_baseline
        pmse_p = shots36p * pshot_diff_op
        pm_other = ops36p - pmse_p

        rb_diff = (rb36p - config.RB_AVG_BASELINE) * config.RB_COEFF_TAP
        na_diff = (na36p - config.NA_AVG_BASELINE) * config.NA_COEFF
        rb_na_adj = rb_diff * config.RB_DIFF_WEIGHT + na_diff * config.NA_DIFF_WEIGHT

        op = (pm_other - rb_na_adj) * config.OP_MULTIPLIER

    # Override OP if provided (weekly/daily mode — use season-to-date OP)
    if override_op is not None:
        op = override_op

    # === DOPM (Daily Offensive Plus Minus) — alternative OP from game PM ===
    # When game_plus_minus is provided, derive OP from raw PM instead of OBPM/OWS.
    # Flow: PM → PM36 → PM36p → subtract DPS36p → DOPM → strip box-score effects → OPD
    dopm = None       # Daily Offensive Plus Minus (PM36p minus defense)
    opd = None        # OPD = OP Daily (OP residual derived from DOPM)
    pm36 = None
    pm36p = None
    tapd = None       # TAPD = TAP Daily (TAP using OPD instead of standard OP)
    if game_plus_minus is not None:
        pm36 = float(game_plus_minus) / mp * 36
        pm36p = pm36 * pace_factor
        dopm = pm36p - dps36p  # subtract defense to isolate offense = DOPM

        # Same OP stripping as standard path
        era_baseline = config.get_era_pshot_baseline(season_year)
        pshot_diff_pm = p_shot - era_baseline
        pmse_p_pm = shots36p * pshot_diff_pm
        pm_other_pm = dopm - pmse_p_pm

        rb_diff_pm = (rb36p - config.RB_AVG_BASELINE) * config.RB_COEFF_TAP
        na_diff_pm = (na36p - config.NA_AVG_BASELINE) * config.NA_COEFF
        rb_na_adj_pm = rb_diff_pm * config.RB_DIFF_WEIGHT + na_diff_pm * config.NA_DIFF_WEIGHT

        opd = (pm_other_pm - rb_na_adj_pm) * config.OP_MULTIPLIER

        # TAPD: TAP using OPD (DOPM-derived OP)
        ep36pop_dopm = ep36p + opd
        tapd = (ep36pop_dopm
                + rb36p * config.RB_COEFF_TAP
                + na36p * config.NA_COEFF
                + dps36p * config.DPS_COEFF_TAP)

    # === Final Stats ===
    ep36pop = ep36p + op

    # DPS coefficients (separate for TED and TAP — see future-analysis-items.md #6, #10, #11)
    dps_coeff_ted = config.DPS_COEFF_TED
    dps_coeff_tap = config.DPS_COEFF_TAP

    # TED (paper's original — no OP, RB * 0.6)
    ted = ep36p + rb36p * config.RB_COEFF_TED + na36p * config.NA_COEFF + dps36p * dps_coeff_ted
    rted = ep36 + rb36 * config.RB_COEFF_TED + na36 * config.NA_COEFF + dps36 * dps_coeff_ted

    # TAP (with OP, RB * 0.5967)
    tap = ep36pop + rb36p * config.RB_COEFF_TAP + na36p * config.NA_COEFF + dps36p * dps_coeff_tap
    # TAPd / rTAPd = "TAP deflated" — TAP without OP (pure box-score calculation).
    # Legacy concept from v10 Excel (cols AV-AW). NOT the same as TAPD (TAP Daily).
    tap_deflated = ep36p + rb36p * config.RB_COEFF_TAP + na36p * config.NA_COEFF + dps36p * dps_coeff_tap
    rtap_deflated = ep36 + rb36 * config.RB_COEFF_TAP + na36 * config.NA_COEFF + dps36 * dps_coeff_tap

    # MAP (conceptual decomposition: PMSEp + RB_Diff*0.45 + NA_Diff*0.3 + DPS36p*coeff + OP)
    rb_diff_val = (rb36p - config.RB_AVG_BASELINE) * config.RB_COEFF_TAP
    na_diff_val = (na36p - config.NA_AVG_BASELINE) * config.NA_COEFF
    map_val = (pmse_p
               + rb_diff_val * config.RB_DIFF_WEIGHT
               + na_diff_val * config.NA_DIFF_WEIGHT
               + dps36p * dps_coeff_tap
               + op)
    rmap = (pmse_p
            + rb_diff_val * config.RB_DIFF_WEIGHT
            + na_diff_val * config.NA_DIFF_WEIGHT
            + dps36p * dps_coeff_tap)

    return {
        'player': player_data.get('player', ''),
        'team': player_data.get('team', ''),
        'g': g,
        'mp': mp,
        'pts': pts,
        'pace': pace,
        # Intermediates
        'poss36': poss36,
        'pace_factor': pace_factor,
        'p36': p36, 'p36p': p36p,
        'shots36': shots36, 'shots36p': shots36p,
        'rb36': rb36, 'rb36p': rb36p,
        'na36': na36, 'na36p': na36p,
        'ep36': ep36, 'ep36p': ep36p,
        'p_shot': p_shot,
        'dps36': dps36, 'dps36p': dps36p,
        'ops36p': ops36p,
        'pmse_p': pmse_p,
        'op': op, 'ep36pop': ep36pop, 'override_op': override_op,
        # DOPM — Daily Offensive Plus Minus (None if game_plus_minus not provided)
        'pm36': pm36, 'pm36p': pm36p, 'dopm': dopm,
        'opd': opd, 'tapd': tapd,
        'game_plus_minus': game_plus_minus,
        # Final stats
        'ted': ted, 'rted': rted,
        'tap': tap, 'tap_deflated': tap_deflated, 'rtap_deflated': rtap_deflated,
        'map': map_val, 'rmap': rmap,
    }
