"""
RB3CON_PARSER - Reads RB3 STFS packages into the same metadata-row / note-stream shapes expected by build.py

STFS block-address math (_fix_blocknum/_get_blockhash) is adapted from arkem/py360: https://github.com/arkem/py360
whose own credited source is the Free60 project's STFS documentation: https://free60.org/System-Software/Formats/STFS/

Only the .mid and songs.dta entries inside a song's folder are ever read 
.mogg (audio) is never opened & often encrypted

DTA metadata (songs.dta) reference: https://rock-band-customs.gitlab.io/authoring-dtas.html
DTA text parsing lives in parsers/dta.py (shared with dta_parser)

One container can hold multiple songs
each song folder under /songs/ is matched to its own entry in songs.dta by its internal song-id symbol
song_path for each is f"{container path}::{song_id}" since there's no per-song file to key against
A song that fails inside a multi-song pack is logged on its own, the rest should still load

DIFFICULTY: DTA rank values are RB3's own internal difficulty scores
RANK_DIFF_MAPS (to bring them back into 0-6 range) was checked against the above dta gitlab,
https://github.com/mtolly/onyx and https://github.com/StackOverflow0x/RB3-Difficulty-Slider

this module does no note-level work itself, just hands data to the parsers
RB3's core-instrument MIDI track names match what mid_parser expects unchanged
"""

import concurrent.futures as cf
import os
import pathlib
import struct

import tqdm

from functions import instruments
from parsers import dta, ini_parser, mid_parser

STFS_MAGICS = (b'CON ', b'LIVE', b'PIRS')

# rb3cons are commonly distributed with no file extension
FILENAME_SUFFIXES = ('_rb3con', '.rb3con')

# RB3 rank->tier breakpoints
RANK_DIFF_MAPS = {
    'drums':  [124, 151, 178, 242, 345, 448],
    'vocals': [132, 175, 218, 279, 353, 427],
    'bass':   [135, 181, 228, 293, 364, 436],
    'guitar': [139, 176, 221, 267, 333, 409],
    'keys':   [153, 211, 269, 327, 385, 443],
    'band':   [163, 215, 243, 267, 292, 345],
}

# DTA rank block key -> Fretwork instrument key
# pro/real insts OOS
RANK_KEY_TO_INSTRUMENT = {
    'drum': 'drums', 'guitar': 'guitar', 'bass': 'bass',
    'vocals': 'vocals', 'keys': 'keys', 'band': 'band',
}


class Rb3ConError(ValueError):
    """Raised for a malformed/unrecognized .rb3con package."""


def is_rb3con_filename(name):
    lname = name.lower()
    return any(lname.endswith(suffix) for suffix in FILENAME_SUFFIXES)


# rank -> tier, on song.ini's 0-6 diff tag scale
def _rank_to_tier(diff_map, rank):
    tier = 0
    for threshold in (1, *diff_map):
        if threshold > rank:
            break
        tier += 1
    return tier - 1 if tier else 0


# ------------------------
# STFS container reading
# ------------------------

def _read_exact(f, n, what):
    data = f.read(n)
    if len(data) != n:
        raise Rb3ConError(f"truncated while reading {what} ({len(data)}/{n} bytes)")
    return data


class _BlockHash:
    __slots__ = ('info', 'nextblock')

    def __init__(self, data):
        self.info = data[0x14]
        self.nextblock = struct.unpack(">I", b'\x00' + data[0x15:0x18])[0]


class _FileEntry:
    __slots__ = ('name', 'isdirectory', 'firstblock', 'pathindex', 'size')

    def __init__(self, data):
        self.name = data[:0x28].rstrip(b'\x00').decode('utf-8', errors='replace')
        if not self.name:
            raise Rb3ConError("empty filename in file table")
        self.isdirectory = (data[0x28] & 0x80) == 0x80
        self.firstblock = struct.unpack("<I", data[0x2F:0x2F + 3] + b'\x00')[0]
        self.pathindex = struct.unpack(">h", data[0x32:0x34])[0]
        self.size = struct.unpack(">I", data[0x34:0x38])[0]


# The block-address math in this class (_fix_blocknum, _get_blockhash, _read_filetable_chain)
# adapted from arkem/py360 (https://github.com/arkem/py360)
# py360 is used under its license:
#
#   Copyright 2011 Arkem. All rights reserved.
#
#   Redistribution and use in source and binary forms, with or without modification, are
#   permitted provided that the following conditions are met:
#
#   Redistributions of source code must retain the above copyright notice, this list of
#   conditions and the following disclaimer. Redistributions in binary form must reproduce the
#   above copyright notice, this list of conditions and the following disclaimer in the
#   documentation and/or other materials provided with the distribution.
#
#   THIS SOFTWARE IS PROVIDED ``AS IS'' AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT
#   NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
#   PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE AUTHOR OR CONTRIBUTORS BE LIABLE FOR ANY
#   DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT
#   NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
#   OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
#   CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY
#   OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

