"""
DRUM_DENSITY - Drum-specific windowing: raw HPS/TPS/KPS series + diagnostics.

Reuses fret_density's WINDOW_MS/STEP_MS grid and POPCOUNT lookup table 
(already built for guitar's fret_var, directly reusable for HPS's popcount-per-onset and TPS's hamming distance).

Each of HPS/TPS/KPS(1x)/KPS(2x) now reports peak/avg/median/std, mirroring
fret_density's pNPS/aNPS/medNPS/stdNPS set. 
"""

import numpy as np

from functions import fret_density

WINDOW_MS = fret_density.WINDOW_MS
STEP_MS = fret_density.STEP_MS
POPCOUNT = fret_density.POPCOUNT

# cap-density-zero-travel: inside a roll-lane span, exact lane identity isn't
# something the game requires (see chart_parser.py/mid_parser.py's
# _extract_roll_spans docstrings), so:
#   - travel contributes 0 for onsets inside a span - there's no meaningful
#     "pattern" being played, just maintaining a pace
#   - density is capped at ROLL_CAP_HPS per second instead of counting the
#     literal (often over-charted, purely visual) note rate charters use to
#     represent a roll
# ROLL_CAP_HPS IS AN ESTIMATE, NOT A SPEC VALUE - actual RB/CH roll-lane
# hit-rate thresholds aren't published (the docs only say "a certain
# threshold... [that] can be either a static time threshold, or... based off
# of the actual charted notes"). Treat this as a tunable placeholder pending
# real calibration against a library that actually has roll-heavy songs.
ROLL_CAP_HPS = 4.0


# Boolean per-onset mask - True where a hand onset's time falls inside ANY of
# the given (start_ms, end_ms, kind) roll spans. Caller is responsible for
# passing the spans for the SPECIFIC level being scored - see chart_parser.py/
# mid_parser.py, which now extract roll spans per level rather than sharing
# one list across every level.
def _roll_mask(times, spans):
    mask = np.zeros(times.shape, dtype=bool)
    for start, end, _kind in spans:
        mask |= (times >= start) & (times < end)
    return mask


# Generic prefix-sum windowed reducer - same grid/window logic fret_density.window_arrays
# already uses for VPS, but over an arbitrary (times, values) pair and an EXPLICIT
# sample count. The explicit n_samples is what lets drum_formula.calc_drum_diff
# resample HPS/TPS (hand-anchored) and KPS (kick-anchored) onto one shared, longer
# grid later without recomputing anything - the prefix-sum naturally yields 0 for
# windows past the last onset, so extending n_samples beyond a stream's own range
# is always safe. values must be aligned 1:1 with times (same array a mask/weight
# was derived from).
def windowed_sum(times, values, n_samples, window_ms=WINDOW_MS, step_ms=STEP_MS):
    grid = np.arange(n_samples, dtype=np.float64) * step_ms
    if times.size == 0 or n_samples == 0:
        return grid, np.zeros(n_samples, dtype=np.float64)

    prefix = np.concatenate(([0.0], np.cumsum(np.asarray(values, dtype=np.float64))))
    left = np.searchsorted(times, grid, side='left')
    right = np.searchsorted(times, grid + window_ms, side='left')
    return grid, prefix[right] - prefix[left]


# -----------------------------------------------------------------------
# Hand/kick interaction - two distinct signals, both contribute (per design
# discussion): a song can be demanding because both limbs are busy AT THE
# SAME TIME (Co), or because the kick is doing something genuinely separate
# from the hands rather than landing on top of them (Indep). Neither implies
# the other - straight double-bass under a busy hand pattern is high-Co,
# low-Indep; a sparse syncopated kick weaving between hand hits is the
# opposite.
#
# Both use the RAW (roll-uncapped) hand density - roll-lane suppression
# matters most for the pattern/travel axis (is this precisely-hard or just a
# visual flourish); for a coarse "is the other limb busy right now" signal,
# the literal charted rate is a reasonable simplification.
# -----------------------------------------------------------------------

