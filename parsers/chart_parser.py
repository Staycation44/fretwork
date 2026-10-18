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

===5 FRET===
guitar/coop/rhythm/bass/keys encoding
    One uint8 per tick. Bit N set means fret N is played:
    bits 0-4 are GRBYO, bit 7 is open
    bits 5-6 are unused (at this time) - in .chart those are the tap and force-flip modifiers

===DRUM===
same section/event logic as 5 fret w/ different note numbers, split hands/kick streams
    notes 1-5 are hand lanes (hand mask bits 0-4, supporting both 4 + 5 lane)
    note 0 is 1x kick (kick mask bit 0), note 32 is 2x kick (kick mask bit 1, expert only)

NOTE STATE IS NOT PARSED - strum/tap/hopo are not used in the calcs and are discarded

DROPPED: star power ('S 2') and solo ('E solo') events are skipped
"""

import pathlib

from functions import instruments
from parsers import pool, text_decode, timing

# ------------------------
# Chart-specific constants
# ------------------------
# 5 fret note numbers -> lane mask bit
OPEN_NOTE = 7
NOTE_TO_BIT = {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, OPEN_NOTE: instruments.OPEN_BIT}

# Drum note numbers
DRUM_KICK_NOTE = 0
DRUM_2X_KICK_NOTE = 32
DRUM_HAND_NOTES = {1, 2, 3, 4, 5}

# Roll lane special phrase types: S <type> <length>
# can't overcount these because of the charted notes vs actual implication for difficulty
DRUM_ROLL_TYPE_TO_KIND = {65: 'single', 66: 'double'}

# .chart format default
DEFAULT_RESOLUTION = 192

# ---------------------------------------------------------------------
# Raw section parsing (chart's [Section] / key = value text format)
# ---------------------------------------------------------------------

# Parses already-decoded .chart text
def parse_chart_text(text):
    c_dict = {}
    c_sect = None

    for line in text.splitlines():
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


# SyncTrack 'B <bpm*1000>' markers -> raw {tick: bpm}
# zero/invalid markers are dropped and logged by timing.converter
def _chart_tempos(sync_track):
    tempos = {}
    for tick, markers in sync_track.items():
        markers = markers if isinstance(markers, list) else [markers]
        for marker in markers:
            if marker.startswith('B'):
                tempos[int(tick)] = int(marker.split()[1]) / 1000
    return tempos


# ----------------------
# Note-stream extraction
# ----------------------

# Extracts one instrument/level's note stream from its already-parsed section
# Shared scan logic across every 5-fret instrument and every level
# note numbering (0-4/7) doesn't change per level
# Returns None if the section has no usable notes
def _extract_section(section, instrument_key, to_ms_array):
    allow_opens = instruments.SUPPORTS_OPEN_NOTES[instrument_key]

    masks_by_tick = {}

    for tick_str, events in section.items():
        events = events if isinstance(events, list) else [events]

        mask = 0
        for event in events:
            parts = event.split()
            # 'N <fret> <length>' - everything else is skipped
            if len(parts) >= 2 and parts[0] == 'N':
                n_val = int(parts[1])
                if n_val in NOTE_TO_BIT and (allow_opens or n_val != OPEN_NOTE):
                    mask |= 1 << NOTE_TO_BIT[n_val]

        if mask:  # skip ticks that only carried modifiers or phrases
            masks_by_tick[int(tick_str)] = mask

    if not masks_by_tick:
        return None
    return {'notes': timing.masks_to_stream(masks_by_tick, to_ms_array)}


#---------------
# DRUM STUFF
#---------------

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
            'hand_mask': timing.masks_to_stream(hand_by_tick, to_ms_array),
            'kick_mask': timing.masks_to_stream(kick_by_tick, to_ms_array),
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


# [Song] Resolution -> (ticks per beat, warning or None)
# missing / non-numeric / non-positive fallback to 192
def _chart_resolution(song_section):
    raw = song_section.get('Resolution')
    if isinstance(raw, list):
        raw = raw[-1]  # duplicated key - last one wins, same as the ini parser
    if raw is None:
        return DEFAULT_RESOLUTION, f"no Resolution in [Song], assumed {DEFAULT_RESOLUTION}"
    try:
        res = int(float(raw.strip().strip('"')))
    except (ValueError, OverflowError):  # non-numeric, nan, inf
        res = 0
    if res <= 0:
        return DEFAULT_RESOLUTION, f"invalid Resolution {raw!r} in [Song], assumed {DEFAULT_RESOLUTION}"
    return res, None


# Core extraction over an already-parsed chart dict - shared by chart_notes() (notes.chart on
# disk) and chart_notes_from_text() (a chart embedded in a container).
def _chart_notes_from_dict(c_dict, song_path, warn_label=None):
    warn_label = warn_label if warn_label is not None else song_path

    for required in ('Song', 'SyncTrack'):
        if required not in c_dict:
            raise ValueError(f"Missing required section '{required}' in {warn_label}")

    tick_res, res_warning = _chart_resolution(c_dict['Song'])
    to_ms_array, warnings = timing.converter(_chart_tempos(c_dict['SyncTrack']), tick_res, warn_label)
    if res_warning:
        warnings.append((warn_label, 'InvalidResolution', res_warning))

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
        raise ValueError(f"No recognized instrument section with usable notes found in {warn_label}")

    return {
        'song_path': song_path,
        'source_format': 'chart',
        'resolution': tick_res,
        'instruments': instruments_out,
        'roll_spans': roll_spans_out,
        'warnings': warnings,  # popped into the build errors CSV by chart_loop
    }


# notes.chart on disk, decoded the same way as song.ini (utf-8 / utf-16 BOM / cp1252 fallback)
def chart_notes(chart_source):
    c_dict = parse_chart_text(text_decode.read_text(chart_source))
    song_path = str(pathlib.Path(chart_source).parent.resolve())
    return _chart_notes_from_dict(c_dict, song_path, warn_label=str(chart_source))


# Same as chart_notes(), for chart text already decoded from a container (.sng).
# song_path is the container's own identity.
def chart_notes_from_text(text, song_path, warn_label=None):
    c_dict = parse_chart_text(text)
    return _chart_notes_from_dict(c_dict, song_path, warn_label=warn_label)


# -----------
# Search loop - also parallel just for fun since it's the same
# -----------

# worker for chart_loop's process pool
def _chart_notes_worker(file):
    try:
        return chart_notes(file), None
    except Exception as exc:
        return None, pool.error_row(file, exc)


# notes.chart files -> {song_path: stream}, errors appended to errors
def chart_loop(files, errors=None, max_workers=None):
    results = pool.run_parallel(_chart_notes_worker, files, "Parsing charts", "file", max_workers)
    return pool.collect_streams(results, errors)
