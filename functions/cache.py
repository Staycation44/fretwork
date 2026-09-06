"""
CACHE - The cache save/load pieces and retrieval code generation
BUILD writes a cache of all the song data needed from the search_path in config.py
ANALYZE and RENDER can read from caches to generate metrics/visuals

Shape:

    {
        'generated_at': str,
        'search_path':  str,
        'codes':        {code: song_path},   # code = 8-digit song hash + level letter + instrument letter
        'songs': {
            song_path: {
                'song_path':     str,
                'meta':          {...},   # trimmed ini row, incl. per-instrument Level dict (Expert-referenced)
                'source_format': 'chart' | 'mid',
                'codes':         {instrument_key: {level_key: code, ...}, ...},
                'instruments': {
                    instrument_key: {
                        level_key: {
                            'notes': {
                                'time_ms': ndarray,   # sorted
                                'lanes':   ndarray uint8,  # bitmask, bit N = lane N
                            },
                            'spans': {'star_power': [(ms, ms)...], 'solo': [...]},
                        },
                        ...  # only levels actually charted for this instrument
                    },
                    ...  # only instruments actually present for this song
                },
            },
            ...
        },
        'dropped':  {counter_name: int, ...},
    }

Every level charted for an instrument is cached (whatever combination of E/M/H/X)

Caches should be managed based on timestamp / generation time & date

When generated with errors, a CSV is produced alongside the cache with details

Retrieval codes are per the 8-digit song hash + a level (E/M/H/X) + instrument (G/C/R/B/K)
'04821993' + Expert + Bass -> '04821993XB'. 
Render uses the code to define the instrument/level

Since the 8-digit part is already unique per song before any suffix is added,
appending suffixes can't introduce a new collision between two different songs
"""

import hashlib
import pickle
from datetime import datetime

from functions import instruments

# Hash-derived retrieval codes digit length (pre level/instrument suffix)
CODE_LEN = 8
SUFFIX_LEN = 2  # level letter + instrument letter

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


# Builds the full song+instrument+level -> code map for every
# (song_path, instrument_key, level_key) triple present
def assign_codes(song_instrument_level_triples, digits=None):
    triples = list(song_instrument_level_triples)
    song_paths = sorted({song_path for song_path, _, _ in triples})
    song_codes = assign_song_codes(song_paths, digits)

    codes = {}
    for song_path, instrument_key, level_key in triples:
        suffix = (
            instruments.LEVEL_CODE_SUFFIX[level_key]
            + instruments.CODE_SUFFIX[instrument_key]
        )
        codes[(song_path, instrument_key, level_key)] = song_codes[song_path] + suffix

    assert len(set(codes.values())) == len(codes), "song+instrument+level code collision"
    return codes

# Persistence
def save(cache, cache_path):
    with open(cache_path, 'wb') as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)
    return cache_path

def load(cache_path):
    with open(cache_path, 'rb') as f:
        return pickle.load(f)

# Lookup retrieval codes - str or int w/ zero padding
# '421XB' and '00000421XB' both work, Last 2 chars are level & instrument
def entries_by_code(cache, codes):
    entries = []
    missing = []

    for raw in codes:
        raw = str(raw).strip()

        if len(raw) < SUFFIX_LEN + 1 or not raw[-1].isalpha() or not raw[-2].isalpha():
            missing.append(raw)
            continue

        instrument_letter = raw[-1].upper()
        level_letter = raw[-2].upper()

        if (instrument_letter not in instruments.SUFFIX_TO_INSTRUMENT
                or level_letter not in instruments.SUFFIX_TO_LEVEL):
            missing.append(raw)
            continue

        digits_part = raw[:-SUFFIX_LEN].zfill(CODE_LEN)
        full_code = digits_part + level_letter + instrument_letter

        song_path = cache['codes'].get(full_code)
        if song_path is None:
            missing.append(raw)
            continue

        song = cache['songs'].get(song_path)
        instrument_key = instruments.SUFFIX_TO_INSTRUMENT[instrument_letter]
        level_key = instruments.SUFFIX_TO_LEVEL[level_letter]

        instrument_levels = (song or {}).get('instruments', {}).get(instrument_key, {})
        inst_entry = instrument_levels.get(level_key)
        if inst_entry is None:
            missing.append(raw)
            continue

        # Expert's own note stream, alongside the requested level 
        # RemapDiff/CalcTier are anchored to Expert row's data
        # None if this instrument has no Expert chart
        expert_notes = instrument_levels.get('expert', {}).get('notes')

        entries.append({
            **inst_entry,
            'code': full_code,
            'song_path': song_path,
            'instrument': instrument_key,
            'level': level_key,
            'meta': song['meta'],
            'source_format': song['source_format'],
            'expert_notes': expert_notes,
        })

    return entries, missing
