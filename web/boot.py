"""
BOOT - assembles the JSON payload the page's JavaScript reads on load

Delivered as one <script type="application/json"> island rather than inlined
into the script, so spreadsheet text can never be parsed as code.
"""

import json

from functions import labels as labels_mod

# Mirrors xlsx_format.SCALED_COLS. Kept local on purpose: importing that module
# would pull openpyxl onto the server's startup path to save four strings.
SCALED_COLS = ['Difficulty', 'D', 'RemapDiff', 'CalcTier']


def boot_payload(frames_data):
    return {
        'data': frames_data,
        'scaled': SCALED_COLS,
        'labels': labels_mod.COLUMN_LABELS,
        'help': labels_mod.COLUMN_HELP,
        'ui': labels_mod.UI,
        'timecols': list(labels_mod.TIME_COLUMNS),
        'missing': {k: list(v) for k, v in labels_mod.MISSING_VALUES.items()},
        'missText': labels_mod.MISSING_TEXT,
        'missHelp': labels_mod.MISSING_HELP,
    }


# Escaping every "<" keeps spreadsheet text from closing the script tag or
# entering its double-escaped state. A valid JSON escape, parsed back unchanged.
def boot_json(frames_data):
    return json.dumps(boot_payload(frames_data)).replace('<', '\\u003c')
