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

Active windows (median/std gating) - onset based, same as 5 fret & drums
    SPS gates on windows with at least one syllable onset (sung + talkie)
    PPS gates on windows with at least one sung-note onset (slides/PHs included)

Talkie length
    Authored talkie lengths are ignored so RB & GH style talkies can be treated equivalently
    default Talkie length set based on official measurement, but clipped for no overlap
    Only used for duration

Static features (sung notes only)
    Pitches    = distinct MIDI pitches used
    maxPitch   = highest sung pitch
    talkieFrac = talkie onsets / NoteCount - descriptive, flags rap/spoken charts

std values are used for CoV, same as 5 fret/drums

Percussion is render/duration only (essentially treated as rest time)

Charts with zero syllables return None

Grid start is t=0 and runs until the latest endpoint across all three streams

Window/grid/summary mechanics are shared with 5 fret & drums in windowing.py
"""

import numpy as np

from functions import windowing

WINDOW_MS = windowing.WINDOW_MS
STEP_MS = windowing.STEP_MS

# Pitch travel constants
PITCH_CAP = 12      # octave of semitones
PITCH_GAMMA = 0.5   # sqrt compression

# fixed talkie length (estimated from official data), clipped to the next onset
TALKIE_FILL_MS = 133.0


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


# Windowing pass across SPS/PPS + the onset gates
# zero activity windows are included
#     Returns:
#        {
#            'time_ms':          ndarray,  # uniform grid, starts at 0
#            'raw_sps_samples':  ndarray,  # syllables per window
#            'raw_pps_samples':  ndarray,  # pitch travel per window
#            'active':           ndarray,  # bool, any syllable onset (sung/talkie) in window
#            'active_sung':      ndarray,  # bool, any sung-note onset in window
#            'syllable_times':   ndarray,  # sorted syllable onsets (sung + talkie)
#            'travel':           ndarray,  # per sung note travel (not windowed)
#            'pitch':            ndarray,  # per sung note pitch, in onset order
#            'talkie_count':     int,
#            'dur_ms':           float,    # latest end across sung/talkie/percussion
#            'raw_perc_samples': ndarray,  # percussion hits per window (render only)
#            'has_percussion':   bool,     # true = draw perc line (render only)
#        }
def window_arrays(notes, talkie, percussion=None, window_ms=WINDOW_MS, step_ms=STEP_MS):
    sung_t, sung_end, pitch, is_placeholder, is_slide = windowing.sort_stream(
        notes['time_ms'], notes['end_ms'], notes['pitch'], notes['is_placeholder'], notes['is_slide'])
    talk_t = np.sort(np.asarray(talkie['time_ms'], dtype=np.float64))
    perc_t = np.sort(np.asarray((percussion or {}).get('time_ms', []), dtype=np.float64))

    new_syllable = ~(is_slide.astype(bool) | is_placeholder.astype(bool))
    syllable_times = np.sort(np.concatenate([sung_t[new_syllable], talk_t]))
    if syllable_times.size == 0:
        return None

    sung_end = sung_end.astype(np.float64)
    talk_end = talkie_ends(talk_t, sung_t)
    pitch = pitch.astype(np.int64)
    travel = pitch_travel(pitch)

    perc_end = np.asarray((percussion or {}).get('end_ms', []), dtype=np.float64)
    dur_ms = float(max(
        (arr.max() for arr in (sung_end, talk_end, perc_end) if arr.size),
        default=0.0,
    ))

    grid = windowing.grid_to(dur_ms, step_ms)

    raw_sps = windowing.windowed_sum(syllable_times, np.ones(syllable_times.size), grid, window_ms)
    raw_pps = windowing.windowed_sum(sung_t, travel, grid, window_ms)
    raw_perc = windowing.windowed_sum(perc_t, np.ones(perc_t.size), grid, window_ms)

    # onset gates - a window is active only if something starts in it
    active = raw_sps > 0
    active_sung = windowing.windowed_sum(sung_t, np.ones(sung_t.size), grid, window_ms) > 0

    return {
        'time_ms': grid,
        'raw_sps_samples': raw_sps,
        'raw_pps_samples': raw_pps,
        'active': active,
        'active_sung': active_sung,
        'syllable_times': syllable_times,
        'travel': travel,
        'pitch': pitch,
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
    note_count = int(windows['syllable_times'].size)

    sps_window_values = windows['raw_sps_samples'] / window_s
    pps_window_values = windows['raw_pps_samples'] / window_s

    # static pitch features - sung notes only
    pitch = windows['pitch']
    if pitch.size:
        pitches = int(np.unique(pitch).size)
        max_pitch = int(pitch.max())
    else:
        # talkie-only chart - nothing pitched
        pitches = max_pitch = 0

    return {
        'NoteCount': note_count,
        'DurationS': dur_s,
        'Pitches': pitches,
        'maxPitch': max_pitch,
        'talkieFrac': windows['talkie_count'] / note_count if note_count else 0.0,
        # PPS gates on sung-note onsets, SPS on syllable onsets (sung + talkie)
        **windowing.rate_stats('PPS', pps_window_values, float(windows['travel'].sum()), dur_s,
                               windows['active_sung']),
        **windowing.rate_stats('SPS', sps_window_values, note_count, dur_s, windows['active']),
    }
