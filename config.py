"""
CONFIG - Where to look for songs, what to name outputs - render colors and some other settings
 
HEADER is the run identifier (based on a library folder) 
Outputs from build or analyze produces are named:
    {header}_{kind}_{timestamp}.{ext}

A header of "FullTest" gives you:
    FullTest_cache_08052026-0330.pkl, - from Build
    FullTest_errors_08052026-0330.csv, - from Build (with errors)
    FullTest_metrics_08052026-0330.xlsx, - from Analyze
    FullTest_BackupData.csv - from Build (for difficulty editing)

changing the header here also defines the cache Analyze will calculate from 
AND which cache Render will use for visualization retrieval codes (overridable with args)
AND which backup file Analyze will use to restore song.ini diff_guitar values (overridable with args)
"""

# ------
# Paths - EDIT THESE FIRST BEFORE RUNNING ANYTHING
# ------

# Library to scan. set here or override on the command line with --search-path.
SEARCH_PATH = r"C:\Users\user\Documents\Clone Hero\Songs" # edit to your library path before running Build

# Identifies the run. Overridable with --header.
HEADER = "Test" # edit to title your cache before running Build/Analyze/Render


# ------------------------
# song.ini difficulty write-back - OPTIONAL, off by default (DON'T EDIT UNLESS YOU KNOW WHAT YOU'RE DOING)
# ------------------------
# DIFF_WRITE_MODE controls what ANALYZE does with the calculated difficulty:
#    None        - don't touch song.ini at all (default)
#   "CalcTier"   - write the continuous log-scaled tier to each instrument's own diff_*
#   "RemapDiff"  - writes the manual 0-6 remap instead to each instrument's own diff_*
#   "Restore"    - restore every song.ini's diff_* tags (every instrument at once) to
#                  the values backed up from BUILD
#
# Overridable per-run with --diff-mode on ANALYZE
# Safest to leave this at None and use --diff-mode when you actually want to override

DIFF_WRITE_MODE = "None" # None | "CalcTier" | "RemapDiff" | "Restore"




#------------------------------
# RENDER output directory - DON'T NEED TO EDIT, these dump to the tool's folder
#------------------------------
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