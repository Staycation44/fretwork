"""
LABELS - human-facing display strings for the abbreviated column/metric keys

The short keys ('pNPS', 'medVPS', 'COV', 'DurationS') stay exactly as they are
everywhere in the data path - density.calc_metrics output, formula.calc_nvcov
output, the dataframes in analyze.py, and the xlsx headers. Nothing keyed off a
column name has to change. This module is the single place that maps one of
those keys to something a person can read, applied only at display time.

    COLUMN_LABELS  short label for a column header
    COLUMN_HELP    one-line explanation, for tooltips / hover text
    UI             interface strings for serve.py's page

Anything not in COLUMN_LABELS falls back to the raw key, so a new metric column
shows up readable-ish instead of blowing up - see label().

Formula terms are spelled out in Methodology.md; the help text here is the short
version of the same thing.
"""

# NPS/VPS get spelled out - "notes/sec" and "fret changes/sec" are what they
# actually measure, and that reads better than the acronym in a column header
COLUMN_LABELS = {
    # identity / metadata
    'Code':       'Code',
    'Song Title': 'Song',
    'Artist':     'Artist',
    'Level':      'Level',
    'Type':       'Part',
    'Charter':    'Charter',
    'Release':    'Source',
    'Official':   'Official',

    # shape of the chart
    'NoteCount':  'Notes',
    'DurationS':  'Length',

    # difficulty
    'Difficulty': 'Original Tier',
    'D':          'Difficulty (D)',
    'RemapDiff':  'Remap Tier',
    'CalcTier':   'Calc Tier',

    # note density
    'pNPS':       'Peak notes/sec',
    'aNPS':       'Avg notes/sec',
    'medNPS':     'Median notes/sec',
    'stdNPS':     'Std dev notes/sec',

    # fret variability
    'pVPS':       'Peak changes/sec',
    'aVPS':       'Avg changes/sec',
    'medVPS':     'Median changes/sec',
    'stdVPS':     'Std dev changes/sec',

    # formula components
    'N':          'Note factor (N)',
    'V':          'Variability factor (V)',
    'COV':        'Consistency (CoV)',
}

COLUMN_HELP = {
    'Code':       'Retrieval code: 8-digit song hash, then level (E/M/H/X) and instrument (G/C/R/B/K). Pass it to render.py.',
    'Song Title': 'Song name from song.ini.',
    'Artist':     'Artist from song.ini.',
    'Level':      'Charted difficulty level: Easy, Medium, Hard or Expert.',
    'Type':       'Which part this row is: Lead, Co-op, Rhythm, Bass or Keys.',
    'Charter':    'Who charted the song, from song.ini.',
    'Release':    'Release or source pack. Officials are matched against the tables in sources/.',
    'Official':   'True when the source pack is an official Guitar Hero or Rock Band release.',

    'NoteCount':  'Total notes in this chart. Frets played together count as one note, same as the games score it.',
    'DurationS':  'Time from t=0 to the last note.',

    'Difficulty': 'The diff_* tier already in song.ini. -1 means the tag is missing.',
    'D':          'Calculated difficulty, D = N x V x CoV. The main output. Higher is harder, uncapped.',
    'RemapDiff':  'D binned to 0-6, calibrated per instrument so the spread matches official tiers. From the Expert chart only.',
    'CalcTier':   'Log-scaled tier, one step per 0.44 increase in ln(D) above 7.6. Uncapped, so hard customs reach 10+. From the Expert chart only.',

    'pNPS':       'Busiest one-second window, in notes per second.',
    'aNPS':       'Notes per second across the whole chart, including rests.',
    'medNPS':     'Median one-second window. Resistant to a single spike.',
    'stdNPS':     'Spread of note density across the chart.',

    'pVPS':       'Busiest one-second window of fret movement.',
    'aVPS':       'Fret changes per second across the whole chart.',
    'medVPS':     'Median one-second window of fret movement.',
    'stdVPS':     'Spread of fret movement across the chart.',

    'N':          'Note-density term: cube root of median x average x peak notes/sec.',
    'V':          'Variability term: cube root of median x average x peak changes/sec.',
    'COV':        'Interaction term, 1 or higher. Rewards charts whose difficulty is uneven.',
}

# ---------------------------------------------------------------------
# "no data" sentinels
# ---------------------------------------------------------------------
# Difficulty's -1 has two origins that mean the same thing to a reader:
#   - the diff_* tag is absent, and ini_parser falls back to '-1'
#   - the tag is present but set to -1, which is the unrated convention
#     (the GH3 pack does this: every diff_* is -1 while diff_band is set)
# xlsx_format already treats -1 as blank for fill/color-scale purposes; this is
# the same idea for any human-facing surface.
MISSING_VALUES = {
    'Difficulty': (-1,),
}

MISSING_TEXT = '\u2014'  # em dash

MISSING_HELP = {
    'Difficulty': 'No difficulty rating in song.ini (diff_* is -1 or absent)',
    'RemapDiff':  'No Expert chart for this instrument to anchor the tier to',
    'CalcTier':   'No Expert chart for this instrument to anchor the tier to',
}


# True for None/NaN or a column's own "unrated" sentinel
def is_missing(column, value):
    if value is None:
        return True
    return value in MISSING_VALUES.get(column, ())


# columns holding a duration in seconds - shown as m:ss, still sorted as a number
TIME_COLUMNS = ('DurationS',)


def label(column):
    return COLUMN_LABELS.get(column, column)


def help_text(column):
    return COLUMN_HELP.get(column, '')


# interface strings for serve.py's page, kept here so the wording lives in one file
UI = {
    'title':            'Fretwork',
    'subtitle':         'library difficulty',
    'search':           'Filter by song, artist, charter or source...',
    'clear_one':        'Clear 1 filter',
    'clear_many':       'Clear {n} filters',
    'count':            '{shown} of {total} songs',
    'filter_tip':       'Filter this column',
    'sort_tip':         'Sort by this column',
    'code_tip':         'Click to see the difficulty graph, shift-click to copy the code',
    'select_all':       'Select all',
    'select_none':      'Clear',
    'value_search':     'Search values',
    'range_apply':      'Apply',
    'range_clear':      'Clear',
    'range_hint':       '{label} between min and max',
    'range_min':        'min {v}',
    'range_max':        'max {v}',
    'rendering':        'Rendering graph...',
    'render_failed':    'Could not render this chart. Is the matching cache loaded?',
    'copied':           'Copied {code}',
    'no_data':          'No songs match these filters.',

    # row / graph interaction
    'row_tip':          'Click for the difficulty graph',
    'copy_code_tip':    'Copy this code',
    'close_tip':        'Close (Esc)',

    # column chooser
    'columns':          'Columns',
    'columns_tip':      'Choose which columns to show',
    'columns_reset':    'Show all',
}