# Co-busy-ness: per-window min(hand_rate, kick_rate) on a SHARED grid. Hand's
# HPS and a kick reading's KPS are normally anchored to their own stream's
# last-onset time (different n_samples) - resampled here onto one grid long
# enough to cover whichever stream runs longer, using windowed_sum's explicit
# n_samples parameter (safe past either stream's own range - see its docstring).
def _co_busy_raw(hand_times, hps_weights, kick_times, window_ms=WINDOW_MS, step_ms=STEP_MS):
    n_samples = max(_n_samples_for(hand_times, step_ms), _n_samples_for(kick_times, step_ms))
    _, hand_sum = windowed_sum(hand_times, hps_weights, n_samples, window_ms, step_ms)
    _, kick_sum = windowed_sum(kick_times, np.ones(kick_times.size), n_samples, window_ms, step_ms)
    window_s = window_ms / 1000.0
    return np.minimum(hand_sum / window_s, kick_sum / window_s)


# Independent kick onsets - a kick onset is "coincident" if it shares a hand
# onset's exact time_ms (both streams share the same tick->ms conversion, so
# same-tick events land on identical float ms). Returns a boolean mask aligned
# to kick_times, True where that onset is NOT doubled up with a hand hit.
def _independent_kick_mask(kick_times, hand_times):
    hand_set = set(hand_times.tolist())
    return np.array([t not in hand_set for t in kick_times.tolist()], dtype=bool)


# Number of grid samples needed to cover a stream out to its own last onset -
# same '// step_ms + 1' rule fret_density.window_arrays uses for guitar/bass/keys.
def _n_samples_for(times, step_ms=STEP_MS):
    if times.size == 0:
        return 0
    return int(times[-1] // step_ms) + 1


# Hand-stream per-onset weights:
#   hps_weights[i] = popcount(mask[i])                       -> feeds HPS
#   travel[i]      = popcount(mask[i] ^ mask[i-1])            -> feeds TPS
# travel[0] is popcount(mask[0]) (xor against an empty/0 mask) since the first
# onset of the song is a pure addition from an empty kit, mirroring fret_var's
# treatment of a song's first note.
def _hand_weights(masks):
    masks = np.asarray(masks, dtype=np.uint8)
    if masks.size == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.int64)

    hps_weights = POPCOUNT[masks]

    travel = np.empty(masks.size, dtype=np.int64)
    travel[0] = POPCOUNT[masks[0]]
    if masks.size > 1:
        travel[1:] = POPCOUNT[masks[:-1] ^ masks[1:]]

    return hps_weights, travel


