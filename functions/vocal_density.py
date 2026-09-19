"""
VOCAL DENSITY - Density metrics, computed from the cached vocal streams

Two windowed families (same 1s window / 250ms step grid as 5 fret & drums) plus static per-song features

PPS = Pitch-travel Per Second
    Each sung note (slides (+) and placeholders (+$) included) compared to the previous sung pitch
    Tracks across octaves, even though the game accepts octave shifts (most people try to hit the notes as recorded)
    A song's first note has nothing to compare against, so it scores 0
    Talkies aren't pitched and don't break the chain

SPS = Syllables Per Second
    Sung notes that aren't slides (+) or placeholders (+$) plus talkies (RB convention (*/^/#), or GH-style lyric-only) 
    Sung notes + talkies also defines NoteCount

aPPS & aSPS = total / DurationS

Active windows (median/std gating)
    SPS gates on sung+talkie within the window
    PPS gates on sung notes within the window

Talkie length
    Authored talkie lengths are ignored so RB & GH style talkies can be treated equivalently
    default Talkie length set based on official measurement, but clipped for no overlap
    Only used for occupancy gating and duration

Static features (sung notes only)
    Pitches    = distinct MIDI pitches used
    maxPitch   = highest sung pitch
    ShortFrac  = share of sung notes (slides/PHs included) shorter than SHORT_NOTE_MS
    talkieFrac = talkie onsets / NoteCount - descriptive, flags rap/spoken charts

std values are used for CoV, same as 5 fret/drums

Percussion is render/duration only (essentially treated as rest time)

Charts with zero syllables return None

Grid start is t=0 and runs until the latest endpoint across all three streams
"""

import numpy as np

from functions import fret_density

WINDOW_MS = fret_density.WINDOW_MS
STEP_MS = fret_density.STEP_MS

# Pitch travel constants
PITCH_CAP = 12      # octave of semitones
PITCH_GAMMA = 0.5   # sqrt compression

# short notes = fast articulation
SHORT_NOTE_MS = 120.0

# fixed talkie length (estimated from official data), clipped to the next onset
TALKIE_FILL_MS = 133.0

# minimum interval length so a zero-length event still marks its window active
MIN_EVENT_MS = 1e-3


def _sorted_stream(stream, keys):
    times = np.asarray(stream['time_ms'], dtype=np.float64)
    arrays = {k: np.asarray(stream[k]) for k in keys}
    if times.size > 1 and not np.all(np.diff(times) >= 0):
        order = np.argsort(times, kind='stable')
        times = times[order]
        arrays = {k: v[order] for k, v in arrays.items()}
    return times, arrays


# PPS, capped/compressed interval from previous pitch
def pitch_travel(pitches, cap=PITCH_CAP, gamma=PITCH_GAMMA):
    p = np.asarray(pitches, dtype=np.int64)
    out = np.zeros(p.size, dtype=np.float64)
    if p.size > 1:
        d = np.minimum(np.abs(np.diff(p)), cap).astype(np.float64)
        out[1:] = d ** gamma
    return out


# talkie end = onset + min(gap to next onset, fill)
def talkie_ends(talkie_times, sung_times, fill_ms=TALKIE_FILL_MS):
    if talkie_times.size == 0:
        return np.empty(0, dtype=np.float64)
    onsets = np.unique(np.concatenate([sung_times, talkie_times]))
    j = np.searchsorted(onsets, talkie_times, side='right')
    gap = np.full(talkie_times.size, np.inf)
    has_next = j < onsets.size
    gap[has_next] = onsets[j[has_next]] - talkie_times[has_next]
    return talkie_times + np.minimum(gap, fill_ms)


# Per grid window: any start/end interval overlapping the window
def occupancy_gate(starts, ends, grid, window_ms=WINDOW_MS):
    active = np.zeros(grid.size, dtype=bool)
    if starts.size == 0:
        return active
    order = np.argsort(starts, kind='stable')
    s = starts[order]
    e = np.maximum(ends[order], s + MIN_EVENT_MS)
    run_max_end = np.maximum.accumulate(e)

    # intervals starting before the window closes
    idx = np.searchsorted(s, grid + window_ms, side='left')
    has = idx > 0
    active[has] = run_max_end[idx[has] - 1] > grid[has]
    return active


# windowed sum of per-event values over the grid
def _window_sum(times, values, grid, window_ms=WINDOW_MS):
    prefix = np.concatenate(([0.0], np.cumsum(values)))
    left = np.searchsorted(times, grid, side='left')
    right = np.searchsorted(times, grid + window_ms, side='left')
    return prefix[right] - prefix[left]


