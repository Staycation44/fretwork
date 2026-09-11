"""
CHART_PARSER - Parses notes.chart files into per-instrument, per-level note streams:
    {
        'song_path': str,
        'source_format': 'chart',
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
            ...  # one entry per recognized instrument actually present in the file
        },
    }

    Drums' 'notes' shape is different - two independent per-tick streams instead
    of one 'lanes' bitmask (see DRUM ENCODING below):
        'notes': {
            'hand_mask': {'time_ms': np.ndarray, 'lanes': np.ndarray uint8},
            'kick_mask': {'time_ms': np.ndarray, 'lanes': np.ndarray uint8},
        }

EMHX: .chart differentiates level purely by section-name prefix
note numbering (0-4 fret, 7 open) is identical across all four potential sections

parse_chart() already read every section in the file (woohoo inefficiency!), so almost no added cost

===5 FRET===
guitar/coop/rhythm/bass/keys encoding
    One uint8 per tick. Bit N set means fret N is played:
    bits 0-4 are GRBYO, bit 7 is open
    bits 5-6 are unused (at this time) - in .chart those are the tap and force-flip modifiers

===DRUM===
same section/event logic as 5 fret w/ different note numbers, split hands/kick streams
    bits 1-5 are hand lanes (hand mask 0-4, supporting both 4 + 5 lane)
    bit 0 is 1x kick, bit 32 is 2x kick (expert only)

NOTE STATE IS NOT PARSED - strum/tap/hopo are not used in the calcs and are discarded

DROPPED: star power ('S 2') and solo ('E solo') events are skipped
"""

import concurrent.futures as cf
import os
import pathlib

import numpy as np
import tqdm

from functions import instruments
from parsers.timing import tempo_map, ticks_to_ms

# ------------------------
# Chart-specific constants
# ------------------------
# 5 fret note numbers
OPEN_NOTE = 7
NOTE_FRETS = {0, 1, 2, 3, 4, OPEN_NOTE}

# Drum note numbers
DRUM_KICK_NOTE = 0
DRUM_2X_KICK_NOTE = 32
DRUM_HAND_NOTES = {1, 2, 3, 4, 5}

# Roll lane special phrase types: S <type> <length> 
# can't overcount these because of the charted notes vs actual implication for difficulty
DRUM_ROLL_TYPE_TO_KIND = {65: 'single', 66: 'double'}

# ---------------------------------------------------------------------
# Raw section parsing (chart's [Section] / key = value text format)
# ---------------------------------------------------------------------

def parse_chart(chart_source):
    c_dict = {}
    c_sect = None

    with open(chart_source, encoding='utf-8-sig') as c_data:
        for line in c_data:
            line = line.strip()

            if line.startswith('[') and line.endswith(']'):
                c_sect = line[1:-1]
                c_dict[c_sect] = {}

            elif ' = ' in line and c_sect is not None:
                key, value = line.split(' = ', 1)
                key = key.strip()
                value = value.strip()

                if key in c_dict[c_sect]:
                    if not isinstance(c_dict[c_sect][key], list):
                        c_dict[c_sect][key] = [c_dict[c_sect][key]]
                    c_dict[c_sect][key].append(value)
                else:
                    c_dict[c_sect][key] = value

    # Global [Events] holds section names / lyrics - nothing used from this section
    c_dict.pop('Events', None)
    return c_dict

# SyncTrack 'B <bpm*1000>' markers -> tempo arrays for tick -> ms conversion
def build_tempo_map(sync_track, tick_res):
    tempos = {}
    for tick, markers in sync_track.items():
        tick = int(tick)
        markers = markers if isinstance(markers, list) else [markers]
        for marker in markers:
            if marker.startswith('B'):
                tempos[tick] = int(marker.split()[1]) / 1000

    if not tempos:
        tempos[0] = 120.0

    return tempo_map(tempos, tick_res)


# ----------------------
# Note-stream extraction
# ----------------------

# Extracts one instrument/level's note stream from its already-parsed section
# Shared scan logic across every 5-fret instrument and every level
# note numbering (0-4/7) doesn't change per level
# Returns None if the section has no usable notes
def _extract_section(section, instrument_key, to_ms_array):
    allow_opens = instruments.SUPPORTS_OPEN_NOTES[instrument_key]
    note_frets = NOTE_FRETS if allow_opens else (NOTE_FRETS - {OPEN_NOTE})

    masks_by_tick = {}

    for tick_str, events in section.items():
        events = events if isinstance(events, list) else [events]

        mask = 0
        for event in events:
            parts = event.split()
            # 'N <fret> <length>' - everything else is skipped
            if len(parts) >= 2 and parts[0] == 'N':
                n_val = int(parts[1])
                if n_val in note_frets:
                    mask |= 1 << n_val

        if mask:  # skip ticks that only carried modifiers or phrases
            masks_by_tick[int(tick_str)] = mask

    if not masks_by_tick:
        return None

    ordered_ticks = sorted(masks_by_tick)

    return {
        'notes': {
            'time_ms': to_ms_array(ordered_ticks),
            'lanes': np.array([masks_by_tick[t] for t in ordered_ticks], dtype=np.uint8),
        },
    }


#---------------
# DRUM STUFF
#---------------

