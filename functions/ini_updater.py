"""
INI_UPDATER - Updates or restores song.ini's diff_* values, one column per instrument:

Restore calls restore_from_backup() directly and skips metrics/spreadsheet generation

update_ini_values() patches with targeted line replacements inside the [song] section,
preserving everything else in the file byte-for-byte (encoding, BOM/byte order, undecodable bytes)
    - every occurrence of a key is updated (the parser reads the last duplicate, the game may read either)
    - keys that don't exist yet are added at the end of [song], a value of None removes the key
    - files are only rewritten when something actually changed, via a temp file + os.replace

The backup CSV lives with the cache files:
    - one row per song, one column per instrument's diff_* tag
    - a blank cell means that instrument has not been backed up & Analyze won't write to it
    - 'missing' means song.ini had no tag for it, Restore removes the key again
    - Build fills blank cells from the current song.ini (safe, since nothing is written to a blank cell)
"""

import csv
import os
import pathlib
import shutil

from functions import instruments, timestamp

# backup CSV columns: song_path + one column per instrument's actual ini tag name
BACKUP_COLUMNS = ["song_path"] + list(instruments.DIFF_TAGS.values())
VALID_MODES = ("CalcTier", "RemapDiff", "Restore")

# backup cell for a song.ini that had no tag for that instrument
MISSING = "missing"

# song folder -> its song.ini, joined by pathlib so the separator matches song_path's
def song_ini_path(song_path):
    return pathlib.Path(song_path) / "song.ini"

# ---------------------------------------------------------------------
# ini read/write
# ---------------------------------------------------------------------

# -> (text, codec) where codec = (python codec, BOM bytes, error handler) round-trips the file exactly
# surrogateescape/surrogatepass keep undecodable bytes / lone surrogates intact through a rewrite
def _read_text(file):
    raw = pathlib.Path(file).read_bytes()
    if raw.startswith(b'\xff\xfe'):
        codec = ('utf-16-le', b'\xff\xfe', 'surrogatepass')
    elif raw.startswith(b'\xfe\xff'):
        codec = ('utf-16-be', b'\xfe\xff', 'surrogatepass')
    elif raw.startswith(b'\xef\xbb\xbf'):
        codec = ('utf-8', b'\xef\xbb\xbf', 'surrogateescape')
    else:
        try:
            raw.decode('utf-8')
            codec = ('utf-8', b'', 'surrogateescape')
        except UnicodeDecodeError:
            codec = ('cp1252', b'', 'surrogateescape')
    name, bom, errors = codec
    return raw[len(bom):].decode(name, errors=errors), codec


# temp file in the same folder + os.replace, so an interrupted write never truncates song.ini
def _write_text(file, text, codec):
    name, bom, errors = codec
    file = pathlib.Path(file)
    tmp = file.with_name(file.name + ".fretwork.tmp")
    try:
        tmp.write_bytes(bom + text.encode(name, errors=errors))
        shutil.copymode(file, tmp)
        os.replace(tmp, file)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


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

# Patches any number of key = value lines inside [song]
# Every occurrence of a key is updated, a None value removes the key, new keys go at the end
# Leaves everything else alone - returns True only if the file was rewritten
def update_ini_values(ini_path, values):
    if not values:
        return False

    text, codec = _read_text(ini_path)
    newline = '\r\n' if '\r\n' in text else '\n'
    ends_with_newline = text.endswith(('\n', '\r\n'))
    lines = text.splitlines()

    start, end = _song_section_bounds(lines)
    if start is None:
        raise KeyError(f"No [song] section found in {ini_path}")

    # keyed lowercase for matching, carrying the original key spelling for the append case
    pending = {key.strip().lower(): (key, value) for key, value in values.items()}
    found = set()

    out = lines[:start]
    for line in lines[start:end]:
        stripped = line.strip()
        if stripped and stripped[0] not in ';#' and '=' in stripped:
            k = stripped.split('=', 1)[0].strip().lower()
            if k in pending:
                found.add(k)
                _key, value = pending[k]
                if value is None:
                    continue  # tag removed
                eq_idx = line.index('=')
                prefix = line[:eq_idx + 1]
                had_space = line[eq_idx + 1:eq_idx + 2] == ' '
                line = f"{prefix}{' ' if had_space else ''}{value}"
        out.append(line)

    for k, (key, value) in pending.items():
        if k not in found and value is not None:
            out.append(f"{key} = {value}")
    out.extend(lines[end:])

    new_text = newline.join(out)
    if ends_with_newline:
        new_text += newline

    if new_text == text:
        return False
    _write_text(ini_path, new_text, codec)
    return True


