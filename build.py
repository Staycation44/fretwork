"""
BUILD - longest part of the process - builds a library cache for analysis/visualization

Parses every song under config's search_path,
joins them by file path, and writes one consolidated timestamped cache
Every recognized instrument is extracted from each song's chart/mid file at every level (EMHX)

Additionally backs up every song's original diff_* values w/ instrument columns to {header}_BackupData.csv
Existing backup rows are never overwritten - only their blank cells get filled from the current song.ini
(Analyze never writes to a blank cell, so a blank cell still holds the original)

The library is walked once: 
 - song.ini / notes.chart / notes.mid combinations built out by the parsers 
- .sng / .rb3con containers are unpacked in memory and reshaped to go into the cache
- loose songs.dta packs (unpacked GH2 ARKs, Onyx DIY folders) are read song by song from the .dta + each song's .mid

folders with a chart/mid but no song.ini plus unsupported .yargsong files are counted in the report

Run this once or whenever your song library changes significantly

    python build.py
    python build.py --search-path "M:/Rhythm Game Songs" --header FullTest

midi preferred if both chart & mid exist per game convetions, chart is a fallback for unparseable midi
"""

import argparse
import csv
import os
import pathlib

import config
from functions import instruments, ini_updater, timestamp
from parsers import chart_parser, dta_parser, ini_parser, mid_parser, rb3con_parser, sng_parser
from functions import cache as cache_mod

# The ini columns that survive to the metrics spreadsheet, aside from per-instrument Difficulty
META_KEYS = ('Name', 'Artist', 'Charter', 'Release', 'Official')

# names matched the way the file system does
_INI_NAME = os.path.normcase("song.ini")
_CHART_NAME = os.path.normcase("notes.chart")
_MID_NAME = os.path.normcase("notes.mid")

# .sng (Clone Hero container)
SNG_EXTS = ('.sng',)

# .yargsong deliberately exclusion due to licensing encryption
UNSUPPORTED_EXTS = ('.yargsong',)


# One walk of the library: file lists for the parsers + counts for the terminal report
def scan_library(search_path):
    ini_files, chart_files, mid_files, sng_files, rb3con_files, dta_files = [], [], [], [], [], []
    unsupported = {ext: 0 for ext in UNSUPPORTED_EXTS}
    ini_dirs, note_dirs = set(), set()

    for dirpath, _dirnames, filenames in os.walk(search_path):
        for name in filenames:
            key = os.path.normcase(name)
            if key == _INI_NAME:
                ini_files.append(pathlib.Path(dirpath, name))
                ini_dirs.add(dirpath)
            elif key == _CHART_NAME:
                chart_files.append(pathlib.Path(dirpath, name))
                note_dirs.add(dirpath)
            elif key == _MID_NAME:
                mid_files.append(pathlib.Path(dirpath, name))
                note_dirs.add(dirpath)
            elif dta_parser.is_dta_pack_filename(name):
                # one songs.dta per pack, its .mid files are found from the dta entries
                dta_files.append(pathlib.Path(dirpath, name))
            elif rb3con_parser.is_rb3con_filename(name):
                # these commonly ship with no extension
                rb3con_files.append(pathlib.Path(dirpath, name))
            else:
                ext = os.path.splitext(name)[1].lower()
                if ext in SNG_EXTS:
                    sng_files.append(pathlib.Path(dirpath, name))
                elif ext in unsupported:
                    unsupported[ext] += 1

    return {
        'ini': ini_files,
        'chart': chart_files,
        'mid': mid_files,
        'sng': sng_files,
        'rb3con': rb3con_files,
        'dta': dta_files,
        'no_ini_folders': len(note_dirs - ini_dirs),
        'unsupported': unsupported,
    }


# parse mid & chart files into per-instrument note streams keyed to song folder path
# each stream contains every recognized instrument (at least 1 must be present)
# each split into whichever EMHX levels that instrument has charted
#
# A folder with both notes.mid and notes.chart uses the midi
# chart fallback when midi fails to parse
def build_note_index(search_path, errors, scan=None):
    scan = scan or {}
    mid_files = scan.get('mid')
    if mid_files is None:
        mid_files = list(pathlib.Path(search_path).rglob("notes.mid"))
    chart_files = scan.get('chart')
    if chart_files is None:
        chart_files = list(pathlib.Path(search_path).rglob("notes.chart"))

    mid_streams = mid_parser.mid_loop(search_path, errors, max_workers=config.PARSE_MAX_WORKERS,
                                      files=mid_files)

    # keyed the same way the parsers key song_path
    mid_dirs = {str(pathlib.Path(f).parent.resolve()) for f in mid_files}
    charts_to_parse = []
    for chart_file in chart_files:
        folder = str(pathlib.Path(chart_file).parent.resolve())
        if folder in mid_streams:
            if errors is not None:
                errors.append((str(chart_file), 'MultipleChart',
                               "folder also has notes.mid - notes.mid used, notes.chart ignored"))
            continue
        charts_to_parse.append(chart_file)

    chart_streams = chart_parser.chart_loop(search_path, errors, max_workers=config.PARSE_MAX_WORKERS,
                                            files=charts_to_parse)

    # chart fallback
    if errors is not None:
        for song_path in chart_streams:
            if song_path in mid_dirs:
                errors.append((song_path, 'ChartFallback',
                               "notes.mid failed to parse - using notes.chart instead"))

    note_index = {}
    note_index.update(chart_streams)
    note_index.update(mid_streams)  # never overlaps, charts next to a parsed midi are skipped above
    return note_index


