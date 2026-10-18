"""
LIBRARY_WALK - common library-walking functions for build.py and ini_updater.py

Follows directory symlinks (Linux symbolic links) and Windows junctions visiting each directory once
Directories are keyed by (device, inode) so a linked loop ends and a folder reached through two links isn't parsed twice
"""

import os
import pathlib


def walk_library(search_path):
    seen = set()
    for dirpath, dirnames, filenames in os.walk(search_path, followlinks=True):
        try:
            st = os.stat(dirpath)
        except OSError:
            dirnames[:] = []
            continue
        if st.st_ino:
            key = (st.st_dev, st.st_ino)
            if key in seen:     # symlink cycle, or a second link to an already-walked folder
                dirnames[:] = []
                continue
            seen.add(key)
        yield dirpath, dirnames, filenames


def find_ci(root, rel, want_dir=False):
    cur = pathlib.Path(root)
    for part in pathlib.PurePosixPath(str(rel).replace('\\', '/')).parts:
        if part in ('', '.'):
            continue
        candidate = cur / part
        if not candidate.exists():
            candidate = _entry_ci(cur, part)
            if candidate is None:
                return None
        cur = candidate
    found = cur.is_dir() if want_dir else cur.is_file()
    return cur if found else None


def _entry_ci(folder, name):
    wanted = name.lower()
    try:
        for entry in os.scandir(folder):
            if entry.name.lower() == wanted:
                return pathlib.Path(folder, entry.name)
    except OSError:
        pass
    return None
