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

Drums have no RemapDiff/CalcTier equivalent yet so the Expert-anchor step +
the song.ini CalcTier/RemapDiff write-back are both skipped entirely for instrument_key == 'drums'


TODO - reconcile split details across instruments, xlsx_foramt, & analyze
"""
import argparse
import pathlib
import time

import pandas as pd
import tqdm

import config
from functions import instruments
from functions import cache as cache_mod
from functions import drum_density, drum_formula, fret_density, fret_formula, ini_updater, xlsx_format, timestamp


# shared row-metadata block - identical between the fret and drum row builders
# drums get its own row shape after metadata
def _row_meta(meta, instrument_key, level_key):
    return {
        'Name': meta.get('Name'),
        'Artist': meta.get('Artist'),
        'Charter': meta.get('Charter'),
        'Type': instruments.TYPE_LABELS[instrument_key],
        'Level': instruments.LEVEL_DISPLAY_NAMES[level_key],
        'Difficulty': (meta.get('Difficulty') or {}).get(instrument_key, '-1'),
        'Release': meta.get('Release'),
        'Official': meta.get('Official'),
    }


# metrics: pre-computed density metrics for this level (expert)
def _fret_row(code, meta, notes, instrument_key, level_key, anchor_remap, anchor_tier,
              metrics=None):
    if metrics is None:
        metrics = fret_density.calc_metrics(notes)
    if metrics is None:
        return None
    nvcov = fret_formula.calc_nvcov(metrics)

    return {
        'Code': code,
        **_row_meta(meta, instrument_key, level_key),
        **metrics,
        **nvcov,
        'RemapDiff': anchor_remap,
        'CalcTier': anchor_tier,
    }


# One EMHX level's drum row: D_1x/D_2x live as sibling columns on one row 
# Returns None if there's no usable hand or 1x-kick data at this level 
def _kick_reading_diag(reading, r, suffix):
    return {
        f'pKPS_{suffix}': reading['pKPS'], f'aKPS_{suffix}': reading['aKPS'],
        f'medKPS_{suffix}': reading['medKPS'], f'stdKPS_{suffix}': reading['stdKPS'],
        f'pCo_{suffix}': reading.get('pCo'), f'aCo_{suffix}': reading.get('aCo'),
        f'medCo_{suffix}': reading.get('medCo'), f'stdCo_{suffix}': reading.get('stdCo'),
        f'IndepFrac_{suffix}': reading.get('IndepFrac'),
        f'pIKPS_{suffix}': reading.get('pIKPS'), f'aIKPS_{suffix}': reading.get('aIKPS'),
        f'medIKPS_{suffix}': reading.get('medIKPS'), f'stdIKPS_{suffix}': reading.get('stdIKPS'),
        f'K_{suffix}': r['K'],
        f'Co_axis_{suffix}': r['Co_axis'], f'Indep_axis_{suffix}': r['Indep_axis'],
        f'CoV_overall_{suffix}': r['CoV_overall'],
        f'Kick_level_{suffix}': r['Kick_level'],
        f'Interaction_{suffix}': r['Interaction'],
        f'Base_{suffix}': r['Base'],
    }


def _drum_row(code, meta, notes, instrument_key, level_key, roll_spans=None):
    metrics = drum_density.calc_drum_metrics(notes, roll_spans=roll_spans)
    hand = metrics['hand']
    reading_1x = metrics['1x']
    if hand is None or reading_1x is None:
        return None

    reading_2x = metrics['2x']
    r1x = drum_formula.calc_drum_d(metrics, '1x')

    # NoteCount/DurationS for split streams
    hand_times = hand['time_ms']
    kick_times = reading_1x['time_ms']
    note_count = int(hand_times.size + kick_times.size)
    dur_s = max(float(hand_times[-1]), float(kick_times[-1])) / 1000.0

    row = {
        'Code': code,
        **_row_meta(meta, instrument_key, level_key),
        'NoteCount': note_count,
        'DurationS': int(dur_s),
        'D_1x': r1x['D'],
        'pHPS': hand['pHPS'], 'aHPS': hand['aHPS'], 'medHPS': hand['medHPS'], 'stdHPS': hand['stdHPS'],
        'pTPS': hand['pTPS'], 'aTPS': hand['aTPS'], 'medTPS': hand['medTPS'], 'stdTPS': hand['stdTPS'],
        'H': r1x['H'], 'T': r1x['T'], 'Pattern': r1x['Pattern'],
        'Movement': r1x['Movement'],
        'Hand_level': r1x['Hand_level'],
        **_kick_reading_diag(reading_1x, r1x, '1x'),
    }

    if reading_2x is not None:
        r2x = drum_formula.calc_drum_d(metrics, '2x')
        row['D_2x'] = r2x['D']
        row.update(_kick_reading_diag(reading_2x, r2x, '2x'))
    else:
        row['D_2x'] = None
        row.update({k: None for k in instruments.DRUM_KICK_DIAG_COLS_2X})

    return row


#Save clock, since that's slower than most of the analysis...
def _save_workbook(writer):
    start = time.time()
    print("Saving spreadsheet...", end='', flush=True)
    writer.close()
    end = time.time()
    print(f" done {end - start:.1f}s")

# Parses EMHX options from config
def _resolve_levels(spec):
    spec = (spec or 'ALL').strip().upper()
    if spec == 'ALL':
        return set(instruments.LEVEL_KEYS)
    selected = {instruments.SUFFIX_TO_LEVEL[ch] for ch in spec if ch in instruments.SUFFIX_TO_LEVEL}
    bad = [ch for ch in spec if ch not in instruments.SUFFIX_TO_LEVEL]
    if bad:
        raise ValueError(f"Unrecognized level letter(s) {bad} in XLSX_LEVELS '{spec}' (expected E/M/H/X or ALL)")
    if not selected:
        raise ValueError(f"XLSX_LEVELS '{spec}' resolved to no levels")
    return selected


# column order for a given sheet, with EXTRA_METRICS-gated hidden columns dropped
def _column_order_for(sheet_name):
    profile = instruments.SHEET_PROFILES[sheet_name]
    if config.EXTRA_METRICS:
        return profile.column_order
    return [c for c in profile.column_order if c not in profile.hidden_cols]


# run the analysis - loading from selected/default cache
def analyze(cache=None, cache_path=None, header=None, out_dir=None, diff_mode=None, xlsx_levels=None):
    header = header or config.HEADER
    diff_mode = diff_mode if diff_mode is not None else config.DIFF_WRITE_MODE
    xlsx_levels = xlsx_levels if xlsx_levels is not None else config.XLSX_LEVELS
    selected_levels = _resolve_levels(xlsx_levels)

    if diff_mode == "Restore":
        result = ini_updater.sync_difficulty("Restore", header)
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
        all_song_instruments, desc="Computing metrics", unit="songs"
    ):
        song = cache['songs'][song_path]
        codes_for_instrument = song.get('codes', {}).get(instrument_key, {})

        # Drums has no Expert-anchored RemapDiff/CalcTier yet
        if instrument_key == 'drums':
            roll_spans_by_level = song.get('roll_spans', {}).get('drums', {})
            for level_key, inst_entry in levels.items():
                if level_key not in selected_levels:
                    continue
                total += 1
                code = codes_for_instrument.get(level_key)
                roll_spans = roll_spans_by_level.get(level_key, [])

                row = _drum_row(code, song['meta'], inst_entry['notes'], instrument_key, level_key, roll_spans)
                if row is None:
                    skipped += 1
                    continue

                rows_by_instrument[instrument_key].append(row)
                row_counts[instrument_key][level_key] += 1
            continue

        # Expert's metrics are computed once here, they anchor RemapDiff/CalcTier
        expert_entry = levels.get('expert')
        expert_metrics = fret_density.calc_metrics(expert_entry['notes']) if expert_entry is not None else None
        anchor_remap, anchor_tier = fret_formula.anchor_remap_tier(expert_metrics, instrument_key)

        if diff_mode in ("CalcTier", "RemapDiff") and anchor_remap is not None:
            difficulties_by_instrument[instrument_key][song_path] = {
                'RemapDiff': anchor_remap,
                'CalcTier': anchor_tier,
            }

        for level_key, inst_entry in levels.items():
            if level_key not in selected_levels:
                continue
            total += 1
            code = codes_for_instrument.get(level_key)

            row = _fret_row(code, song['meta'], inst_entry['notes'], instrument_key,
                             level_key, anchor_remap, anchor_tier,
                             metrics=expert_metrics if level_key == 'expert' else None)
            if row is None:
                skipped += 1
                continue

            rows_by_instrument[instrument_key].append(row)
            row_counts[instrument_key][level_key] += 1

    # song.ini write-back happens after metrics are computed for every song
    # difficulties_by_instrument['drums'] is empty for now
    # drum specific branch needed here
    if diff_mode in ("CalcTier", "RemapDiff"):
        for instrument_key in instruments.INSTRUMENT_KEYS:
            diffs = difficulties_by_instrument[instrument_key]
            if not diffs:
                continue
            ini_updater.sync_difficulty(
                diff_mode, header, instrument=instrument_key,
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
    writer = pd.ExcelWriter(xlsx_out, engine='openpyxl')
    try:
        # counted in rows
        with tqdm.tqdm(total=total_rows, desc="Writing spreadsheet", unit="rows") as write_bar:
            for sheet_name, rows in sheet_rows.items():
                write_bar.set_postfix_str(sheet_name)

                profile = instruments.SHEET_PROFILES[sheet_name]

                df = pd.DataFrame(rows)
                df = df.rename(columns={'Name': 'Song Title'})

                # Difficulty comes from song.ini as a string, convert to numeric and fill missing with -1
                df['Difficulty'] = pd.to_numeric(df['Difficulty'], errors='coerce').fillna(-1).astype(int)

                # EXTRA_METRICS = False drops the hidden diagnostic columns
                column_order = _column_order_for(sheet_name)
                df = df[column_order]

                # rounding reads the same per-sheet float-column (X.XX formatting)
                float_cols = [c for c in df.columns if c in profile.float_cols or c == profile.sort_col]
                df[float_cols] = df[float_cols].round(2)
                df = df.sort_values(profile.sort_col, ascending=False)

                sheet = sheet_name[:31]  # Excel sheet-name limit
                df.to_excel(writer, sheet_name=sheet, index=False)
                xlsx_format.style_sheet(writer.sheets[sheet], df, sheet_name=sheet_name)
                write_bar.update(len(df))
                frames[sheet_name] = df
    except BaseException:
        writer.close()
        raise

    # workbook save clock call
    _save_workbook(writer)

    # analyze complete terminal output
    print(f"\n{header} analysis complete")
    print(f"{total} Rows written:")
    active_levels = [level for level in instruments.LEVEL_KEYS if level in selected_levels]
    print(instruments.level_matrix(row_counts, active_levels, skip_empty=True))

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
    parser.add_argument('--xlsx-levels', default=None,
                         help="Which EMHX levels to emit, e.g. X, EX, EMHX, or ALL. "
                              "Default: config.XLSX_LEVELS.")
    args = parser.parse_args()

    analyze(cache_path=args.cache, header=args.header, diff_mode=args.diff_mode,
            xlsx_levels=args.xlsx_levels)


if __name__ == '__main__':
    main()