# Windowing pass across SPS/PPS + the occupancy gates
# zero activity windows are included
#     Returns:
#        {
#            'time_ms':          ndarray,  # uniform grid, starts at 0
#            'raw_sps_samples':  ndarray,  # syllables per window
#            'raw_pps_samples':  ndarray,  # pitch travel per window
#            'active':           ndarray,  # bool, any sung/talkie time in window
#            'active_sung':      ndarray,  # bool, any sung time in window
#            'syllable_times':   ndarray,  # sorted syllable onsets (sung + talkie)
#            'travel':           ndarray,  # per sung note travel (not windowed)
#            'pitch':            ndarray,  # per sung note pitch, in onset order
#            'sung_dur_ms':      ndarray,  # per sung note authored length
#            'talkie_count':     int,
#            'dur_ms':           float,    # latest end across sung/talkie/percussion
#            'raw_perc_samples': ndarray,  # percussion hits per window (render only)
#            'has_percussion':   bool,     # true = draw perc line (render only)
#        }
def window_arrays(notes, talkie, percussion=None, window_ms=WINDOW_MS, step_ms=STEP_MS):
    sung_t, sung = _sorted_stream(notes, ('end_ms', 'pitch', 'is_placeholder', 'is_slide'))
    talk_t = np.sort(np.asarray(talkie['time_ms'], dtype=np.float64))
    perc_t = np.sort(np.asarray((percussion or {}).get('time_ms', []), dtype=np.float64))

    new_syllable = ~(sung['is_slide'].astype(bool) | sung['is_placeholder'].astype(bool))
    syllable_times = np.sort(np.concatenate([sung_t[new_syllable], talk_t]))
    if syllable_times.size == 0:
        return None

    sung_end = sung['end_ms'].astype(np.float64)
    talk_end = talkie_ends(talk_t, sung_t)
    pitch = sung['pitch'].astype(np.int64)
    travel = pitch_travel(pitch)

    perc_end = np.asarray((percussion or {}).get('end_ms', []), dtype=np.float64)
    dur_ms = float(max(
        (arr.max() for arr in (sung_end, talk_end, perc_end) if arr.size),
        default=0.0,
    ))

    n_samples = int(dur_ms // step_ms) + 1
    grid = np.arange(n_samples, dtype=np.float64) * step_ms

    raw_sps = _window_sum(syllable_times, np.ones(syllable_times.size), grid, window_ms)
    raw_pps = _window_sum(sung_t, travel, grid, window_ms)
    raw_perc = (_window_sum(perc_t, np.ones(perc_t.size), grid, window_ms)
                if perc_t.size else np.zeros(grid.size, dtype=np.float64))

    active = occupancy_gate(
        np.concatenate([sung_t, talk_t]),
        np.concatenate([sung_end, talk_end]),
        grid, window_ms,
    )
    active_sung = occupancy_gate(sung_t, sung_end, grid, window_ms)

    return {
        'time_ms': grid,
        'raw_sps_samples': raw_sps,
        'raw_pps_samples': raw_pps,
        'active': active,
        'active_sung': active_sung,
        'syllable_times': syllable_times,
        'travel': travel,
        'pitch': pitch,
        'sung_dur_ms': sung_end - sung_t,
        'talkie_count': int(talk_t.size),
        'dur_ms': dur_ms,
        'raw_perc_samples': raw_perc,
        'has_percussion': bool(perc_t.size),
    }


# provides PPS/SPS + static pitch features to calculate D
def calc_vocal_metrics(notes, talkie, percussion=None, window_ms=WINDOW_MS, step_ms=STEP_MS, windows=None):
    if windows is None:
        windows = window_arrays(notes, talkie, percussion, window_ms, step_ms)
    if windows is None:
        return None

    dur_s = windows['dur_ms'] / 1000.0
    window_s = window_ms / 1000.0
    active = windows['active']             # SPS gate
    active_sung = windows['active_sung']   # PPS gate

    # SPS
    note_count = int(windows['syllable_times'].size)
    sps_window_values = windows['raw_sps_samples'] / window_s

    # PPS
    pps_window_values = windows['raw_pps_samples'] / window_s
    total_travel = float(windows['travel'].sum())

    # static pitch features - sung notes only
    pitch = windows['pitch']
    if pitch.size:
        pitches = int(np.unique(pitch).size)
        max_pitch = int(pitch.max())
        short_frac = float(np.mean(windows['sung_dur_ms'] < SHORT_NOTE_MS))
    else:
        # talkie-only chart - nothing pitched
        pitches = max_pitch = 0
        short_frac = 0.0

    return {
        'NoteCount': note_count,
        'DurationS': dur_s,
        'Pitches': pitches,
        'maxPitch': max_pitch,
        'ShortFrac': short_frac,
        'talkieFrac': windows['talkie_count'] / note_count if note_count else 0.0,
        'pPPS': float(pps_window_values.max()) if pps_window_values.size else 0.0,
        'aPPS': total_travel / dur_s if dur_s > 0 else 0.0,
        'medPPS': fret_density.active_median(pps_window_values, active_sung),
        'stdPPS': fret_density.active_std(pps_window_values, active_sung),
        'pSPS': float(sps_window_values.max()) if sps_window_values.size else 0.0,
        'aSPS': note_count / dur_s if dur_s > 0 else 0.0,
        'medSPS': fret_density.active_median(sps_window_values, active),
        'stdSPS': fret_density.active_std(sps_window_values, active),
    }
