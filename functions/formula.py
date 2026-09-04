"""
FORMULA - Per-song difficulty scalar, computed by functions.density.compute_density_metrics

D = N * V * COV

    epsN = pNPS * 0.05
    N = ((medNPS + epsN) * aNPS * pNPS) ** (1 / 3)
    cvN = (stdNPS / aNPS + medNPS)

    epsV = pVPS * 0.05
    V = ((medVPS + epsV) * aVPS * pVPS) ** (1 / 3)
    cvV = (stdVPS / aVPS + medVPS)

    COV = 1 + (cvN * cvV) ** 0.5

N & V balance peak segment impact against average and median
COV is the interaction that accounts for spikes of difficulty - more variable songs >1, less variable -> 1
epsilon prevents median values of 0 from collapsing D while still being derived from song data

D/N/V/COV are computed identically regardless of instrument - purely a function of the note
stream's density/variability shape, nothing instrument-specific in the math itself.

RemapDiff (0-6 bins) and CalcTier (log-scaled) are instrument-specific
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

"""
GUITAR REMAP BINS (diff_guitar distribution)
Tier    Official	remap
0	    4.3%	    4.3%
1	    10.6%	    11.2%
2	    24.0%	    22.8%
3	    25.1%	    25.9%
4	    17.7%	    17.2%
5	    12.0%	    12.3%
6	    6.2%	    6.4%
"""
GUITAR_REMAP_BINS = [0, 8, 14, 21, 29, 38, 55, math.inf]   # calibrated vs diff_guitar tag distribution (incl coop/rhythm)

"""
BASS REMAP BINS (diff_bass distribution)
Tier    Official	remap
0	    6.7%	    4.9%
1	    22.8%	    22.7%
2	    27.6%	    28.9%
3	    23.9%	    23.9%
4	    10.9%	    11.8%
5	    5.8%	    5.3%
6	    2.4%	    2.5%
"""
BASS_REMAP_BINS   = [0, 3, 8, 13, 19, 26, 36, math.inf]    # calibrated vs diff_bass tag distribution

"""
KEYS REMAP BINS (diff_keys distribution)
Tier    Official	remap
0	    8.7%	    6.6%
1	    19.5%	    22.8%
2	    18.3%	    18.0%
3	    22.4%	    20.3%
4	    14.9%	    15.6%
5	    8.3%	    8.5%
6	    7.9%	    8.1%
"""
KEYS_REMAP_BINS   = [0, 1, 5, 10, 16, 25, 35, math.inf]    # calibrated vs diff_keys tag distribution

REMAP_BINS = {
    'guitar': GUITAR_REMAP_BINS,
    'bass':   BASS_REMAP_BINS,
    'keys':   KEYS_REMAP_BINS,
}

# --------------------------------------------
# CalcTier (log-scaled) params, per group
# --------------------------------------------
# ~One tier per LN_INC of log(D / BASE_D).
GUITAR_BASE_D, GUITAR_LN_INC = 7.6, 0.44   # calibrated; also covers coop/rhythm
BASS_BASE_D,   BASS_LN_INC   = 7.6, 0.44   # = not planning to rebin, seems ok
KEYS_BASE_D,   KEYS_LN_INC   = 7.6, 0.44   # = not planning to rebin, seems ok

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

# D Formula
def calc_diff(metrics, instrument='guitar'):
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

    # base scalar difficulty - instrument-agnostic
    D = N * V * COV

    return {
        'N': N,
        'V': V,
        'COV': COV,
        'D': D,
        'RemapDiff': remap_diff(D, instrument),
        'CalcTier': calc_tier(D, instrument),
    }
