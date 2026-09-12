"""
DRUM FORMULA - Per-song difficulty scalar, computed from outputs of drum_density

similar shape to 5fret but with three axes & summed rather than multiplied
different limb groups add so one quiet group can't drag the whole song toward zero

D = (H + T + K) * COV * STAM

    epsH = aHPS * 0.05
    H = ((medHPS + epsH) * aHPS * pHPS) ** (1 / 3)
    cvH = stdHPS / (medHPS + aHPS)

    epsT = aTPS * 0.05
    T = ((medTPS + epsT) * aTPS * pTPS) ** (1 / 3)

    epsK = aKPS * 0.05
    K = ((medKPS + epsK) * aKPS * pKPS) ** (1 / 3)
    cvK = stdKPS / (medKPS + aKPS)

    COV = 1 + c_scale * (cvH * cvK) ** 0.5

    STAM = (DurationS / t_ref) ** s_stam

    # base scalar difficulty
    D = (H + T + K) * COV * STAM

H/T/K (Hands / Travel / Kick) each balance peak window values against average and median
H is how much is being hit across pads, T is how far the hands travel between hits, K is the foot action

COV is the interaction that accounts for uneven difficulty taken across limb groups
A song has to be uneven in both hands and feet to earn the full bonus

epsilon prevents median values of 0 from collapsing D while still being derived from song data

D is computed per kick reading - kick_mode picks 1x (single pedal) or 2x (double pedal)

RemapDiff (0-6 bins) and CalcTier (log-scaled) are drums-specific - see Methodology.md for calibration data

EMHX / RemapDiff & CalcTier anchor to expert, since only 1 diff value per instrument in song.ini
Drums anchors to the 1x reading specifically - 2x is optional, 1x is the reading every chart has

Travel is a little overtuned, but works adeuqately
"""

import math

# ---------------------------------
# Remap (0-6) params
# ---------------------------------
DIFF_LABELS = [0, 1, 2, 3, 4, 5, 6]   # shared label set

# Bin edges calibrated so RemapDiff distribution roughly matches diff_drums' official distribution in the reference library
# Methodology.md has table data for these bins
DRUM_REMAP_BINS = [0, 10.3, 12.3, 14.0, 16.2, 19.2, 22.8, math.inf]

# --------------------------------------------
# CalcTier (log-scaled) params
# --------------------------------------------
# ~One tier per LN_INC of log(D / BASE_D)
BASE_D = 10.3
LN_INC = 0.16


# RB manual 0-6 fit
def remap_diff(D):
    if D <= 0:
        return 0  # broken/zero-density songs -> 0
    lower = DRUM_REMAP_BINS[0]
    for label, upper in zip(DIFF_LABELS, DRUM_REMAP_BINS[1:]):
        if lower < D <= upper:
            return label
        lower = upper
    return None

# log tier calculation
def calc_tier(D):
    if D < BASE_D:
        return 0
    return int(math.floor(math.log(D / BASE_D) / LN_INC) + 1)

# D Formula - H/T/K/COV/D
def calc_drum_d(metrics, kick_mode='1x'):
    hand = metrics.get('hand')
    kick = metrics.get(kick_mode)
    DurationS = metrics.get('DurationS', 0.0)

    if hand is not None:
        pHPS, medHPS, aHPS, stdHPS = hand['pHPS'], hand['medHPS'], hand['aHPS'], hand['stdHPS']
        pTPS, medTPS, aTPS, stdTPS = hand['pTPS'], hand['medTPS'], hand['aTPS'], hand['stdTPS']

        # HPS combo
        epsH = aHPS * 0.05
        H = ((medHPS + epsH) * aHPS * pHPS) ** (1 / 3)
        cvH = stdHPS / (medHPS + aHPS) if (medHPS + aHPS) > 0 else 0.0

        # TPS combo
        epsT = aTPS * 0.05
        T = ((medTPS + epsT) * aTPS * pTPS) ** (1 / 3)

    if kick is not None:
        pKPS, medKPS, aKPS, stdKPS = kick['pKPS'], kick['medKPS'], kick['aKPS'], kick['stdKPS']

        # KPS combo
        epsK = aKPS * 0.05
        K = ((medKPS + epsK) * aKPS * pKPS) ** (1 / 3)
        cvK = stdKPS / (medKPS + aKPS) if (medKPS + aKPS) > 0 else 0.0

    # limb groups added
    BASE = H + T + K

    # CoV interaction across hands & kick
    c_scale = 2 # tuneable scale value
    COV = 1 + c_scale * (cvH * cvK) ** 0.5

    # STAMINA!!! sublinear by duration / slowly building boost for long songs, discounts short songs
    # ~66% @ 30s, ~75% @ 60s, 83% @ 90s, etc / 1x @ t_ref / 1.1x @ ~6 mins, 1.2x @ 9.5 mins, etc
    t_ref  = 230.0 # 3-4 min average song
    s_stam = 0.20 # curve exponent
    STAM = (DurationS / t_ref) ** s_stam if DurationS > 0 else 0.0

    # base scalar difficulty
    D = BASE * COV * STAM

    return {
        'H': H,
        'T': T,
        'K': K,
        'Base': BASE,
        'CoV': COV,
        'STAM': STAM,
        'D': D,
    }

# RemapDiff/CalcTier anchored to the Expert level's D, off the 1x reading
def anchor_remap_tier(expert_metrics):
    if expert_metrics is None or expert_metrics.get('hand') is None or expert_metrics.get('1x') is None:
        return None, None
    expert_D = calc_drum_d(expert_metrics, '1x')['D']
    return remap_diff(expert_D), calc_tier(expert_D)
