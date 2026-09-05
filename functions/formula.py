"""
FORMULA - Per-song difficulty scalar, computed from outputs of functions.density.compute_density_metrics

D = N * V * COV

    epsN = pNPS * 0.05
    N = ((medNPS + epsN) * aNPS * pNPS) ** (1 / 3)
    cvN = stdNPS / (aNPS + medNPS)

    epsV = pVPS * 0.05
    V = ((medVPS + epsV) * aVPS * pVPS) ** (1 / 3)
    cvV = stdVPS / (aVPS + medVPS)

    COV = 1 + (cvN * cvV) ** 0.5

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
# CalcTier (log-scaled) params, per group
# --------------------------------------------
# ~One tier per LN_INC of log(D / BASE_D). Shared across all three groups for now
GUITAR_BASE_D, GUITAR_LN_INC = 7.6, 0.44
BASS_BASE_D,   BASS_LN_INC   = 7.6, 0.44
KEYS_BASE_D,   KEYS_LN_INC   = 7.6, 0.44

CALCTIER_PARAMS = {
    'guitar': (GUITAR_BASE_D, GUITAR_LN_INC),
    'bass':   (BASS_BASE_D, BASS_LN_INC),
    'keys':   (KEYS_BASE_D, KEYS_LN_INC),
}


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
    base_d, ln_inc = CALCTIER_PARAMS[CALIBRATION_GROUP[instrument]]
    if D < base_d:
        return 0
    return int(math.floor(math.log(D / base_d) / ln_inc) + 1)

# D Formula - N/V/COV/D only, instrument-agnostic 
# Split out from calc_diff so RemapDiff/CalcTier calc can be anchored to Expert level's D
def calc_nvcov(metrics):
    pNPS, medNPS, aNPS, stdNPS = metrics['pNPS'], metrics['medNPS'], metrics['aNPS'], metrics['stdNPS']
    pVPS, medVPS, aVPS, stdVPS = metrics['pVPS'], metrics['medVPS'], metrics['aVPS'], metrics['stdVPS']

    # NPS combo
    epsN = pNPS * 0.05
    N = ((medNPS + epsN) * aNPS * pNPS) ** (1 / 3)
    cvN = (stdNPS / (aNPS + medNPS))

    # VPS combo
    epsV = pVPS * 0.05
    V = ((medVPS + epsV) * aVPS * pVPS) ** (1 / 3)
    cvV = (stdVPS / (aVPS + medVPS))

    # CoV interaction across NPS & VPS
    COV = 1 + (cvN * cvV) ** 0.5

    # base scalar difficulty
    D = N * V * COV

    return {
        'N': N,
        'V': V,
        'COV': COV,
        'D': D,
    }

# D Formula - self-anchored
def calc_diff(metrics, instrument='guitar'):
    nvcov = calc_nvcov(metrics)
    D = nvcov['D']

    return {
        **nvcov,
        'RemapDiff': remap_diff(D, instrument),
        'CalcTier': calc_tier(D, instrument),
    }

# RemapDiff/CalcTier anchored to the Expert level's D
def anchor_remap_tier(expert_metrics, instrument='guitar'):
    if expert_metrics is None:
        return None, None
    expert_D = calc_nvcov(expert_metrics)['D']
    return remap_diff(expert_D, instrument), calc_tier(expert_D, instrument)
