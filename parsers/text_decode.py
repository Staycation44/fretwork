"""
TEXT_DECODE - shared text decoding for song.ini and notes.chart

Neither format declares an encoding - usually utf-8, cp1252 from older tools, utf-16 if saved from notepad
"""


def decode_text(raw):
    if raw.startswith((b'\xff\xfe', b'\xfe\xff')):
        return raw.decode('utf-16', errors='replace')
    try:
        return raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        return raw.decode('cp1252', errors='replace')


def read_text(file):
    with open(file, 'rb') as f:
        return decode_text(f.read())
