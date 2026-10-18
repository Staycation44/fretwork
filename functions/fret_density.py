"""
5 FRET DENSITY - Density metrics, computed from the cached notestream

NPS = Notes Per Second
    Notes are counted per game logic - any number of frets on the same timestamp count as 1 note

VPS = Variability per Second
    Variability is maximum fret changes between notes (released or added)

same format comes from both mid/chart files - density and curves can both use this data

lanes[i] is a bitmask, bit N = lane N (bits 0-4 frets, bit 7 open) - this keeps the cache smaller

Grid start is t=0 and runs until the last note

Window/grid/summary mechanics are shared with drums & vocals in windowing.py
"""

import numpy as np

from functions import windowing

WINDOW_MS = windowing.WINDOW_MS
STEP_MS = windowing.STEP_MS
POPCOUNT = windowing.POPCOUNT

# VPS source - max of lanes added/removed compared to previous note - first note counts all notes as added
def fret_var(fret_masks):
    masks = np.asarray(fret_masks, dtype=np.uint8)
    if masks.size == 0:
        return np.empty(0, dtype=np.int64)

    out = np.empty(masks.size, dtype=np.int64)
    out[0] = POPCOUNT[masks[0]]

    if masks.size > 1:
        prev, curr = masks[:-1], masks[1:]
        removed = POPCOUNT[prev & ~curr]
        added = POPCOUNT[curr & ~prev]
        out[1:] = np.maximum(removed, added)

    return out

# Shared windowing pass across NPS/VPS
# zero activity windows are included
#     Returns:
#        {
#            'time_ms':          ndarray,  # uniform grid, starts at 0
#            'raw_nps_samples':  ndarray,  # notes per window
#            'raw_vps_samples':  ndarray,  # variability per window
#            'vps_changes':      ndarray,  # per-note changes (not windowed)
#            'timestamps_ms':    ndarray,  # sorted note times
#        }
def window_arrays(notes, window_ms=WINDOW_MS, step_ms=STEP_MS):
    if not notes:
        return None

    times, masks = windowing.sort_stream(notes['time_ms'], np.asarray(notes['lanes'], dtype=np.uint8))
    if times.size == 0:
        return None

    changes = fret_var(masks)
    grid = windowing.grid_to(times[-1], step_ms)

    return {
        'time_ms': grid,
        'raw_nps_samples': windowing.windowed_sum(times, np.ones(times.size), grid, window_ms),
        'raw_vps_samples': windowing.windowed_sum(times, changes, grid, window_ms),
        'vps_changes': changes,
        'timestamps_ms': times,
    }

# provides NPS & VPS metrics to calculate D
def calc_metrics(notes, window_ms=WINDOW_MS, step_ms=STEP_MS, windows=None):
    if windows is None:
        windows = window_arrays(notes, window_ms, step_ms)
    if windows is None:
        return None

    timestamps = windows['timestamps_ms']
    note_count = int(timestamps.size)
    dur_s = float(timestamps[-1]) / 1000.0   # from t=0

    window_s = window_ms / 1000.0
    nps_window_values = windows['raw_nps_samples'] / window_s
    vps_window_values = windows['raw_vps_samples'] / window_s
    nps_active_mask = nps_window_values > 0 # active window mask used for both NPS & VPS (gated by note activity)

    return {
        'NoteCount': note_count,
        'DurationS': dur_s,   # float seconds, same as drum/vocal density (rows display it as int)
        **windowing.rate_stats('NPS', nps_window_values, note_count, dur_s, nps_active_mask),
        **windowing.rate_stats('VPS', vps_window_values, int(windows['vps_changes'].sum()), dur_s, nps_active_mask),
    }
