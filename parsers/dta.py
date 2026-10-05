"""
DTA - Shared text DTA parsing for rb3con_parser and dta_parser

DTA is Harmonix's script format. songs.dta holds one top-level entry per song:
    (shortname (name "Title") (artist "Artist") (song (name songs/x/x) (midi_file songs/x/x.mid)) ...)

Three bracket kinds nest the same way here:
    ( )  arrays
    { }  commands, e.g. GH2 customs' {do {set $author "..."}} metadata blocks inside 'artist'
    [ ]  macros/properties
Everything parses into nested Python lists; quoted strings and bare symbols both come back as str

Field reference: https://rock-band-customs.gitlab.io/authoring-dtas.html
GH2 songs.dta reference: https://mariteaux.somnolescent.net/modding/guitar-hero/tutorials/adding-new-song-definitions/
"""

OPENERS = '({['
CLOSERS = ')}]'
_DELIMS = OPENERS + CLOSERS + ';"\''


class DtaError(ValueError):
    """Raised for malformed DTA text."""


def tokenize(text):
    tokens = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif c == ';':
            while i < n and text[i] not in '\r\n':
                i += 1
        elif c in OPENERS:
            tokens.append('(')
            i += 1
        elif c in CLOSERS:
            tokens.append(')')
            i += 1
        elif c in '"\'':
            j = text.find(c, i + 1)
            j = n if j == -1 else j
            tokens.append(text[i + 1:j])
            i = j + 1
        else:
            j = i
            while j < n and not text[j].isspace() and text[j] not in _DELIMS:
                j += 1
            tokens.append(text[i:j])
            i = j
    return tokens


def parse(text):
    tokens = tokenize(text)
    pos = [0]

    def parse_expr():
        if pos[0] >= len(tokens):
            raise DtaError("unexpected end of DTA data")
        tok = tokens[pos[0]]
        if tok == '(':
            pos[0] += 1
            items = []
            while pos[0] < len(tokens) and tokens[pos[0]] != ')':
                items.append(parse_expr())
            if pos[0] >= len(tokens):
                raise DtaError("unbalanced brackets in DTA data")
            pos[0] += 1  # consume closer
            return items
        pos[0] += 1
        return tok

    top = []
    while pos[0] < len(tokens):
        if tokens[pos[0]] == ')':
            raise DtaError("unbalanced brackets in DTA data")
        top.append(parse_expr())
    return top


# Top-level song entries only: (shortname ...) lists - stray top-level symbols (e.g. #define lines) are skipped
def song_entries(tree):
    return [entry for entry in tree if isinstance(entry, list) and entry and isinstance(entry[0], str)]


# tree is a list of parsed items at one nesting level
def find(tree, key):
    for item in tree:
        if isinstance(item, list) and item and isinstance(item[0], str) and item[0].lower() == key:
            return item[1:]
    return None


def find_value(tree, key, default=None):
    found = find(tree, key)
    return found[0] if found else default


# Plain text value for a field, skipping any nested command/array
def find_text(tree, key, default=None):
    found = find(tree, key)
    if not found:
        return default
    for item in reversed(found):
        if isinstance(item, str):
            return item
        branch = _if_else_branch(item)
        if branch is not None:
            return branch
    return default


def _if_else_branch(item):
    if (isinstance(item, list) and len(item) == 4 and isinstance(item[0], str)
            and item[0].lower() == 'if_else' and isinstance(item[3], str)):
        return item[3]
    return None


# {set $var value} commands anywhere in an entry -> {'author': value, ...} ($ stripped, lowercased)
# GH2 customs (GH2 Deluxe / Onyx DIY packs) carry author, album, origin and rank values this way
def set_vars(tree):
    found = {}

    def walk(node):
        if not isinstance(node, list):
            return
        if (len(node) >= 3 and isinstance(node[0], str) and node[0].lower() == 'set'
                and isinstance(node[1], str) and node[1].startswith('$') and isinstance(node[2], str)):
            found.setdefault(node[1][1:].lower(), node[2])
            return
        for child in node:
            walk(child)

    walk(tree)
    return found


# Re-decodes a DTA string per the entry's (encoding ...) tag - text is first read as latin1
#   (encoding utf8)   -> re-decoded as utf-8
#   (encoding latin1) -> kept as latin1
#   undeclared        -> utf-8 if the bytes are valid utf-8 (some custom tools skip the tag), else latin1
def decode_string(song_entry, value):
    if value is None:
        return None
    raw = value.encode('latin1')
    declared = find_value(song_entry, 'encoding')
    encoding = str(declared).strip().lower() if isinstance(declared, str) else None
    if encoding in ('utf8', 'utf-8'):
        return raw.decode('utf-8', errors='replace')
    if encoding is None:
        try:
            return raw.decode('utf-8')
        except UnicodeDecodeError:
            pass
    return value