class _Stfs:
    def __init__(self, path):
        self.path = path
        self.fd = open(path, 'rb')
        try:
            self._open()
        except BaseException:
            self.fd.close()
            raise

    def _open(self):
        magic = self.fd.read(4)
        if magic not in STFS_MAGICS:
            raise Rb3ConError(f"not an STFS package (bad magic {magic!r})")
        self.fd.seek(0)
        header = self.fd.read(0x971A)
        if len(header) < 0x971A:
            raise Rb3ConError("truncated STFS header")

        entry_id = struct.unpack(">I", header[0x340:0x344])[0]
        self.table_size_shift = 0 if ((entry_id + 0xFFF) & 0xF000) >> 0xC == 0xB else 1
        self.table_spacing = ((0xAB, 0x718F, 0xFE7DA), (0xAC, 0x723A, 0xFD00B))

        self.filetable_blockcount = struct.unpack("<H", header[0x37C:0x37E])[0]
        self.filetable_blocknumber = struct.unpack("<I", header[0x37E:0x381] + b'\x00')[0]
        self.allocated_count = struct.unpack(">I", header[0x395:0x399])[0]

        self._parse_filetable()

    def close(self):
        self.fd.close()

    def _read_block(self, blocknum, length=0x1000):
        self.fd.seek(0xC000 + blocknum * 0x1000)
        return self.fd.read(length)

    def _fix_blocknum(self, block_num):
        adjust = 0
        if block_num >= 0xAA:
            adjust += ((block_num // 0xAA) + 1) << self.table_size_shift
        if block_num >= 0x70E4:
            adjust += ((block_num // 0x70E4) + 1) << self.table_size_shift
        return adjust + block_num

    def _get_blockhash(self, blocknum, table_offset=0):
        record = blocknum % 0xAA
        tablenum = blocknum // 0xAA * self.table_spacing[self.table_size_shift][0]
        if blocknum >= 0xAA:
            tablenum += (blocknum // 0x70E4 + 1) << self.table_size_shift
            if blocknum >= 0x70E4:
                tablenum += 1 << self.table_size_shift
        tablenum += table_offset - (1 << self.table_size_shift)
        hashdata = self._read_block(tablenum)
        return _BlockHash(hashdata[record * 0x18: record * 0x18 + 0x18])

    # File table's first block is conventionally block 0
    def _read_filetable_chain(self, firstblock, numblocks):
        buf = bytearray()
        block = firstblock
        for _ in range(numblocks):
            buf += self._read_block(self._fix_blocknum(block), 0x1000)
            blockhash = self._get_blockhash(block)
            if self.table_size_shift > 0 and blockhash.info < 0x80:
                blockhash = self._get_blockhash(block, 1)
            block = blockhash.nextblock
        return bytes(buf)

    def _read_chain(self, firstblock, size):
        buf = bytearray()
        block = firstblock
        info = 0x80
        remaining = size
        while remaining > 0 and 0 < block < self.allocated_count and info >= 0x80:
            readlen = min(0x1000, remaining)
            buf += self._read_block(self._fix_blocknum(block), readlen)
            remaining -= readlen
            blockhash = self._get_blockhash(block)
            if self.table_size_shift > 0 and blockhash.info < 0x80:
                blockhash = self._get_blockhash(block, 1)
            block = blockhash.nextblock
            info = blockhash.info
        return bytes(buf)

    def _parse_filetable(self):
        raw = self._read_filetable_chain(self.filetable_blocknumber, self.filetable_blockcount)
        entries = []
        for i in range(0, len(raw), 0x40):
            chunk = raw[i:i + 0x40]
            if len(chunk) < 0x40 or chunk[0] == 0:
                continue
            try:
                entries.append(_FileEntry(chunk))
            except Rb3ConError:
                continue

        self.entries = entries
        self.paths = {}
        for entry in entries:
            parts = [entry.name]
            cur = entry
            while cur.pathindex != -1 and cur.pathindex < len(entries):
                cur = entries[cur.pathindex]
                parts.append(cur.name)
            parts.reverse()
            self.paths['/'.join(parts)] = entry

    def read_file(self, entry):
        return self._read_chain(entry.firstblock, entry.size)


# --------------------
# Song-level parsing
# --------------------

def _difficulties_from_rank(song_entry):
    rank_pairs = dta.find(song_entry, 'rank') or []
    diffs = {}
    for pair in rank_pairs:
        if not isinstance(pair, list) or len(pair) < 2:
            continue
        rank_key = str(pair[0]).lower()
        instrument_key = RANK_KEY_TO_INSTRUMENT.get(rank_key)
        if instrument_key is None:
            continue
        try:
            rank = int(float(pair[1]))
        except (TypeError, ValueError):
            continue
        diff_map = RANK_DIFF_MAPS[instrument_key]
        diffs[instruments.DIFF_TAGS[instrument_key]] = str(_rank_to_tier(diff_map, rank))
    return diffs


# One song within a container -> (meta_row, note_stream), matching ini_parser/mid_parser's own output shapes
def _rb3con_song(stfs, song_id, song_entry, folder_path):
    song_path = f"{stfs.path}::{song_id}"

    ini = _difficulties_from_rank(song_entry)
    name = dta.decode_string(song_entry, dta.find_text(song_entry, 'name'))
    artist = dta.decode_string(song_entry, dta.find_text(song_entry, 'artist'))
    if name:
        ini['name'] = name
    if artist:
        ini['artist'] = artist
    meta_row = ini_parser.ini_metadata_from_pairs(ini, song_path)

    mid_entry = next(
        (e for path, e in stfs.paths.items()
         if path.startswith(folder_path + '/') and path.lower().endswith('.mid') and not e.isdirectory),
        None)
    if mid_entry is None:
        raise Rb3ConError(f"{song_path}: no .mid file found under {folder_path}")

    mid_bytes = stfs.read_file(mid_entry)
    note_stream = mid_parser.mid_notes_from_bytes(mid_bytes, song_path, warn_label=f"{song_path}!{mid_entry.name}")
    return meta_row, note_stream


# Parses every song in one .rb3con -> (results, song_errors)
#   results:     list of (meta_row, note_stream) pairs, allows for multi songs packs
#   song_errors: (song_path, error, message) for songs in the pack that failed on their own
def rb3con_songs(path):
    path = str(pathlib.Path(path).resolve())
    stfs = _Stfs(path)
    try:
        dta_entry = next(
            (e for p, e in stfs.paths.items() if p.lower().endswith('songs.dta') and not e.isdirectory),
            None)
        if dta_entry is None:
            raise Rb3ConError(f"{path}: no songs.dta found in package")
        dta_text = stfs.read_file(dta_entry).decode('latin1')
        dta_songs = {entry[0]: entry for entry in dta.song_entries(dta.parse(dta_text))}

        song_folders = {
            p[len('songs/'):].split('/', 1)[0]: f"songs/{p[len('songs/'):].split('/', 1)[0]}"
            for p, e in stfs.paths.items()
            if e.isdirectory and p.lower().startswith('songs/') and p.count('/') == 1 and p != 'songs'
        }

        results = []
        song_errors = []
        matched = 0
        for song_id, folder_path in song_folders.items():
            song_entry = dta_songs.get(song_id)
            if song_entry is None:
                continue
            matched += 1
            try:
                results.append(_rb3con_song(stfs, song_id, song_entry, folder_path))
            except Exception as exc:
                # one broken song doesn't remove the pack
                song_errors.append((f"{path}::{song_id}", type(exc).__name__, str(exc) or repr(exc)))

        if not matched:
            raise Rb3ConError(f"{path}: no song folders matched an entry in songs.dta")
        return results, song_errors
    finally:
        stfs.close()


# -----------
# Search loop - parallel, same shape as sng_loop
# -----------

def _rb3con_worker(file):
    try:
        return rb3con_songs(file), None
    except Exception as exc:
        return None, (str(file), type(exc).__name__, str(exc) or repr(exc))


def _resolve_workers(max_workers):
    if max_workers is not None:
        return max(1, int(max_workers))
    return max(1, (os.cpu_count() or 1) - 1)


# Returns (ini_rows, note_index): dicts keyed by song_path for build.py
def rb3con_loop(search_path, errors=None, max_workers=None, files=None):
    ini_rows = {}
    note_index = {}

    if files is None:
        files = [p for p in pathlib.Path(search_path).rglob("*") if p.is_file() and is_rb3con_filename(p.name)]

    if not files:
        return ini_rows, note_index

    workers = _resolve_workers(max_workers)
    chunksize = max(1, len(files) // (workers * 4))

    with cf.ProcessPoolExecutor(max_workers=workers) as pool:
        results = pool.map(_rb3con_worker, files, chunksize=chunksize)
        for result, error in tqdm.tqdm(results, total=len(files), desc="Parsing rb3con", unit="file"):
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
