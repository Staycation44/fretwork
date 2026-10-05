"""
DTA_PARSER - Reads loose (unpacked) DTA song packs into the same metadata-row / note-stream shapes expected by build.py

A pack is a songs.dta plus loose per-song .mid files, e.g. an Onyx "DIY" folder or an unpacked GH2 ARK:
    <pack>/config/songs.dta                     Onyx DIY / GH2 Deluxe packs
    <pack>/config/gen/songs.dta                 ARK unpacked with arkexpander, songs.dtb converted with dtab
    <pack>/songs/<shortname>/<shortname>.mid
Extracted Rock Band packs (<pack>/songs/songs.dta) have the same shape and load the same way
Entries marked (validate_ignore ...) - GH2's tutorial lessons - aren't songs and are skipped

One songs.dta holds many songs, so song_path for each is f"{songs.dta path}::{shortname}" (same idea as rb3con)
A song that fails inside a pack is logged on its own, the rest of the pack still loads

MIDI LOOKUP: midi_file paths are relative to the pack root, which isn't always the DTA's own folder
(GH2 keeps songs.dta in config/) so each path is tried against the DTA's folder and then its parents
Fallback is the song block's (name ...) path + .mid, then the first .mid in songs/<shortname>/

CO-OP: GH2 entries may carry a (song_coop ...) block pointing at a separate co-op MIDI
That chart becomes its own song entry, so no chart from either file is ever dropped:
    song_path  f"{songs.dta path}::{shortname}::coop"
    Name       "<Name> (Co-op)", all other metadata shared with the main entry

METADATA:
    Name/Artist  - (name ...) / (artist ...); GH2 customs nest a {do {set $var ...}} block inside artist, skipped here
    Charter      - GH2 customs' {set $author ...} where present, else 'unk'
    Release      - GH2 customs' {set $songorigin ...} where present else Custom
    Official     - True only when $author is exactly one official studio (OFFICIAL_AUTHORS) else FALSE
    Difficulty   - RB-style (rank ...) blocks map exactly as rb3con does / GH2 packs have none so they stay blank

GH2 MIDI reference: https://thenathannator.github.io/GuitarGame_ChartFormats/Implementation-Specific/Guitar-Hero-1-and-2/MIDI-Tracks/Guitar/
GH2 songs.dta reference: https://mariteaux.somnolescent.net/modding/guitar-hero/tutorials/adding-new-song-definitions/
"""

import concurrent.futures as cf
import os
import pathlib

import tqdm

from parsers import dta, ini_parser, mid_parser, rb3con_parser

DTA_FILENAME = 'songs.dta'
SOURCE_FORMAT = 'dta'

# $author values that mark an unmodified official chart
OFFICIAL_AUTHORS = {
    'harmonix', 'harmonix music systems',
    'neversoft', 'vicarious visions', 'budcat', 'budcat creations', 'freestylegames',
}

# how many folders above songs.dta to try as the pack root (config/ -> pack root is 1 up)
ROOT_SEARCH_DEPTH = 3


class DtaPackError(ValueError):
    """Raised for a song whose chart can't be located or read."""


def is_dta_pack_filename(name):
    return name.lower() == DTA_FILENAME


# ------------------------
# Path resolution
# ------------------------

# rel under root, matching each part -> Path or None
def _find_ci(root, rel, want_dir=False):
    cur = root
    for part in pathlib.PurePosixPath(rel.replace('\\', '/')).parts:
        if part in ('', '.'):
            continue
        candidate = cur / part
        if not candidate.exists():
            if not cur.is_dir():
                return None
            lpart = part.lower()
            candidate = next((c for c in cur.iterdir() if c.name.lower() == lpart), None)
            if candidate is None:
                return None
        cur = candidate
    if want_dir:
        return cur if cur.is_dir() else None
    return cur if cur.is_file() else None


