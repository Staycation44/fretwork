"""
CACHE - The cache save/load pieces and retrieval code generation
BUILD writes a cache of all the song data needed from the search_path in config.py
ANALYZE and RENDER can read from caches to generate metrics/visuals

Shape:

    {
        'generated_at': str,
        'search_path':  str,
        'codes':        {code: song_path},   # code = 8-digit song hash + instrument suffix
        'songs': {
            song_path: {
                'song_path':     str,
                'meta':          {...},   # trimmed ini row, incl. per-instrument Difficulty dict
                'source_format': 'chart' | 'mid',
                'codes':         {instrument_key: code, ...},
                'instruments': {
                    instrument_key: {
                        'notes': {
                            'time_ms': ndarray,   # sorted
                            'lanes':   ndarray uint8,  # bitmask, bit N = lane N
                        },
                        'spans': {'star_power': [(ms, ms)...], 'solo': [...]},
                    },
                    ...  # only instruments actually present for this song
                },
            },
            ...
        },
        'dropped':  {counter_name: int, ...},
    }

Caches should be managed based on timestamp / generation time & date

When generated with errors, a CSV is produced alongside the cache with details

Retrieval codes are per (song, instrument): the 8-digit song hash with a single-letter instrument suffix 
Render can go straight from a code to the right instrument's note stream without a separate flag

Since the 8-digit part is already unique per song before any suffix is added, 
appending a suffix can't introduce a new collision between two different songs
"""

import hashlib
import pickle
from datetime import datetime

from functions import instruments

# Hash-derived retrieval codes digit length (pre instrument suffix)
CODE_LEN = 8

def gen_ts():
    return datetime.now().strftime("%m%d%Y-%H%M")

# Retrieval codes
def _hash_code(song_path, digits):
    digest = hashlib.sha1(song_path.encode('utf-8')).hexdigest()
    return int(digest, 16) % (10 ** digits)

# assigns the numeric 8-digit code per song
def assign_song_codes(song_paths, digits=None):
    digits = digits or CODE_LEN
    span = 10 ** digits

    song_paths = list(song_paths)
    if len(song_paths) > span // 2:
        raise ValueError(
            f"{len(song_paths)} songs is too many for {digits}-digit codes; "
            f"raise cache.CODE_LEN"
        )

    taken = {}
    for song_path in sorted(song_paths):
        code_int = _hash_code(song_path, digits)
        while code_int in taken:
            code_int = (code_int + 1) % span
        taken[code_int] = song_path

    codes = {path: str(code).zfill(digits) for code, path in taken.items()}

    assert len(set(codes.values())) == len(codes), "code collision survived probing"
    return codes


# Builds the full song+instrument -> code map for every (song_path, instrument_key) pair
def assign_codes(song_instrument_pairs, digits=None):
    song_instrument_pairs = list(song_instrument_pairs)
    song_paths = sorted({song_path for song_path, _ in song_instrument_pairs})
    song_codes = assign_song_codes(song_paths, digits)

    codes = {}
    for song_path, instrument_key in song_instrument_pairs:
        suffix = instruments.CODE_SUFFIX[instrument_key]
        codes[(song_path, instrument_key)] = song_codes[song_path] + suffix

    assert len(set(codes.values())) == len(codes), "song+instrument code collision"
    return codes

# Persistence
def save(cache, cache_path):
    with open(cache_path, 'wb') as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)
    return cache_path

def load(cache_path):
    with open(cache_path, 'rb') as f:
        return pickle.load(f)

# Lookup retrieval codes - str or int w/ zero padding on the numeric part, so '421B' and '00000421B' both work
def entries_by_code(cache, codes):
    entries = []
    missing = []

    for raw in codes:
        raw = str(raw).strip()

        if not raw or not raw[-1].isalpha() or raw[-1].upper() not in instruments.SUFFIX_TO_INSTRUMENT:
            missing.append(raw)
            continue

        suffix = raw[-1].upper()
        digits_part = raw[:-1].zfill(CODE_LEN)
        full_code = digits_part + suffix

        song_path = cache['codes'].get(full_code)
        if song_path is None:
            missing.append(raw)
            continue

        song = cache['songs'].get(song_path)
        instrument_key = instruments.SUFFIX_TO_INSTRUMENT[suffix]
        inst_entry = (song or {}).get('instruments', {}).get(instrument_key)
        if inst_entry is None:
            missing.append(raw)
            continue

        entries.append({
            **inst_entry,
            'code': full_code,
            'song_path': song_path,
            'instrument': instrument_key,
            'meta': song['meta'],
            'source_format': song['source_format'],
        })

    return entries, missing
