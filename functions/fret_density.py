"""
5 FRET DENSITY - Density metrics, computed from the cached notestream

NPS = Notes Per Second
    Notes are counted per game logic - any number of frets on the same timestamp count as 1 note
VPS = Variability per Second
    Variability is maximum fret changes between notes (released or added)

same format comes from both mid/chart files - density and curves can both use this data

lanes[i] is a bitmask, bit N = lane N (bits 0-4 frets, bit 7 open) - this keeps the cache smaller

Grid origin is t=0 and runs until the last note
"""

import numpy as np

WINDOW_MS = 1000
STEP_MS = WINDOW_MS / 4

POPCOUNT = np.array([bin(i).count('1') for i in range(256)], dtype=np.int64)

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

    times = np.asarray(notes['time_ms'], dtype=np.float64)
    masks = np.asarray(notes['lanes'], dtype=np.uint8)

    if times.size == 0:
        return None

    if times.size > 1 and not np.all(np.diff(times) >= 0):
        order = np.argsort(times, kind='stable')
        times = times[order]
        masks = masks[order]

    changes = fret_var(masks)

    # prefix sum for windowed VPS sampling
    prefix = np.concatenate(([0], np.cumsum(changes)))

    song_end = times[-1]

    n_samples = int(song_end // step_ms) + 1
    grid = np.arange(n_samples, dtype=np.float64) * step_ms

    left = np.searchsorted(times, grid, side='left')
    right = np.searchsorted(times, grid + window_ms, side='left')

    return {
        'time_ms': grid,
        'raw_nps_samples': (right - left).astype(np.int64),
        'raw_vps_samples': prefix[right] - prefix[left],
        'vps_changes': changes,
        'timestamps_ms': times,
    }

# Median over windows w/ activity
def active_median(values, active_mask=None):
    if active_mask is None:
        active_mask = values > 0
    active = values[active_mask]
    return float(np.median(active)) if active.size else 0.0

# Std dev over windows w/ activity
def active_std(values, active_mask=None):
    if active_mask is None:
        active_mask = values > 0
    active = values[active_mask]
    return float(np.std(active)) if active.size else 0.0

# provides NPS & VPS metrics to calculate D
def calc_metrics(notes, window_ms=WINDOW_MS, step_ms=STEP_MS):
    windows = window_arrays(notes, window_ms, step_ms)
    if windows is None:
        return None

    timestamps = windows['timestamps_ms']

    # NPS
    note_count = int(timestamps.size)
    dur_ms = float(timestamps[-1])   # from t=0
    dur_s = dur_ms / 1000.0

    avg_nps = note_count / dur_s if dur_s > 0 else 0.0

    window_s = window_ms / 1000.0
    nps_window_values = windows['raw_nps_samples'] / window_s
    nps_active_mask = nps_window_values > 0 # active window mask used for both NPS & VPS

    peak_nps = float(nps_window_values.max()) if nps_window_values.size else 0.0
    std_nps  = active_std(nps_window_values, nps_active_mask) # gated by note activity
    med_nps  = active_median(nps_window_values, nps_active_mask) # gated by note activity

    # VPS
    total_changes = int(windows['vps_changes'].sum())
    avg_vps = total_changes / dur_s if dur_s > 0 else 0.0

    vps_window_values = windows['raw_vps_samples'] / window_s

    peak_vps = float(vps_window_values.max()) if vps_window_values.size else 0.0
    std_vps  = active_std(vps_window_values, nps_active_mask) # gated by note activity
    med_vps  = active_median(vps_window_values, nps_active_mask) # gated by note activity

    return {
        'NoteCount': note_count,
        'DurationS': int(dur_s),
        'aNPS': avg_nps,
        'pNPS': peak_nps,
        'stdNPS': std_nps,
        'medNPS': med_nps,
        'aVPS': avg_vps,
        'pVPS': peak_vps,
        'stdVPS': std_vps,
        'medVPS': med_vps,
    }
