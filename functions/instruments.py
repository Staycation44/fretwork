"""
INSTRUMENTS - Central definition of every supported instrument:
    - which .mid track name(s) map to it
    - which .chart section name maps to it, per level
    - which .mid pitch block maps to it, per level
    - which song.ini tag holds its (Expert-referenced) difficulty
    - the single-letter suffixes used in retrieval codes (level + instrument)
    - whether it supports open notes

Track/section names sourced from TheNathannator's GuitarGame_ChartFormats documentation

LEGACY FALLBACK: notes.chart's legacy 'SingleBass' is a fallback for bass

LEVELS (EMHX)
    - Both formats chart up to four levels per instrument - Easy, Medium, Hard, Expert.
    - .chart differentiates by section name prefix only (ExpertSingle)
    - .chart note numbering (0-4 fret, 7 open) is identical across all four sections
    - .mid differentiates by pitch block instead
    - .mid track names don't change per level

A given song may chart anywhere from 1 to all 4 levels for a given instrument

Legacy GH1/2-style open note encoding in .mid assumed Expert-only

DRUMS
Drums shares a lot with the 5-fret instruments:
- 'PART DRUMS' mid / [Level]'Drums' chart naming conventions
- same per-level .mid pitch block bases) -
Differences:
- Note-number decoding
- splitting note streams out to have hands and kick separated
"""

# canonical instrument keys, in a stable display/iteration order
INSTRUMENT_KEYS = ['guitar', 'coop', 'rhythm', 'bass', 'keys', 'drums']

DISPLAY_NAMES = {
    'guitar': 'Guitar',
    'coop':   'Co-op Guitar',
    'rhythm': 'Rhythm Guitar',
    'bass':   'Bass',
    'keys':   'Keys',
    'drums':  'Drums',
}

# canonical level keys, in a stable display/iteration order
LEVEL_KEYS = ['easy', 'medium', 'hard', 'expert']

# full-word label per level - used for the xlsx 'Level' column and render headers
# ("Expert Guitar", "Medium Bass", ...)
LEVEL_DISPLAY_NAMES = {
    'easy':   'Easy',
    'medium': 'Medium',
    'hard':   'Hard',
    'expert': 'Expert',
}

# .mid track name(s) per instrument - unaffected by level (pitch blocks)
# Guitar carries the GH1-era 'T1 GEMS' legacy fallback
MID_TRACK_NAMES = {
    'guitar': ['PART GUITAR', 'T1 GEMS'],
    'coop':   ['PART GUITAR COOP'],
    'rhythm': ['PART RHYTHM'],
    'bass':   ['PART BASS'],
    'keys':   ['PART KEYS'],
    'drums':  ['PART DRUMS'],
}

# .mid pitch block base per level, per TheNathannator's 5-Fret Guitar mid docs:
#   lane N (0-4, GRBYO) = base + N
#   open note           = base - 1
# Same block layout applies to every 5-fret instrument track (guitar/coop/rhythm/bass/keys).
# Drums reuses these same per-level bases
#   hand lanes N (1-5, supporting 4 and 5 lane) = base + N
#   kick 1x = base, kick 2x = base - 1 (expert only)
MID_PITCH_BASE = {
    'expert': 96,
    'hard':   84,
    'medium': 72,
    'easy':   60,
}

# .chart section base name per instrument (level prefix stripped) -
# Bass carries the 'SingleBass' legacy fallback, checked after 'DoubleBass' at every level
CHART_BASE_SECTIONS = {
    'guitar': ['Single'],
    'coop':   ['DoubleGuitar'],
    'rhythm': ['DoubleRhythm'],
    'bass':   ['DoubleBass', 'SingleBass'],
    'keys':   ['Keyboard'],
    'drums':  ['Drums'],
}

# .chart level-name prefix per level
CHART_LEVEL_PREFIX = {
    'expert': 'Expert',
    'hard':   'Hard',
    'medium': 'Medium',
    'easy':   'Easy',
}

