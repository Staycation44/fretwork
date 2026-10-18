"""
DRUM DENSITY - Density metrics, computed from the cached notestream

HPS = Hands Per Second
    Every lane struck counts - a 2-lane hit counts 2 (popcount), the same as two separate hits
    Drums differ from 5 fret here: guitar counts any simultaneous frets as 1 note, drums counts limbs

TPS = Travel Per Second
    Travel is the count of lanes activated since the previous hit, additions only
    Every newly struck lane counts 1 regardless of distance, so 4 and 5 lane kits score the same way

KPS = Kicks Per Second
    Read twice per song - 1x (single pedal, bit 0) and 2x (double pedal, bits 0|1)

same format comes from both mid/chart files - density and curves can both use this data

lanes[i] is a bitmask, bit N = lane N (bits 0-4 pads/cymbals) - same encoding fret_density uses

Hands and kick are separate streams: HPS/TPS are hand-anchored and computed once per song,
KPS is computed per reading since it's the only axis that differs between 1x and 2x.
Every avg rate divides by one shared song duration (the later of the two streams' last hit),
so hand and kick stay comparable to each other.

Window/grid/summary mechanics are shared with 5 fret & vocals in windowing.py
"""

import numpy as np

from functions import windowing

WINDOW_MS = windowing.WINDOW_MS
STEP_MS = windowing.STEP_MS
POPCOUNT = windowing.POPCOUNT

# roll span doesn't define exact lane identity so travel counts 0
# density is capped at defined rate rather than the charted note rate
# ESTIMATE, could be calibrated but fit is ok
ROLL_CAP_HPS = 4.0


# HPS/TPS source - per-hit weights off the hand stream's lane masks
#   hits[i] = popcount(mask[i]) -> HPS
#   travel[i] = popcount(lanes added vs previous hit) -> TPS
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
        travel[1:] = POPCOUNT[curr & ~prev]

    return hits, travel


# True where a note falls inside any roll span
# Spans defined per level
def roll_mask(times, spans):
    mask = np.zeros(times.shape, dtype=bool)
    for start, end, _kind in spans:
        mask |= (times >= start) & (times < end)
    return mask


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
    times, masks = windowing.sort_stream(hand_mask['time_ms'], np.asarray(hand_mask['lanes'], dtype=np.uint8))
    roll_spans = roll_spans or []

    if times.size == 0:
        return None

    hits, travel = hand_var(masks)

    # split hits into normal/roll so only the roll share gets capped, travel zeroes
    if roll_spans:
        in_roll = roll_mask(times, roll_spans)
        travel = np.where(in_roll, 0, travel)
        hits_normal = np.where(in_roll, 0, hits)
        hits_roll = np.where(in_roll, hits, 0)
    else:
        hits_normal = hits
        hits_roll = np.zeros_like(hits)

    grid = windowing.grid_to(times[-1], step_ms)
    hps_normal = windowing.windowed_sum(times, hits_normal, grid, window_ms)
    hps_roll = windowing.windowed_sum(times, hits_roll, grid, window_ms)
    tps_sum = windowing.windowed_sum(times, travel, grid, window_ms)

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
    times, lanes = windowing.sort_stream(kick_mask['time_ms'], np.asarray(kick_mask['lanes'], dtype=np.uint8))

    times = times[(lanes & bit_mask) != 0]
    if times.size == 0:
        return None

    grid = windowing.grid_to(times[-1], step_ms)
    kps_sum = windowing.windowed_sum(times, np.ones(times.size), grid, window_ms)
    return {'time_ms': grid, 'raw_kps_samples': kps_sum, 'timestamps_ms': times}


# Note count: every hand hit (same as HPS) + kick hit (either 1x or 2x)
def _note_count(hand_lanes, kick_times):
    hand_lanes = np.asarray(hand_lanes, dtype=np.uint8)
    hand_notes = int(POPCOUNT[hand_lanes].sum()) if hand_lanes.size else 0
    return hand_notes + int(kick_times.size)


# provides HPS/TPS/KPS metrics to calculate D
# windows: window_arrays() output for this hand stream, if the caller already has it (render)
# A chart with no kick notes returns '1x' = None, its NoteCount_1x is the hand count alone
def calc_drum_metrics(notes, roll_spans=None, window_ms=WINDOW_MS, step_ms=STEP_MS, windows=None):
    hand_times = np.asarray(notes['hand_mask']['time_ms'], dtype=np.float64)
    hand_lanes = np.asarray(notes['hand_mask']['lanes'], dtype=np.uint8)
    kick_mask = notes['kick_mask']

    dur_s = song_duration_s(hand_times, kick_mask)
    window_s = window_ms / 1000.0

    # HPS & TPS
    hand_out = None
    if windows is None:
        windows = window_arrays(notes['hand_mask'], roll_spans, window_ms, step_ms)
    if windows is not None:
        hps_window_values = windows['raw_hps_samples'] / window_s
        tps_window_values = windows['raw_tps_samples'] / window_s
        hps_active_mask = hps_window_values > 0   # active window mask used for both HPS & TPS (gated by hit activity)

        hand_out = {
            **windowing.rate_stats('HPS', hps_window_values, windows['total_hits'], dur_s, hps_active_mask),
            **windowing.rate_stats('TPS', tps_window_values, float(windows['travel'].sum()), dur_s, hps_active_mask),
        }

    # KPS per 1x/2x, gated by kick activity
    readings = {}
    for mode, bit_mask in (('1x', 0b01), ('2x', 0b11)):
        kicks = kick_arrays(kick_mask, bit_mask, window_ms, step_ms)
        if kicks is None:
            readings[mode] = None
            continue

        kps_window_values = kicks['raw_kps_samples'] / window_s
        readings[mode] = {
            'time_ms': kicks['timestamps_ms'],
            **windowing.rate_stats('KPS', kps_window_values, float(kicks['timestamps_ms'].size), dur_s,
                                   kps_window_values > 0),
        }

    # 2x only exists if there are notes for it
    kick_lanes = np.asarray(kick_mask['lanes'], dtype=np.uint8)
    if not (kick_lanes.size and np.any(kick_lanes & 0b10)):
        readings['2x'] = None

    return {
        'hand': hand_out,
        'DurationS': dur_s,
        'NoteCount_1x': _note_count(hand_lanes, readings['1x']['time_ms'] if readings['1x'] else np.empty(0)),
        'NoteCount_2x': _note_count(hand_lanes, readings['2x']['time_ms']) if readings['2x'] else None,
        **readings,
    }
