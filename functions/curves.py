"""
CURVES - smoothes density.py's windowed arrays for visualization

The raw arrays are converted to rates (notes/sec, hits/sec, etc) before smoothing by an EMA

5 fret: d_raw uses sqrt(nps*vps) to fit to scale

Drums: d_raw sums hps+tps+kps directly, fits on scale naturally

Vocals: d_raw = R*A*pps + S_WEIGHT*sps, scale is okay / percussion is almost always low

d_raw lines don't apply COV/STAM since those are song-level balancing values

Each calc_*_curves accepts the density module's window_arrays() output (windows=) so render can
window a stream once and share it with the metrics calc; vocals also take the already computed
difficulty (its R/A shape d_raw)
"""

import math

import numpy as np

from functions import fret_density, drum_density, vocal_density, vocal_formula

# Shared smoothing time constant for curves
TAU_MS = 2000.0

# Sequential single-pole accumulator
def _ema_forward(samples, decay):
    gain = 1.0 - decay
    acc = 0.0
    out = []
    for raw in samples.tolist():
        acc = acc * decay + raw * gain
        out.append(acc)
    return np.array(out, dtype=np.float64)

# Single-pole low-pass the array, run forward then backward
# so peaks don't lag by tau the way a single pass does
def _ema_smooth(samples, step_ms, tau_ms):
    samples = np.asarray(samples, dtype=np.float64)
    if samples.size == 0:
        return samples
    if tau_ms <= 0:
        return samples.copy()

    decay = math.exp(-step_ms / tau_ms)

    forward = _ema_forward(samples, decay)
    backward = _ema_forward(forward[::-1], decay)
    return backward[::-1]

# Generic smoothing pass for all insts
def smooth_series(raw_rates, step_ms, tau_ms=TAU_MS):
    return {name: _ema_smooth(values, step_ms, tau_ms) for name, values in raw_rates.items()}

# Zero-pad to match hand and kick stream lengths
def _pad_to_length(arr, n):
    arr = np.asarray(arr, dtype=np.float64)
    if arr.size >= n:
        return arr
    return np.pad(arr, (0, n - arr.size))

# -------------
# 5 Fret curves
# -------------

# fret-only: builds raw rates from windows and assembles the final curve dict (incl. d_raw)
def _calc_fret_curves(windows, window_ms, step_ms, tau_ms=TAU_MS):

    if windows is None or len(windows['time_ms']) == 0:
        return None

    window_s = window_ms / 1000.0
    raw_rates = {
        'nps': windows['raw_nps_samples'] / window_s,
        'vps': windows['raw_vps_samples'] / window_s,
    }
    smoothed = smooth_series(raw_rates, step_ms, tau_ms)

    return {
        'time_ms': windows['time_ms'],
        'nps': smoothed['nps'],
        'vps': smoothed['vps'],
        'd_raw': np.sqrt(smoothed['nps'] * smoothed['vps']),
    }

# final curves for render / 5 Fret
def calc_curves(notes,
                window_ms=fret_density.WINDOW_MS,
                step_ms=fret_density.STEP_MS, tau_ms=TAU_MS, windows=None):

    if windows is None:
        windows = fret_density.window_arrays(notes, window_ms, step_ms)
    return _calc_fret_curves(windows, window_ms, step_ms, tau_ms)

# -----------
# Drum curves
# -----------

# final curves for render - drums
def calc_drum_curves(notes, roll_spans=None,
                      window_ms=drum_density.WINDOW_MS, step_ms=drum_density.STEP_MS, tau_ms=TAU_MS,
                      windows=None):
    hand_mask = notes['hand_mask']
    kick_mask = notes['kick_mask']

    if windows is None:
        windows = drum_density.window_arrays(hand_mask, roll_spans, window_ms, step_ms)
    if windows is None:
        return None

    kicks_1x = drum_density.kick_arrays(kick_mask, 0b01, window_ms, step_ms)

    # 2x only exists if there are notes for it
    kick_lanes = np.asarray(kick_mask['lanes'], dtype=np.uint8)
    has_2x_lanes = bool(kick_lanes.size and np.any(kick_lanes & 0b10))
    kicks_2x = drum_density.kick_arrays(kick_mask, 0b11, window_ms, step_ms) if has_2x_lanes else None

    # Hand and kick streams need to match length
    n_hand = windows['time_ms'].size
    n_1x = kicks_1x['time_ms'].size if kicks_1x is not None else 0
    n_2x = kicks_2x['time_ms'].size if kicks_2x is not None else 0
    n_max = max(n_hand, n_1x, n_2x)

    grid = drum_density.make_grid(n_max, step_ms)
    window_s = window_ms / 1000.0

    raw_rates = {
        'hps': _pad_to_length(windows['raw_hps_samples'], n_max) / window_s,
        'tps': _pad_to_length(windows['raw_tps_samples'], n_max) / window_s,
        'kps_1x': (_pad_to_length(kicks_1x['raw_kps_samples'], n_max) / window_s
                   if kicks_1x is not None else np.zeros(n_max, dtype=np.float64)),
    }
    if kicks_2x is not None:
        raw_rates['kps_2x'] = _pad_to_length(kicks_2x['raw_kps_samples'], n_max) / window_s

    smoothed = smooth_series(raw_rates, step_ms, tau_ms)

    kps = {'1x': smoothed['kps_1x'], '2x': smoothed.get('kps_2x')}
    d_raw = {
        '1x': smoothed['hps'] + smoothed['tps'] + smoothed['kps_1x'],
        '2x': (smoothed['hps'] + smoothed['tps'] + smoothed['kps_2x']) if kicks_2x is not None else None,
    }

    return {
        'time_ms': grid,
        'hps': smoothed['hps'],
        'tps': smoothed['tps'],
        'kps': kps,
        'd_raw': d_raw,
        'has_2x': kicks_2x is not None,
    }

# ------------
# Vocal curves
# ------------

# final curves for render - vocals
# difficulty: calc_vocal_d() output, if the caller already has it - derived here otherwise
def calc_vocal_curves(notes, talkie, percussion=None,
                       window_ms=vocal_density.WINDOW_MS, step_ms=vocal_density.STEP_MS, tau_ms=TAU_MS,
                       windows=None, difficulty=None):
    if windows is None:
        windows = vocal_density.window_arrays(notes, talkie, percussion, window_ms, step_ms)
    if windows is None:
        return None

    if difficulty is None:
        metrics = vocal_density.calc_vocal_metrics(notes, talkie, percussion, window_ms, step_ms,
                                                   windows=windows)
        difficulty = vocal_formula.calc_vocal_d(metrics)

    window_s = window_ms / 1000.0
    raw_rates = {
        'pps': windows['raw_pps_samples'] / window_s,
        'sps': windows['raw_sps_samples'] / window_s,
        'perc': windows['raw_perc_samples'] / window_s,
    }
    smoothed = smooth_series(raw_rates, step_ms, tau_ms)

    has_perc = windows['has_percussion']

    return {
        'time_ms': windows['time_ms'],
        'pps': smoothed['pps'],
        'sps': smoothed['sps'],
        'perc': smoothed['perc'] if has_perc else None,
        'd_raw': difficulty['R'] * difficulty['A'] * smoothed['pps'] + vocal_formula.S_WEIGHT * smoothed['sps'],
        'has_perc': has_perc,
    }