# CHART_SECTIONS[instrument_key][level_key] -> ordered list of section names to try,
# e.g. CHART_SECTIONS['bass']['hard'] == ['HardDoubleBass', 'HardSingleBass']
CHART_SECTIONS = {
    instrument_key: {
        level_key: [f'{CHART_LEVEL_PREFIX[level_key]}{base}' for base in bases]
        for level_key in LEVEL_KEYS
    }
    for instrument_key, bases in CHART_BASE_SECTIONS.items()
}

# song.ini Difficulty tag per instrument - Expert-referenced only. 
# song.ini has no level based tag so assuming the Expert tiering as canonical
# RemapDiff/CalcTier reuse this against the Expert row's D for E/M/H tier display + write/restore
DIFF_TAGS = {
    'guitar': 'diff_guitar',
    'coop':   'diff_guitar_coop',
    'rhythm': 'diff_rhythm',
    'bass':   'diff_bass',
    'keys':   'diff_keys',
    'drums':  'diff_drums',
}

# instrument suffix for retrieval code,
CODE_SUFFIX = {
    'guitar': 'G',
    'coop':   'C',
    'rhythm': 'R',
    'bass':   'B',
    'keys':   'K',
    'drums':  'D',
}
SUFFIX_TO_INSTRUMENT = {suffix: key for key, suffix in CODE_SUFFIX.items()}

# level suffix for retrieval code
LEVEL_CODE_SUFFIX = {
    'easy':   'E',
    'medium': 'M',
    'hard':   'H',
    'expert': 'X',
}
SUFFIX_TO_LEVEL = {suffix: key for key, suffix in LEVEL_CODE_SUFFIX.items()}

# Keys has no mechanically reasonable open notes
# Drums has no open-note (kick replaces), defensive exclusion
SUPPORTS_OPEN_NOTES = {
    'guitar': True,
    'coop':   True,
    'rhythm': True,
    'bass':   True,
    'keys':   False,
    'drums':  False,
}

# analyze.py xlsx tab grouping by instrument
# EMHX is a filterable column within each tab not a separate tab
SHEET_GROUPS = {
    'Guitar': ['guitar', 'coop', 'rhythm'],
    'Bass':   ['bass'],
    'Keys':   ['keys'],
    'Drums':  ['drums'],
}

# per-row label for 'Type' column
TYPE_LABELS = {
    'guitar': 'Lead',
    'coop':   'Co-op',
    'rhythm': 'Rhythm',
    'bass':   'Bass',
    'keys':   'Keys',
    'drums':  'Drums',
}


# --------------------------------------------------------------------------
# Terminal reporting - shared by BUILD's cache summary and ANALYZE's row count
# --------------------------------------------------------------------------
# counts:     {instrument_key: {level_key: int}}
# levels:     which levels to show as columns
#             ANALYZE passes its XLSX_LEVELS selection here
# skip_empty: drop instrument rows with no counts in the shown levels
#             BUILD shows all, ANALYZE skips based on filters
def level_matrix(counts, levels=None, skip_empty=False):
    levels = list(levels) if levels is not None else list(LEVEL_KEYS)
    if not levels:
        return ''

    name_width = max(len(DISPLAY_NAMES[key]) for key in INSTRUMENT_KEYS)
    labels = [LEVEL_DISPLAY_NAMES[level] for level in levels]
    col_width = max(max(len(label) for label in labels), 5) + 2

    lines = [" " * (name_width + 4) + "".join(label.rjust(col_width) for label in labels)]

    for instrument_key in INSTRUMENT_KEYS:
        row = counts[instrument_key]
        if skip_empty and not any(row[level] for level in levels):
            continue
        lines.append(
            f"    {DISPLAY_NAMES[instrument_key]:<{name_width}}"
            + "".join(str(row[level]).rjust(col_width) for level in levels)
        )

    return "\n".join(lines)
