"""
TIMING - Shared tick -> ms conversion for the chart and midi parsers

Both formats have a similar tempo model - ticks with bpm stamps
.chart has a SyncTrack section
.mid has set_tempo meta messages
outputs from both parsers are the same so these functions are shared
"""

import numpy as np


# {tick: bpm} -> aligned (ticks, cumulative_ms, ms_per_beat) indexed by tempo-marker position, once per file
def tempo_map(tempos, tick_res):
    sorted_ticks = sorted(tempos)

    ticks = np.asarray(sorted_ticks, dtype=np.int64)
    ms_per_beat = np.array([60000.0 / tempos[t] for t in sorted_ticks], dtype=np.float64)

    # elapsed ms across each tempo span, accumulated from the first marker
    if ticks.size > 1:
        spans = (np.diff(ticks) / tick_res) * ms_per_beat[:-1]
        cum = np.concatenate(([0.0], np.cumsum(spans)))
    else:
        cum = np.zeros(ticks.size, dtype=np.float64)

    return ticks, cum, ms_per_beat


# tick -> ms over whole array - tick_values already sorted
def ticks_to_ms(tick_values, tick_res, ticks, cum, ms_per_beat):
    values = np.asarray(tick_values, dtype=np.int64)
    if values.size == 0:
        return np.empty(0, dtype=np.float64)

    idx = np.searchsorted(ticks, values, side='right') - 1
    np.clip(idx, 0, None, out=idx)

    return cum[idx] + ((values - ticks[idx]) / tick_res) * ms_per_beat[idx]
