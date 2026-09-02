"""
RENDER - one PNG per retrieval code based on settings in config + plot

Takes codes from the ANALYZE workbook and writes an individual PNG for each. 
Codes are an 8-digit song hash plus a single-letter instrument suffix
G for guitar, B for bass, K for keys

    python render.py 04821993G
    python render.py 04821993G 71620045B 09933120K
    python render.py --codes-file picks.txt
    python render.py 04821993G --header FullTest

With no --cache given, RENDER loads the most recently built cache for config.HEADER (or --header).

Curves are recomputed here rather than read from the cache - doesn't take much processing time
"""

import argparse
import pathlib

import tqdm

import config
from functions import cache as cache_mod
from functions import curves as curves_mod
from functions import density, formula, ini_updater, plot, timestamp


def render_codes(codes, cache=None, cache_path=None, header=None, out_dir=None,
                 with_difficulty=True):
    header = header or config.HEADER

    if cache is None:
        if cache_path is None:
            cache_path = timestamp.latest_output('cache', header, ext='pkl')
        cache = cache_mod.load(cache_path)

    entries, missing = cache_mod.entries_by_code(cache, codes)

    if missing:
        print(f"No song for code(s): {', '.join(missing)}")
    if not entries:
        print("Nothing to render.")
        return []

    out_dir = out_dir or config.RENDER_DIR

    # Original diffs from backup CSV for header, per instrument
    # {} if no backup exists yet (old caches/metrics)
    original_diffs = ini_updater.load_backup_diffs(header, config.CACHE_DIR)

    written = []
    for entry in tqdm.tqdm(entries, desc="Rendering", unit="song"):
        song_curves = curves_mod.calc_curves(entry['notes'])
        if song_curves is None:
            print(f"  [skip] {entry['code']}: no curve data")
            continue

        difficulty = None
        if with_difficulty:
            metrics = density.calc_metrics(entry['notes'])
            if metrics is not None:
                difficulty = formula.calc_diff(metrics, entry['instrument'])

        original_diff = original_diffs.get(entry['song_path'], {}).get(entry['instrument'])

        written.append(plot.render_song(entry, song_curves, difficulty,
                                         original_diff=original_diff,
                                         out_dir=out_dir))

    print(f"\nPNGs written: {len(written)}")
    if written:
        print(f"Output dir:   {pathlib.Path(out_dir).resolve()}")

    return written


def _read_codes_file(path):
    with open(path, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser(description="Render curve views for one or more songs.")
    parser.add_argument('codes', nargs='*', help="retrieval code(s) from the metrics workbook, e.g. 04821993B")
    parser.add_argument('--codes-file', default=None, help="file with one code per line")
    parser.add_argument('--header', default=None, help="run identifier to look up (default: config.HEADER)")
    parser.add_argument('--cache', default=None, help="explicit cache path (overrides header lookup)")
    parser.add_argument('--out-dir', default=None, help="PNG output directory")
    args = parser.parse_args()

    codes = list(args.codes)
    if args.codes_file:
        codes.extend(_read_codes_file(args.codes_file))

    if not codes:
        parser.error("give at least one code, or --codes-file")

    render_codes(codes, cache_path=args.cache, header=args.header, out_dir=args.out_dir)


if __name__ == '__main__':
    main()
