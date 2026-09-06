"""
TIMING - Shared tick/time helpers for the chart and midi parsers

Both formats have a similar tempo model - ticks with bpm stamps
.chart has a SyncTrack section
.mid has set_tempo meta messages
outputs from both parsers are the same so these functions are shared

Two conversion paths:
    tick_to_ms() - one tick at a time, for the handful of star power/solo spans
    ticks_to_ms() - a whole sorted tick array at once, for note streams
"""

import bisect

import numpy as np

# tempo mapping
def map_cum(tempos, tick_res):
    sorted_ticks = sorted(tempos.keys())
    cumulative_ms = {}
    running_ms = 0.0

    for i, t in enumerate(sorted_ticks):
        cumulative_ms[t] = running_ms
        if i + 1 < len(sorted_ticks):
            next_t = sorted_ticks[i + 1]
            bpm = tempos[t]
            running_ms += ((next_t - t) / tick_res) * (60000.0 / bpm)

    return sorted_ticks, cumulative_ms

# convert ticks to ms
def tick_to_ms(tick, tick_res, tempos, sorted_ticks, cum_ms):
    tick = int(tick)
    idx = max(bisect.bisect_right(sorted_ticks, tick) - 1, 0)
    ref_tick = sorted_ticks[idx]
    return (
        cum_ms[ref_tick]
        + ((tick - ref_tick) / tick_res) * (60000.0 / tempos[ref_tick])
    )


# map_cum's dict output flattened into aligned arrays, built once per file
# Returns (ticks, cum, ms_per_beat), all indexed by tempo-marker position
def tempo_arrays(tempos, sorted_ticks, cum_ms):
    ticks = np.asarray(sorted_ticks, dtype=np.int64)
    cum = np.array([cum_ms[t] for t in sorted_ticks], dtype=np.float64)
    ms_per_beat = np.array([60000.0 / tempos[t] for t in sorted_ticks], dtype=np.float64)
    return ticks, cum, ms_per_beat


# vectorized tick_to_ms over a whole array - tick_values already sorted
def ticks_to_ms(tick_values, tick_res, ticks, cum, ms_per_beat):
    values = np.asarray(tick_values, dtype=np.int64)
    if values.size == 0:
        return np.empty(0, dtype=np.float64)

    idx = np.searchsorted(ticks, values, side='right') - 1
    np.clip(idx, 0, None, out=idx)

    return cum[idx] + ((values - ticks[idx]) / tick_res) * ms_per_beat[idx]
