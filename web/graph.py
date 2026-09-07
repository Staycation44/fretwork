"""
GRAPH - renders one chart's PNG on demand, caching within the process

Owns the note cache and the PNG memo, so two renderers cannot split them.
"""

import pathlib
import threading

import config
from functions import cache as cache_mod
from functions import difficulty, timestamp


class GraphRenderer:
    """Renders retrieval codes to PNG bytes, loading the cache once, lazily."""

    def __init__(self, header, cache_path=None, out_dir=None):
        self.header = header
        self.cache_path = cache_path
        self.out_dir = out_dir or config.RENDER_DIR
        self._cache = None
        self._diffs = None
        self._png = {}
        self._lock = threading.Lock()

    # None when the code is unknown or the chart has no curve data.
    def png(self, code):
        if code in self._png:
            return self._png[code]
        with self._lock:
            if code in self._png:
                return self._png[code]
            data = self._render(code)
            if data is not None:
                self._png[code] = data
            return data

    def _render(self, code):
        # plot pulls matplotlib, so it stays off the startup path
        from functions import curves as curves_mod
        from functions import plot

        entries, _missing = cache_mod.entries_by_code(self.cache(), [code])
        if not entries:
            return None

        entry = entries[0]
        song_curves = curves_mod.calc_curves(entry['notes'])
        if song_curves is None:
            return None

        png_path = plot.render_song(
            entry, song_curves, difficulty.entry_difficulty(entry),
            original_diff=self.original_diff(entry), out_dir=self.out_dir)
        return pathlib.Path(png_path).read_bytes()

    def cache(self):
        if self._cache is None:
            path = self.cache_path or timestamp.latest_output(
                'cache', self.header, ext='pkl')
            self._cache = cache_mod.load(path)
        return self._cache

    # The backed-up song.ini tier shown in the render header.
    def original_diff(self, entry):
        from functions import ini_updater

        if self._diffs is None:
            self._diffs = ini_updater.load_backup_diffs(self.header, config.CACHE_DIR)
        return self._diffs.get(entry['song_path'], {}).get(entry['instrument'])
