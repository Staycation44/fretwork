"""
5 FRET FORMULA v2 - Per-song difficulty scalar, computed from outputs of functions.density.compute_density_metrics

Updates over v1:
refined for window gating some metrics (median and stdev now operate off of active windows only)
Scaling CoV - better account of spikes over the course of the song / rest sections
Stamina term to discount shorter songs, and slowly build a boost for longer songs

D = N * V * COV * STAM

    epsN = aNPS * 0.05
    N = ((medNPS + epsN) * aNPS * pNPS) ** (1 / 3)
    cvN = stdNPS / (medNPS + aNPS)

    epsV = aVPS * 0.05
    V = ((medVPS + epsV) * aVPS * pVPS) ** (1 / 3)
    cvV = stdVPS / (medVPS + aVPS)

    COV = 1 + c_scale * (cvN * cvV) ** 0.5

    STAM = (DurationS / t_ref) ** s_stam

    # base scalar difficulty
    D = N * V * COV * STAM

N & V balance peak segment impact against average and median
COV is the interaction that accounts for uneven difficulty - more variable songs >1, less variable -> 1
epsilon prevents median values of 0 from collapsing D while still being derived from song data

D/N/V/COV are computed identically regardless of instrument

RemapDiff (0-6 bins) and CalcTier (log-scaled) are instrument-specific - see Methodology.md for calibration data

EMHX / RemapDiff & CalcTier anchor to expert, since only 1 diff value per instrument in song.ini
"""

import math

# ------------------------------------------------------------
# Calibration groups - guitar/coop/rhythm share, bass & keys are separate
# ------------------------------------------------------------
CALIBRATION_GROUP = {
    'guitar': 'guitar',
    'coop':   'guitar',
    'rhythm': 'guitar',
    'bass':   'bass',
    'keys':   'keys',
}

# ---------------------------------
# Remap (0-6) params, per group
# ---------------------------------
DIFF_LABELS = [0, 1, 2, 3, 4, 5, 6]   # shared label set

# Bin edges calibrated so RemapDiff distribution roughly matches diff_* tag's official distribution in the reference library - see Methodology.md
# Methodology.md has table data for these bins
GUITAR_REMAP_BINS = [0, 8.0, 13.7, 21.2, 29.0, 38.2, 55.2, math.inf]
BASS_REMAP_BINS   = [0, 3.5, 8.3, 13.1, 19.1, 25.6, 36.2, math.inf]
KEYS_REMAP_BINS   = [0, 1.3, 4.8, 9.6, 16.3, 25.2, 35.2, math.inf]

REMAP_BINS = {
    'guitar': GUITAR_REMAP_BINS,
    'bass':   BASS_REMAP_BINS,
    'keys':   KEYS_REMAP_BINS,
}

# --------------------------------------------
# CalcTier (log-scaled) params
# --------------------------------------------
# ~One tier per LN_INC of log(D / BASE_D)
# One shared pair for every group.
# Split them per calibration group here if/when they're actually fit separately.
BASE_D = 7.6
LN_INC = 0.44


# RB manual 0-6 fit
def remap_diff(D, instrument='guitar'):
    if D <= 0:
        return 0  # broken/zero-density songs -> 0
    bin_edges = REMAP_BINS[CALIBRATION_GROUP[instrument]]
    lower = bin_edges[0]
    for label, upper in zip(DIFF_LABELS, bin_edges[1:]):
        if lower < D <= upper:
            return label
        lower = upper
    return None

# log tier calculation
def calc_tier(D, instrument='guitar'):
    if D < BASE_D:
        return 0
    return int(math.floor(math.log(D / BASE_D) / LN_INC) + 1)

# D Formula - N/V/COV/D only, instrument-agnostic 
# Split from the tier calls so RemapDiff/CalcTier can be anchored to the Expert level's D
def calc_nvcov(metrics):
    pNPS, medNPS, aNPS, stdNPS = metrics['pNPS'], metrics['medNPS'], metrics['aNPS'], metrics['stdNPS']
    pVPS, medVPS, aVPS, stdVPS = metrics['pVPS'], metrics['medVPS'], metrics['aVPS'], metrics['stdVPS']
    DurationS = metrics['DurationS']

    # NPS combo
    epsN = aNPS * 0.05
    N = ((medNPS + epsN) * aNPS * pNPS) ** (1 / 3)
    cvN = stdNPS / (medNPS + aNPS)

    # VPS combo
    epsV = aVPS * 0.05
    V = ((medVPS + epsV) * aVPS * pVPS) ** (1 / 3)
    cvV = stdVPS / (medVPS + aVPS)

    # CoV interaction across NPS & VPS
    c_scale = 4 # tuneable scale value (impact of COV)
    COV = 1 + c_scale * (cvN * cvV) ** 0.5

    # STAMINA!!! sublinear by duration / slowly building boost for long songs, discounts short songs
    # ~66% @ 30s, ~75% @ 60s, 83% @ 90s, etc / 1x @ t_ref / 1.1x @ ~6 mins, 1.2x @ 9.5 mins, etc
    t_ref  = 230.0 # 3-4 min average song
    s_stam = 0.20 # curve exponent
    STAM = (DurationS / t_ref) ** s_stam

    # base scalar difficulty
    D = N * V * COV * STAM

    return {
        'N': N,
        'V': V,
        'COV': COV,
        'STAM': STAM,
        'D': D,
    }

# RemapDiff/CalcTier anchored to the Expert level's D
def anchor_remap_tier(expert_metrics, instrument='guitar'):
    if expert_metrics is None:
        return None, None
    expert_D = calc_nvcov(expert_metrics)['D']
    return remap_diff(expert_D, instrument), calc_tier(expert_D, instrument)
