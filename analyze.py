"""
ANALYZE - Loads the cache for config.HEADER & computes density metrics + difficulty values
for every instrument/EMHX-level present in the cache
Using Restore skips the calculations/spreadsheet generation and only restores song.inis to backed up values

pairs cache and spreadsheet together
    FullTest_cache_08052026-0330.pkl  ->  FullTest_metrics_08052026-0330.xlsx

    python analyze.py
    python analyze.py --header FullTest
    python analyze.py --cache FullTest_cache_08052026-0330.pkl
    python analyze.py --diff-mode CalcTier
    python analyze.py --diff-mode Restore

Output is a single .xlsx spreadsheet, one tab per instrument group that has data in the cache
(EMHX levels share the same tab as a filterable 'Level' column - see xlsx_format.py - not
separate tabs per level)
Formatted via xlsx_format.py

Run with DIFF_WRITE_MODE options to write calculated difficulty to song.inis or restore backed-up values (all instruments at once).

EMHX / RemapDiff & CalcTier anchor to expert, since only 1 diff value per instrument in song.ini
D remains calculated per level
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
    'Code', 'Song Title', 'Artist', 'Level', 'Type', 'Charter', 'Release', 'Official',
    'NoteCount', 'DurationS', 'Difficulty', 'D', 'RemapDiff', 'CalcTier',
    'pNPS', 'aNPS', 'medNPS', 'stdNPS', 'pVPS', 'aVPS', 'medVPS', 'stdVPS',
    'N', 'V', 'COV',
]


# metrics: pre-computed density metrics for this level (expert)
# None needs to recompute
def song_row(code, meta, notes, instrument_key, level_key, anchor_remap, anchor_tier,
             metrics=None):
    if metrics is None:
        metrics = density.calc_metrics(notes)
    if metrics is None:
        return None
    nvcov = formula.calc_nvcov(metrics)

    row_meta = {
        'Name': meta.get('Name'),
        'Artist': meta.get('Artist'),
        'Charter': meta.get('Charter'),
        'Type': instruments.TYPE_LABELS[instrument_key],
        'Level': instruments.LEVEL_DISPLAY_NAMES[level_key],
        'Difficulty': (meta.get('Difficulty') or {}).get(instrument_key, '-1'),
        'Release': meta.get('Release'),
        'Official': meta.get('Official'),
    }

    return {
        'Code': code,
        **row_meta,
        **metrics,
        **nvcov,
        'RemapDiff': anchor_remap,
        'CalcTier': anchor_tier,
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
    row_counts = {
        key: {level: 0 for level in instruments.LEVEL_KEYS}
        for key in instruments.INSTRUMENT_KEYS
    }
    difficulties_by_instrument = {key: {} for key in instruments.INSTRUMENT_KEYS}
    total = 0
    skipped = 0

    # one item per (song, instrument) - EMHX levels are handled inside the loop
    all_song_instruments = [
        (song_path, instrument_key, levels)
        for song_path, song in cache['songs'].items()
        for instrument_key, levels in song.get('instruments', {}).items()
    ]

    print(f"\nAnalyzing {header} cache")
    for song_path, instrument_key, levels in tqdm.tqdm(
        all_song_instruments, desc="Computing metrics", unit="song/instrument"
    ):
        song = cache['songs'][song_path]
        codes_for_instrument = song.get('codes', {}).get(instrument_key, {})

        # Expert's metrics are computed once here, they anchor RemapDiff/CalcTier
        expert_entry = levels.get('expert')
        expert_metrics = density.calc_metrics(expert_entry['notes']) if expert_entry is not None else None
        anchor_remap, anchor_tier = formula.anchor_remap_tier(expert_metrics, instrument_key)

        if diff_mode in ("CalcTier", "RemapDiff") and anchor_remap is not None:
            difficulties_by_instrument[instrument_key][song_path] = {
                'RemapDiff': anchor_remap,
                'CalcTier': anchor_tier,
            }

        for level_key, inst_entry in levels.items():
            total += 1
            code = codes_for_instrument.get(level_key)

            row = song_row(code, song['meta'], inst_entry['notes'], instrument_key,
                            level_key, anchor_remap, anchor_tier,
                            metrics=expert_metrics if level_key == 'expert' else None)
            if row is None:
                skipped += 1
                continue

            rows_by_instrument[instrument_key].append(row)
            row_counts[instrument_key][level_key] += 1

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

    # rows are grouped per sheet up front so the write bar knows its total before it starts
    sheet_rows = {
        sheet_name: [row for instrument_key in group_keys for row in rows_by_instrument[instrument_key]]
        for sheet_name, group_keys in instruments.SHEET_GROUPS.items()
    }
    sheet_rows = {sheet_name: rows for sheet_name, rows in sheet_rows.items() if rows}
    total_rows = sum(len(rows) for rows in sheet_rows.values())

    frames = {}
    print()
    with pd.ExcelWriter(xlsx_out, engine='openpyxl') as writer:
        # counted in rows
        with tqdm.tqdm(total=total_rows, desc="Writing spreadsheet", unit="row") as write_bar:
            for sheet_name, rows in sheet_rows.items():
                write_bar.set_postfix_str(sheet_name)

                df = pd.DataFrame(rows)
                df = df.rename(columns={'Name': 'Song Title'})

                # Difficulty comes from song.ini as a string, convert to numeric and fill missing with -1
                df['Difficulty'] = pd.to_numeric(df['Difficulty'], errors='coerce').fillna(-1).astype(int)

                df = df[COLUMN_ORDER]
                float_cols = [c for c in df.columns if c in xlsx_format.FLOAT_COLS or c == 'D']
                df[float_cols] = df[float_cols].round(2)
                df = df.sort_values('D', ascending=False)

                sheet = sheet_name[:31]  # Excel sheet-name limit
                df.to_excel(writer, sheet_name=sheet, index=False)
                # style_sheet advances the bar per column
                xlsx_format.style_sheet(writer.sheets[sheet], df, progress=write_bar.update)
                frames[sheet_name] = df

            write_bar.set_postfix_str('saving')
        # workbook is written to disk here, on ExcelWriter's context exit


    print(f"\n{header} analysis complete:")
    print(  f"Cache version:  {gen_on}")
    print(  f"Rows written:   {total}")

    print(f"\nRows per instrument/level:")
    name_width = max(len(instruments.DISPLAY_NAMES[key]) for key in instruments.INSTRUMENT_KEYS)
    level_labels = [instruments.LEVEL_DISPLAY_NAMES[level] for level in instruments.LEVEL_KEYS]
    col_width = max(max(len(label) for label in level_labels), 5) + 2
    print(" " * (name_width + 4) + "".join(label.rjust(col_width) for label in level_labels))
    for instrument_key in instruments.INSTRUMENT_KEYS:
        counts = row_counts[instrument_key]
        if not any(counts.values()):
            continue
        name = instruments.DISPLAY_NAMES[instrument_key]
        print(f"    {name:<{name_width}}" + "".join(
            str(counts[level]).rjust(col_width) for level in instruments.LEVEL_KEYS
        ))

    print(f"\nSpreadsheet written: {pathlib.Path(xlsx_out).resolve()}")
    print()

    return frames


def main():
    parser = argparse.ArgumentParser(description="Compute metrics from a note stream cache.")
    parser.add_argument('--header', default=None, help="run identifier to look up (default: config.HEADER)")
    parser.add_argument('--cache', default=None, help="explicit cache path (overrides header lookup)")
    parser.add_argument('--diff-mode', default=None, choices=list(ini_updater.VALID_MODES),
                         help="Write CalcTier/RemapDiff into each instrument's own diff_* tag "
                              "(anchored to the Expert-level D - see module docstring), or "
                              "Restore every instrument's originals from backup (skips metrics/"
                              "spreadsheet generation entirely). Default: config.DIFF_WRITE_MODE.")
    args = parser.parse_args()

    analyze(cache_path=args.cache, header=args.header, diff_mode=args.diff_mode)


if __name__ == '__main__':
    main()
