"""
ANALYZE - Loads the cache for config.HEADER & computes density metrics + difficulty values for every instrument present in the cache
Using Restore skips the calculations/workbook generation and only restores song.inis to backed up values

pairs cache and workbook together
    FullTest_cache_08052026-0330.pkl  ->  FullTest_metrics_08052026-0330.xlsx

    python analyze.py
    python analyze.py --header FullTest
    python analyze.py --cache FullTest_cache_08052026-0330.pkl
    python analyze.py --diff-mode CalcTier
    python analyze.py --diff-mode Restore

Output is a single .xlsx workbook, one tab per instrument group that has data in the cache
Formatted via xlsx_format.py

Run with DIFF_WRITE_MODE options to write calculated difficulty to song.inis or restore backed-up values (all instruments at once).
"""
import argparse
import pathlib

import pandas as pd
import tqdm

import config
from functions import instruments
from functions import cache as cache_mod
from functions import density, formula, ini_updater, xlsx_format, timestamp

COLUMN_ORDER = [
    'Code', 'Song Title', 'Artist', 'Type', 'Charter', 'Release', 'Official',
    'NoteCount', 'DurationS', 'Difficulty', 'D', 'RemapDiff', 'CalcTier',
    'pNPS', 'aNPS', 'medNPS', 'stdNPS', 'pVPS', 'aVPS', 'medVPS', 'stdVPS',
    'N', 'V', 'COV',
]


def song_row(code, meta, inst_entry, instrument_key):
    metrics = density.calc_metrics(inst_entry['notes'])
    if metrics is None:
        return None
    difficulty = formula.calc_diff(metrics, instrument_key)

    row_meta = {
        'Name': meta.get('Name'),
        'Artist': meta.get('Artist'),
        'Charter': meta.get('Charter'),
        'Type': instruments.TYPE_LABELS[instrument_key],
        'Difficulty': (meta.get('Difficulty') or {}).get(instrument_key, '-1'),
        'Release': meta.get('Release'),
        'Official': meta.get('Official'),
    }

    return {
        'Code': code,
        **row_meta,
        **metrics,
        **difficulty,
    }

# run the analysis - loading from selected/default cache
def analyze(cache=None, cache_path=None, header=None, out_dir=None, diff_mode=None):
    header = header or config.HEADER
    diff_mode = diff_mode if diff_mode is not None else config.DIFF_WRITE_MODE

    if diff_mode == "Restore":
        result = ini_updater.sync_difficulty("Restore", header, config.CACHE_DIR)
        return result

    if cache is None:
        if cache_path is None:
            cache_path = timestamp.latest_output('cache', header, out_dir, ext='pkl')
        cache = cache_mod.load(cache_path)

    gen_on = cache.get('generated_at', 'unknown')

    rows_by_instrument = {key: [] for key in instruments.INSTRUMENT_KEYS}
    difficulties_by_instrument = {key: {} for key in instruments.INSTRUMENT_KEYS}
    total = 0
    skipped = 0

    all_inst_entries = [
        (song_path, instrument_key, inst_entry)
        for song_path, song in cache['songs'].items()
        for instrument_key, inst_entry in song.get('instruments', {}).items()
    ]

    print(f"\nAnalyzing {header} cache")
    for song_path, instrument_key, inst_entry in tqdm.tqdm(
        all_inst_entries, desc="Computing metrics", unit="song"
    ):
        total += 1
        song = cache['songs'][song_path]
        code = song.get('codes', {}).get(instrument_key)

        row = song_row(code, song['meta'], inst_entry, instrument_key)
        if row is None:
            skipped += 1
            continue

        rows_by_instrument[instrument_key].append(row)
        if diff_mode in ("CalcTier", "RemapDiff"):
            difficulties_by_instrument[instrument_key][song_path] = {
                k: row[k] for k in ('CalcTier', 'RemapDiff')
            }

    # song.ini write-back happens after metrics are computed for every song
    if diff_mode in ("CalcTier", "RemapDiff"):
        for instrument_key in instruments.INSTRUMENT_KEYS:
            diffs = difficulties_by_instrument[instrument_key]
            if not diffs:
                continue
            ini_updater.sync_difficulty(
                diff_mode, header, config.CACHE_DIR, instrument=instrument_key,
                songs=diffs.keys(), difficulties=diffs,
            )

    ts = timestamp.ext_ts(cache_path, 'cache', header) if cache_path else None
    xlsx_out = timestamp.output_path('metrics', header, ts=ts, out_dir=out_dir, ext='xlsx')

    frames = {}
    with pd.ExcelWriter(xlsx_out, engine='openpyxl') as writer:
        for sheet_name, group_keys in instruments.SHEET_GROUPS.items():
            rows = [row for instrument_key in group_keys for row in rows_by_instrument[instrument_key]]
            if not rows:
                continue
            df = pd.DataFrame(rows)
            df = df.rename(columns={'Name': 'Song Title'})

            # Difficulty comes from song.ini as a string, convert to numeric and fill missing with -1
            df['Difficulty'] = pd.to_numeric(df['Difficulty'], errors='coerce').fillna(-1).astype(int)

            df = df[COLUMN_ORDER].round(2)
            df = df.sort_values('D', ascending=False)

            sheet = sheet_name[:31]  # Excel sheet-name limit
            df.to_excel(writer, sheet_name=sheet, index=False)
            xlsx_format.style_sheet(writer.sheets[sheet], df)
            frames[sheet_name] = df


    print(f"\n{header} analysis complete:")
    print(  f"Cache version:  {gen_on}")
    print(  f"Rows written:   {total}")

    print(f"\nRows per instrument:")
    for instrument_key in instruments.INSTRUMENT_KEYS:
        n = len(rows_by_instrument[instrument_key])
        if n:
            print(f"    {instruments.DISPLAY_NAMES[instrument_key]:<14} {n}")

    print(f"\nSpreadsheet written: {pathlib.Path(xlsx_out).resolve()}")
    print()

    return frames


def main():
    parser = argparse.ArgumentParser(description="Compute metrics from a note stream cache.")
    parser.add_argument('--header', default=None, help="run identifier to look up (default: config.HEADER)")
    parser.add_argument('--cache', default=None, help="explicit cache path (overrides header lookup)")
    parser.add_argument('--diff-mode', default=None, choices=list(ini_updater.VALID_MODES),
                         help="Write CalcTier/RemapDiff into each instrument's own diff_* tag, or "
                              "Restore every instrument's originals from backup (skips metrics/"
                              "workbook generation entirely). Default: config.DIFF_WRITE_MODE.")
    args = parser.parse_args()

    analyze(cache_path=args.cache, header=args.header, diff_mode=args.diff_mode)


if __name__ == '__main__':
    main()
