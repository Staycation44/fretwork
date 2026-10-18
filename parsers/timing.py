"""
TIMING - Shared tick -> ms conversion for the chart and midi parsers

Both formats have a similar tempo model - ticks with bpm stamps
    .chart has a SyncTrack section
    .mid has set_tempo meta messages
outputs from both parsers are the same so these functions are shared

clean_tempos() guards both formats so zero/invalid tempo markers are skipped
Errors are logged to the build errors CSV by the parsers and a missing tick-0 tempo is filled with 120 BPM

converter() is the one entry point the parsers use: raw {tick: bpm} in, a tick -> ms function
and the InvalidTempo warning rows out
masks_to_stream() packs a {tick: lane mask} dict into the cache's {'time_ms', 'lanes'} stream shape
"""

import math

import numpy as np

DEFAULT_BPM = 120.0  # MIDI default, and what the games assume before a song's first tempo marker

# {tick: bpm} -> (clean {tick: bpm}, [(tick, bpm) dropped])
# drops zero/negative/non-finite markers (skipped and logged by the parsers)
# adds DEFAULT_BPM at tick 0 when the first marker sits later, so the lead-in keeps its real length
def clean_tempos(tempos):
    clean = {}
    dropped = []
    for tick, bpm in tempos.items():
        if isinstance(bpm, (int, float)) and math.isfinite(bpm) and bpm > 0:
            clean[tick] = float(bpm)
        else:
            dropped.append((tick, bpm))
    if not clean or min(clean) > 0:
        clean[0] = DEFAULT_BPM
    return clean, sorted(dropped)


# {tick: bpm} -> aligned (ticks, cumulative_ms, ms_per_beat) indexed by tempo-marker position, once per file
# expects clean_tempos() output: positive bpm only, first marker at tick 0
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


# tick -> ms over whole array, tick_values already sorted
def ticks_to_ms(tick_values, tick_res, ticks, cum, ms_per_beat):
    values = np.asarray(tick_values, dtype=np.int64)
    if values.size == 0:
        return np.empty(0, dtype=np.float64)

    idx = np.searchsorted(ticks, values, side='right') - 1
    np.clip(idx, 0, None, out=idx)

    return cum[idx] + ((values - ticks[idx]) / tick_res) * ms_per_beat[idx]


# raw {tick: bpm} (+ markers the parser already dropped) -> (to_ms_array, warning rows)
# to_ms_array(ticks) converts a sorted tick list to ms with this file's tempo map
def converter(tempos, tick_res, warn_label, dropped=()):
    tempos, invalid = clean_tempos(tempos)
    arrays = tempo_map(tempos, tick_res)
    warnings = [
        (warn_label, 'InvalidTempo', f"skipped tempo marker at tick {tick} ({bpm} BPM)")
        for tick, bpm in sorted([*dropped, *invalid])
    ]

    def to_ms_array(tick_values):
        return ticks_to_ms(tick_values, tick_res, *arrays)

    return to_ms_array, warnings


# {tick: lane mask} -> {'time_ms', 'lanes'} stream in tick order, empty arrays for an empty dict
def masks_to_stream(masks_by_tick, to_ms_array):
    ordered_ticks = sorted(masks_by_tick)
    return {
        'time_ms': to_ms_array(ordered_ticks),
        'lanes': np.array([masks_by_tick[t] for t in ordered_ticks], dtype=np.uint8),
    }
