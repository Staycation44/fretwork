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


# every file under search_path whose name passes match(name), as pathlib.Path
def library_files(search_path, match):
    for dirpath, _dirnames, filenames in walk_library(search_path):
        for name in filenames:
            if match(name):
                yield pathlib.Path(dirpath, name)


def name_is(filename):
    wanted = filename.lower()
    return lambda name: name.lower() == wanted

def ext_in(exts):
    wanted = tuple(ext.lower() for ext in exts)
    return lambda name: os.path.splitext(name)[1].lower() in wanted

def find_in_folder(folder, filename):
    folder = pathlib.Path(folder)
    exact = folder / filename
    if exact.is_file():
        return exact
    wanted = filename.lower()
    try:
        for entry in os.scandir(folder):
            if entry.name.lower() == wanted and entry.is_file():
                return folder / entry.name
    except OSError:
        pass
    return None
