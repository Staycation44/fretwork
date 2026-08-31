"""
INI_UPDATER - Everything that touches song.ini's diff_guitar value:

- update_ini_value() / get_ini_value(): read or patch one key in [song]
- backup_data(): backs up each song's original diff_guitar the first time it's seen (during BUILD)
- restore_from_backup(): each song's original diff_guitar for a header to its backed-up original
- sync_difficulty(): ANALYZE decision, driven by config.DIFF_WRITE_MODE to:
    write CalcTier/RemapDiff into song.ini for a difficulty mode
    OR run restore_from_backup() when mode is "Restore"
    OR do nothing when mode is None

config.DIFF_WRITE_MODE = "Restore" calls restore_from_backup() directly and skips metrics/CSV generation

update_ini_value() patches with a targeted line replacement inside the [song] section,
preserving everything else in the file and preventing the BOM/encoding from being changed
It will also add the key if it doesn't exist
"""

import csv
import pathlib

DIFF_KEY = "diff_guitar"
BACKUP_COLUMNS = ["song_path", "diff_guitar"]
VALID_MODES = ("CalcTier", "RemapDiff", "Restore")


# ---------------------------------------------------------------------
# Tolerant ini read/write
# ---------------------------------------------------------------------

# Same BOM/utf-8/cp1252 fallback as parsers.ini_parser._read_text, but
# keeps the detected encoding around so writes can match it exactly
# (including whether the file had a BOM at all) instead of always forcing
# utf-8-sig like the old ini_updater did.
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


# bounds (start, end) of the [song] section body (end exclusive), matched
# case-insensitively like the old ini_updater's section lookup.
# (None, None) if no [song] section exists.
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


# Patches a single key = value line inside [song]. Everything else in the
# file - comments, other keys' casing/spacing, stray non key=value lines,
# encoding, trailing newline - is left exactly as it was. Adds the key at
# the end of the section if it isn't already present.
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
# Backup - written by build.py, read by restore_from_backup()
# ---------------------------------------------------------------------

def backup_csv_path(header, cache_dir):
    return pathlib.Path(cache_dir) / f"{header}_BackupData.csv"


def _existing_backup_paths(backup_csv):
    if not backup_csv.exists():
        return set()
    with open(backup_csv, "r", newline="", encoding="utf-8") as f:
        return {row["song_path"] for row in csv.DictReader(f)}


# songs: iterable of (song_path, original_diff_guitar) pairs, e.g. from
# build.py's ini_rows. Loads the existing-paths set once up front (not once
# per song, like the old per-song backup_data() did) and skips any path
# already backed up, so re-running build never overwrites a real original
# with an already-modified value. Returns how many new rows were written.
def backup_data(songs, header, cache_dir):
    backup_csv = backup_csv_path(header, cache_dir)
    backup_csv.parent.mkdir(parents=True, exist_ok=True)
    existing_paths = _existing_backup_paths(backup_csv)
    is_new = not backup_csv.exists()

    new_rows = [
        {"song_path": str(song_path), "diff_guitar": str(diff)}
        for song_path, diff in songs
        if str(song_path) not in existing_paths
    ]
    if not new_rows:
        return 0

    with open(backup_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BACKUP_COLUMNS)
        if is_new:
            writer.writeheader()
        writer.writerows(new_rows)

    return len(new_rows)


# Restores every song.ini for header back to its backed-up diff_guitar.
# Returns (restored_count, failures) where failures is a list of
# (song_path, error_type, message) - e.g. the song folder was moved or
# deleted since the backup was written.
def restore_from_backup(header, cache_dir):
    backup_csv = backup_csv_path(header, cache_dir)
    if not backup_csv.exists():
        raise FileNotFoundError(f"No backup found for header '{header}' at {backup_csv}")

    restored = 0
    failed = []
    with open(backup_csv, "r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            song_path = row["song_path"]
            difficulty = row["diff_guitar"]
            try:
                update_ini_value(f"{song_path}/song.ini", DIFF_KEY, difficulty)
                restored += 1
            except Exception as exc:
                failed.append((song_path, type(exc).__name__, str(exc)))

    return restored, failed


# ---------------------------------------------------------------------
# Single entry point - config.DIFF_WRITE_MODE drives this from analyze.py
# ---------------------------------------------------------------------

# mode:          None | "CalcTier" | "RemapDiff" | "Restore"
# songs:         iterable of song_path - only needed for CalcTier/RemapDiff
# difficulties:  dict song_path -> formula.calc_diff() result - only needed
#                for CalcTier/RemapDiff
# Returns None if mode is None (no-op), otherwise a small summary dict.
def sync_difficulty(mode, header, cache_dir, songs=None, difficulties=None):
    if mode is None:
        return None

    if mode not in VALID_MODES:
        raise ValueError(f"Unknown diff mode '{mode}', expected one of {VALID_MODES} or None")

    if mode == "Restore":
        restored, failed = restore_from_backup(header, cache_dir)
        print(f"Restored {restored} song.ini file(s) from backup" +
              (f", {len(failed)} failed" if failed else ""))
        return {"mode": mode, "restored": restored, "failed": failed}

    if songs is None or difficulties is None:
        raise ValueError(f"diff mode '{mode}' needs songs + difficulties")

    applied = 0
    failed = []
    for song_path in songs:
        try:
            update_ini_value(f"{song_path}/song.ini", DIFF_KEY, difficulties[song_path][mode])
            applied += 1
        except Exception as exc:
            failed.append((song_path, type(exc).__name__, str(exc)))

    print(f"Applied {mode} to {applied} song.ini file(s)" +
          (f", {len(failed)} failed" if failed else ""))
    return {"mode": mode, "applied": applied, "failed": failed}
