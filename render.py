"""
RENDER - one PNG per retrieval code based on settings in config + plot

Takes codes from the ANALYZE spreadsheet and writes an individual PNG for each.
Codes are an 8-digit hash + level (E/M/H/X) + instrument (G/C/R/B/K/D/V)

    python render.py 04821993XG
    python render.py 04821993XG 71620045HB 09933120EK
    python render.py --codes-file picks.txt
    python render.py 04821993XG --header FullTest

With no --cache given, RENDER loads the most recently built cache for config.HEADER (or --header).
--cache accepts a full path or a bare cache filename from the caches folder.
The cache's own header picks the backup CSV used for the original 'diff' in the header line.

Curves are recomputed here rather than read from the cache - doesn't take much processing time

EMHX
- Each code renders exactly one EMHX level's curves (D/NPS/VPS, or D/HPS/TPS/KPS for drums) over time
- Render recalcs expert metrics and uses them to anchor the difficulty remap/tier for every level

Different instruments require different functions

Drums renders 2x under 1x when both appear for a chart
Vocals are Expert-only, so no EMHX anchor step - RemapDiff/CalcTier come straight from D
"""

import argparse
import pathlib

import tqdm

import config
from functions import cache as cache_mod, drum_density, drum_formula, fret_density, fret_formula
from functions import vocal_density, vocal_formula
from functions import curves as curves_mod
from functions import ini_updater, plot, timestamp


# One guitar/bass/keys entry - Expert metrics reused when this entry is the Expert level
def _render_fret_entry(entry, out_dir, original_diffs):
    windows = fret_density.window_arrays(entry['notes'])
    song_curves = curves_mod.calc_curves(entry['notes'], windows=windows)
    if song_curves is None:
        return None, f"{entry['code']}: no curve data"

    difficulty = None
    metrics = fret_density.calc_metrics(entry['notes'], windows=windows)
    if metrics is not None:
        expert_notes = entry.get('expert_notes')
        if entry['level'] == 'expert':
            expert_metrics = metrics
        else:
            expert_metrics = fret_density.calc_metrics(expert_notes) if expert_notes is not None else None
        anchor_remap, anchor_tier = fret_formula.anchor_remap_tier(expert_metrics, entry['instrument'])

        difficulty = {
            **fret_formula.calc_nvcov(metrics),
            'RemapDiff': anchor_remap,
            'CalcTier': anchor_tier,
        }

    path = plot.render_song(entry, song_curves, difficulty,
                            original_diff=_original_diff(entry, original_diffs), out_dir=out_dir)
    return path, None


# One drum entry - hand windows shared by curves + metrics, Expert metrics reused at Expert
def _render_drum_entry(entry, out_dir, original_diffs):
    roll_spans = entry.get('roll_spans')
    windows = drum_density.window_arrays(entry['notes']['hand_mask'], roll_spans)
    drum_curves = curves_mod.calc_drum_curves(entry['notes'], roll_spans=roll_spans, windows=windows)
    if drum_curves is None:
        return None, f"{entry['code']}: no curve data"

    difficulty = None
    metrics = drum_density.calc_drum_metrics(entry['notes'], roll_spans=roll_spans, windows=windows)
    if metrics is not None:
        expert_notes = entry.get('expert_notes')
        expert_roll_spans = entry.get('expert_roll_spans')
        if entry['level'] == 'expert':
            expert_metrics = metrics
        else:
            expert_metrics = (drum_density.calc_drum_metrics(expert_notes, roll_spans=expert_roll_spans)
                              if expert_notes is not None else None)
        anchor_remap, anchor_tier = drum_formula.anchor_remap_tier(expert_metrics)

        difficulty = {
            'D_1x': drum_formula.calc_drum_d(metrics, '1x')['D'],
            'RemapDiff': anchor_remap,
            'CalcTier': anchor_tier,
        }
        # 2x is optional - only present, and only shown, when the song actually charts it
        if metrics.get('2x') is not None:
            difficulty['D_2x'] = drum_formula.calc_drum_d(metrics, '2x')['D']

    path = plot.render_drum_song(entry, drum_curves, difficulty,
                                 original_diff=_original_diff(entry, original_diffs), out_dir=out_dir)
    return path, None


