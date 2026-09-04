"""
INI_UPDATER - Updates or restores song.ini's diff_* values, one column per instrument:

- update_ini_value() / get_ini_value(): read or patch one key in [song]
- backup_data(): backs up each song's original diff_* values the first time it's seen (BUILD)
- restore_from_backup(): restores every diff_* tag present in the backup back to its original (every instrument)
- sync_difficulty(): ANALYZE decision, driven by config.DIFF_WRITE_MODE (or --diff-mode) to:
    write CalcTier/RemapDiff into song.ini's diff_<instrument> tag for one instrument's mode
    OR run restore_from_backup() when mode is "Restore" (restores every instrument at once)
    OR do nothing when mode is None

Restore calls restore_from_backup() directly and skips metrics/workbook generation

update_ini_value() patches with a targeted line replacement inside the [song] section,
preserving everything else in the file and preventing the BOM/encoding from being changed
It will also add the key if it doesn't exist
"""

import csv
import pathlib

from functions import instruments

# backup CSV columns: song_path + one column per instrument's actual ini tag name
BACKUP_COLUMNS = ["song_path"] + list(instruments.DIFF_TAGS.values())
VALID_MODES = ("CalcTier", "RemapDiff", "Restore")


# ---------------------------------------------------------------------
# ini read/write
# ---------------------------------------------------------------------

# Same BOM/utf-8/cp1252 fallback as parsers.ini_parser._read_text, but
# keeps the detected encoding around so writes can match it exactly
def _read_text(file):
    raw = pathlib.Path(file).read_bytes()
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16', errors='replace'), 'utf-16'
    if raw.startswith(b'\xef\xbb\xbf'):
        return raw.decode('utf-8-sig'), 'utf-8-sig'
    try:
        return raw.decode('utf-8'), 'utf-8'
    except UnicodeDecodeError:
        return raw.decode('cp1252', errors='replace'), 'cp1252'


def _write_text(file, text, encoding):
    errors = 'strict' if encoding in ('utf-8', 'utf-8-sig') else 'replace'
    pathlib.Path(file).write_bytes(text.encode(encoding, errors=errors))


# bounds (start, end) of the [song] section body (end exclusive)
def _song_section_bounds(lines):
    start = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if start is not None:
                return start, i
            if stripped[1:-1].strip().lower() == 'song':
                start = i + 1
    if start is not None:
        return start, len(lines)
    return None, None

# Patches a single key = value line inside [song]
# Leaves everything else alone
# Adds the key at the end of the section if it isn't already present
def update_ini_value(ini_path, key, value):
    text, encoding = _read_text(ini_path)
    newline = '\r\n' if '\r\n' in text else '\n'
    ends_with_newline = text.endswith(('\n', '\r\n'))
    lines = text.splitlines()

    start, end = _song_section_bounds(lines)
    if start is None:
        raise KeyError(f"No [song] section found in {ini_path}")

    key_lower = key.strip().lower()
    target = None
    for i in range(start, end):
        stripped = lines[i].strip()
        if not stripped or stripped[0] in ';#' or '=' not in stripped:
            continue
        k = stripped.split('=', 1)[0].strip().lower()
        if k == key_lower:
            target = i
            break

    if target is not None:
        line = lines[target]
        eq_idx = line.index('=')
        prefix = line[:eq_idx + 1]
        had_space = line[eq_idx + 1:eq_idx + 2] == ' '
        lines[target] = f"{prefix}{' ' if had_space else ''}{value}"
    else:
        lines.insert(end, f"{key} = {value}")

    new_text = newline.join(lines)
    if ends_with_newline:
        new_text += newline

    _write_text(ini_path, new_text, encoding)


def get_ini_value(ini_path, key):
    text, _ = _read_text(ini_path)
    lines = text.splitlines()
    start, end = _song_section_bounds(lines)
    if start is None:
        return None

    key_lower = key.strip().lower()
    for line in lines[start:end]:
        stripped = line.strip()
        if not stripped or stripped[0] in ';#' or '=' not in stripped:
            continue
        k, _, v = stripped.partition('=')
        if k.strip().lower() == key_lower:
            return v.strip()
    return None


# ---------------------------------------------------------------------
# Backup - written by build.py / read by restore_from_backup()
# ---------------------------------------------------------------------

def backup_csv_path(header, cache_dir):
    return pathlib.Path(cache_dir) / f"{header}_BackupData.csv"