def _candidate_roots(dta_path):
    roots = [dta_path.parent]
    for parent in dta_path.parent.parents:
        if len(roots) > ROOT_SEARCH_DEPTH:
            break
        roots.append(parent)
    return roots


# (song ...) / (song_coop ...) block -> resolved .mid Path or None
def _resolve_block_midi(roots, block):
    rels = []
    midi_file = dta.find_text(block, 'midi_file')
    if midi_file:
        rels.append(midi_file)
    name = dta.find_text(block, 'name')
    if name:
        rels.append(name + '.mid')
    for root in roots:
        for rel in rels:
            found = _find_ci(root, rel)
            if found is not None:
                return found
    return None


# last resort for the main chart: first non-co-op .mid in songs/<shortname>/
def _fallback_midi(roots, song_id):
    for root in roots:
        folder = _find_ci(root, f"songs/{song_id}", want_dir=True)
        if folder is None:
            continue
        mids = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == '.mid')
        main = [p for p in mids if not p.stem.lower().endswith('_coop')]
        if main:
            return main[0]
    return None


# ------------------------
# Song-level parsing
# ------------------------

def _song_meta(song_entry, song_path):
    ini = rb3con_parser._difficulties_from_rank(song_entry)
    variables = dta.set_vars(song_entry)

    name = dta.decode_string(song_entry, dta.find_text(song_entry, 'name'))
    artist = dta.decode_string(song_entry, dta.find_text(song_entry, 'artist'))
    charter = dta.decode_string(song_entry, variables.get('author'))
    if name:
        ini['name'] = name
    if artist:
        ini['artist'] = artist
    if charter:
        ini['charter'] = charter
    meta_row = ini_parser.ini_metadata_from_pairs(ini, song_path)

    origin = dta.decode_string(song_entry, variables.get('songorigin'))
    if origin and origin.strip():
        meta_row['Release'] = ini_parser.DETAG.sub("", origin).strip()
    if charter and charter.strip().lower() in OFFICIAL_AUTHORS:
        meta_row['Official'] = True
    return meta_row


def _read_stream(midi_path, song_path):
    return mid_parser.mid_notes_from_bytes(
        midi_path.read_bytes(), song_path, warn_label=f"{song_path}!{midi_path.name}")


# co-op MIDI by game role: its PART GUITAR is the co-op lead unless the file has a real PART GUITAR COOP
def _coop_by_role(coop_stream):
    instruments_in = coop_stream['instruments']
    if 'coop' not in instruments_in and 'guitar' in instruments_in:
        instruments_in['coop'] = instruments_in.pop('guitar')
    return coop_stream


# The (song_coop ...) chart as its own entry -> (meta_row, note_stream), or None if it adds nothing
def _coop_variant(song_entry, roots, song_path, main_meta, main_midi):
    coop_block = dta.find(song_entry, 'song_coop')
    if not coop_block:
        return None
    coop_midi = _resolve_block_midi(roots, coop_block)
    if coop_midi is None:
        raise DtaPackError(f"{song_path}: song_coop block present but its .mid wasn't found")
    if coop_midi.resolve() == main_midi.resolve():
        return None

    coop_path = f"{song_path}::coop"
    coop_meta = dict(main_meta)
    coop_meta['SongPath'] = coop_path
    coop_meta['Name'] = f"{main_meta['Name']} (Co-op)"
    coop_meta['Difficulty'] = dict(main_meta['Difficulty'])

    coop_stream = _coop_by_role(_read_stream(coop_midi, coop_path))
    coop_stream['source_format'] = SOURCE_FORMAT
    return coop_meta, coop_stream


