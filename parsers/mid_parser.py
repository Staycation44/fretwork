"""
MID_PARSER - Parses notes.mid files into per-instrument, per-level note streams:
    {
        'song_path': str,
        'source_format': 'mid',
        'resolution': int,
        'instruments': {
            instrument_key: {
                'levels': {
                    level_key: {
                        'notes': {
                            'time_ms': np.ndarray,   # sorted, one entry per tick
                            'lanes':   np.ndarray uint8,   # bitmask, bit N = lane N
                        },
                        'spans': {
                            'star_power': [(start_ms, end_ms), ...],
                            'solo':       [(start_ms, end_ms), ...],
                        },
                    },
                    ...  # one entry per level actually present for this instrument
                },
                'dropped': {counter_name: int, ...},  # track-wide, see EMHX note below
            },
            ...  # one entry per recognized instrument track actually present in the file
        },
    }

Scope: Easy/Medium/Hard/Expert (EMHX), 5-fret instruments (Guitar/Bass/Keys)

File load is the most expensive part, so midi is still slow, but per instrument scan is pretty fast

NOTE STATE IS NOT PARSED - strum/tap/hopo are not used in the calcs and are discarded

EMHX: .mid encodes level as a pitch block within one track per instrument
lane N (0-4, GRBYO) sits at MID_PITCH_BASE[level] + N open sits at MID_PITCH_BASE[level] - 1
A single linear scan of the track buckets each note_on into the right level by pitch
Star power and solo are track-wide, shared across every level, and are not part of the pitch blocks

Note-based open notes (pitch == MID_PITCH_BASE[level] - 1) require an [ENHANCED_OPENS] text event

Legacy GH1/2-style open notes (pitch 0, a specific MIDI channel) are assumed Expert only

SysEx-based open note (0x01) events are not implemented
"""

import pathlib

import mido
import numpy as np
import tqdm

from functions import instruments
from parsers.timing import map_cum, tick_to_ms

# ---------------------------------------------------------------------
# Mid-specific constants
# ---------------------------------------------------------------------
OPEN_MID = 7  # internal bit position for an open note - format-agnostic, matches chart_parser

# pitch -> (level_key, lane) for the four GRBYO blocks, built from instruments.py
LANE_PITCH_TO_INFO = {
    base + lane: (level_key, lane)
    for level_key, base in instruments.MID_PITCH_BASE.items()
    for lane in range(5)
}

# pitch -> level_key for each level's note-based open pitch (base - 1), gated by
# ENHANCED_OPENS at parse time - see module docstring
OPEN_PITCH_TO_LEVEL = {
    base - 1: level_key
    for level_key, base in instruments.MID_PITCH_BASE.items()
}

SP_PIT = 116             # modern star power phrase
SOLO_PIT = 103                   # solo phrase, unless it IS star power
LEGACY_SP = 103      # older charts, per multiplier_note tag

# Legacy GH1/2-style open note encoding - assumed Expert-only, see module docstring
M_OPEN_PIT = 0
M_OPEN_CNL = 5
LEGACY_OPEN_LEVEL = 'expert'

ENH_OPEN = 'ENHANCED_OPENS'


# ---------------------------------------------
# EOF diagnostics - reporting for broken files
# ---------------------------------------------
# mido raises a blank EOFError() or OSError(), adding a little info, hopefully this helps someone torubleshoot
# attempted some recovery of partial note streams from truncated files, but it didn't help much
def _diagnose_eof(mid_source):
    try:
        size = pathlib.Path(mid_source).stat().st_size
    except OSError as exc:
        return f"couldn't stat file to report its size ({exc})"
    return f"{size}-byte file"


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


# Extracts one instrument's note stream from its located track, split into per-EMHX-level lane masks from one scan
# Returns None if the track has no usable notes at any level
def _extract_track(track, instrument_key, to_ms, multiplier_note=None):
    allow_opens = instruments.SUPPORTS_OPEN_NOTES[instrument_key]

    enhanced_opens = allow_opens and any(
        msg.type == 'text' and ENH_OPEN in msg.text.upper()
        for msg in track
    )

    # star power / solo pitch assignment - track-wide, shared across every EMHX level
    legacy_sp = (multiplier_note == LEGACY_SP)
    sp_pitch = LEGACY_SP if legacy_sp else SP_PIT
    solo_pitch = None if legacy_sp else SOLO_PIT

    phrase_pitches = {sp_pitch}
    if solo_pitch is not None:
        phrase_pitches.add(solo_pitch)

    dropped = {
        'unclosed_star_power': 0,
        'unclosed_solo': 0,
        'legacy_open_unknown_channel': 0,
    }

    masks_by_tick = {level_key: {} for level_key in instruments.LEVEL_KEYS}
    star_power = []
    solos = []

    open_starts = {}
    abs_tick = 0

    for msg in track:
        abs_tick += msg.time

        if msg.type == 'note_on' and msg.velocity > 0:
            pitch = msg.note
            level_key = None
            lane = None

            if pitch in LANE_PITCH_TO_INFO:
                level_key, lane = LANE_PITCH_TO_INFO[pitch]

            elif allow_opens and pitch in OPEN_PITCH_TO_LEVEL:
                if enhanced_opens:
                    level_key = OPEN_PITCH_TO_LEVEL[pitch]
                    lane = OPEN_MID
                # else: note-based open marker without ENHANCED_OPENS

            elif allow_opens and pitch == M_OPEN_PIT:
                if msg.channel == M_OPEN_CNL:
                    level_key, lane = LEGACY_OPEN_LEVEL, OPEN_MID
                else:
                    dropped['legacy_open_unknown_channel'] += 1

            elif pitch in phrase_pitches:
                open_starts.setdefault(pitch, []).append(abs_tick)

            if level_key is not None:
                level_masks = masks_by_tick[level_key]
                level_masks[abs_tick] = level_masks.get(abs_tick, 0) | (1 << lane)

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

    shared_spans = {
        'star_power': star_power,
        'solo': solos,
    }

    levels_out = {}
    for level_key, level_masks in masks_by_tick.items():
        if not level_masks:
            continue

        ordered_ticks = sorted(level_masks.keys())
        levels_out[level_key] = {
            'notes': {
                'time_ms': np.array([to_ms(t) for t in ordered_ticks]),
                'lanes': np.array([level_masks[t] for t in ordered_ticks], dtype=np.uint8),
            },
            # same shared track-wide spans duplicated onto every level
            'spans': {
                'star_power': list(shared_spans['star_power']),
                'solo': list(shared_spans['solo']),
            },
        }

    if not levels_out:
        return None

    return {
        'levels': levels_out,
        'dropped': dropped,
    }


def mid_notes(mid_source, multiplier_note=None):
    try:
        mid = mido.MidiFile(str(mid_source), clip=True)
    except (EOFError, OSError) as exc:
        # these errors mean truncated/corrupted file
        if type(exc) not in (EOFError, OSError):
            raise
        raise type(exc)(
            f"{_diagnose_eof(mid_source)} - corrupt or truncated midi "
            f"({type(exc).__name__} from mido)"
        ) from exc

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
            continue  # this instrument just isn't in the file - not an error

        stream = _extract_track(track, instrument_key, to_ms, multiplier_note)
        if stream is not None:
            instruments_out[instrument_key] = stream

    if not instruments_out:
        raise ValueError(
            f"No recognized instrument track with usable notes found. "
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
                message = str(exc) or repr(exc)
                errors.append((str(file), type(exc).__name__, message))
            continue

    return mid_out
