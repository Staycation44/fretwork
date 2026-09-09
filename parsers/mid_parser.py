"""
MID_PARSER - Parses notes.mid files into per-instrument, per-level note streams:
    {
        'song_path': str,
        'source_format': 'mid',
        'resolution': int,
        'instruments': {
            instrument_key: {
                level_key: {
                    'notes': {
                        'time_ms': np.ndarray,   # sorted, one entry per tick
                        'lanes':   np.ndarray uint8,   # bitmask, bit N = lane N
                    },
                },
                ...  # one entry per level actually present for this instrument
            },
            ...  # one entry per recognized instrument track actually present in the file
        },
    }

    Drums' 'notes' has two streams (hands/kick)
        'notes': {
            'hand_mask': {'time_ms': np.ndarray, 'lanes': np.ndarray uint8},
            'kick_mask': {'time_ms': np.ndarray, 'lanes': np.ndarray uint8},
        }

Scope: Easy/Medium/Hard/Expert (EMHX). 5-fret (Guitar/Bass/Keys) + Drums,
both read from 'PART <NAME>' tracks via instruments.MID_TRACK_NAMES

File load is the most expensive part, so midi is still slow, but per instrument scan is pretty fast

NOTE STATE IS NOT PARSED - strum/tap/hopo are not used in the calcs and are discarded


Only note_on is read - note_off/velocity-0 messages are ignored, since note length isn't used by any metric.

NOT PARSED: star power and solo phrases, SysEx-based open notes (0x01), 
and GH1/2-style legacy open notes (pitch 0 on a specific channel)

===5 FRET===
.mid encodes level as a pitch block within one track per instrument
lane N (0-4, GRBYO) sits at MID_PITCH_BASE[level] + N, open sits at MID_PITCH_BASE[level] - 1
A single linear scan of the track buckets each note_on into the right level by pitch

Note-based open notes (pitch == MID_PITCH_BASE[level] - 1) require an [ENHANCED_OPENS] text event

===DRUMS===
Same level MID_PITCH_BASE blocks and parsing scan, 2 note streams (hand/kick)
Hand lane N (4 or 5 lane) = base + n (1-5)
Kick lane 1x base, kick lane 2x = base - 1 (expert only)


"""

import pathlib

import mido
import numpy as np
import tqdm

from functions import instruments
from parsers.timing import tempo_map, ticks_to_ms

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

ENH_OPEN = 'ENHANCED_OPENS'

# Drum pitch -> (level_key, slot) where slot is 'kick', '2xkick', or a hand_mask bit index (0-4)
# 4 + 5 lane supported (5 lane is just an extra note)
DRUM_PITCH_TO_INFO = {}
for _level_key, _base in instruments.MID_PITCH_BASE.items():
    DRUM_PITCH_TO_INFO[_base] = (_level_key, 'kick')
    for _lane in range(1, 6):
        DRUM_PITCH_TO_INFO[_base + _lane] = (_level_key, _lane - 1)
DRUM_PITCH_TO_INFO[instruments.MID_PITCH_BASE['expert'] - 1] = ('expert', '2xkick')
del _level_key, _base, _lane


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

    return tempo_map(tempos, mid.ticks_per_beat)


# -----------------------
# Note-stream extraction
# -----------------------

