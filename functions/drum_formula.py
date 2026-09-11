"""
DRUM FORMULA - Per-song drum difficulty scalar
using only what's measurable via drum_density.calc_drum_metrics (HPS/TPS/KPS/Co/IKPS/peak/avg/median/std)

need to check gated median/stdev from 5 fret v2

STRUCTURE
---------
Hand_level = H * Movement (density * rate-independent complexity)
Kick_level = K (kick's own pseudo-geomean)
Base       = Hand_level + Kick_level   
(different limb-groups add, not multiply - avoids one term dragging the other to zero whenever either limbset is quiet)

CoV_overall = 1 + cv (combined hand+kick workload series)
    consistency term for the whole song, not per limb
    Built from the combined per-window series (hand's HPS_raw + a kick reading's KPS_raw, resampled onto a shared grid
    A spike in either limb shows up as a spike in the combined series

Interaction = sqrt(Co_axis * Indep_axis)
    both Co_axis and Indep_axis arefloored at 1 - a kick fully in line with the hands still contributes some credit rather than zeroing
    significantly flawed - non-monotonic and certain easy patterns score higher than significant syncopation
    basically just measures hand sparseness...

D = Base * CoV_overall * Interaction

HAND/KICK BALANCE: 
    Hand_level is H*Movement
    Kick_level is just K. 
    This asymmetry underrates kick's contribution
    A KickTiming term (inter-onset-interval CV, mirroring Pattern's approach) +
    A variants moving Indep_axis into Kick_level directly were tried and removed 
    Kick underrating is still an open question, other problems to resolve first

REST-HEAVY SONGS: check with 5 fret enhancements, worked well there

other things to try:
- a "Chord" axis - popcount-per-onset distribution, tempo-independent like Pattern
re-add if underrating simultaneous multi-limb hits turns out to still be a problem (johnny cash TFTB good example)

OPEN INVESTIGATION: repetitive-but-easier songs (barracuda, club foot, down with disease) score very high. 
T runs 2-4 std above the library mean on all three while Pattern is only mildly elevated
nothing currently measures whether a pattern is the same short cycle repeating vs. continuously evolving
The same blind spot shows up in Indep_axis 

Underlying problem with this whole family of metrics is that real drumming is built from repeated short phrases at every difficulty level...

trying to avoid pattern matching, but may need a new approach.
"""

import numpy as np


def _axis(peak, avg, med, std):
    eps = 0.05 * peak
    value = ((med + eps) * avg * peak) ** (1 / 3) if peak > 0 else 0.0
    cv = std / (avg + med) if (avg + med) > 0 else 0.0
    return value, cv


# Pads hand's HPS_raw and a kick reading's KPS_raw to a common length and sums
# them into one combined per-window workload series. Right-padding with 0 is
# always safe - windowed_sum already guarantees 0 past a stream's own last
# onset (see drum_density.windowed_sum's docstring).
def _combined_series(hand, kick):
    parts = []
    if hand is not None:
        parts.append(np.asarray(hand['HPS_raw']))
    if kick is not None:
        parts.append(np.asarray(kick['KPS_raw']))
    if not parts:
        return np.empty(0)
    n = max(p.size for p in parts)
    return sum(np.pad(p, (0, n - p.size)) for p in parts)


# metrics = drum_density.calc_drum_metrics() output: {'hand': {...}|None, '1x': {...}|None, '2x': {...}|None}
# kick_mode picks which kick reading ('1x' or '2x') to combine with the hand axis.
def calc_drum_d(metrics, kick_mode='1x'):
    hand = metrics.get('hand')
    kick = metrics.get(kick_mode)

    H = T = Pattern = Movement = Hand_level = 0.0
    if hand is not None:
        H, _cvH = _axis(hand['pHPS'], hand['aHPS'], hand['medHPS'], hand['stdHPS'])
        T, _cvT = _axis(hand['pTPS'], hand['aTPS'], hand['medTPS'], hand['stdTPS'])

        eps_guard = 1e-9
        rPeak = hand['pTPS'] / (hand['pHPS'] + eps_guard)
        rAvg = hand['aTPS'] / (hand['aHPS'] + eps_guard)
        rMed = hand['medTPS'] / (hand['medHPS'] + eps_guard)
        epsR = 0.05 * rPeak
        Pattern = max((rMed + epsR) * rAvg * rPeak, 0.0) ** (1 / 3)

        Movement = (T * Pattern) ** 0.5
        Hand_level = H * Movement

    K = Kick_level = 0.0
    Co_axis = Indep_axis = 0.0
    Interaction = 1.0
    if kick is not None:
        K, _cvK = _axis(kick['pKPS'], kick['aKPS'], kick['medKPS'], kick['stdKPS'])
        Kick_level = K

        if kick.get('pCo') is not None:
            Co_axis, _cvCo = _axis(kick['pCo'], kick['aCo'], kick['medCo'], kick['stdCo'])
            Co_axis = max(Co_axis, 1.0)
        if kick.get('pIKPS') is not None:
            Indep_axis, _cvIndep = _axis(kick['pIKPS'], kick['aIKPS'], kick['medIKPS'], kick['stdIKPS'])
            Indep_axis = max(Indep_axis, 1.0)
        if Co_axis and Indep_axis:
            Interaction = (Co_axis * Indep_axis) ** 0.5

    Base = Hand_level + Kick_level

    series = _combined_series(hand, kick)
    if series.size:
        peak, avg, med, std = float(series.max()), float(series.mean()), float(np.median(series)), float(series.std())
        cv_overall = std / (avg + med) if (avg + med) > 0 else 0.0
    else:
        cv_overall = 0.0
    CoV_overall = 1 + cv_overall

    D = Base * CoV_overall * Interaction

    return {
        'H': H, 'T': T, 'Pattern': Pattern, 'Movement': Movement,
        'Hand_level': Hand_level,
        'K': K, 'Kick_level': Kick_level,
        'Co_axis': Co_axis, 'Indep_axis': Indep_axis, 'Interaction': Interaction,
        'Base': Base, 'CoV_overall': CoV_overall,
        'D': D,
    }
