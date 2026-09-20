"""
TIMESTAMP - timestamped output naming + cache/metrics/backup directory lookup

All outputs are named {header}_{kind}_{timestamp}.{ext} and land in the folder
config.OUTPUT_DIRS maps that kind to.

Relative output folders in config.py are anchored to the tool's folder (same as ini_parser's
sources/), so outputs land in the same place no matter which folder the scripts are run from.
Paths passed on the command line (--out-dir, --cache) stay relative to where you run from.
"""

import glob
import pathlib
from datetime import datetime

import config

TS_FORMAT = "%m%d%Y-%H%M"

# the tool's folder (this file lives in functions/)
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent

# characters that can't appear in a Windows filename - a header containing them can't name outputs
INVALID_HEADER_CHARS = set('<>:"/\\|?*')


# Short generation stamp
def timestamp():
    return datetime.now().strftime(TS_FORMAT)


# config-relative path -> anchored to the tool's folder, absolute paths untouched
def project_path(path):
    path = pathlib.Path(path)
    return path if path.is_absolute() else BASE_DIR / path


# Refuses a header that can't be used in output filenames - run early, before any work
def validate_header(header):
    header = str(header) if header is not None else ''
    bad = sorted(set(header) & INVALID_HEADER_CHARS)
    if not header.strip():
        raise ValueError("HEADER is empty - set HEADER in config.py or pass --header")
    if bad or header != header.strip() or header.endswith('.'):
        detail = f"contains {' '.join(bad)}" if bad else "starts/ends with a space or ends with '.'"
        raise ValueError(
            f"HEADER '{header}' can't be used in output filenames ({detail}) - "
            f"change HEADER in config.py or pass a different --header"
        )
    return header


# location of an output, default (config, anchored to the tool's folder) or an explicit override
def output_dir(kind, out_dir=None):
    if out_dir is not None:
        return pathlib.Path(out_dir)
    return project_path(config.OUTPUT_DIRS.get(kind, '.'))


# {header}_{kind}_{timestamp}.{ext}
def output_path(kind, header=None, ts=None, ext='csv', out_dir=None):
    header = header or config.HEADER
    ts = ts or timestamp()
    resolved = output_dir(kind, out_dir)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved / f"{header}_{kind}_{ts}.{ext}"


# (header, timestamp) from a {header}_cache_{timestamp} filename, (None, None) if it doesn't match
def split_cache_name(path):
    stem = pathlib.Path(path).stem
    if '_cache_' not in stem:
        return None, None
    header, ts = stem.rsplit('_cache_', 1)
    return (header or None), (ts or None)


# explicit --cache value -> existing file; a bare name is also looked up in the caches folder
def resolve_cache_path(cache_path):
    path = pathlib.Path(cache_path)
    if path.is_file():
        return path
    candidate = output_dir('cache') / path.name
    if not path.is_absolute() and candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"Cache file not found: {cache_path} (also looked in {output_dir('cache')}) - "
        f"check the --cache path, or run build.py to create a cache"
    )


# newest by file mtime
def latest_output(kind, header=None, out_dir=None, ext='pkl'):
    header = header or config.HEADER
    resolved = output_dir(kind, out_dir)
    pattern = f"{glob.escape(header)}_{kind}_*.{ext}"
    matches = list(resolved.glob(pattern))
    if not matches:
        hint = (" - run build.py first, or check HEADER in config.py / --header"
                if kind == 'cache' else "")
        raise FileNotFoundError(
            f"No {kind} file for header '{header}' in {resolved} "
            f"(looked for {header}_{kind}_*.{ext}){hint}"
        )
    return max(matches, key=lambda p: p.stat().st_mtime)
