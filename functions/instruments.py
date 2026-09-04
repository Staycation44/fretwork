"""
INSTRUMENTS - Central definition of every supported instrument:
    - which .mid track name(s) map to it
    - which .chart section name maps to it
    - which song.ini difficulty tag holds its difficulty
    - the single-letter suffix used in retrieval codes
    - whether it supports open notes

Every other module (mid_parser, chart_parser, cache, ini_parser, ini_updater, formula,
build, analyze, render) reads from here rather than hardcoding instrument-specific
strings, so adding/renaming an instrument later is a one-file change.

Track/section names sourced from TheNathannator's GuitarGame_ChartFormats documentation

LEGACY FALLBACK: notes.chart's legacy 'SingleBass' is a fallback for bass when the modern 'DoubleBass' section is missing
"""

# canonical instrument keys, in a stable display/iteration order
INSTRUMENT_KEYS = ['guitar', 'coop', 'rhythm', 'bass', 'keys']

DISPLAY_NAMES = {
    'guitar': 'Guitar',
    'coop':   'Co-op Guitar',
    'rhythm': 'Rhythm Guitar',
    'bass':   'Bass',
    'keys':   'Keys',
}

# .mid track name(s) per instrument
# Guitar carries the GH1-era 'T1 GEMS' legacy fallback
MID_TRACK_NAMES = {
    'guitar': ['PART GUITAR', 'T1 GEMS'],
    'coop':   ['PART GUITAR COOP'],
    'rhythm': ['PART RHYTHM'],
    'bass':   ['PART BASS'],
    'keys':   ['PART KEYS'],
}

# .chart difficulty-section name(s) per instrument 
# Bass carries the 'SingleBass' legacy fallback
CHART_SECTIONS = {
    'guitar': ['ExpertSingle'],
    'coop':   ['ExpertDoubleGuitar'],
    'rhythm': ['ExpertDoubleRhythm'],
    'bass':   ['ExpertDoubleBass', 'ExpertSingleBass'],
    'keys':   ['ExpertKeyboard'],
}

# song.ini difficulty tag per instrument
DIFF_TAGS = {
    'guitar': 'diff_guitar',
    'coop':   'diff_guitar_coop',
    'rhythm': 'diff_rhythm',
    'bass':   'diff_bass',
    'keys':   'diff_keys',
}

# single-letter suffix appended to 8-digit song hash for retrieval code,
# e.g. song code '04821993' + bass -> '04821993B'
CODE_SUFFIX = {
    'guitar': 'G',
    'coop':   'C',
    'rhythm': 'R',
    'bass':   'B',
    'keys':   'K',
}
SUFFIX_TO_INSTRUMENT = {suffix: key for key, suffix in CODE_SUFFIX.items()}

# Keys has no mechanically-sensible open note (the source game never supported one on this
# track) - open-note handling is skipped entirely for it in both parsers.
SUPPORTS_OPEN_NOTES = {
    'guitar': True,
    'coop':   True,
    'rhythm': True,
    'bass':   True,
    'keys':   False,
}

# analyze.py xlsx tab grouping.
SHEET_GROUPS = {
    'Guitar': ['guitar', 'coop', 'rhythm'],
    'Bass':   ['bass'],
    'Keys':   ['keys'],
}

# per-row label for 'Type' column
TYPE_LABELS = {
    'guitar': 'Lead',
    'coop':   'Co-op',
    'rhythm': 'Rhythm',
    'bass':   'Bass',
    'keys':   'Keys',
}
