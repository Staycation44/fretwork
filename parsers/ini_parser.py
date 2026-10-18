"""
INI_PARSER - Parses song.ini files for metadata (name/artist/charter/difficulty/release)

Difficulty is captured per-instrument (see instruments.DIFF_TAGS)

Source tables (gh/rb/ch) and html-tag cleanup regex live here
"""

import pathlib
import re

import tqdm

from functions import instruments
from parsers import pool, text_decode

# --------------
# Source tables
# --------------
BASE_DIR = pathlib.Path(__file__).resolve().parent.parent
SOURCES_DIR = BASE_DIR / "sources"

SOURCE_FILES = [
    ("gh.txt", True),          # Guitar Hero officials
    ("rb.txt", True),          # Rock Band officials
    ("sources.txt", False),    # Clone Hero community icons list
]

_RELEASE_SOURCES = None

def load_sources(path):
    table = {}
    with open(path, encoding='utf-8', errors='replace') as data:
        for line in data:
            line = line.strip()
            if ' = ' in line:
                key, value = line.split(' = ', 1)
                table[key] = value
    return table


def release_sources():
    global _RELEASE_SOURCES
    if _RELEASE_SOURCES is None:
        _RELEASE_SOURCES = []
        for filename, is_official in SOURCE_FILES:
            path = SOURCES_DIR / filename
            if path.exists():
                _RELEASE_SOURCES.append((load_sources(path), is_official))
            else:
                print(f"  [warn] source table missing, Release will be incomplete: {path}")
    return _RELEASE_SOURCES


# regex to strip html tags from ini metadata fields
DETAG = re.compile(r"<.*?>")


# --------
# Parsing
# --------

# key = value parse
# configparser chokes on % and line breaks in loading_phrase so was removed
# [section] lines skipped (only ever [song]), keys lowercased, last dupe wins
def parse_ini(file):
    ini = {}
    for line in text_decode.read_text(file).splitlines():
        line = line.strip()
        if not line or line[0] in ';#[':
            continue
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        ini[key.strip().lower()] = value.strip()
    return ini


# Builds one metadata row from an already-parsed {lowercased key: value} dict
# shared for song.ini and .sng metadata
def ini_metadata_from_pairs(ini, song_path):
    if not ini:
        raise ValueError(f"No key = value metadata found for {song_path}")

    # clean up tags & fix missing data, hard codes for malformed or missing
    name = DETAG.sub("", ini.get('name', 'unk'))
    artist = DETAG.sub("", ini.get('artist', 'unk'))
    charter = DETAG.sub("", ini.get('charter', 'unk'))
    icon = ini.get('icon', '')

    # one difficulty value per instrument, keyed the same way as everywhere else
    difficulties = {
        instrument_key: ini.get(diff_tag)
        for instrument_key, diff_tag in instruments.DIFF_TAGS.items()
    }

    # determine source and mark as official or not
    release, official = "Custom", False
    for source_dict, is_official in release_sources():
        if icon in source_dict:
            release = source_dict[icon]
            official = is_official
            break

    return {
        'SongPath': song_path,
        'Name': name,
        'Artist': artist,
        'Charter': charter,
        'Difficulty': difficulties,
        'Release': release,
        'Official': official,
    }


def ini_metadata(file):
    ini = parse_ini(file)
    # Song folder identity - full resolved path to account for duplicate songs across different sources
    song_path = str(file.parent.resolve())
    return ini_metadata_from_pairs(ini, song_path)

# -----------
# Search loop
# -----------

# song.ini files -> {song_path: metadata row}, errors appended to errors
def ini_loop(files, errors=None):
    ini_out = {}
    for file in tqdm.tqdm(files, desc="Gathering ini data", unit="file"):
        try:
            row = ini_metadata(file)
            ini_out[row['SongPath']] = row
        except Exception as exc:
            if errors is not None:
                errors.append(pool.error_row(file, exc))

    return ini_out
