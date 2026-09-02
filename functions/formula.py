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

RemapDiff (0-6 bins) and CalcTier (log-scaled) ARE instrument-specific - TODO calibration for each
"""

import math

# ---------------------------------
# Remap (0-6) params, per instrument
# ---------------------------------
# based on general distribution from official GUITAR library across tiers by percentage:
"""
Tier    Official	remap
0	    4.3%	    4.3%
1	    10.6%	    11.2%
2	    24.0%	    22.8%
3	    25.1%	    25.9%
4	    17.7%	    17.2%
5	    12.0%	    12.3%
6	    6.2%	    6.4%
"""
DIFF_LABELS = [0, 1, 2, 3, 4, 5, 6]   # shared label set, same for every instrument

GUITAR_REMAP_BINS = [0, 8, 14, 21, 29, 38, 55, math.inf]   # calibrated, see table above
BASS_REMAP_BINS   = [0, 8, 14, 21, 29, 38, 55, math.inf]   # = guitar's - needs its own rebin
COOP_REMAP_BINS   = [0, 8, 14, 21, 29, 38, 55, math.inf]   # = guitar's - may just inherit permanently
RHYTHM_REMAP_BINS = [0, 8, 14, 21, 29, 38, 55, math.inf]   # = guitar's - may just inherit permanently
KEYS_REMAP_BINS   = [0, 8, 14, 21, 29, 38, 55, math.inf]   # = guitar's - needs its own rebin

REMAP_BINS = {
    'guitar': GUITAR_REMAP_BINS,
    'bass':   BASS_REMAP_BINS,
    'coop':   COOP_REMAP_BINS,
    'rhythm': RHYTHM_REMAP_BINS,
    'keys':   KEYS_REMAP_BINS,
}

# --------------------------------------------
# CalcTier (log-scaled) params, per instrument
# --------------------------------------------
# ~One tier per LN_INC of log(D / BASE_D).
GUITAR_BASE_D, GUITAR_LN_INC = 7.6, 0.44   # calibrated
BASS_BASE_D,   BASS_LN_INC   = 7.6, 0.44   # = guitar's - needs its own rebin
COOP_BASE_D,   COOP_LN_INC   = 7.6, 0.44   # = guitar's - may just inherit permanently
RHYTHM_BASE_D, RHYTHM_LN_INC = 7.6, 0.44   # = guitar's - may just inherit permanently
KEYS_BASE_D,   KEYS_LN_INC   = 7.6, 0.44   # = guitar's - needs its own rebin

CALCTIER_PARAMS = {
    'guitar': (GUITAR_BASE_D, GUITAR_LN_INC),
    'bass':   (BASS_BASE_D, BASS_LN_INC),
    'coop':   (COOP_BASE_D, COOP_LN_INC),
    'rhythm': (RHYTHM_BASE_D, RHYTHM_LN_INC),
    'keys':   (KEYS_BASE_D, KEYS_LN_INC),
}


# RB manual 0-6 fit
def remap_diff(D, instrument='guitar'):
    bin_edges = REMAP_BINS[instrument]
    lower = bin_edges[0]
    for label, upper in zip(DIFF_LABELS, bin_edges[1:]):
        if lower < D <= upper:
            return label
        lower = upper
    return None

# log tier calculation
def calc_tier(D, instrument='guitar'):
    base_d, ln_inc = CALCTIER_PARAMS[instrument]
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
