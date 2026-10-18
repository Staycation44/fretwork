"""
SNG_PARSER - Reads .sng container files into the same metadata-row / note-stream shapes build.py expects

.yargsong is intentionally not implemented

.yargsong is the same rough container as .sng, but with a layer of encryption I'm not messing with (don't want to blow up their licensing)

Only notes.mid / notes.chart are read out of a container - notes.mid preferred, notes.chart only if
there's no midi or it fails to parse (same rule build.py applies to song folders)

.SNG spec: https://github.com/mdsitton/SngFileFormat
"""

import concurrent.futures as cf
import os
import pathlib
import struct

import numpy as np
import tqdm

from functions import library_walk
from parsers import chart_parser, ini_parser, mid_parser
from parsers.text_decode import decode_text

MAGIC = b'SNGPKG'
SNG_EXTENSIONS = ('.sng',)

# the only embedded files this tool ever needs - everything else in the container is skipped
WANTED_FILES = {'notes.mid', 'notes.chart'}


class SngError(ValueError):
    """Raised for a malformed/unrecognized .sng container."""


# --------------------------
# Low-level section reading
# --------------------------

def _read_exact(f, n, what):
    data = f.read(n)
    if len(data) != n:
        raise SngError(f"truncated while reading {what} ({len(data)}/{n} bytes)")
    return data


def _u32(f, what='uint32'):
    return struct.unpack('<I', _read_exact(f, 4, what))[0]


def _u64(f, what='uint64'):
    return struct.unpack('<Q', _read_exact(f, 8, what))[0]


def _i32(f, what='int32'):
    return struct.unpack('<i', _read_exact(f, 4, what))[0]


def _read_header(f):
    magic = _read_exact(f, 6, 'magic')
    if magic != MAGIC:
        raise SngError(f"not an SNG container (bad magic {magic!r})")
    version = _u32(f, 'version')
    xor_mask = _read_exact(f, 16, 'xorMask')
    return version, xor_mask


# Section length always covers at least its own 8-byte count field
# shorter means something is corrupted/broken
def _require_room_for_count(section_len, what):
    if section_len < 8:
        raise SngError(f"{what} section too short to hold its own count field ({section_len} bytes)")

def _require_within_section(f, section_end, what):
    if f.tell() > section_end:
        raise SngError(f"{what} section ran past its declared length by {f.tell() - section_end} bytes")


# key/value string pairs / song.ini data already parsed
def _read_metadata_section(f):
    section_len = _u64(f, 'metadata section length')
    section_end = f.tell() + section_len
    _require_room_for_count(section_len, 'metadata')
    count = _u64(f, 'metadata count')
    pairs = {}
    for _ in range(count):
        key = _read_exact(f, _i32(f, 'metadata key length'), 'metadata key').decode('utf-8', errors='replace')
        value = _read_exact(f, _i32(f, 'metadata value length'), 'metadata value').decode('utf-8', errors='replace')
        pairs[key] = value
    _require_within_section(f, section_end, 'metadata')
    f.seek(section_end)
    return pairs


def _read_file_index_section(f):
    section_len = _u64(f, 'file index section length')
    section_end = f.tell() + section_len
    _require_room_for_count(section_len, 'file index')
    count = _u64(f, 'file count')
    entries = []
    for _ in range(count):
        name_len = _read_exact(f, 1, 'filename length')[0]
        name = _read_exact(f, name_len, 'filename').decode('utf-8', errors='replace')
        contents_len = _u64(f, 'file contents length')
        contents_index = _u64(f, 'file contents index')
        entries.append((name, contents_len, contents_index))
    _require_within_section(f, section_end, 'file index')
    f.seek(section_end)
    return entries

def _unmask(masked, xor_mask):
    if not masked:
        return b''
    data = np.frombuffer(masked, dtype=np.uint8)
    idx = np.arange(len(data), dtype=np.uint32)
    mask_bytes = np.frombuffer(xor_mask, dtype=np.uint8)
    key = mask_bytes[idx % 16] ^ (idx & 0xFF).astype(np.uint8)
    return (data ^ key).tobytes()

