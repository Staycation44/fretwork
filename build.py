"""
BUILD - longest part of the process - builds a library cache for analysis/visualization

Parses every song.ini, notes.chart and/or notes.mid under config's search_path,
joins them by file path, and writes one consolidated timestamped cache
Every recognized instrument is extracted from each song's chart/mid file at every level (EMHX)

Additionally backs up every song's original diff_* values w/ instrument columns to {header}_BackupData.csv.

Run this once or whenever your song library changes significantly

    python build.py
    python build.py --search-path "M:/Rhythm Game Songs" --header FullTest

.mid is parsed before .chart - midis are the slowest to process, charts are quick
"""

import argparse
import csv

import config
from functions import instruments, ini_updater, timestamp
from parsers import chart_parser, ini_parser, mid_parser 
from functions import cache as cache_mod

# The ini columns that survive to the metrics spreadsheet, aside from per-instrument Difficulty
META_KEYS = ('Name', 'Artist', 'Charter', 'Release', 'Official')

# parse mid & chart files into per-instrument note streams keyed to song folder path
# each stream contains every recognized instrument (at least 1 must be present)
# each split into whichever EMHX levels that instrument has charted
# chart wins on overlap at the whole-song level (a song is assumed to be authored in one format)
def build_note_index(search_path, errors):
    mid_streams = mid_parser.mid_loop(search_path, errors, max_workers=config.PARSE_MAX_WORKERS)
    chart_streams = chart_parser.chart_loop(search_path, errors, max_workers=config.PARSE_MAX_WORKERS)

    note_index = {}
    note_index.update(mid_streams)
    note_index.update(chart_streams)  # chart wins on overlap
    return note_index


def build_cache(search_path=None, header=None, out_dir=None):
    search_path = search_path or config.SEARCH_PATH
    header = header or config.HEADER

    errors = []

    print(f"\nBuilding {header} cache")

    ini_df = ini_parser.ini_loop(search_path, errors)
    if ini_df.empty:
        raise ValueError(f"No parseable song.ini files found under {search_path}")

    ini_rows = {row['SongPath']: row for row in ini_df.to_dict('records')}

    note_index = build_note_index(search_path, errors)

    songs = {}
    no_instruments = 0
    instrument_counts = {
        key: {level: 0 for level in instruments.LEVEL_KEYS}
        for key in instruments.INSTRUMENT_KEYS
    }

    for song_path, ini_row in ini_rows.items():
        stream = note_index.get(song_path)
        if stream is None:
            no_instruments += 1  # ini exists but no parseable chart or mid
            continue

        song_instruments = {}
        for instrument_key, levels in stream['instruments'].items():
            song_levels = {}
            for level_key, level_stream in levels.items():
                notes = level_stream['notes']

                # for drums empty means both hand and kick must have no notes
                if instrument_key == 'drums':
                    is_empty = (
                        len(notes['hand_mask']['time_ms']) == 0
                        and len(notes['kick_mask']['time_ms']) == 0
                    )
                else:
                    is_empty = len(notes['time_ms']) == 0

                if is_empty:
                    errors.append((
                        song_path, 'EmptyStream',
                        f'{instrument_key} ({level_key}): parsed to zero notes',
                    ))
                    continue

                song_levels[level_key] = level_stream
                instrument_counts[instrument_key][level_key] += 1

            if song_levels:
                song_instruments[instrument_key] = song_levels

        if not song_instruments:
            no_instruments += 1
            continue

        songs[song_path] = {
            'song_path': song_path,
            'meta': {k: ini_row[k] for k in META_KEYS} | {'Difficulty': ini_row['Difficulty']},
            'source_format': stream['source_format'],
            'instruments': song_instruments,
        }

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
        header,
    )

    # codes assigned per (song, instrument, level) present
    triples = [
        (song_path, instrument_key, level_key)
        for song_path, song in songs.items()
        for instrument_key, levels in song['instruments'].items()
        for level_key in levels
    ]
    triple_codes = cache_mod.assign_codes(triples)
    for (song_path, instrument_key, level_key), code in triple_codes.items():
        codes_for_song = songs[song_path].setdefault('codes', {})
        codes_for_song.setdefault(instrument_key, {})[level_key] = code

    built = {
        'generated_at': timestamp.timestamp(),
        'search_path': str(search_path),
        'codes': {code: song_path for (song_path, _instrument_key, _level_key), code in triple_codes.items()},
        'songs': songs,
    }

    cache_path = timestamp.output_path('cache', header, out_dir=out_dir, ext='pkl')
    cache_mod.save(built, cache_path)

    # terminal report
    print(f"\n{header} cache complete:")
    print(f"    Song.ini count        {len(ini_rows)}")
    print(f"    No usable chart/mid   {no_instruments}")
    print(f"    Errors                {len(errors)}")
    print(f"    Diffs backed up       {backed_up}")
    print(f"    Cached songs          {len(songs)}")

    print(f"\nSongs per instrument/level:")
    print(instruments.level_matrix(instrument_counts))

    if errors:
        errors_path = timestamp.output_path('errors', header, out_dir=out_dir, ext='csv')
        with open(errors_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['path', 'error', 'message'])
            writer.writerows(errors)
        print(f"\nError detail: {errors_path.resolve()}")

    print(f"\nCache written:  {cache_path.resolve()}")
    print()

    return built


def main():
    parser = argparse.ArgumentParser(description="Build a notestream cache from a song library.")
    parser.add_argument('--search-path', default=None, help="library folder to scan (default: config.SEARCH_PATH)")
    parser.add_argument('--header', default=None, help="run identifier for output filenames (default: config.HEADER)")
    args = parser.parse_args()

    build_cache(args.search_path, args.header)


if __name__ == '__main__':
    main()
