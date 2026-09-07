"""
TIMESTAMP - timestamped output naming + cache/metrics/backup directory lookup

All outputs are named {header}_{kind}_{timestamp}.{ext} and land in the folder
config.OUTPUT_DIRS maps that kind to.
"""

import pathlib
from datetime import datetime

import config

TS_FORMAT = "%m%d%Y-%H%M"

# Short generation stamp
def timestamp():
    return datetime.now().strftime(TS_FORMAT)

# location of an output, default (config) or an explicit override
def output_dir(kind, out_dir=None):
    if out_dir is not None:
        return pathlib.Path(out_dir)
    return pathlib.Path(config.OUTPUT_DIRS.get(kind, '.'))


# {header}_{kind}_{timestamp}.{ext}
def output_path(kind, header=None, ts=None, ext='csv', out_dir=None):
    header = header or config.HEADER
    ts = ts or timestamp()
    resolved = output_dir(kind, out_dir)
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved / f"{header}_{kind}_{ts}.{ext}"


# timestamp from filename, so ANALYZE can read
def ext_ts(path, kind, header=None):
    header = header or config.HEADER
    stem = pathlib.Path(path).stem
    prefix = f"{header}_{kind}_"
    if not stem.startswith(prefix):
        raise ValueError(f"{path} doesn't match expected pattern {prefix}<timestamp>")
    return stem[len(prefix):]


# newest by file mtime
def latest_output(kind, header=None, out_dir=None, ext='pkl'):
    header = header or config.HEADER
    resolved = output_dir(kind, out_dir)
    matches = list(resolved.glob(f"{header}_{kind}_*.{ext}"))
    if not matches:
        raise FileNotFoundError(
            f"No {kind} file for header '{header}' in {resolved} "
            f"(looked for {header}_{kind}_*.{ext})"
        )
    return max(matches, key=lambda p: p.stat().st_mtime)