# Reads one container
# only entries in WANTED_FILES
def _read_sng(path):
    with open(path, 'rb') as f:
        _version, xor_mask = _read_header(f)
        metadata = _read_metadata_section(f)
        entries = _read_file_index_section(f)
        _fdlen = _u64(f, 'file data section length')

        files = {}
        for name, length, index in entries:
            lname = name.lower()
            if lname not in WANTED_FILES or lname in files:
                continue
            f.seek(index)
            masked = _read_exact(f, length, f"'{name}' contents")
            files[lname] = _unmask(masked, xor_mask)

    return metadata, files


# --------------------
# Song-level parsing
# -------------------

# Parses one .sng into (meta_row, note_stream)
# matches ini_parser/mid_parser/chart_parser output
# song_path is the container's resolved path
def sng_song(path):
    path = pathlib.Path(path)
    song_path = str(path.resolve())

    raw_meta, files = _read_sng(path)
    if not files:
        raise SngError(f"{path}: no notes.mid or notes.chart found inside container")

    ini = {key.strip().lower(): value for key, value in raw_meta.items()}
    meta_row = ini_parser.ini_metadata_from_pairs(ini, song_path)

    warnings = []
    note_stream = None
    mid_exc = None

    # notes.mid preferred
    # notes.chart is only read if there's no midi, or the midi fails to parse
    if 'notes.mid' in files:
        try:
            note_stream = mid_parser.mid_notes_from_bytes(
                files['notes.mid'], song_path, warn_label=f"{path}!notes.mid")
            warnings.extend(note_stream.pop('warnings', []))
            if 'notes.chart' in files:
                warnings.append((f"{path}!notes.chart", 'MultipleChart',
                                 "container also has notes.mid - notes.mid used, notes.chart ignored"))
        except Exception as exc:
            if 'notes.chart' not in files:
                raise
            mid_exc = exc
            # midi error logged, then fall through to the chart
            warnings.append((f"{path}!notes.mid", type(exc).__name__, str(exc) or repr(exc)))
            warnings.append((f"{path}!notes.chart", 'ChartFallback',
                             "notes.mid failed to parse - using notes.chart instead"))

    if note_stream is None:
        try:
            chart_text = decode_text(files['notes.chart'])
            note_stream = chart_parser.chart_notes_from_text(
                chart_text, song_path, warn_label=f"{path}!notes.chart")
        except Exception as exc:
            if mid_exc is None:
                raise
            # both failed - one error row that names both, so the midi failure isn't lost
            raise SngError(
                f"notes.mid: {type(mid_exc).__name__}: {mid_exc} / "
                f"notes.chart fallback: {type(exc).__name__}: {exc}"
            ) from exc
        warnings.extend(note_stream.pop('warnings', []))

    note_stream['warnings'] = warnings
    return meta_row, note_stream


# -----------
# Search loop - parallel, same shape as mid_loop/chart_loop
# -----------

def _sng_song_worker(file):
    try:
        return sng_song(file), None
    except Exception as exc:
        return None, (str(file), type(exc).__name__, str(exc) or repr(exc))


def _resolve_workers(max_workers):
    if max_workers is not None:
        return max(1, int(max_workers))
    return max(1, (os.cpu_count() or 1) - 1)


# Returns (ini_rows, note_index): dicts keyed by song_path for build.py
def sng_loop(search_path, errors=None, max_workers=None, files=None):
    ini_rows = {}
    note_index = {}

    if files is None:
        files = list(library_walk.library_files(search_path, library_walk.ext_in(SNG_EXTENSIONS)))

    if not files:
        return ini_rows, note_index

    workers = _resolve_workers(max_workers)
    chunksize = max(1, len(files) // (workers * 4))

    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_sng_song_worker, files, chunksize=chunksize)
        for result, error in tqdm.tqdm(results, total=len(files), desc="Parsing sng", unit="file"):
            if result is not None:
                meta_row, note_stream = result
                warnings = note_stream.pop('warnings', [])
                if errors is not None:
                    errors.extend(warnings)
                song_path = meta_row['SongPath']
                ini_rows[song_path] = meta_row
                note_index[song_path] = note_stream
            elif errors is not None:
                errors.append(error)

    return ini_rows, note_index
