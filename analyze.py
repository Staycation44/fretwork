"""
ANALYZE - Loads the cache for config.HEADER & computes density metrics + difficulty values

pairs cache and metrics together
    FullTest_cache_08052026-0330.pkl  ->  FullTest_metrics_08052026-0330.csv

    python analyze.py
    python analyze.py --header FullTest
    python analyze.py --cache FullTest_cache_08052026-0330.pkl

CSV contains: 
retrieval code (for render visualization)
timestamp of generation
song.ini metadata (name/artist/charter/difficulty/release) 
forumla difficulty metrics (duration, NPS/VPS metrics, D, remapped & calculated tier)
"""
import configparser
import argparse
import pathlib

import pandas as pd
import tqdm

import config
from functions import ini_updater
from functions import cache as cache_mod
from functions import density, formula

LEAD_COLS = ['Code', 'CacheGeneratedAt']

def song_row(entry, gen_on, diff_type=None):
    metrics = density.calc_metrics(entry['notes'])
    if metrics is None:
        return None

    difficulty = formula.calc_diff(metrics)

    ini_path = pathlib.Path(f"{entry["song_path"]}/song.ini")

    if diff_type is not None:
        if diff_type == "CalcTier" or diff_type == "RemapDiff":
            ini_updater.update_ini_value(ini_path, "diff_guitar", difficulty[diff_type])

    return {
        'Code': entry['code'],
        'CacheGeneratedAt': gen_on,
        **entry['meta'],
        **metrics,
        **difficulty,
    }

# run the analysis - loading from selected/default cache
def analyze(cache=None, cache_path=None, header=None, out_dir=None, diff_type=None):
    header = header or config.HEADER

    if cache is None:
        if cache_path is None:
            cache_path = config.latest_output('cache', header, out_dir, ext='pkl')
        cache = cache_mod.load(cache_path)

    gen_on = cache.get('generated_at', 'unknown')

    rows = []
    skipped = 0

    for entry in tqdm.tqdm(cache['songs'].values(), desc="Computing metrics", unit="song"):
        row = song_row(entry, gen_on, diff_type)
        if row is None:
            skipped += 1
            continue
        rows.append(row)

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
    parser.add_argument('--modify_game', default=None, help="Choose which type of calc you'd like to use for in-game.")
    args = parser.parse_args()

    analyze(cache_path=args.cache, header=args.header, diff_type=args.modify_game)


if __name__ == '__main__':
    main()