def build_cache(search_path=None, header=None, out_dir=None):
    search_path = search_path or config.SEARCH_PATH
    header = timestamp.validate_header(header or config.HEADER)

    if not pathlib.Path(search_path).is_dir():
        raise ValueError(
            f"Search path not found: {search_path} - check SEARCH_PATH in config.py or pass --search-path"
        )

    errors = []

    print(f"\nBuilding {header} cache")

    # a backup CSV with an unrecognised header is refused now, not after the parse
    backup_csv = ini_updater.backup_csv_path(header)
    ini_updater.migrate_backup_header(backup_csv)
    new_backup = not backup_csv.exists()

    scan = scan_library(search_path)

    ini_rows = ini_parser.ini_loop(search_path, errors, files=scan['ini'])

    # .sng containers carry their own metadata + notes.mid/.chart
    # each container is one song keyed by resolved file path
    sng_ini_rows, sng_note_streams = sng_parser.sng_loop(
        search_path, errors, max_workers=config.PARSE_MAX_WORKERS, files=scan.get('sng'))
    ini_rows.update(sng_ini_rows)

    # _rb3con packages carry their own metadata (songs.dta) + notes.mid
    rb3con_ini_rows, rb3con_note_streams = rb3con_parser.rb3con_loop(
        search_path, errors, max_workers=config.PARSE_MAX_WORKERS, files=scan.get('rb3con'))
    ini_rows.update(rb3con_ini_rows)

    # loose songs.dta packs carry their own metadata + per-song .mid files
    dta_ini_rows, dta_note_streams = dta_parser.dta_loop(
        search_path, errors, max_workers=config.PARSE_MAX_WORKERS, files=scan.get('dta'))
    ini_rows.update(dta_ini_rows)

    if not ini_rows:
        raise ValueError(
            f"No parseable song files found under {search_path} - check "
            f"SEARCH_PATH in config.py or pass --search-path"
        )

    note_index = build_note_index(search_path, errors, scan)
    note_index.update(sng_note_streams)
    note_index.update(rb3con_note_streams)
    note_index.update(dta_note_streams)

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

                # Defensive/redundant: every parser already checks for empty streams
                if instrument_key == 'drums':
                    is_empty = (
                        len(notes['hand_mask']['time_ms']) == 0
                        and len(notes['kick_mask']['time_ms']) == 0
                    )
                # for vocals empty means no pitch, no perc, no talkie
                elif instrument_key == 'vocals':
                    talkie = level_stream['talkie']
                    percussion = level_stream['percussion']
                    is_empty = (
                        len(notes['time_ms']) == 0
                        and len(talkie['time_ms']) == 0
                        and len(percussion['time_ms']) == 0
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
            # drum roll lanes
            'roll_spans': stream.get('roll_spans', {}),
        }

    # first backup under this header - warn if another header already backs these songs up,
    # since any values Analyze wrote under that header would be captured here as originals
    if new_backup:
        for other_header, count in ini_updater.other_header_overlap(header, songs).items():
            print(f"\nWarning: {count} of these songs are already backed up under header '{other_header}'. "
                  f"If Analyze has written difficulties to them, this new '{header}' backup holds the "
                  f"written values, not the originals - Restore from '{other_header}' first.")

    backed_up, backup_filled = ini_updater.backup_data(
        (
            (
                song_path,
                {
                    instrument_key: value
                    for instrument_key, value in ini_rows[song_path]["Difficulty"].items()
                    # 'band' backup for restores
                    if instrument_key in songs[song_path]['instruments'] or instrument_key == 'band'
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
        'header': header,
        'generated_at': timestamp.timestamp(),
        'search_path': str(search_path),
        'codes': {code: song_path for (song_path, _instrument_key, _level_key), code in triple_codes.items()},
        'songs': songs,
    }

    cache_path = timestamp.output_path('cache', header, out_dir=out_dir, ext='pkl')
    cache_mod.save(built, cache_path)

    # terminal report
    print(f"\n{header} cache complete:")
    print(f"    Song.ini count        {len(ini_rows) - len(sng_ini_rows) - len(rb3con_ini_rows) - len(dta_ini_rows)}")
    if scan.get('sng'):
        print(f"    .sng count            {len(scan['sng'])}")
    if scan.get('rb3con'):
        print(f"    _rb3con count         {len(scan['rb3con'])} ({len(rb3con_ini_rows)} songs)")
    if scan.get('dta'):
        print(f"    songs.dta count       {len(scan['dta'])} ({len(dta_ini_rows)} songs)")
    if scan['no_ini_folders']:
        print(f"    Chart/mid, no ini     {scan['no_ini_folders']}")
    for ext, count in scan['unsupported'].items():
        if count:
            print(f"    {ext + ' (unsupported)':<22}{count}")
    print(f"    Errors                {len(errors)}")
    print(f"    Diffs backed up       {backed_up}")
    if backup_filled:
        print(f"    Backup cells filled   {backup_filled}")
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

    try:
        build_cache(args.search_path, args.header)
    except ValueError as exc:
        raise SystemExit(f"\n{exc}\n")


if __name__ == '__main__':
    main()