# One kick reading (1x = bit0 only, 2x = bits0|1 merged), or None if that reading
# has no onsets at all (see §2.1: bit 0 = regular kick, bit 1 = Expert+/2x kick).
# hand_times/hps_weights are optional - when given (a real hand stream exists),
# also computes Co (co-busy-ness) and Indep (independent-kick-rate) stats;
# both are None when there's no hand stream to interact with (kick-only chart).
def _kick_reading(kick_mask, bit_mask, window_ms, step_ms, hand_times=None, hps_weights=None):
    times = np.asarray(kick_mask['time_ms'], dtype=np.float64)
    lanes = np.asarray(kick_mask['lanes'], dtype=np.uint8)

    hit = (lanes & bit_mask) != 0
    times = times[hit]
    if times.size == 0:
        return None

    n_samples = _n_samples_for(times, step_ms)
    _, kps_sum = windowed_sum(times, np.ones(times.size), n_samples, window_ms, step_ms)
    window_s = window_ms / 1000.0
    kps_raw = kps_sum / window_s

    dur_s = times[-1] / 1000.0
    out = {
        'time_ms': times,
        'n_samples': n_samples,
        'KPS_raw': kps_raw,
        'pKPS': float(kps_raw.max()) if kps_raw.size else 0.0,
        'aKPS': (float(times.size) / dur_s) if dur_s > 0 else 0.0,
        'stdKPS': float(np.std(kps_raw)) if kps_raw.size else 0.0,
        'medKPS': float(np.median(kps_raw)) if kps_raw.size else 0.0,
    }

    has_hands = hand_times is not None and hand_times.size > 0
    if has_hands:
        co_raw = _co_busy_raw(hand_times, hps_weights, times, window_ms, step_ms)
        out.update({
            'Co_raw': co_raw,
            'pCo': float(co_raw.max()) if co_raw.size else 0.0,
            'aCo': float(co_raw.mean()) if co_raw.size else 0.0,
            'stdCo': float(np.std(co_raw)) if co_raw.size else 0.0,
            'medCo': float(np.median(co_raw)) if co_raw.size else 0.0,
        })

        indep_mask = _independent_kick_mask(times, hand_times)
        indep_times = times[indep_mask]
        # IndepFrac: how MUCH of the kick part is independent (0-1 ratio) -
        # separate question from how demanding that independent portion is
        out['IndepFrac'] = float(indep_mask.sum()) / float(times.size)

        if indep_times.size > 0:
            indep_n_samples = _n_samples_for(indep_times, step_ms)
            _, ikps_sum = windowed_sum(indep_times, np.ones(indep_times.size), indep_n_samples, window_ms, step_ms)
            ikps_raw = ikps_sum / window_s
            indep_dur_s = indep_times[-1] / 1000.0
            out.update({
                'IKPS_raw': ikps_raw,
                'pIKPS': float(ikps_raw.max()) if ikps_raw.size else 0.0,
                'aIKPS': (float(indep_times.size) / indep_dur_s) if indep_dur_s > 0 else 0.0,
                'stdIKPS': float(np.std(ikps_raw)) if ikps_raw.size else 0.0,
                'medIKPS': float(np.median(ikps_raw)) if ikps_raw.size else 0.0,
            })
        else:
            out.update({'IKPS_raw': np.empty(0), 'pIKPS': 0.0, 'aIKPS': 0.0, 'stdIKPS': 0.0, 'medIKPS': 0.0})
    else:
        out.update({
            'Co_raw': None, 'pCo': None, 'aCo': None, 'stdCo': None, 'medCo': None,
            'IndepFrac': None,
            'IKPS_raw': None, 'pIKPS': None, 'aIKPS': None, 'stdIKPS': None, 'medIKPS': None,
        })

    return out


