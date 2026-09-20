"""
VOCAL_PARSER - Extracts PART VOCALS into note/talkie/percussion streams for the cache

_extract_vocal_track(track, to_ms_array) returns
    {'expert': {'notes': {...}, 'talkie': {...}, 'percussion': {...}}}
    or None if the track has no sung notes, talkie onsets, or percussion hits

All other instruments use EMHX levels, so vocals is treated as Expert for downstream handling

THREE SEPARATE STREAMS:
    'notes'      - sung, pitched, non-talkie: time_ms / end_ms / pitch / is_placeholder / is_slide
                   is_placeholder: lyric is '+$' (split-hold filler, not a new syllable)
                   is_slide:       lyric is '+' (pitch glide from the previous note, not a new syllable)

    'talkie'     - every rap/talkie/spoken hit: time_ms / end_ms. Two authoring styles:
                   - a normally-pitched note whose lyric ends in '#' / '^' / '*' (RB style)
                   - a lyric event with no note under it (GH style)
                   vocal_density ignores end_ms and gives every talkie a fixed length

    'percussion' - note 96 taps: time_ms / end_ms

Lyric checks ignore trailing join/format marks ('-', '=', '/', '%')

Sung notes + talkies are the note count and feed D
percussion is kept for render only

Discarded: 0/1 range-shift, 97 non-playable percussion, 105 phrase markers, 106 versus tag
+ 116 overdrive, and any other unrecognized note value (animation/venue cues)
"""

import numpy as np

PITCH_LOW, PITCH_HIGH = 36, 84
PERC_PLAYABLE = 96

TALKIE_SUFFIXES = ('#', '^', '*')
PLACEHOLDER_LYRIC = '+$'
SLIDE_LYRIC = '+'

# trailing marks that format syllables
LYRIC_FORMAT_MARKS = '-=/%'

# Used to cut off notes that are left on at track end (defensive)
TRACK_END_CLOSE_MS = 500.0


def _is_kept(note):
    return PITCH_LOW <= note <= PITCH_HIGH or note == PERC_PLAYABLE


# lyric with format marks removed
def _lyric_base(text):
    return None if text is None else text.rstrip(LYRIC_FORMAT_MARKS)


def _extract_vocal_track(track, to_ms_array):
    # One chronological scan of the mido messages
    open_by_note = {}
    pitched_pairs = []
    perc_pairs = []
    lyric_events = []
    end_tick = 0

    abs_tick = 0
    for msg in track:
        abs_tick += msg.time
        end_tick = abs_tick

        if msg.type == 'note_on' and msg.velocity > 0:
            if _is_kept(msg.note):
                open_by_note.setdefault(msg.note, []).append(abs_tick)
        elif msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0):
            starts = open_by_note.get(msg.note) if _is_kept(msg.note) else None
            if not starts:
                continue  # stray note-off with nothing open
            start_tick = starts.pop(0)
            if msg.note == PERC_PLAYABLE:
                perc_pairs.append([start_tick, abs_tick])
            else:
                pitched_pairs.append([start_tick, abs_tick, msg.note])
        elif msg.type == 'lyrics':
            lyric_events.append((abs_tick, msg.text))
        # text/animation events ([idle]/[intense]/etc.) ignored

    # notes left on near the end of the track are closed at track end (defensive)
    dangling = [(note, start) for note, starts in open_by_note.items() for start in starts]
    if dangling:
        start_ms_all = to_ms_array([start for _note, start in dangling])
        end_tick_ms = to_ms_array([end_tick])[0]
        for (note, start_tick), start_ms in zip(dangling, start_ms_all):
            if end_tick_ms - start_ms > TRACK_END_CLOSE_MS:
                continue
            if note == PERC_PLAYABLE:
                perc_pairs.append([start_tick, end_tick])
            else:
                pitched_pairs.append([start_tick, end_tick, note])

    pitched_pairs.sort(key=lambda p: p[0])
    perc_pairs.sort(key=lambda p: p[0])

    # Lyric resolution
    # - split pitched notes into sung vs. talkie by lyric suffix
    # - tag '+$' placeholders and '+' slides on sung notes
    # - lyric events with no note under them become talkie hits (no authored length)
    lyric_by_tick = {}
    for tick, text in sorted(lyric_events, key=lambda e: e[0]):
        lyric_by_tick.setdefault(tick, text)

    sung_pairs = []
    talkie_pairs = []
    for start_tick, end_tick_pair, note in pitched_pairs:
        base = _lyric_base(lyric_by_tick.get(start_tick))
        if base is not None and base.endswith(TALKIE_SUFFIXES):
            talkie_pairs.append([start_tick, end_tick_pair])
        else:
            sung_pairs.append([
                start_tick, end_tick_pair, note,
                base == PLACEHOLDER_LYRIC,
                base == SLIDE_LYRIC,
            ])

    note_ticks = {start_tick for start_tick, _e, _n in pitched_pairs}
    for tick, text in lyric_by_tick.items():
        if tick in note_ticks:
            continue
        base = _lyric_base(text)
        if base and base not in (SLIDE_LYRIC, PLACEHOLDER_LYRIC):
            talkie_pairs.append([tick, None])
    talkie_pairs.sort(key=lambda p: p[0])

    # GH-style talkies carry no length
    talkie_starts = [p[0] for p in talkie_pairs]
    talkie_has_end = np.array([p[1] is not None for p in talkie_pairs], dtype=bool)
    talkie_end_ms = np.full(len(talkie_pairs), np.nan, dtype=np.float64)
    if talkie_has_end.any():
        talkie_end_ms[talkie_has_end] = to_ms_array([p[1] for p in talkie_pairs if p[1] is not None])

    if not sung_pairs and not talkie_pairs and not perc_pairs:
        return None

    return {
        'expert': {
            'notes': {
                'time_ms': to_ms_array([p[0] for p in sung_pairs]),
                'end_ms': to_ms_array([p[1] for p in sung_pairs]),
                'pitch': np.array([p[2] for p in sung_pairs], dtype=np.uint8),
                'is_placeholder': np.array([p[3] for p in sung_pairs], dtype=bool),
                'is_slide': np.array([p[4] for p in sung_pairs], dtype=bool),
            },
            'talkie': {
                'time_ms': to_ms_array(talkie_starts),
                'end_ms': talkie_end_ms,
            },
            'percussion': {
                'time_ms': to_ms_array([p[0] for p in perc_pairs]),
                'end_ms': to_ms_array([p[1] for p in perc_pairs]),
            },
        }
    }
