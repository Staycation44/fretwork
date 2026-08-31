"""
ANALYZE - Loads the cache for config.HEADER & computes density metrics + difficulty values
using restore skips the calculations/CSV generation and only edits inis to backed up values

pairs cache and metrics together
    FullTest_cache_08052026-0330.pkl  ->  FullTest_metrics_08052026-0330.csv

    python analyze.py
    python analyze.py --header FullTest
    python analyze.py --cache FullTest_cache_08052026-0330.pkl
    python analyze.py --diff-mode CalcTier
    python analyze.py --diff-mode Restore

CSV contains: 
retrieval code (for render visualization)
timestamp of generation
song.ini metadata (name/artist/charter/difficulty/release) 
forumla difficulty metrics (duration, NPS/VPS metrics, D, remapped & calculated tier)

Run with DIFF_WRITE_MODE options to write calculated difficulty to song.inis or restore backed-up values
"""
import argparse
import pathlib

import pandas as pd
import tqdm

import config
from functions import cache as cache_mod
from functions import density, formula, ini_updater

LEAD_COLS = ['Code', 'CacheGeneratedAt']

def song_row(entry, gen_on):
    metrics = density.calc_metrics(entry['notes'])
    if metrics is None:
        return None

    difficulty = formula.calc_diff(metrics)

    return {
        'Code': entry['code'],
        'CacheGeneratedAt': gen_on,
        **entry['meta'],
        **metrics,
        **difficulty,
    }

# run the analysis - loading from selected/default cache
def analyze(cache=None, cache_path=None, header=None, out_dir=None, diff_mode=None):
    header = header or config.HEADER
    diff_mode = diff_mode if diff_mode is not None else config.DIFF_WRITE_MODE

    if cache is None:
        if cache_path is None:
            cache_path = config.latest_output('cache', header, out_dir, ext='pkl')
        cache = cache_mod.load(cache_path)

    gen_on = cache.get('generated_at', 'unknown')

    rows = []
    difficulties = {}
    skipped = 0

    for entry in tqdm.tqdm(cache['songs'].values(), desc="Computing metrics", unit="song"):
        row = song_row(entry, gen_on)
        if row is None:
            skipped += 1
            continue
        rows.append(row)
        if diff_mode in ("CalcTier", "RemapDiff"):
            difficulties[entry['song_path']] = {k: row[k] for k in ('CalcTier', 'RemapDiff')}

    # song.ini write-back happens after metrics are computed for every song,
    # not interleaved mid-loop, and is a no-op when diff_mode is None (default)
    if diff_mode is not None:
        ini_updater.sync_difficulty(
            diff_mode, header, config.CACHE_DIR,
            songs=difficulties.keys(), difficulties=difficulties,
        )

    df = pd.DataFrame(rows)

    ordered = LEAD_COLS + [c for c in df.columns if c not in LEAD_COLS]
    df = df[ordered]

    # Round floats for readability
    df = df.round(2)

    ts = config.ext_ts(cache_path, 'cache', header) if cache_path else None
    csv_out = config.output_path('metrics', header, ts=ts, out_dir=out_dir, ext='csv')
    df.to_csv(csv_out, index=False)

    print(f"\nRows written:        {len(rows)}")
    print(f"Skipped (no notes):  {skipped}")
    print(f"Cache generated:     {gen_on}")
    print(f"CSV written:         {pathlib.Path(csv_out).resolve()}")

    return df


def main():
    parser = argparse.ArgumentParser(description="Compute metrics from a note stream cache.")
    parser.add_argument('--header', default=None, help="run identifier to look up (default: config.HEADER)")
    parser.add_argument('--cache', default=None, help="explicit cache path (overrides header lookup)")
    parser.add_argument('--diff-mode', default=None, choices=list(ini_updater.VALID_MODES),
                         help="Write CalcTier/RemapDiff into song.ini, or Restore originals "
                              "(default is None / no write-back, use config.DIFF_WRITE_MODE to override)")
    args = parser.parse_args()

    analyze(cache_path=args.cache, header=args.header, diff_mode=args.diff_mode)


if __name__ == '__main__':
    main()
