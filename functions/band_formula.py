"""
BAND FORMULA - Cross-instrument per-song 'band diff' (diff_band)
built on top of each instrument's own Expert-anchored D

Needs >= 2 core instruments with a real D (> 0) to mean anything - otherwise no band row / no write

Each instrument's D is placed on two continuous scales that agree with its own values:
    continuous CalcTier - log(D / BASE_D) / LN_INC + 1, floored at 0
                          floor() of it is exactly that instrument's CalcTier
   
    continuous Remap    - position inside the instrument's own remap bins (log-interpolated between
                          the bin edges), centred on each label so rounding gives back its RemapDiff

    CalcBandTier  = floor(blended CalcTier), uncapped
    RemapBandDiff = blended Remap, standard rounding (2.5 -> 3), capped 0-6
"""

import math

from functions import fret_formula, drum_formula, vocal_formula

# -------------
# Participants
# -------------
LEAD_PRIORITY = ['guitar', 'keys']    # first present wins the lead/core slot
CORE_SUPPORT = ['bass', 'drums']      # always core, when present
MODIFIER_KEYS = ['vocals', 'keys']    # keys counts here only if it didn't win the lead slot

# fixed left-to-right order for the xlsx 'Instruments' column
# excl coop/rhythm
BAND_ROLE_ORDER = ['guitar', 'bass', 'drums', 'keys', 'vocals']

# tier-space params per instrument, reused as-is from each instrument's own calibration
TIER_PARAMS = {
    'guitar': (fret_formula.BASE_D, fret_formula.LN_INC),
    'coop':   (fret_formula.BASE_D, fret_formula.LN_INC),
    'rhythm': (fret_formula.BASE_D, fret_formula.LN_INC),
    'bass':   (fret_formula.BASE_D, fret_formula.LN_INC),
    'keys':   (fret_formula.BASE_D, fret_formula.LN_INC),
    'drums':  (drum_formula.BASE_D, drum_formula.LN_INC),
    'vocals': (vocal_formula.BASE_D, vocal_formula.LN_INC),
}

# remap bin edges per instrument, reused as-is from each instrument's own calibration
REMAP_BINS = {
    **{key: fret_formula.REMAP_BINS[group] for key, group in fret_formula.CALIBRATION_GROUP.items()},
    'drums':  drum_formula.DRUM_REMAP_BINS,
    'vocals': vocal_formula.VOCAL_REMAP_BINS,
}

REMAP_MIN, REMAP_MAX = 0, 6

# blend weights
W_PEAK = 0.4    # how hard a standout core instrument pulls band diff toward itself
W_SWAY = 0.2    # how much vocals / non-lead keys can nudge the result

# keeps a D sitting exactly on an upper bin edge inside that bin (edges are (lower, upper])
_EDGE_EPS = 1e-9


# continuous CalcTier - floor() matches the instrument's own CalcTier, floored at 0 like CalcTier
def _continuous_calc_tier(D, instrument):
    base_d, ln_inc = TIER_PARAMS[instrument]
    return max(0.0, math.log(D / base_d) / ln_inc + 1)


# continuous Remap - label L spans (L - 0.5, L + 0.5), so standard rounding returns RemapDiff
# bin 0 starts at D = 0 so it interpolates linearly, the open top bin borrows the previous
# bin's log width and tops out at the bin's upper half
def _continuous_remap(D, instrument):
    edges = REMAP_BINS[instrument]
    for label, (lower, upper) in enumerate(zip(edges[:-1], edges[1:])):
        if math.isinf(upper):
            width = math.log(lower / edges[label - 1])
            frac = math.log(D / lower) / width
        elif D <= upper:
            frac = D / upper if lower <= 0 else math.log(D / lower) / math.log(upper / lower)
        else:
            continue
        return label - 0.5 + min(max(frac, 0.0), 1.0 - _EDGE_EPS)
    return float(REMAP_MAX)


# standard rounding (2.5 -> 3), not Python's round-half-to-even
def _round_half_up(value):
    return int(math.floor(value + 0.5))


def _lead_key(present):
    for key in LEAD_PRIORITY:
        if key in present:
            return key
    return None


# core average pulled toward the standout core, then nudged toward the modifiers
def _blend(values, lead):
    core = [values[k] for k in ([lead] + CORE_SUPPORT) if k in values]
    core_avg = sum(core) / len(core)
    base = core_avg + W_PEAK * (max(core) - core_avg)

    mods = [values[k] for k in MODIFIER_KEYS if k != lead and k in values]
    if not mods:
        return base
    return base + W_SWAY * (sum(mods) / len(mods) - base)


# d_by_instrument: {instrument_key: D or None}
def calc_band_d(d_by_instrument):
    # only instruments with a real D take part - a zero/missing D has no real remap/tier
    usable = {
        key: D for key, D in d_by_instrument.items()
        if key in TIER_PARAMS and D is not None and D > 0
    }

    lead = _lead_key(usable)
    core_keys = [k for k in ([lead] + CORE_SUPPORT) if k and k in usable]
    if len(core_keys) < 2:
        return {'RemapBandDiff': None, 'CalcBandTier': None}

    calc_t = _blend({k: _continuous_calc_tier(D, k) for k, D in usable.items()}, lead)
    remap_r = _blend({k: _continuous_remap(D, k) for k, D in usable.items()}, lead)

    return {
        'RemapBandDiff': max(REMAP_MIN, min(REMAP_MAX, _round_half_up(remap_r))),
        'CalcBandTier': int(math.floor(calc_t)),
    }