def _existing_backup_paths(backup_csv):
    if not backup_csv.exists():
        return set()
    with open(backup_csv, "r", newline="", encoding="utf-8") as f:
        return {row["song_path"] for row in csv.DictReader(f)}


# song_path -> {instrument_key: original diff value}, from the backup CSV
# Used by render.py to show the original difficulty for whichever instrument is rendered
# Returns {} if no backup exists yet for this header (old caches/metrics)
def load_backup_diffs(header, cache_dir):
    backup_csv = backup_csv_path(header, cache_dir)
    if not backup_csv.exists():
        return {}
    out = {}
    with open(backup_csv, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            out[row["song_path"]] = {
                instrument_key: (row.get(diff_tag) or '-1')
                for instrument_key, diff_tag in instruments.DIFF_TAGS.items()
            }
    return out

# songs: iterable of (song_path, difficulties) pairs
def backup_data(songs, header, cache_dir):
    backup_csv = backup_csv_path(header, cache_dir)
    backup_csv.parent.mkdir(parents=True, exist_ok=True)
    existing_paths = _existing_backup_paths(backup_csv)
    is_new = not backup_csv.exists()

    new_rows = []
    for song_path, difficulties in songs:
        if str(song_path) in existing_paths:
            continue
        difficulties = difficulties or {}
        row = {"song_path": str(song_path)}
        for instrument_key, diff_tag in instruments.DIFF_TAGS.items():
            row[diff_tag] = str(difficulties[instrument_key]) if instrument_key in difficulties else ''
        new_rows.append(row)

    if not new_rows:
        return 0

    with open(backup_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BACKUP_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(new_rows)

    return len(new_rows)


# Restores every song.ini for header back to its backed-up diff_* values,
# a blank column means that instrument wasn't charted for that song at backup time / no tag added
# Returns (restored_count, failures) if a song folder was moved, deleted, etc
def restore_from_backup(header, cache_dir):
    backup_csv = backup_csv_path(header, cache_dir)
    if not backup_csv.exists():
        raise FileNotFoundError(f"No backup found for header '{header}' at {backup_csv}")

    restored = 0
    failed = []
    with open(backup_csv, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            song_path = row["song_path"]
            song_failed = False
            for instrument_key, diff_tag in instruments.DIFF_TAGS.items():
                value = row.get(diff_tag)
                if not value:
                    continue  # blank column, leave song.ini alone
                try:
                    update_ini_value(f"{song_path}/song.ini", diff_tag, value)
                except Exception as exc:
                    failed.append((song_path, instrument_key, type(exc).__name__, str(exc)))
                    song_failed = True
            if not song_failed:
                restored += 1

    return restored, failed


# -----------------------------------------------------------------------------
# SYNC - config.DIFF_WRITE_MODE drives ANALYZE behavior (none/write/restore)
# -----------------------------------------------------------------------------
# mode:          None | "CalcTier" | "RemapDiff" | "Restore"
# instrument:    which instrument's diff_* tag to write (required for CalcTier/RemapDiff,
#                unused/omit for Restore - Restore always covers every instrument at once)
# songs:         iterable of song_path for diff write modes
# difficulties:  dict song_path -> formula.calc_diff() result for diff write modes
def sync_difficulty(mode, header, cache_dir, instrument=None, songs=None, difficulties=None):
    if mode is None:
        return None

    if mode not in VALID_MODES:
        raise ValueError(f"Unknown diff mode '{mode}', expected one of {VALID_MODES} or None")

    if mode == "Restore":
        restored, failed = restore_from_backup(header, cache_dir)
        print(f"Restored {restored} song.inis from backup" +
              (f", {len(failed)} failed" if failed else ""))
        return {"mode": mode, "restored": restored, "failed": failed}

    if songs is None or difficulties is None or instrument is None:
        raise ValueError(f"diff mode '{mode}' needs songs + difficulties + instrument")

    diff_tag = instruments.DIFF_TAGS[instrument]

    applied = 0
    failed = []
    for song_path in songs:
        try:
            update_ini_value(f"{song_path}/song.ini", diff_tag, difficulties[song_path][mode])
            applied += 1
        except Exception as exc:
            failed.append((song_path, type(exc).__name__, str(exc)))

    print(f"Applied {mode} to {applied} song.inis [{instrument}]" +
          (f", {len(failed)} failed" if failed else ""))
    return {"mode": mode, "instrument": instrument, "applied": applied, "failed": failed}