# Extracts one instrument's note stream from its located track, split into per-EMHX-level lane masks from one scan
# Returns None if the track has no usable notes at any level
def _extract_track(track, instrument_key, to_ms_array):
    allow_opens = instruments.SUPPORTS_OPEN_NOTES[instrument_key]
    enhanced_opens = False

    masks_by_tick = {level_key: {} for level_key in instruments.LEVEL_KEYS}
    pending_opens = []   # (abs_tick, level_key) - applied only if ENHANCED_OPENS turns up
    abs_tick = 0

    for msg in track:
        abs_tick += msg.time

        if msg.type == 'note_on' and msg.velocity > 0:
            lane_info = LANE_PITCH_TO_INFO.get(msg.note)

            if lane_info is not None:
                level_key, lane = lane_info
                level_masks = masks_by_tick[level_key]
                level_masks[abs_tick] = level_masks.get(abs_tick, 0) | (1 << lane)

            elif allow_opens and msg.note in OPEN_PITCH_TO_LEVEL:
                # held until the track has been scanned for ENHANCED_OPENS
                # dropped if the marker is missing
                pending_opens.append((abs_tick, OPEN_PITCH_TO_LEVEL[msg.note]))

        elif msg.type == 'text' and ENH_OPEN in msg.text.upper():
            enhanced_opens = True

    # Note-based only if the track has ENHANCED_OPENS
    if allow_opens and enhanced_opens:
        for open_tick, level_key in pending_opens:
            level_masks = masks_by_tick[level_key]
            level_masks[open_tick] = level_masks.get(open_tick, 0) | (1 << OPEN_MID)

    levels_out = {}
    for level_key, level_masks in masks_by_tick.items():
        if not level_masks:
            continue

        ordered_ticks = sorted(level_masks)
        levels_out[level_key] = {
            'notes': {
                'time_ms': to_ms_array(ordered_ticks),
                'lanes': np.array([level_masks[t] for t in ordered_ticks], dtype=np.uint8),
            },
        }

    return levels_out or None


# DRUM NOTES
# One {tick: mask} dict -> a {'time_ms', 'lanes'} stream, empty arrays if the dict is empty
def _drum_stream(masks_by_tick, to_ms_array):
    if not masks_by_tick:
        return {
            'time_ms': np.empty(0, dtype=np.float64),
            'lanes': np.empty(0, dtype=np.uint8),
        }
    ordered_ticks = sorted(masks_by_tick)
    return {
        'time_ms': to_ms_array(ordered_ticks),
        'lanes': np.array([masks_by_tick[t] for t in ordered_ticks], dtype=np.uint8),
    }


# Drum equivalent of _extract_track, same scan with split to hands/kick
def _extract_drum_track(track, to_ms_array):
    hand_by_tick = {level_key: {} for level_key in instruments.LEVEL_KEYS}
    kick_by_tick = {level_key: {} for level_key in instruments.LEVEL_KEYS}
    abs_tick = 0

    for msg in track:
        abs_tick += msg.time

        if msg.type != 'note_on' or msg.velocity == 0:
            continue

        info = DRUM_PITCH_TO_INFO.get(msg.note)
        if info is None:
            continue

        level_key, slot = info
        if slot == 'kick':
            level_masks = kick_by_tick[level_key]
            level_masks[abs_tick] = level_masks.get(abs_tick, 0) | (1 << 0)
        elif slot == '2xkick':
            level_masks = kick_by_tick[level_key]
            level_masks[abs_tick] = level_masks.get(abs_tick, 0) | (1 << 1)
        else:  # slot is a hand_mask bit index (0-3)
            level_masks = hand_by_tick[level_key]
            level_masks[abs_tick] = level_masks.get(abs_tick, 0) | (1 << slot)

    levels_out = {}
    for level_key in instruments.LEVEL_KEYS:
        hand_masks = hand_by_tick[level_key]
        kick_masks = kick_by_tick[level_key]
        if not hand_masks and not kick_masks:
            continue
        levels_out[level_key] = {
            'notes': {
                'hand_mask': _drum_stream(hand_masks, to_ms_array),
                'kick_mask': _drum_stream(kick_masks, to_ms_array),
            },
        }

    return levels_out or None


def mid_notes(mid_source):
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
    tempo_arrs = map_mid_tempo(mid)

    def to_ms_array(ticks):
        return ticks_to_ms(ticks, tick_res, *tempo_arrs)

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

        levels = (
            _extract_drum_track(track, to_ms_array)
            if instrument_key == 'drums'
            else _extract_track(track, instrument_key, to_ms_array)
        )
        if levels is not None:
            instruments_out[instrument_key] = levels

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
def mid_loop(search_path, errors=None):
    mid_out = {}

    search = pathlib.Path(search_path)
    files = list(search.rglob("notes.mid"))

    for file in tqdm.tqdm(files, desc="Parsing midis", unit="file"):
        try:
            stream = mid_notes(file)
            mid_out[stream['song_path']] = stream
        except Exception as exc:
            if errors is not None:
                message = str(exc) or repr(exc)
                errors.append((str(file), type(exc).__name__, message))
            continue

    return mid_out