# Drum prep
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


# Drum equivalent of _extract_section, splits hands/kick
def _extract_drum_section(section, to_ms_array):
    hand_by_tick = {}
    kick_by_tick = {}

    for tick_str, events in section.items():
        events = events if isinstance(events, list) else [events]

        hand_mask = 0
        kick_mask = 0
        for event in events:
            parts = event.split()
            if len(parts) >= 2 and parts[0] == 'N':
                n_val = int(parts[1])
                if n_val in DRUM_HAND_NOTES:
                    hand_mask |= 1 << (n_val - 1)
                elif n_val == DRUM_KICK_NOTE:
                    kick_mask |= 1 << 0
                elif n_val == DRUM_2X_KICK_NOTE:
                    kick_mask |= 1 << 1

        if hand_mask or kick_mask:  # skip ticks that only carried modifiers/unrecognized notes
            tick = int(tick_str)
            if hand_mask:
                hand_by_tick[tick] = hand_mask
            if kick_mask:
                kick_by_tick[tick] = kick_mask

    if not hand_by_tick and not kick_by_tick:
        return None

    return {
        'notes': {
            'hand_mask': _drum_stream(hand_by_tick, to_ms_array),
            'kick_mask': _drum_stream(kick_by_tick, to_ms_array),
        },
    }


# Scans difficulty section for roll-lane spans - called per level
def _extract_roll_spans(section, to_ms_array):
    starts, ends, kinds = [], [], []
    for tick_str, events in section.items():
        events = events if isinstance(events, list) else [events]
        for event in events:
            parts = event.split()
            # S <type> <length>, only roll-lane types are kept
            if len(parts) >= 3 and parts[0] == 'S':
                kind = DRUM_ROLL_TYPE_TO_KIND.get(int(parts[1]))
                if kind is not None:
                    start_tick = int(tick_str)
                    starts.append(start_tick)
                    ends.append(start_tick + int(parts[2]))
                    kinds.append(kind)

    if not starts:
        return []

    start_ms = to_ms_array(starts)
    end_ms = to_ms_array(ends)
    return sorted(zip(start_ms.tolist(), end_ms.tolist(), kinds))


def chart_notes(chart_source):
    c_dict = parse_chart(chart_source)
    for required in ('Song', 'SyncTrack'):
        if required not in c_dict:
            raise ValueError(f"Missing required section '{required}' in {chart_source}")

    tick_res = int(c_dict['Song']['Resolution'])
    tempo_arrs = build_tempo_map(c_dict['SyncTrack'], tick_res)

    def to_ms_array(ticks):
        return ticks_to_ms(ticks, tick_res, *tempo_arrs)

    instruments_out = {}
    roll_spans_out = {}
    for instrument_key in instruments.INSTRUMENT_KEYS:
        levels_out = {}
        drum_roll_spans = {} if instrument_key == 'drums' else None

        for level_key in instruments.LEVEL_KEYS:
            section = None
            for section_name in instruments.CHART_SECTIONS[instrument_key][level_key]:
                section = c_dict.get(section_name)
                if section:
                    break

            if not section:
                continue  # this instrument/level combo isn't in the file

            stream = (
                _extract_drum_section(section, to_ms_array)
                if instrument_key == 'drums'
                else _extract_section(section, instrument_key, to_ms_array)
            )
            if stream is not None:
                levels_out[level_key] = stream
                if drum_roll_spans is not None:
                    spans = _extract_roll_spans(section, to_ms_array)
                    if spans:
                        drum_roll_spans[level_key] = spans

        if levels_out:
            instruments_out[instrument_key] = levels_out
            if drum_roll_spans:
                roll_spans_out['drums'] = drum_roll_spans

    if not instruments_out:
        raise ValueError(f"No recognized instrument section with usable notes found in {chart_source}")

    return {
        'song_path': str(pathlib.Path(chart_source).parent.resolve()),
        'source_format': 'chart',
        'resolution': tick_res,
        'instruments': instruments_out,
        'roll_spans': roll_spans_out,
    }


# -----------
# Search loop - also parallel just for fun since it's the same
# -----------

# worker for chart_loop's process pool
def _chart_notes_worker(file):
    try:
        return chart_notes(file), None
    except Exception as exc:
        return None, (str(file), type(exc).__name__, str(exc) or repr(exc))


# max_workers=None -> leave one core free (uncapped maxes out CPU lol)
def _resolve_workers(max_workers):
    if max_workers is not None:
        return max(1, int(max_workers))
    return max(1, (os.cpu_count() or 1) - 1)


# loops through path and reports errors for unparseable files
def chart_loop(search_path, errors=None, max_workers=None):
    chart_out = {}

    search = pathlib.Path(search_path)
    files = list(search.rglob("notes.chart"))

    if not files:
        return chart_out

    workers = _resolve_workers(max_workers)
    chunksize = max(1, len(files) // (workers * 4))

    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_chart_notes_worker, files, chunksize=chunksize)
        for stream, error in tqdm.tqdm(results, total=len(files), desc="Parsing charts", unit="file"):
            if stream is not None:
                chart_out[stream['song_path']] = stream
            elif errors is not None:
                errors.append(error)

    return chart_out