# One song entry within a pack -> (songs, song_errors), matching ini_parser/mid_parser's own output shapes
#   songs:       [(meta_row, note_stream)] - the main chart, plus its co-op chart when it has its own MIDI
#   song_errors: a failed co-op chart, logged without losing the main one
def dta_song(dta_path, song_id, song_entry):
    dta_path = pathlib.Path(dta_path)
    song_path = f"{dta_path}::{song_id}"
    roots = _candidate_roots(dta_path)

    meta_row = _song_meta(song_entry, song_path)

    song_block = dta.find(song_entry, 'song') or []
    main_midi = _resolve_block_midi(roots, song_block) or _fallback_midi(roots, song_id)
    if main_midi is None:
        raise DtaPackError(f"{song_path}: no .mid found for this song (checked midi_file, song name, songs/{song_id}/)")

    note_stream = _read_stream(main_midi, song_path)
    note_stream['source_format'] = SOURCE_FORMAT
    songs, song_errors = [(meta_row, note_stream)], []

    try:
        coop = _coop_variant(song_entry, roots, song_path, meta_row, main_midi)
        if coop is not None:
            songs.append(coop)
    except Exception as exc:
        song_errors.append((f"{song_path}::coop", type(exc).__name__, str(exc) or repr(exc)))

    return songs, song_errors


# songs.dta -> (tasks, errors): one (dta_path, song_id, entry) task per song entry
def pack_tasks(dta_path):
    dta_path = pathlib.Path(dta_path).resolve()
    text = dta_path.read_bytes().decode('latin1')
    tasks, errors, seen = [], [], set()
    for entry in dta.song_entries(dta.parse(text)):
        song_id = entry[0]
        if dta.find(entry, 'song') is None or dta.find(entry, 'validate_ignore') is not None:
            continue  # not a song definition, or a GH2 tutorial lesson
        if song_id in seen:
            errors.append((f"{dta_path}::{song_id}", 'DuplicateSongId',
                           "shortname defined more than once in this songs.dta - first definition used"))
            continue
        seen.add(song_id)
        tasks.append((str(dta_path), song_id, entry))
    if not tasks:
        raise DtaPackError(f"{dta_path}: no song definitions found")
    return tasks, errors


# -----------
# Search loop - parallel per song (one pack can hold a whole setlist)
# -----------

def _dta_song_worker(task):
    dta_path, song_id, _entry = task
    try:
        return dta_song(*task), None
    except Exception as exc:
        return None, (f"{dta_path}::{song_id}", type(exc).__name__, str(exc) or repr(exc))


def _resolve_workers(max_workers):
    if max_workers is not None:
        return max(1, int(max_workers))
    return max(1, (os.cpu_count() or 1) - 1)


# Returns (ini_rows, note_index): dicts keyed by song_path for build.py
def dta_loop(search_path, errors=None, max_workers=None, files=None):
    ini_rows = {}
    note_index = {}

    if files is None:
        files = [p for p in pathlib.Path(search_path).rglob("*") if p.is_file() and is_dta_pack_filename(p.name)]

    tasks = []
    for file in files:
        try:
            pack, pack_errors = pack_tasks(file)
            tasks.extend(pack)
            if errors is not None:
                errors.extend(pack_errors)
        except Exception as exc:
            if errors is not None:
                errors.append((str(file), type(exc).__name__, str(exc) or repr(exc)))

    if not tasks:
        return ini_rows, note_index

    workers = _resolve_workers(max_workers)
    chunksize = max(1, len(tasks) // (workers * 4))

    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_dta_song_worker, tasks, chunksize=chunksize)
        for result, error in tqdm.tqdm(results, total=len(tasks), desc="Parsing songs.dta", unit="song"):
            if result is not None:
                songs, song_errors = result
                if errors is not None:
                    errors.extend(song_errors)
                for meta_row, note_stream in songs:
                    warnings = note_stream.pop('warnings', [])
                    if errors is not None:
                        errors.extend(warnings)
                    song_path = meta_row['SongPath']
                    ini_rows[song_path] = meta_row
                    note_index[song_path] = note_stream
            elif errors is not None:
                errors.append(error)

    return ini_rows, note_index