# ---------------------------------------------------------------------
# Backup - written by build.py / read by restore_from_backup() and the write guard
# ---------------------------------------------------------------------

def backup_csv_path(header):
    return timestamp.output_dir('backup') / f"{header}_BackupData.csv"


# song.ini difficulty value -> backup cell (None = no tag in song.ini)
def _cell(value):
    return MISSING if value is None else str(value)


# song_path -> row dict (every BACKUP_COLUMNS name present, blank where empty)
def load_backup_rows(header):
    backup_csv = backup_csv_path(header)
    if not backup_csv.exists():
        return {}
    with open(backup_csv, "r", newline="", encoding="utf-8") as f:
        return {
            row["song_path"]: {col: (row.get(col) or '') for col in BACKUP_COLUMNS}
            for row in csv.DictReader(f)
        }


# Brings a backup CSV's header up to BACKUP_COLUMNS (adding new instruments)
# Returns True when the file was rewritten
# False when there is no file/header already equals BACKUP_COLUMNS, or the header is longer
# readers fill the missing names with None, which every reader here treats as blank
# Raises ValueError for any other header, guessing is worse than stopping for rewrites
def migrate_backup_header(backup_csv):
    backup_csv = pathlib.Path(backup_csv)
    if not backup_csv.exists():
        return False
    with open(backup_csv, "r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if header is None or header == BACKUP_COLUMNS:
            return False
        if header == BACKUP_COLUMNS[:len(header)]:
            added = BACKUP_COLUMNS[len(header):]
        elif header[:len(BACKUP_COLUMNS)] == BACKUP_COLUMNS:
            return False   # written by a newer instruments table; readers cope
        else:
            raise ValueError(f"unrecognised backup CSV header in {backup_csv}: {header}")
        rows = list(reader)

    tmp = backup_csv.with_suffix(backup_csv.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(BACKUP_COLUMNS)
        for row in rows:
            # a row appended under the old header with the new shape already
            # carries its extra fields, in BACKUP_COLUMNS order, past the header
            extra = row[len(header):len(BACKUP_COLUMNS)]
            writer.writerow(row[:len(header)] + extra + [''] * (len(added) - len(extra)))
    os.replace(tmp, backup_csv)
    print(f"Backup CSV header updated: {backup_csv} (+{', +'.join(added)})")
    return True


# song_path -> {instrument_key: backup cell}, from the backup CSV
# cells are raw: '' = not backed up, 'missing' = song.ini had no tag, otherwise the original value
# Used by render.py to show the original difficulty
def load_backup_diffs(header):
    return {
        song_path: {
            instrument_key: row[diff_tag]
            for instrument_key, diff_tag in instruments.DIFF_TAGS.items()
        }
        for song_path, row in load_backup_rows(header).items()
    }


# Other headers' backups that already cover some of these songs - {header: overlap count}
# Checked by build when this header has no backup yet: if Analyze wrote to those songs under
# the other header, a fresh backup here would capture the written values as originals
def other_header_overlap(header, song_paths):
    song_paths = set(str(p) for p in song_paths)
    own = backup_csv_path(header).resolve()
    overlap = {}
    for other in sorted(timestamp.output_dir('backup').glob("*_BackupData.csv")):
        if other.resolve() == own:
            continue
        with open(other, "r", newline="", encoding="utf-8") as f:
            count = sum(1 for row in csv.DictReader(f) if row.get("song_path") in song_paths)
        if count:
            overlap[other.name[:-len("_BackupData.csv")]] = count
    return overlap


# songs: iterable of (song_path, difficulties) pairs, difficulties {instrument_key: value or None}
# New songs get a row, existing rows get their blank cells filled for the instruments given
# (a filled cell is never overwritten). Returns (rows_added, cells_filled)
def backup_data(songs, header):
    backup_csv = backup_csv_path(header)
    backup_csv.parent.mkdir(parents=True, exist_ok=True)
    migrate_backup_header(backup_csv)

    fieldnames = list(BACKUP_COLUMNS)
    rows = []
    if backup_csv.exists():
        with open(backup_csv, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or fieldnames   # may carry extra (newer) columns
            rows = list(reader)
    by_path = {row["song_path"]: row for row in rows}

    added = 0
    filled = 0
    for song_path, difficulties in songs:
        song_path = str(song_path)
        difficulties = difficulties or {}
        row = by_path.get(song_path)
        if row is None:
            row = {"song_path": song_path}
            for instrument_key, diff_tag in instruments.DIFF_TAGS.items():
                row[diff_tag] = _cell(difficulties[instrument_key]) if instrument_key in difficulties else ''
            rows.append(row)
            by_path[song_path] = row
            added += 1
            continue
        for instrument_key, value in difficulties.items():
            diff_tag = instruments.DIFF_TAGS[instrument_key]
            if not row.get(diff_tag):
                row[diff_tag] = _cell(value)
                filled += 1

    if not (added or filled):
        return 0, 0

    tmp = backup_csv.with_suffix(backup_csv.suffix + ".tmp")
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore', restval='')
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, backup_csv)

    return added, filled


# Restores every song.ini for header back to its backed-up diff_* values
# 'missing' cells remove the tag again, blank cells are left alone
# Returns (restored_count, unchanged_count, failures) - failures if a song folder was moved, deleted, etc
def restore_from_backup(header):
    backup_csv = backup_csv_path(header)
    if not backup_csv.exists():
        raise FileNotFoundError(f"No backup found for header '{header}' at {backup_csv}")
    migrate_backup_header(backup_csv)

    restored = 0
    unchanged = 0
    failed = []
    for song_path, row in load_backup_rows(header).items():
        values = {
            diff_tag: (None if row[diff_tag] == MISSING else row[diff_tag])
            for diff_tag in instruments.DIFF_TAGS.values()
            if row[diff_tag]
        }
        if not values:
            continue  # every column blank, leave song.ini alone

        ini_path = song_ini_path(song_path)
        if not ini_path.is_file():
            # song folder moved or deleted since BUILD
            failed.append((song_path, None, 'FileNotFoundError', f"no song.ini at {ini_path}"))
            continue

        try:
            if update_ini_values(ini_path, values):
                restored += 1
            else:
                unchanged += 1
        except Exception as exc:
            failed.append((song_path, None, type(exc).__name__, str(exc)))

    return restored, unchanged, failed


# -----------------------------------------------------------------------------
# SYNC - analyze.py resolves the per-instrument mode, this applies it (none/write/restore)
# -----------------------------------------------------------------------------
# mode:          None | "CalcTier" | "RemapDiff" | "Restore"
# instrument:    which instrument's diff_* tag to write (required for CalcTier/RemapDiff,
#                unused/omit for Restore - Restore always covers every instrument at once)
# songs:         iterable of song_path for diff write modes
# difficulties:  dict song_path -> {'RemapDiff': int, 'CalcTier': int} for diff write modes
# backup_rows:   load_backup_rows(header), loaded once by the caller - songs without a
#                backed-up cell for this instrument are skipped (their original isn't safe yet)
def sync_difficulty(mode, header, instrument=None, songs=None, difficulties=None, backup_rows=None):
    if mode is None:
        return None

    if mode not in VALID_MODES:
        raise ValueError(f"Unknown diff mode '{mode}', expected one of {VALID_MODES} or None")

    if mode == "Restore":
        restored, unchanged, failed = restore_from_backup(header)
        print(f"Restored {restored} song.inis from backup" +
              (f", {unchanged} unchanged" if unchanged else "") +
              (f", {len(failed)} failed" if failed else ""))
        return {"mode": mode, "restored": restored, "unchanged": unchanged, "failed": failed}

    if songs is None or difficulties is None or instrument is None:
        raise ValueError(f"diff mode '{mode}' needs songs + difficulties + instrument")

    if backup_rows is None:
        backup_rows = load_backup_rows(header)
    diff_tag = instruments.DIFF_TAGS[instrument]

    applied = 0
    unchanged = 0
    not_backed_up = 0
    failed = []
    for song_path in songs:
        if not backup_rows.get(song_path, {}).get(diff_tag):
            not_backed_up += 1
            continue
        ini_path = song_ini_path(song_path)
        if not ini_path.is_file():
            failed.append((song_path, 'FileNotFoundError', f"no song.ini at {ini_path}"))
            continue
        try:
            if update_ini_values(ini_path, {diff_tag: difficulties[song_path][mode]}):
                applied += 1
            else:
                unchanged += 1
        except Exception as exc:
            failed.append((song_path, type(exc).__name__, str(exc)))

    print(f"Applied {mode} to {applied} song.inis [{instrument}]" +
          (f", {unchanged} unchanged" if unchanged else "") +
          (f", {not_backed_up} not backed up (skipped)" if not_backed_up else "") +
          (f", {len(failed)} failed" if failed else ""))
    return {"mode": mode, "instrument": instrument, "applied": applied, "unchanged": unchanged,
            "not_backed_up": not_backed_up, "failed": failed}
