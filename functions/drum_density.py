"""
DRUM DENSITY - Density metrics, computed from the cached notestream

HPS = Hands Per Second
    Every lane struck counts - a 2-lane hit counts 2 (popcount), the same as two separate hits
    Drums differ from 5 fret here: guitar counts any simultaneous frets as 1 note, drums counts limbs

TPS = Travel Per Second
    Travel is the distance-weighted cost of the lanes turning ON since the previous hit
    Additions only - a drum hit is discrete, there's no held lane to release

KPS = Kicks Per Second
    Read twice per song - 1x (single pedal, bit 0) and 2x (double pedal, bits 0|1)

same format comes from both mid/chart files - density and curves can both use this data

lanes[i] is a bitmask, bit N = lane N (bits 0-4 pads/cymbals) - same encoding fret_density uses

Hands and kick are separate streams: HPS/TPS are hand-anchored and computed once per song,
KPS is computed per reading since it's the only axis that differs between 1x and 2x.
Every avg rate divides by one shared song duration (the later of the two streams' last hit),
so hand and kick stay comparable to each other.

Grid origin is t=0 and runs until the last note
WINDOW_MS/STEP_MS, POPCOUNT and the active-window gating are all shared with fret_density
"""

import numpy as np

from functions import fret_density

WINDOW_MS = fret_density.WINDOW_MS
STEP_MS = fret_density.STEP_MS
POPCOUNT = fret_density.POPCOUNT

N_LANES = 5

# roll span doesn't define exact lane identity so travel counts 0
# density is capped at defined rate rather than the charted note rate
# ESTIMATE, could be calibrated but fit is ok
ROLL_CAP_HPS = 4.0

# Travel distance compression to fix raw distance issues & 4 vs 5 lane scoring
# 0.5 (sqrt) is fair fit, but still kinda arbitrary
TRAVEL_GAMMA = 0.5


# Distance lookup, [added_mask, prev_mask] -> travel cost
# No prior lane (song's first note, or empty window before) is a pure addition
def _build_travel_lookup(gamma=TRAVEL_GAMMA):
    lut = np.zeros((256, 256), dtype=np.float64)
    for added_byte in range(256):
        added_bits = [b for b in range(N_LANES) if added_byte & (1 << b)]
        if not added_bits:
            continue
        for prev_byte in range(256):
            prev_bits = [b for b in range(N_LANES) if prev_byte & (1 << b)]
            if not prev_bits:
                lut[added_byte, prev_byte] = float(len(added_bits))
                continue
            dists = [min(abs(j - k) for k in prev_bits) for j in added_bits]
            lut[added_byte, prev_byte] = float(np.mean([d ** gamma if d > 0 else 0.0 for d in dists]))
    return lut


TRAVEL_LOOKUP = _build_travel_lookup()


# HPS/TPS source - per-hit weights off the hand stream's lane masks
#   hits[i] = popcount(mask[i]) -> HPS
#   travel[i] = distance-weighted lanes added -> TPS
# first hit counts all its lanes as added
def hand_var(hand_masks):
    masks = np.asarray(hand_masks, dtype=np.uint8)
    if masks.size == 0:
        return np.empty(0, dtype=np.int64), np.empty(0, dtype=np.float64)

    hits = POPCOUNT[masks]

    travel = np.empty(masks.size, dtype=np.float64)
    travel[0] = float(POPCOUNT[masks[0]])
    if masks.size > 1:
        prev, curr = masks[:-1], masks[1:]
        travel[1:] = TRAVEL_LOOKUP[curr & ~prev, prev]

    return hits, travel


# True where a note falls inside any roll span
# Spans defined per level
def roll_mask(times, spans):
    mask = np.zeros(times.shape, dtype=bool)
    for start, end, _kind in spans:
        mask |= (times >= start) & (times < end)
    return mask


