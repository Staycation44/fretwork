"""
BUILD - longest part of the process - builds a library cache for analysis/visualization

Parses every song.ini, notes.chart and/or notes.mid under config's search_path,
joins them by file path, and writes one consolidated timestamped cache
Every recognized instrument (see instruments.py) is extracted from each song's chart/mid file

Additionally backs up every song's original diff_* values (one column per instrument) to {header}_BackupData.csv.

Run this once or whenever your song library changes significantly

    python build.py
    python build.py --search-path "M:/Rhythm Game Songs" --header FullTest

ini is parsed first on purpose - need to pass down tags for mid sp/solo
.mid is run second - midis are the slowest to process
.chart is run last, but they are pretty quick
"""

import argparse
import csv

import config
from functions import instruments
from parsers import chart_parser, ini_parser, mid_parser
from functions import cache as cache_mod
from functions import ini_updater

# The ini columns that survive to the metrics workbook, aside from per-instrument Difficulty
META_KEYS = ('Name', 'Artist', 'Charter', 'Release', 'Official')

def _merge_dropped(total, dropped):
    for key, value in (dropped or {}).items():
        total[key] = total.get(key, 0) + value

# parse mid & chart files into per-instrument note streams keyed to song folder path
# each stream contains every recognized instrument (at least 1 must be present)
# chart wins on overlap at the whole-song level (a song is assumed to be authored in one format)
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

    print("Joining metadata")
    songs = {}
    no_instruments = 0
    instrument_counts = {key: 0 for key in instruments.INSTRUMENT_KEYS}

    for song_path, ini_row in ini_rows.items():
        stream = note_index.get(song_path)
        if stream is None:
            no_instruments += 1  # ini exists but no parseable guitar/bass/etc chart or mid
            continue

        song_instruments = {}
        for instrument_key, inst_stream in stream['instruments'].items():
            if len(inst_stream['notes']['time_ms']) == 0:
                errors.append((song_path, 'EmptyStream', f'{instrument_key}: parsed to zero notes'))
                continue

            _merge_dropped(dropped_total, inst_stream.get('dropped'))
            song_instruments[instrument_key] = {
                'notes': inst_stream['notes'],
                'spans': inst_stream['spans'],
            }
            instrument_counts[instrument_key] += 1

        if not song_instruments:
            no_instruments += 1
            continue

        songs[song_path] = {
            'song_path': song_path,
            'meta': {k: ini_row[k] for k in META_KEYS} | {'Difficulty': ini_row['Difficulty']},
            'source_format': stream['source_format'],
            'instruments': song_instruments,
        }

    print("Backing up original difficulties")
    backed_up = ini_updater.backup_data(
        (
            (
                song_path,
                {
                    instrument_key: value
                    for instrument_key, value in ini_rows[song_path]["Difficulty"].items()
                    if instrument_key in songs[song_path]['instruments']
                },
            )
            for song_path in songs
        ),
        header, config.CACHE_DIR,
    )
    print(f"New songs backed up: {backed_up}")

    # codes assigned per (song, instrument) present - see cache.assign_codes
    pairs = [
        (song_path, instrument_key)
        for song_path, song in songs.items()
        for instrument_key in song['instruments']
    ]
    pair_codes = cache_mod.assign_codes(pairs)
    for (song_path, instrument_key), code in pair_codes.items():
        songs[song_path].setdefault('codes', {})[instrument_key] = code

    gen_on = cache_mod.gen_ts()

    built = {
        'generated_at': gen_on,
        'search_path': str(search_path),
        'codes': {code: song_path for (song_path, _instrument_key), code in pair_codes.items()},
        'songs': songs,
        'dropped': dropped_total,
    }

    cache_path = config.output_path('cache', header, out_dir=out_dir, ext='pkl')
    cache_mod.save(built, cache_path)

    # terminal report
    print(f"\nSongs with song.ini:     {len(ini_rows)}")
    print(f"No recognized instrument: {no_instruments}")
    print(f"Errors:                  {len(errors)}")
    print(f"Cached successfully:     {len(songs)}")
    print("\nSongs found per instrument:")
    for instrument_key in instruments.INSTRUMENT_KEYS:
        print(f"  {instruments.DISPLAY_NAMES[instrument_key]:<14} {instrument_counts[instrument_key]}")

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


def main():
    parser = argparse.ArgumentParser(description="Build a notestream cache from a song library.")
    parser.add_argument('--search-path', default=None, help="library folder to scan (default: config.SEARCH_PATH)")
    parser.add_argument('--header', default=None, help="run identifier for output filenames (default: config.HEADER)")
    args = parser.parse_args()

    build_cache(args.search_path, args.header)


if __name__ == '__main__':
    main()
