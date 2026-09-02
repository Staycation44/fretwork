"""
MID_PARSER - Parses notes.mid files into per-instrument note streams:
    {
        'song_path': str,
        'source_format': 'mid',
        'resolution': int,
        'instruments': {
            instrument_key: {
                'notes': {
                    'time_ms': np.ndarray,   # sorted, one entry per tick
                    'lanes':   np.ndarray uint8,   # bitmask, bit N = lane N
                },
                'spans': {
                    'star_power': [(start_ms, end_ms), ...],
                    'solo':       [(start_ms, end_ms), ...],
                },
                'dropped': {counter_name: int, ...},
            },
            ...  # one entry per recognized instrument track actually present in the file
        },
    }

Scope is Expert difficulty only, across every recognized 5-fret instrument track found in
the file (see instruments.py for the full track-name mapping). The file is opened and
tempo-mapped exactly once regardless of how many instrument tracks it contains - only the
per-track note/phrase scan repeats, and that scan is cheap relative to the MidiFile load.

NOTE STATE IS NOT PARSED - strum/tap/hopo are not used in the calcs and are discarded

STAR POWER / SOLO
    Modern charts: pitch 116 = star power, pitch 103 = solo.
    Older charts:  pitch 103 = star power, no solo track.
    song.ini's multiplier_note / star_power_note tag is file-wide - it disambiguates pitch
    103 identically for every instrument track in a given .mid, not just guitar.

SysEx-based open note (0x01) events are not implemented
"""

import pathlib

import mido
import numpy as np
import tqdm

from functions import instruments
from parsers.timing import map_cum, tick_to_ms

# ---------------------------------------------------------------------
# Mid-specific constants (Expert only)
# ---------------------------------------------------------------------
X_FRETS = {96: 0, 97: 1, 98: 2, 99: 3, 100: 4}  # pitch -> lane number
OPEN_MID = 7
X_OPEN_PIT = 95        # note-based open, requires ENHANCED_OPENS

SP_PIT = 116             # modern star power phrase
SOLO_PIT = 103                   # solo phrase, unless it IS star power
LEGACY_SP = 103      # older charts, per multiplier_note tag

# Legacy GH1/2-style open note encoding
M_OPEN_PIT = 0
M_OPEN_CNL = 5

ENH_OPEN = 'ENHANCED_OPENS'


# ----------
# Tempo map
# ----------

def map_mid_tempo(mid):
    tempos = {}

    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == 'set_tempo':
                bpm = 60_000_000 / msg.tempo
                tempos[abs_tick] = bpm  # last writer wins on tie

    if not tempos:
        tempos[0] = 120.0  # MIDI default

    sorted_ticks, cum_ms = map_cum(tempos, mid.ticks_per_beat)
    return tempos, sorted_ticks, cum_ms


# -----------------------
# Note-stream extraction
# -----------------------

def _is_note_off(msg):
    return msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0)


