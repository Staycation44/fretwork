"""
WINDOWING - the shared windowing mechanics used for fret_density, drum_density and vocal_density

One implementation of each step for how a window is counted or summarized:
    WINDOW_MS / STEP_MS   1s window sliding in 250ms steps - each density module aliases these,
                          so one instrument can be retuned locally by changing its own alias
    POPCOUNT              lanes set per uint8 lane mask
    sort_stream()         defensive stable sort of a stream's times + its per-event arrays
    make_grid()           window-start grid by sample count, grid_to() runs it out to an end time
    windowed_sum()        per-event values summed over each [start, start + window) on a grid
    active_median/std()   median / std over windows with activity only
    rate_stats()          the p / a / med / std block every per-second metric reports
"""

import numpy as np

WINDOW_MS = 1000
STEP_MS = WINDOW_MS / 4

POPCOUNT = np.array([bin(i).count('1') for i in range(256)], dtype=np.int64)


# times + any per-event arrays -> the same, in stable time order (no copy when already sorted)
def sort_stream(times, *arrays):
    times = np.asarray(times, dtype=np.float64)
    arrays = [np.asarray(arr) for arr in arrays]
    if times.size > 1 and not np.all(np.diff(times) >= 0):
        order = np.argsort(times, kind='stable')
        times = times[order]
        arrays = [arr[order] for arr in arrays]
    return (times, *arrays)


# Uniform window-start grid (t=0 onward, one sample per step)
def make_grid(n_samples, step_ms=STEP_MS):
    return np.arange(n_samples, dtype=np.float64) * step_ms


# grid from t=0 whose last window starts at or before end_ms
def grid_to(end_ms, step_ms=STEP_MS):
    return make_grid(int(end_ms // step_ms) + 1, step_ms)


# Prefix-sum windowed reducer over sorted (times, values) on a caller-built grid
def windowed_sum(times, values, grid, window_ms=WINDOW_MS):
    if times.size == 0 or grid.size == 0:
        return np.zeros(grid.size, dtype=np.float64)

    prefix = np.concatenate(([0.0], np.cumsum(np.asarray(values, dtype=np.float64))))
    left = np.searchsorted(times, grid, side='left')
    right = np.searchsorted(times, grid + window_ms, side='left')
    return prefix[right] - prefix[left]


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


# The four summaries every per-second metric reports, keyed by name ('NPS' -> pNPS/aNPS/medNPS/stdNPS)
#   window_values: per-window rates (raw window sums / window seconds)
#   total:         whole-song count/weight for the average - the caller decides what counts
#                  (drums pass a roll-capped hit total, not the raw sum)
#   dur_s:         song duration the average divides by
#   active_mask:   which windows the median/std gate on - defaults to windows with any activity
def rate_stats(name, window_values, total, dur_s, active_mask=None):
    return {
        f'p{name}': float(window_values.max()) if window_values.size else 0.0,
        f'a{name}': total / dur_s if dur_s > 0 else 0.0,
        f'med{name}': active_median(window_values, active_mask),
        f'std{name}': active_std(window_values, active_mask),
    }
