"""
MID_REPAIR - rewrites a .mid that mido can't read but plays in-game

Found on GH: WoR DLC and other converted charts, two faults:
    - the header declares more tracks than the file holds (mido reads past the end of the file)
    - running status carried across a SysEx or meta event

repair(data) re-reads every chunk, keeps the running status across SysEx and meta events,
writes every event with an explicit status byte, recomputes each track's length, 
adds an end-of-track event where one is missing, drops an event cut off by the end of its chunk, 
and sets the header's track count to the tracks actually present. Returns the repaired bytes and a list of what was changed.

Used two ways (see mid_parser._read_midi):
    - always when mido can't read the original
    - up front when sysex_carries(data) finds running status straight after a SysEx event
"""

import struct


class RepairError(ValueError):
    pass


def _vlq(buf, i):
    value = 0
    for _ in range(4):
        byte = buf[i]
        i += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, i
    raise RepairError("variable-length number longer than 4 bytes")


def _write_vlq(value):
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append(0x80 | (value & 0x7F))
        value >>= 7
    return bytes(reversed(out))


def _events(body):
    """-> ([(delta, event bytes with explicit status)], notes) for one track body"""
    events, i, status, notes = [], 0, None, []
    after_sys, carried = False, 0          # running status used straight after a SysEx or meta event
    after_sysex, sysex_carried = False, 0  # the same, counted only after a SysEx event (what mido misreads)
    while i < len(body):
        try:
            start = i
            delta, i = _vlq(body, i)
            lead = body[i]
            if lead == 0xFF:
                kind = body[i + 1]
                length, j = _vlq(body, i + 2)
                if j + length > len(body):
                    raise IndexError
                events.append((delta, bytes([0xFF, kind]) + _write_vlq(length) + body[j:j + length]))
                i = j + length
                after_sys = True
                after_sysex = False
                if kind == 0x2F:
                    return events, _carried(notes, carried), sysex_carried
            elif lead in (0xF0, 0xF7):
                length, j = _vlq(body, i + 1)
                if j + length > len(body):
                    raise IndexError
                events.append((delta, bytes([lead]) + _write_vlq(length) + body[j:j + length]))
                i = j + length
                after_sys = after_sysex = True
            else:
                if lead & 0x80:
                    status = lead
                    i += 1
                elif status is None:
                    raise RepairError(f"data byte with no status at track byte {start}")
                else:
                    carried += after_sys
                    sysex_carried += after_sysex
                after_sys = after_sysex = False
                size = 1 if status & 0xF0 in (0xC0, 0xD0) else 2
                if i + size > len(body):
                    raise IndexError
                events.append((delta, bytes([status]) + body[i:i + size]))
                i += size
        except IndexError:
            notes.append(f"event cut off at track byte {start} dropped")
            break
    notes.append("end-of-track added")
    events.append((0, b"\xff\x2f\x00"))
    return events, _carried(notes, carried), sysex_carried


def _carried(notes, carried):
    if carried:
        notes.append(f"running status carried across a SysEx or meta event {carried} times")
    return notes


def sysex_carries(data):
    """-> how many events use running status straight after a SysEx event (0 when there's no SysEx)"""
    if b"\xf0" not in data and b"\xf7" not in data:
        return 0
    try:
        return _repair(data)[2]
    except (RepairError, IndexError):
        return 0


def repair(data):
    """-> (repaired bytes, [what was changed]); raises RepairError when the file isn't a MIDI file"""
    fixed, fixes, _sysex_carried = _repair(data)
    return fixed, fixes


def _repair(data):
    data = bytes(data)
    if data[:4] != b"MThd" or len(data) < 14:
        raise RepairError("no MThd header")
    header_len = struct.unpack(">I", data[4:8])[0]
    fmt, declared, division = struct.unpack(">HHH", data[8:14])
    i, tracks, fixes, sysex_carried = 8 + header_len, [], [], 0
    while i + 8 <= len(data):
        chunk_id, length = data[i:i + 4], struct.unpack(">I", data[i + 4:i + 8])[0]
        body = data[i + 8:i + 8 + length]
        if len(body) < length:
            fixes.append(f"track {len(tracks)}: chunk runs past the end of the file")
        i += 8 + length
        if chunk_id != b"MTrk":
            fixes.append(f"non-track chunk {chunk_id!r} skipped")
            continue
        events, notes, carried = _events(body)
        sysex_carried += carried
        fixes += [f"track {len(tracks)}: {n}" for n in notes]
        tracks.append(b"".join(_write_vlq(delta) + event for delta, event in events))
    if not tracks:
        raise RepairError("no track chunks")
    if declared != len(tracks):
        fixes.append(f"header declared {declared} tracks, file holds {len(tracks)}")
    out = bytearray(b"MThd" + struct.pack(">IHHH", 6, fmt, len(tracks), division))
    for track in tracks:
        out += b"MTrk" + struct.pack(">I", len(track)) + track
    return bytes(out), fixes, sysex_carried
