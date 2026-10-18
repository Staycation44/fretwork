"""
VOCAL FORMULA - Per-song difficulty scalar, computed from outputs of vocal_density

Sort of a hybrid due to the pure insanity of vocals charting...
pitch movement is the main driver of difficulty, but charting & tiering conventions are incredibly messy
officials don't agree on nearly anythin, even DLC vs main setlist
This has the loosest fit to official difficulty, but has a solid theoretical basis

CoV conceptually similar to fret/drums, STAM resued wholesale

D = (P * R + S) * CoV * STAM

    epsP = aPPS * 0.05
    P = ((medPPS + epsP) * aPPS * pPPS) ** (1 / 3)
    cvP = stdPPS / (medPPS + aPPS)

    R = Pitches ** 0.5 * (maxPitch / MID_PITCH)     # 0 with no sung notes

    epsS = aSPS * 0.05
    S = ((medSPS + epsS) * aSPS * pSPS) ** (1 / 3)
    cvS = stdSPS / (medSPS + aSPS)

    CoV = 1 + (cvP * cvS) ** 0.5

    STAM = (DurationS / t_ref) ** s_stam

   # base difficulty scalar
    D = (P * R + S) * CoV * STAM

P (Pitch): Main driver, pitch movement over time, same peak/average/median pseudo-geomean used elsewhere

R (Register): where the vocal line tracks, not how fast it moves through it
    Pitches: distinct pitches used, sqrt-compressed
    maxPitch: top of the line relative to MID_PITCH (60 = middle C, centre of the 36-84 chartable range)

S (Syllables): same pseudo-geomean as P, rescues talkie-only songs from D = 0

CoV: same structure as 5 fret/drums, 1 + sqrt(cvP * cvS), pitch and syllables

No Changes to STAM

Vocals have no EMHX, so RemapDiff/CalcTier come straight from D

RemapDiff & CalcTier calibrated for vocals - see Methodology.md for calibration data
"""

import math

# ---------------------------------
# Remap (0-6)
# ---------------------------------
DIFF_LABELS = [0, 1, 2, 3, 4, 5, 6]

# Bin edges calibrated so RemapDiff distribution matches diff_vocals' official distribution
VOCAL_REMAP_BINS = [0, 12.0, 16.4, 21.5, 27.3, 32.6, 38.0, math.inf]

# --------------------------------------------
# CalcTier
# --------------------------------------------
# ~One tier per LN_INC of log(D / BASE_D)
BASE_D = 14.0
LN_INC = 0.1898



# R / Register anchor - middle C, midpoint of chartable vocal range (midi 36-84)
MID_PITCH = 60


# RB manual 0-6 fit
def remap_diff(D):
    if D <= 0:
        return 0
    lower = VOCAL_REMAP_BINS[0]
    for label, upper in zip(DIFF_LABELS, VOCAL_REMAP_BINS[1:]):
        if lower < D <= upper:
            return label
        lower = upper
    return None

# log tier calculation
def calc_tier(D):
    if D < BASE_D:
        return 0
    return int(math.floor(math.log(D / BASE_D) / LN_INC) + 1)


# D Formula - P/R/S/CoV/D, plus RemapDiff/CalcTier
def calc_vocal_d(metrics):
    pPPS, medPPS, aPPS, stdPPS = metrics['pPPS'], metrics['medPPS'], metrics['aPPS'], metrics['stdPPS']
    pSPS, medSPS, aSPS, stdSPS = metrics['pSPS'], metrics['medSPS'], metrics['aSPS'], metrics['stdSPS']
    Pitches, maxPitch = metrics['Pitches'], metrics['maxPitch']
    DurationS = metrics.get('DurationS', 0.0)

    # PPS combo
    epsP = aPPS * 0.05
    P = ((medPPS + epsP) * aPPS * pPPS) ** (1 / 3)
    cvP = stdPPS / (medPPS + aPPS) if (medPPS + aPPS) > 0 else 0.0

    # register, vocab x top of the line, 0 on talkie-only songs (Base goes to zero on those anyway)
    R = Pitches ** 0.5 * (maxPitch / MID_PITCH) if maxPitch > 0 else 0.0

    # SPS combo
    epsS = aSPS * 0.05
    S = ((medSPS + epsS) * aSPS * pSPS) ** (1 / 3)
    cvS = stdSPS / (medSPS + aSPS) if (medSPS + aSPS) > 0 else 0.0

    # pitch work x register, syllable added
    BASE = P * R + S

    # CoV interaction, across pitch movement & syllable rate
    COV = 1 + (cvP * cvS) ** 0.5

    # STAMINA!!! sublinear by duration / slowly building boost for long songs, discounts short songs
    # ~66% @ 30s, ~75% @ 60s / 1x @ t_ref / 1.1x @ ~6 mins, 1.2x @ 9.5 mins
    T_REF = 230.0  # 3-4 min average song
    S_STAM = 0.20  # curve exponent
    STAM = (DurationS / T_REF) ** S_STAM if DurationS > 0 else 0.0

    # base scalar difficulty
    D = BASE * COV * STAM

    return {
        'P': P,
        'R': R,
        'S': S,
        'Base': BASE,
        'CoV': COV,
        'STAM': STAM,
        'D': D,
        'RemapDiff': remap_diff(D),
        'CalcTier': calc_tier(D),
    }
