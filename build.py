"""
BUILD - longest part of the process - builds a library cache for analysis/visualization

Parses every song.ini, notes.chart and notes.mid under config's search_path, 
joins them by file path, assigns retrieval codes, and writes one consolidated timestamped cache

Run this once or whenever your song library changes significantly

    python build.py
    python build.py --search-path "M:/Rhythm Game Songs" --header FullTest

ini is parsed first on purpose - need to pass down tags for mid sp/solo
.mid is run second - midis are the slowest to process
.chart is run last, but they are pretty quick
"""

import argparse
import csv
from pathlib import Path

import config
from parsers import chart_parser, ini_parser, mid_parser
from functions import cache as cache_mod

# The ini columns that survive to the metrics CSV
META_KEYS = ('Name', 'Artist', 'Charter', 'Difficulty', 'Release', 'Official')

def _merge_dropped(total, dropped):
    for key, value in (dropped or {}).items():
        total[key] = total.get(key, 0) + value

# parse mid & chart files into note streams keyed to song folder path
def build_note_index(search_path, mult_notes, errors):
    mid_streams = mid_parser.mid_loop(search_path, mult_notes, errors)
    chart_streams = chart_parser.chart_loop(search_path, errors)

    note_index = {}
    note_index.update(mid_streams)
    note_index.update(chart_streams)  # chart wins on overlap
    return note_index


def build_cache(search_path=None, header=None, out_dir=None):
    search_path = search_path or config.SEARCH_PATH
    header = header or config.HEADER

    errors = []
    dropped_total = {}

    print("Gathering song.ini metadata")
    ini_df = ini_parser.ini_loop(search_path, errors)
    if ini_df.empty:
        raise ValueError(f"No parseable song.ini files found under {search_path}")

    ini_rows = {row['SongPath']: row for row in ini_df.to_dict('records')}
    mult_notes = {
        path: row.get('MultiplierNote')
        for path, row in ini_rows.items()
        if row.get('MultiplierNote') is not None
    }

    note_index = build_note_index(search_path, mult_notes, errors)

    print("Joining metadata and building difficulty backup")
    songs = {}
    no_guitar = 0

    for song_path, ini_row in ini_rows.items():
        stream = note_index.get(song_path)
        if stream is None:
            no_guitar += 1  # ini exists but no parseable guitar chart/mid
            continue

        if len(stream['notes']['time_ms']) == 0:
            errors.append((song_path, 'EmptyStream', 'parsed to zero notes'))
            continue

        _merge_dropped(dropped_total, stream.get('dropped'))

        songs[song_path] = {
            'song_path': song_path,
            'meta': {k: ini_row[k] for k in META_KEYS},
            'source_format': stream['source_format'],
            'notes': stream['notes'],
            'spans': stream['spans'],
        }

        backup_data(song_path, ini_row["Difficulty"], f"caches/{header}_BackupData.csv")

    codes = cache_mod.assign_codes(songs.keys())
    for song_path, code in codes.items():
        songs[song_path]['code'] = code

    gen_on = cache_mod.gen_ts()

    built = {
        'generated_at': gen_on,
        'search_path': str(search_path),
        'codes': {code: path for path, code in codes.items()},
        'songs': songs,
        'dropped': dropped_total,
    }

    cache_path = config.output_path('cache', header, out_dir=out_dir, ext='pkl')
    cache_mod.save(built, cache_path)

    # terminal report
    print(f"\nSongs with song.ini:  {len(ini_rows)}")
    print(f"No parseable guitar:  {no_guitar}")
    print(f"Errors:               {len(errors)}")
    print(f"Cached successfully:  {len(songs)}")

    if dropped_total:
        print("\nDropped during parsing:")
        for key in sorted(dropped_total):
            if dropped_total[key]:
                print(f"  {key}: {dropped_total[key]}")

    if errors:
        errors_path = config.output_path('errors', header, out_dir=out_dir, ext='csv')
        with open(errors_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['path', 'error', 'message'])
            writer.writerows(errors)
        print(f"\nError detail: {errors_path.resolve()}")

    print(f"Cache written:  {cache_path.resolve()}")
    print(f"Generated:      {gen_on}")

    return built

BACKUP_COLUMNS = ["song_path", "diff_guitar"]

def backup_data(song_path, original_diff, backup_csv):
    backup_csv = Path(backup_csv)
    is_new = not backup_csv.exists()

    if not is_new:
        with open(backup_csv, "r", newline="", encoding="utf-8") as f:
            existing_paths = {row["song_path"] for row in csv.DictReader(f)}
        if str(song_path) in existing_paths:
            return

    with open(backup_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=BACKUP_COLUMNS)

        if is_new:
            writer.writeheader()
        row = {"song_path": str(song_path), "diff_guitar": str(original_diff)}
        writer.writerow(row)

def main():
    parser = argparse.ArgumentParser(description="Build a notestream cache from a song library.")
    parser.add_argument('--search-path', default=None, help="library folder to scan (default: config.SEARCH_PATH)")
    parser.add_argument('--header', default=None, help="run identifier for output filenames (default: config.HEADER)")
    args = parser.parse_args()

    build_cache(args.search_path, args.header)


if __name__ == '__main__':
    main()