# Grid samples needed to cover a stream to its last note
def n_samples_for(times, step_ms=STEP_MS):
    if times.size == 0:
        return 0
    return int(times[-1] // step_ms) + 1


# Prefix-sum windowed reducer over an arbitrary (times, values) pair
# Similar grid/window logic used VPS but specific sample ct for shared hand/kick grid
def windowed_sum(times, values, n_samples, window_ms=WINDOW_MS, step_ms=STEP_MS):
    grid = np.arange(n_samples, dtype=np.float64) * step_ms
    if times.size == 0 or n_samples == 0:
        return grid, np.zeros(n_samples, dtype=np.float64)

    prefix = np.concatenate(([0.0], np.cumsum(np.asarray(values, dtype=np.float64))))
    left = np.searchsorted(times, grid, side='left')
    right = np.searchsorted(times, grid + window_ms, side='left')
    return grid, prefix[right] - prefix[left]


# Song duration shared by every avg (aHPS/aTPS/aKPS) + STAM
# the later of the two streams last hit
def song_duration_s(hand_times, kick_mask):
    kick_times = np.asarray(kick_mask['time_ms'], dtype=np.float64)
    last_ms = 0.0
    if hand_times.size > 0:
        last_ms = max(last_ms, float(hand_times[-1]))
    if kick_times.size > 0:
        last_ms = max(last_ms, float(kick_times[-1]))
    return last_ms / 1000.0


# Windowing pass across HPS/TPS, anchored to the hand stream
# zero activity windows are included
# roll spans zero travel and cap hits, per ROLL_CAP_HPS
#     Returns:
#        {
#            'time_ms':          ndarray,  # uniform grid, starts at 0
#            'raw_hps_samples':  ndarray,  # roll-capped hits per window
#            'raw_tps_samples':  ndarray,  # travel per window
#            'travel':           ndarray,  # per-hit travel (not windowed)
#            'timestamps_ms':    ndarray,  # hand hit times
#            'total_hits':       float,    # roll-capped hit total, for aHPS
#        }
def window_arrays(hand_mask, roll_spans=None, window_ms=WINDOW_MS, step_ms=STEP_MS):
    times = np.asarray(hand_mask['time_ms'], dtype=np.float64)
    masks = np.asarray(hand_mask['lanes'], dtype=np.uint8)
    roll_spans = roll_spans or []

    if times.size == 0:
        return None

    hits, travel = hand_var(masks)

    # split hits into normal/roll so only the roll share gets capped, travel zeroes outright
    if roll_spans:
        in_roll = roll_mask(times, roll_spans)
        travel = np.where(in_roll, 0, travel)
        hits_normal = np.where(in_roll, 0, hits)
        hits_roll = np.where(in_roll, hits, 0)
    else:
        hits_normal = hits
        hits_roll = np.zeros_like(hits)

    n_samples = n_samples_for(times, step_ms)
    _, hps_normal = windowed_sum(times, hits_normal, n_samples, window_ms, step_ms)
    _, hps_roll = windowed_sum(times, hits_roll, n_samples, window_ms, step_ms)
    grid, tps_sum = windowed_sum(times, travel, n_samples, window_ms, step_ms)

    window_s = window_ms / 1000.0
    hps_sum = hps_normal + np.minimum(hps_roll, ROLL_CAP_HPS * window_s)

    # aHPS's cap is taken off actual span durations instead of the windowed grid
    roll_cap_total = ROLL_CAP_HPS * sum((end - start) / 1000.0 for start, end, _kind in roll_spans)
    total_hits = float(hits_normal.sum()) + min(float(hits_roll.sum()), roll_cap_total)

    return {
        'time_ms': grid,
        'raw_hps_samples': hps_sum,
        'raw_tps_samples': tps_sum,
        'travel': travel,
        'timestamps_ms': times,
        'total_hits': total_hits,
    }


# One kick reading - bit_mask 0b01 is the 1x (single pedal) stream, 0b11 for 2x
# None when that reading has no hits at all
def kick_arrays(kick_mask, bit_mask, window_ms=WINDOW_MS, step_ms=STEP_MS):
    times = np.asarray(kick_mask['time_ms'], dtype=np.float64)
    lanes = np.asarray(kick_mask['lanes'], dtype=np.uint8)

    times = times[(lanes & bit_mask) != 0]
    if times.size == 0:
        return None

    n_samples = n_samples_for(times, step_ms)
    grid, kps_sum = windowed_sum(times, np.ones(times.size), n_samples, window_ms, step_ms)
    return {'time_ms': grid, 'raw_kps_samples': kps_sum, 'timestamps_ms': times}


# Note count for one reading: hand hits + kick hits (either 1x or 2x)
def _note_count(hand_times, kick_times):
    return int(hand_times.size + kick_times.size)


# provides HPS/TPS/KPS metrics to calculate D
def calc_drum_metrics(notes, roll_spans=None, window_ms=WINDOW_MS, step_ms=STEP_MS):
    hand_times = np.asarray(notes['hand_mask']['time_ms'], dtype=np.float64)
    kick_mask = notes['kick_mask']

    dur_s = song_duration_s(hand_times, kick_mask)
    window_s = window_ms / 1000.0

    # HPS & TPS
    hand_out = None
    windows = window_arrays(notes['hand_mask'], roll_spans, window_ms, step_ms)
    if windows is not None:
        hps_window_values = windows['raw_hps_samples'] / window_s
        hps_active_mask = hps_window_values > 0   # active window mask used for both HPS & TPS

        tps_window_values = windows['raw_tps_samples'] / window_s

        hand_out = {
            'time_ms': windows['timestamps_ms'],
            'lanes': np.asarray(notes['hand_mask']['lanes'], dtype=np.uint8),
            'aHPS': (windows['total_hits'] / dur_s) if dur_s > 0 else 0.0,
            'pHPS': float(hps_window_values.max()) if hps_window_values.size else 0.0,
            'stdHPS': fret_density.active_std(hps_window_values, hps_active_mask),   # gated by hit activity
            'medHPS': fret_density.active_median(hps_window_values, hps_active_mask),  # gated by hit activity
            'aTPS': (float(windows['travel'].sum()) / dur_s) if dur_s > 0 else 0.0,
            'pTPS': float(tps_window_values.max()) if tps_window_values.size else 0.0,
            'stdTPS': fret_density.active_std(tps_window_values, hps_active_mask),   # gated by hit activity
            'medTPS': fret_density.active_median(tps_window_values, hps_active_mask),  # gated by hit activity
        }

    # KPS per 1x/2x
    readings = {}
    for mode, bit_mask in (('1x', 0b01), ('2x', 0b11)):
        kicks = kick_arrays(kick_mask, bit_mask, window_ms, step_ms)
        if kicks is None:
            readings[mode] = None
            continue

        kps_window_values = kicks['raw_kps_samples'] / window_s
        kps_active_mask = kps_window_values > 0

        readings[mode] = {
            'time_ms': kicks['timestamps_ms'],
            'aKPS': (float(kicks['timestamps_ms'].size) / dur_s) if dur_s > 0 else 0.0,
            'pKPS': float(kps_window_values.max()) if kps_window_values.size else 0.0,
            'stdKPS': fret_density.active_std(kps_window_values, kps_active_mask),   # gated by kick activity
            'medKPS': fret_density.active_median(kps_window_values, kps_active_mask),  # gated by kick activity
        }

    # 2x only exists if there are notes for it
    kick_lanes = np.asarray(kick_mask['lanes'], dtype=np.uint8)
    if not (kick_lanes.size and np.any(kick_lanes & 0b10)):
        readings['2x'] = None

    return {
        'hand': hand_out,
        'DurationS': dur_s,
        'NoteCount_1x': _note_count(hand_times, readings['1x']['time_ms']) if readings['1x'] else None,
        'NoteCount_2x': _note_count(hand_times, readings['2x']['time_ms']) if readings['2x'] else None,
        **readings,
    }