# Extracts one instrument's note stream from its located track
# Shared scan logic across every 5-fret instrument
# Returns None if the track has no usable Expert notes
def _extract_track(track, instrument_key, to_ms, multiplier_note=None):
    allow_opens = instruments.SUPPORTS_OPEN_NOTES[instrument_key]

    enhanced_opens = allow_opens and any(
        msg.type == 'text' and ENH_OPEN in msg.text.upper()
        for msg in track
    )

    # star power / solo pitch assignment
    legacy_sp = (multiplier_note == LEGACY_SP)
    sp_pitch = LEGACY_SP if legacy_sp else SP_PIT
    solo_pitch = None if legacy_sp else SOLO_PIT

    phrase_pitches = {sp_pitch}
    if solo_pitch is not None:
        phrase_pitches.add(solo_pitch)

    dropped = {
        'unclosed_star_power': 0,
        'unclosed_solo': 0,
    }

    masks_by_tick = {}
    star_power = []
    solos = []

    open_starts = {}
    abs_tick = 0

    for msg in track:
        abs_tick += msg.time

        if msg.type == 'note_on' and msg.velocity > 0:
            pitch = msg.note

            if pitch in X_FRETS:
                lane = X_FRETS[pitch]
            elif allow_opens and pitch == M_OPEN_PIT and msg.channel == M_OPEN_CNL:
                lane = OPEN_MID                      # legacy open
            elif allow_opens and pitch == X_OPEN_PIT and enhanced_opens:
                lane = OPEN_MID                      # note-based open
            else:
                lane = None
                if pitch in phrase_pitches:
                    open_starts.setdefault(pitch, []).append(abs_tick)

            if lane is not None:
                masks_by_tick[abs_tick] = masks_by_tick.get(abs_tick, 0) | (1 << lane)

        elif _is_note_off(msg):
            pitch = msg.note
            if pitch in phrase_pitches:
                starts = open_starts.get(pitch)
                if starts:
                    start_tick = starts.pop(0)
                    if pitch == sp_pitch:
                        star_power.append((to_ms(start_tick), to_ms(abs_tick)))
                    elif pitch == solo_pitch:
                        solos.append((to_ms(start_tick), to_ms(abs_tick)))

    # Anything still open at end of track never closes. Dropped, but counted for errors
    for pitch, starts in open_starts.items():
        if not starts:
            continue
        if pitch == sp_pitch:
            dropped['unclosed_star_power'] += len(starts)
        elif pitch == solo_pitch:
            dropped['unclosed_solo'] += len(starts)

    if not masks_by_tick:
        return None

    ordered_ticks = sorted(masks_by_tick.keys())

    return {
        'notes': {
            'time_ms': np.array([to_ms(t) for t in ordered_ticks]),
            'lanes': np.array([masks_by_tick[t] for t in ordered_ticks], dtype=np.uint8),
        },
        'spans': {
            'star_power': star_power,
            'solo': solos,
        },
        'dropped': dropped,
    }


def mid_notes(mid_source, multiplier_note=None):
    mid = mido.MidiFile(str(mid_source), clip=True)
    tick_res = mid.ticks_per_beat

    tempos, sorted_ticks, cum_ms = map_mid_tempo(mid)

    def to_ms(tick):
        return tick_to_ms(tick, tick_res, tempos, sorted_ticks, cum_ms)

    track_map = {t.name.strip(): t for t in mid.tracks if t.name}

    instruments_out = {}
    for instrument_key in instruments.INSTRUMENT_KEYS:
        track = None
        for name in instruments.MID_TRACK_NAMES[instrument_key]:
            if name in track_map:
                track = track_map[name]
                break

        if track is None:
            continue  # this instrument's track just isn't in the file - not an error

        stream = _extract_track(track, instrument_key, to_ms, multiplier_note)
        if stream is not None:
            instruments_out[instrument_key] = stream

    if not instruments_out:
        raise ValueError(
            f"No recognized instrument track with Expert notes found. "
            f"Available tracks: {list(track_map.keys())}"
        )

    return {
        'song_path': str(pathlib.Path(mid_source).parent.resolve()),
        'source_format': 'mid',
        'resolution': tick_res,
        'instruments': instruments_out,
    }


# -----------
# Search loop
# -----------

# loops through search path, retrieving errors to provide along with cache
def mid_loop(search_path, multiplier_notes=None, errors=None):
    multiplier_notes = multiplier_notes or {}
    mid_out = {}

    search = pathlib.Path(search_path)
    files = list(search.rglob("notes.mid"))

    for file in tqdm.tqdm(files, desc="Parsing midis", unit="file"):
        try:
            song_path = str(pathlib.Path(file).parent.resolve())
            stream = mid_notes(file, multiplier_notes.get(song_path))
            mid_out[stream['song_path']] = stream
        except Exception as exc:
            if errors is not None:
                errors.append((str(file), type(exc).__name__, str(exc)))
            continue

    return mid_out
