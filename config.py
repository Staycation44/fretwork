"""
CONFIG - Where to look for songs, what to name outputs - render colors and some other settings
 
HEADER is a run identifier (based on a library folder) 
Outputs from build or analyze produces are named:
    {header}_{kind}_{timestamp}.{ext}

A header of "FullTest" gives you:
    FullTest_cache_08052026-0330.pkl, - from Build
    FullTest_errors_08052026-0330.csv, - from Build (with errors)
    FullTest_metrics_08052026-0330.csv, - from Analyze

changing the header here also defines the cache Analyze will calculate from or
which cache Render will use for visualization retrieval codes (overridable with args)
"""

import pathlib
from datetime import datetime

# ------
# Paths - EDIT THESE FIRST BEFORE RUNNING ANYTHING
# ------

# Library to scan. set here or override on the command line with --search-path.
SEARCH_PATH = r"C:\Users\reyd0\Documents\Clone Hero\PlayerData\Songs" # edit to your library path before running Build

# Identifies this run. Overridable with --header.
HEADER = "MainCache" # edit to title your cache before running Build/Analyze/Render

#------------------------------
# RENDER output directory - DON'T NEED TO EDIT, these dump to the tool's folder
RENDER_DIR = 'renders'

# fix for cache/metrics folders 
OUTPUT_DIR = '.'
CACHE_DIR = 'caches'
METRICS_DIR = 'metrics'

KIND_DIRS = {
    'cache': CACHE_DIR,
    'errors': CACHE_DIR,
    'metrics': METRICS_DIR,
}


# ----------------
# Render settings - Edit to select theme, change colors, etc
# ----------------
# Light/dark themes change background/text/solo colors - selected via 'mode' in DEFAULTS
# the accent palette (color_d, color_nps, color_vps, color_star_power) stay in DEFAULTS and is shared
# read by plot.py

RENDER_THEMES = {
    "light": {
        "figure_bg": "#FFFFFF",
        "axes_bg": "#FFFFFF",
        "text_color": "#1A1A1A",
        "muted_text_color": "#555555",
        "grid_color": "#000000",
        "spine_color": "#333333",
        "color_solo": "#9A9A9A",
    },
    "dark": {
        "figure_bg": "#1E1E1E",
        "axes_bg": "#1E1E1E",
        "text_color": "#EAEAEA",
        "muted_text_color": "#AAAAAA",
        "grid_color": "#FFFFFF",
        "spine_color": "#CCCCCC",
        "color_solo": "#000000", #previously #3A3A3A
    },
}
 
RENDER_DEFAULT = {
    "figsize": [16.0, 7.0],
    "dpi": 120,
 
    "mode": "dark",   # "light" or "dark" - causes plot to use selected values from RENDER_THEMES
 
    "color_d": "#B71FB7",
    "color_nps": "#127BC1",
    "color_vps": "#DD6C1B",
 
    "color_star_power": "#66A6EA",
    "span_alpha": 0.22,
 
    "linewidth": 1.5,
    "grid_alpha": 0.25,
    "title_size": 13,
    "label_size": 10,
    "tick_size": 9,
 
    "fill_curves": True,
    "fill_alpha": 0.12,

    "show_solo_spans": True,
    "show_star_power_spans": False,
}

# --------------------------
# Timestamped output naming - DON'T EDIT - these are to untangle cache files...
# --------------------------

# Short generation stamp: MMDDYYYY-HHMM
def timestamp():
    return datetime.now().strftime("%m%d%Y-%H%M")

# determine where to put files (render already does this on it's own)
def _resolve_out_dir(kind, out_dir):
    if out_dir is not None:
        return pathlib.Path(out_dir)
    return pathlib.Path(OUTPUT_DIR) / KIND_DIRS.get(kind, '')

# {header}_{kind}_{timestamp}.{ext}
def output_path(kind, header=None, ts=None, ext='csv', out_dir=None):
    header = header or globals()['HEADER']
    ts = ts or timestamp()
    out_dir = _resolve_out_dir(kind, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{header}_{kind}_{ts}.{ext}"

TS_FORMAT = "%m%d%Y-%H%M"

def file_ts(path, kind, header):
    try:
        ts = ext_ts(path, kind, header)
        return datetime.strptime(ts, TS_FORMAT)
    except ValueError:
        return datetime.min


def latest_output(kind, header=None, out_dir=None, ext='pkl'):
    header = header or globals()['HEADER']
    out_dir = _resolve_out_dir(kind, out_dir)
    matches = list(out_dir.glob(f"{header}_{kind}_*.{ext}"))
    if not matches:
        raise FileNotFoundError(
            f"No {kind} file for header '{header}' in {out_dir} "
            f"(looked for {header}_{kind}_*.{ext})"
        )
    return max(matches, key=lambda p: file_ts(p, kind, header))


def ext_ts(path, kind, header=None):
    header = header or globals()['HEADER']
    stem = pathlib.Path(path).stem
    prefix = f"{header}_{kind}_"
    if not stem.startswith(prefix):
        raise ValueError(f"{path} doesn't match expected pattern {prefix}<timestamp>")
    return stem[len(prefix):]