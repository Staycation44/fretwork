"""
PATHS - timestamped output naming + cache/metrics lookup helpers
"""

import pathlib
from datetime import datetime

import config

TS_FORMAT = "%m%d%Y-%H%M"

# Short generation stamp
def timestamp():
    return datetime.now().strftime(TS_FORMAT)

# determine where to put files
def _resolve_out_dir(kind, out_dir):
    if out_dir is not None:
        return pathlib.Path(out_dir)
    return pathlib.Path(config.OUTPUT_DIR) / config.KIND_DIRS.get(kind, '')

# {header}_{kind}_{timestamp}.{ext}
def output_path(kind, header=None, ts=None, ext='csv', out_dir=None):
    header = header or config.HEADER
    ts = ts or timestamp()
    out_dir = _resolve_out_dir(kind, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"{header}_{kind}_{ts}.{ext}"


def ext_ts(path, kind, header=None):
    header = header or config.HEADER
    stem = pathlib.Path(path).stem
    prefix = f"{header}_{kind}_"
    if not stem.startswith(prefix):
        raise ValueError(f"{path} doesn't match expected pattern {prefix}<timestamp>")
    return stem[len(prefix):]


def file_ts(path, kind, header):
    try:
        ts = ext_ts(path, kind, header)
        return datetime.strptime(ts, TS_FORMAT)
    except ValueError:
        return datetime.min


def latest_output(kind, header=None, out_dir=None, ext='pkl'):
    header = header or config.HEADER
    out_dir = _resolve_out_dir(kind, out_dir)
    matches = list(out_dir.glob(f"{header}_{kind}_*.{ext}"))
    if not matches:
        raise FileNotFoundError(
            f"No {kind} file for header '{header}' in {out_dir} "
            f"(looked for {header}_{kind}_*.{ext})"
        )
    return max(matches, key=lambda p: file_ts(p, kind, header))