# One vocals entry - Expert only, no EMHX anchoring needed (RemapDiff/CalcTier come straight from D)
def _render_vocal_entry(entry, out_dir, original_diffs):
    talkie = entry.get('talkie')
    percussion = entry.get('percussion')

    windows = vocal_density.window_arrays(entry['notes'], talkie, percussion)
    if windows is None:
        return None, f"{entry['code']}: no curve data"

    metrics = vocal_density.calc_vocal_metrics(entry['notes'], talkie, percussion, windows=windows)
    difficulty = vocal_formula.calc_vocal_d(metrics)
    vocal_curves = curves_mod.calc_vocal_curves(entry['notes'], talkie, percussion=percussion,
                                                windows=windows, difficulty=difficulty)

    path = plot.render_vocal_song(entry, vocal_curves, difficulty,
                                  original_diff=_original_diff(entry, original_diffs), out_dir=out_dir)
    return path, None


# backup CSV cell for this entry's song/instrument - None when the song isn't in the backup
def _original_diff(entry, original_diffs):
    song_diffs = original_diffs.get(entry['song_path'])
    return None if song_diffs is None else song_diffs.get(entry['instrument'], '')


RENDERERS = {
    'drums': _render_drum_entry,
    'vocals': _render_vocal_entry,
}


def render_codes(codes, cache=None, cache_path=None, header=None, out_dir=None):
    explicit_header = header
    header = timestamp.validate_header(header or config.HEADER)

    if cache is None:
        if cache_path is not None:
            cache_path = timestamp.resolve_cache_path(cache_path)
        else:
            cache_path = timestamp.latest_output('cache', header, ext='pkl')
        cache = cache_mod.load(cache_path)

    # the cache's own header picks the backup CSV (original diffs)
    header = cache_mod.resolve_header(cache, cache_path, explicit_header, fallback=header)

    entries, missing = cache_mod.entries_by_code(cache, codes)

    if missing:
        source = pathlib.Path(cache_path).name if cache_path else f"'{header}' cache"
        print(f"\nNo song for: {', '.join(missing)}")
        print(f"  (looked in {source} - check the codes came from this header's spreadsheet, "
              f"or pass --header / --cache)")
    if not entries:
        print()
        return []

    out_dir = pathlib.Path(out_dir) if out_dir else timestamp.project_path(config.RENDER_DIR)

    # Original diffs from backup CSV for header
    # same value regardless of which EMHX level is being rendered (Expert derived)
    original_diffs = ini_updater.load_backup_diffs(header)

    print(f"\nRendering {len(entries)} from {header} cache")
    written = []
    for entry in tqdm.tqdm(entries, desc="Rendering", unit="song"):
        render_entry = RENDERERS.get(entry['instrument'], _render_fret_entry)
        try:
            path, skip_reason = render_entry(entry, out_dir, original_diffs)
        except Exception as exc:
            # one bad entry doesn't stop the rest of the batch
            path, skip_reason = None, f"{entry['code']}: {type(exc).__name__}: {exc}"

        if skip_reason:
            print(f"  [skip] {skip_reason}")
            continue

        written.append(path)

    print(f"\nGraphs rendered: {len(written)}")
    if written:
        print(f"\nOutput: {out_dir.resolve()}")
        print()

    return written


def _read_codes_file(path):
    with open(path, encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]


def main():
    parser = argparse.ArgumentParser(description="Render curve views for one or more songs.")
    parser.add_argument('codes', nargs='*', help="retrieval code(s) from the metrics spreadsheet, e.g. 04821993XB")
    parser.add_argument('--codes-file', default=None, help="file with one code per line")
    parser.add_argument('--header', default=None, help="run identifier to look up (default: config.HEADER)")
    parser.add_argument('--cache', default=None, help="explicit cache path (overrides header lookup)")
    parser.add_argument('--out-dir', default=None, help="PNG output directory (default: config.RENDER_DIR in the tool's folder)")
    args = parser.parse_args()

    codes = list(args.codes)
    if args.codes_file:
        codes.extend(_read_codes_file(args.codes_file))

    if not codes:
        parser.error("give at least one code, or --codes-file")

    try:
        render_codes(codes, cache_path=args.cache, header=args.header, out_dir=args.out_dir)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(f"\n{exc}\n")


if __name__ == '__main__':
    main()
