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
    Charter      - GH2 customs' {set $author ...} where present, else the pack's locale author table, else 'unk'
    Release      - GH2 customs' {set $songorigin ...} where present else Custom
    Official     - True only when the author is exactly one official studio (OFFICIAL_AUTHORS) else FALSE
                   ("Harmonix, mariteaux" is a DX-modified chart, so it isn't Official)
    Difficulty   - RB-style (rank ...) blocks map via dta.RANK_DIFF_MAPS, same as rb3con / GH2 packs have none so they stay blank

AUTHORS: GH2DX convention keeps authors in locale_authors.dta
Found the same way as MIDI paths (DTA folder, then its parents), read once per pack in pack_tasks
A pack without one (vanilla GH2, Onyx DIY, RB packs) just has no table, either defaults to $author or 'unk' when missing
An entry's own {set $author ...} wins over the table, since it's specific to that song definition

GH2 MIDI reference: https://thenathannator.github.io/GuitarGame_ChartFormats/Implementation-Specific/Guitar-Hero-1-and-2/MIDI-Tracks/Guitar/
GH2 songs.dta reference: https://mariteaux.somnolescent.net/modding/guitar-hero/tutorials/adding-new-song-definitions/
GH2DX locale_authors.dta: https://github.com/Milohax-archive/Guitar-Hero-II-Deluxe/blob/2.0/_ark/ui/eng/locale_authors.dta
"""

import pathlib

from functions import library_walk
from parsers import dta, ini_parser, mid_parser, pool

DTA_FILENAME = 'songs.dta'
SOURCE_FORMAT = 'dta'

# $author values that mark an unmodified official chart
OFFICIAL_AUTHORS = {
    'harmonix', 'harmonix music systems',
    'neversoft', 'vicarious visions', 'budcat', 'budcat creations', 'freestylegames',
}

# how many folders above songs.dta to try as the pack root (config/ -> pack root is 1 up)
ROOT_SEARCH_DEPTH = 3

# locale author tables, relative to the pack root - English first, then any other language folder
LOCALE_AUTHORS_REL = 'ui/eng/locale_authors.dta'
LOCALE_AUTHORS_NAME = 'locale_authors.dta'
LOCALE_AUTHOR_SUFFIX = '_author'


class DtaPackError(ValueError):
    """Raised for a song whose chart can't be located or read."""


def is_dta_pack_filename(name):
    return name.lower() == DTA_FILENAME


# ------------------------
# Path resolution
# ------------------------

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
            found = library_walk.find_ci(root, rel)
            if found is not None:
                return found
    return None


# last resort for the main chart: first non-co-op .mid in songs/<shortname>/
def _fallback_midi(roots, song_id):
    for root in roots:
        folder = library_walk.find_ci(root, f"songs/{song_id}", want_dir=True)
        if folder is None:
            continue
        mids = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == '.mid')
        main = [p for p in mids if not p.stem.lower().endswith('_coop')]
        if main:
            return main[0]
    return None


# ------------------------
# Locale author table (GH2DX)
# ------------------------

def _find_locale_authors(roots):
    for root in roots:
        found = library_walk.find_ci(root, LOCALE_AUTHORS_REL)
        if found is not None:
            return found
    for root in roots:
        ui = library_walk.find_ci(root, 'ui', want_dir=True)
        if ui is None:
            continue
        for lang in sorted(p for p in ui.iterdir() if p.is_dir()):
            found = library_walk.find_ci(lang, LOCALE_AUTHORS_NAME)
            if found is not None:
                return found
    return None

def parse_locale_authors(text):
    authors = {}
    for entry in dta.song_entries(dta.parse(text)):
        key = entry[0].lower()
        if not key.endswith(LOCALE_AUTHOR_SUFFIX) or len(entry) < 2 or not isinstance(entry[1], str):
            continue
        shortname = key[:-len(LOCALE_AUTHOR_SUFFIX)]
        author = dta.decode_string([], entry[1]).strip()
        if shortname and author:
            authors.setdefault(shortname, author)
    return authors

def load_locale_authors(dta_path):
    locale_path = _find_locale_authors(_candidate_roots(pathlib.Path(dta_path)))
    if locale_path is None:
        return {}, None
    return parse_locale_authors(locale_path.read_bytes().decode('latin1')), locale_path


# ------------------------
# Song-level parsing
# ------------------------

def _song_meta(song_entry, song_path, locale_author=None):
    ini = dta.song_pairs(song_entry)
    variables = dta.set_vars(song_entry)

    # the entry's own $author first, the pack's locale table second
    charter = dta.decode_string(song_entry, variables.get('author')) or locale_author
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
# locale_author: this song's entry from the pack's locale_authors.dta, if the pack has one
def dta_song(dta_path, song_id, song_entry, locale_author=None):
    dta_path = pathlib.Path(dta_path)
    song_path = f"{dta_path}::{song_id}"
    roots = _candidate_roots(dta_path)

    meta_row = _song_meta(song_entry, song_path, locale_author)

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
        song_errors.append(pool.error_row(f"{song_path}::coop", exc))

    return songs, song_errors


# songs.dta -> (tasks, errors): one (dta_path, song_id, entry, locale_author) task per song entry
# the locale author table is read here once per pack, not once per song in the workers
def pack_tasks(dta_path):
    dta_path = pathlib.Path(dta_path).resolve()
    text = dta_path.read_bytes().decode('latin1')
    tasks, errors, seen = [], [], set()

    try:
        locale_authors, _locale_path = load_locale_authors(dta_path)
    except Exception as exc:
        # a broken table only costs Charter - the pack's songs still load
        locale_authors = {}
        errors.append((str(dta_path), 'LocaleAuthorsError',
                       f"locale_authors.dta unreadable, Charter falls back to $author/unk: "
                       f"{type(exc).__name__}: {exc}"))

    for entry in dta.song_entries(dta.parse(text)):
        song_id = entry[0]
        if dta.find(entry, 'song') is None or dta.find(entry, 'validate_ignore') is not None:
            continue  # not a song definition, or a GH2 tutorial lesson
        if song_id in seen:
            errors.append((f"{dta_path}::{song_id}", 'DuplicateSongId',
                           "shortname defined more than once in this songs.dta - first definition used"))
            continue
        seen.add(song_id)
        tasks.append((str(dta_path), song_id, entry, locale_authors.get(song_id.lower())))
    if not tasks:
        raise DtaPackError(f"{dta_path}: no song definitions found")
    return tasks, errors


# -----------
# Search loop - parallel per song (one pack can hold a whole setlist)
# -----------

def _dta_song_worker(task):
    dta_path, song_id = task[0], task[1]
    try:
        return dta_song(*task), None
    except Exception as exc:
        return None, pool.error_row(f"{dta_path}::{song_id}", exc)


# songs.dta files -> (ini_rows, note_index): dicts keyed by song_path for build.py
def dta_loop(files, errors=None, max_workers=None):
    errors = errors if errors is not None else []
    tasks = []
    for file in files:
        try:
            pack, pack_errors = pack_tasks(file)
            tasks.extend(pack)
            errors.extend(pack_errors)
        except Exception as exc:
            errors.append(pool.error_row(file, exc))

    results = pool.run_parallel(_dta_song_worker, tasks, "Parsing songs.dta", "song", max_workers)
    return pool.collect_songs(results, errors)