# calc_drum_metrics - raw HPS/TPS/KPS series + diagnostics only.
#   notes = {'hand_mask': {'time_ms', 'lanes'}, 'kick_mask': {'time_ms', 'lanes'}}
#   roll_spans = [(start_ms, end_ms, 'single'|'double'), ...] or None/[] - see
#     chart_parser.py/mid_parser.py's _extract_roll_spans. Applies to the hand
#     stream only (roll lanes can't cover kicks, per spec). Pass the spans for
#     THIS level specifically - .chart charts each level's roll markers in its
#     own section and .mid's Expert/Hard split is velocity-driven, so spans are
#     no longer identical across every level for a song.
#   returns {'hand': {...} | None, '1x': {...} | None, '2x': {...} | None}
#
# HPS/TPS are computed ONCE, anchored to the hand stream's own last-onset time
# (§2.4) - never resampled to a kick-mode-specific grid length here, so the
# pHPS/aHPS/pTPS/aTPS diagnostics can't silently diverge between the 1x/2x rows
# for the same song. KPS is computed per-reading since it's the only axis that
# differs by mode.
def calc_drum_metrics(notes, roll_spans=None, window_ms=WINDOW_MS, step_ms=STEP_MS):
    hand_times = np.asarray(notes['hand_mask']['time_ms'], dtype=np.float64)
    hand_masks = np.asarray(notes['hand_mask']['lanes'], dtype=np.uint8)
    kick_mask = notes['kick_mask']
    roll_spans = roll_spans or []

    hand_out = None
    if hand_times.size > 0:
        hps_weights, travel = _hand_weights(hand_masks)

        if roll_spans:
            in_roll = _roll_mask(hand_times, roll_spans)
            travel = np.where(in_roll, 0, travel)               # zero-travel
            hps_weights_normal = np.where(in_roll, 0, hps_weights)
            hps_weights_roll = np.where(in_roll, hps_weights, 0)  # cap-density, below
        else:
            hps_weights_normal = hps_weights
            hps_weights_roll = np.zeros_like(hps_weights)

        n_samples = _n_samples_for(hand_times, step_ms)
        _, hps_sum_normal = windowed_sum(hand_times, hps_weights_normal, n_samples, window_ms, step_ms)
        _, hps_sum_roll = windowed_sum(hand_times, hps_weights_roll, n_samples, window_ms, step_ms)
        _, tps_sum = windowed_sum(hand_times, travel, n_samples, window_ms, step_ms)

        window_s = window_ms / 1000.0
        cap_per_window = ROLL_CAP_HPS * window_s
        hps_sum = hps_sum_normal + np.minimum(hps_sum_roll, cap_per_window)
        hps_raw = hps_sum / window_s
        tps_raw = tps_sum / window_s

        dur_s = hand_times[-1] / 1000.0

        # aHPS mirrors the same cap, but computed off actual span durations
        # rather than the windowed grid (window overlap would otherwise let a
        # single roll get counted ~4x over via the 250ms-step/1000ms-window grid) -
        # each span can contribute at most ROLL_CAP_HPS * its own duration,
        # assuming spans don't overlap each other.
        roll_cap_total = ROLL_CAP_HPS * sum((end - start) / 1000.0 for start, end, _kind in roll_spans)
        capped_roll_total = min(float(hps_weights_roll.sum()), roll_cap_total)
        total_hps_capped = float(hps_weights_normal.sum()) + capped_roll_total

        # SHELVED (see drum_formula.py's module docstring): a "Chord" axis off
        # this same hps_weights array (per-onset popcount, excluding roll onsets
        # via hps_weights[~in_roll]) was built and tested to separate "lots of
        # 2-hand hits" from "just playing fast", since H alone can't tell a
        # 2-lane chord at rate R from a 1-lane hit at rate 2R. Pulled out for
        # now to simplify while the hand/kick restructure settles - revisit if
        # underrating simultaneous multi-limb hits turns out to still be a
        # problem after that.

        hand_out = {
            'time_ms': hand_times,
            'lanes': hand_masks,
            'n_samples': n_samples,
            # raw, UNCAPPED per-onset weights - kept for diagnostics/resampling.
            # travel here IS already roll-zeroed (unlike hps_weights, which isn't).
            'hps_weights': hps_weights,
            'travel': travel,
            'HPS_raw': hps_raw,
            'TPS_raw': tps_raw,
            'pHPS': float(hps_raw.max()) if hps_raw.size else 0.0,
            'aHPS': (total_hps_capped / dur_s) if dur_s > 0 else 0.0,
            'stdHPS': float(np.std(hps_raw)) if hps_raw.size else 0.0,
            'medHPS': float(np.median(hps_raw)) if hps_raw.size else 0.0,
            'pTPS': float(tps_raw.max()) if tps_raw.size else 0.0,
            'aTPS': (float(travel.sum()) / dur_s) if dur_s > 0 else 0.0,
            'stdTPS': float(np.std(tps_raw)) if tps_raw.size else 0.0,
            'medTPS': float(np.median(tps_raw)) if tps_raw.size else 0.0,
        }

    readings = {
        '1x': _kick_reading(kick_mask, 0b01, window_ms, step_ms, hand_times, hps_weights if hand_out else None),
        '2x': _kick_reading(kick_mask, 0b11, window_ms, step_ms, hand_times, hps_weights if hand_out else None),
    }

    # 2x is only distinct from 1x if a bit-1 (2x-exclusive) event exists somewhere -
    # otherwise there's nothing distinct to report for that reading (§4, D_2x rule)
    kick_lanes = np.asarray(kick_mask['lanes'], dtype=np.uint8)
    has_2x_exclusive = bool(kick_lanes.size) and bool(np.any(kick_lanes & 0b10))
    if not has_2x_exclusive:
        readings['2x'] = None

    return {'hand': hand_out, **readings}
