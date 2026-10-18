"""
POOL - shared plumbing for every parser's *_loop 

LOOP POOL LOOP POOL

Each parser keeps its own small module-level worker returning (result, error):
    error_row()       one (label, error type, message) row for the build errors CSV
    run_parallel()    process pool + progress bar, yields each worker's (result, error)
    collect_streams() note-stream results (mid/chart) -> {song_path: stream}
    collect_songs()   container results (sng/rb3con/dta) -> ({song_path: meta_row}, {song_path: stream})

Warnings ride along inside each note stream and are moved into errors here
"""

import concurrent.futures as cf
import os

import tqdm


# one row for the build errors CSV
def error_row(label, exc):
    return (str(label), type(exc).__name__, str(exc) or repr(exc))


# max_workers=None -> leave one core free (uncapped maxes out CPU lol)
def resolve_workers(max_workers):
    if max_workers is not None:
        return max(1, int(max_workers))
    return max(1, (os.cpu_count() or 1) - 1)


# worker(item) -> (result, error) for every item, in order, behind one progress bar
def run_parallel(worker, items, desc, unit, max_workers=None):
    items = list(items)
    if not items:
        return
    workers = resolve_workers(max_workers)
    chunksize = max(1, len(items) // (workers * 4))
    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(worker, items, chunksize=chunksize)
        yield from tqdm.tqdm(results, total=len(items), desc=desc, unit=unit)


# mid/chart results: result is one note stream
def collect_streams(results, errors=None):
    errors = errors if errors is not None else []
    streams = {}
    for stream, error in results:
        if stream is None:
            errors.append(error)
            continue
        errors.extend(stream.pop('warnings', []))
        streams[stream['song_path']] = stream
    return streams


# container results: result is (songs, song_errors), songs a list of (meta_row, note_stream)
def collect_songs(results, errors=None):
    errors = errors if errors is not None else []
    ini_rows, note_index = {}, {}
    for result, error in results:
        if result is None:
            errors.append(error)
            continue
        songs, song_errors = result
        errors.extend(song_errors)
        for meta_row, note_stream in songs:
            errors.extend(note_stream.pop('warnings', []))
            song_path = meta_row['SongPath']
            ini_rows[song_path] = meta_row
            note_index[song_path] = note_stream
    return ini_rows, note_index
