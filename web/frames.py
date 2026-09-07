"""
FRAMES - reads a metrics .xlsx into JSON-safe rows

The only module here that imports pandas.
"""

import json
import pathlib

import pandas as pd

from functions import timestamp


def load_frames(header, xlsx_path=None):
    if xlsx_path is None:
        xlsx_path = timestamp.latest_output('metrics', header, ext='xlsx')
    xlsx_path = pathlib.Path(xlsx_path)
    return xlsx_path, pd.read_excel(xlsx_path, sheet_name=None)


# to_json is the round trip that turns NaN into null and numpy scalars into
# plain numbers; df.values.tolist() would emit bare NaN and invalid JSON.
def frames_payload(frames):
    return {
        name: {
            'columns': list(df.columns),
            'rows': json.loads(df.to_json(orient='values')),
        }
        for name, df in frames.items()
    }
