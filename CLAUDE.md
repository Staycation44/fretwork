# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Fretwork computes difficulty scores for 5-fret rhythm-game charts (Guitar/Co-op/Rhythm/Bass/Keys at Easy/Medium/Hard/Expert) from `song.ini` + `notes.chart` / `notes.mid` files. The formula and calibration are documented in `Methodology.md`; user-facing usage is in `README.md`. Read those before changing metrics or calibration constants.

## Commands

Plain Python 3 scripts, no packaging config, no test suite, no linter. Always work inside the project virtualenv at `.venv/` (gitignored); never install into or run against the system interpreter.

```
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

If `python3 -m venv` fails with an ensurepip error (Debian/Ubuntu and WSL without `python3-venv`), use `uv` instead; it needs no system packages and is what created the venv on the WSL dev box:

```
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
```

A uv-created venv has no `pip` inside it, so add packages with `uv pip install --python .venv/bin/python <pkg>`. Either way, run the scripts with the venv active or as `.venv/bin/python build.py`.

The three entry points run in order and are glued together by `config.HEADER` (see Architecture):

```
python build.py [--search-path DIR] [--header NAME]
python analyze.py [--header NAME] [--cache FILE.pkl] [--diff-mode CalcTier|RemapDiff|Restore] [--xlsx-levels X|EX|EMHX|ALL]
python render.py CODE [CODE ...] [--codes-file FILE] [--header NAME] [--cache FILE.pkl] [--out-dir DIR]
```

`serve.py` is an optional fourth entry point that browses an existing metrics `.xlsx` in a browser instead of Excel. Clicking a row renders that chart's graph on demand; columns have Excel-style filter dropdowns and can be hidden individually (remembered in `localStorage`). It reads the spreadsheet, not the cache, so `analyze.py` must have run first; the cache is loaded lazily only when a graph is clicked. Stdlib `http.server` plus pandas, binds `127.0.0.1` only, nothing added to `requirements.txt`:

```
python serve.py [--header NAME] [--xlsx FILE.xlsx] [--cache FILE.pkl] [--port 8000] [--no-bootstrap]
```

Bootstrap 5.3 supplies the base CSS. It is downloaded once into `CACHE_DIR` as `bootstrap-<version>.min.css` (gitignored with the rest of `caches/`) and served same-origin from `/bootstrap.css`, so the page never contacts a CDN at view time and works offline after the first run. If the fetch fails or `--no-bootstrap` is passed, the page inlines `FALLBACK_CSS` instead, which covers layout plus the `d-none` / `dropdown-menu.show` state classes the page's JS toggles. There is no JS framework and no Bootstrap JS; interaction is plain DOM code that toggles Bootstrap's own classes.

### `web/` is the viewer, and only the viewer

Root `serve.py` is a thin entry point in the same shape as the other three: docstring, one orchestration function, `main()`. Everything else lives in `web/`, a namespace package (no `__init__.py`, matching `functions/` and `parsers/`). It is named `web/` rather than `serve/` because a `serve/` directory beside `serve.py` loses to the module in Python's import resolution and would be silently unimportable.

| Module | Responsibility |
|---|---|
| `web/frames.py` | Reads the metrics `.xlsx` into JSON-safe rows. The only pandas importer. |
| `web/boot.py` | Builds the JSON payload the page reads, and escapes `</` in it. |
| `web/page.py` | Substitutes `index.html`'s four placeholders in one regex pass. |
| `web/bootstrap.py` | Bootstrap fetch/cache plus `FALLBACK_CSS`, its own fallback branch. |
| `web/assets.py` | Locates `static/` relative to `__file__` and loads it at startup. |
| `web/graph.py` | `GraphRenderer`: lazy cache load, PNG memo, render on demand. |
| `web/handler.py` | `MetricsHandler`: routing and response writing only. |
| `web/server.py` | `MetricsServer`: carries the handler's dependencies. |
| `web/banner.py` | The startup and shutdown terminal output. |

The page's markup, CSS and 15 ES modules live under `web/static/`, served from an in-memory dict built by globbing at startup. Keys never derive from a request path, so traversal is impossible by construction rather than by guard. Server data reaches the JS through a `<script type="application/json" id="fw-boot">` island that `boot.js` parses once and re-exports; `boot.py` escapes `</` so spreadsheet text can never close the tag. All mutable page state lives in one exported `state` object because ES module imports are read-only bindings.

Two things must stay off the server's startup import path: matplotlib (via `functions/plot.py`) and openpyxl (via `functions/xlsx_format.py`). `GraphRenderer` imports plot inside its method bodies, and `web/boot.py` keeps a local copy of `SCALED_COLS` rather than importing `xlsx_format` for it.

Before running Build, `config.SEARCH_PATH` must point at a real song library (the committed value is a Windows placeholder). Build on a ~3k-song library takes several minutes; midi parsing dominates.

`--diff-mode CalcTier|RemapDiff` and `config.DIFF_WRITE_MODE` **write to the user's `song.ini` files**. `Restore` rewrites them from the backup CSV and skips analysis entirely. Treat these as destructive to user data.

There are no automated tests. To sanity-check a change to parsing or metrics, build, analyze, and inspect the terminal summary / xlsx / error CSV against a small local library. The convention is a gitignored `songs/` folder at the repo root holding a handful of song folders copied from a real library (song folders contain copyrighted audio and must never be committed):

```
python build.py --search-path songs --header Local
python analyze.py --header Local
```

## Architecture

### Three-stage pipeline keyed by HEADER + timestamp

`build.py` -> cache `.pkl` -> `analyze.py` -> metrics `.xlsx`; `render.py` reads the same cache to draw PNGs. Every output is named `{header}_{kind}_{timestamp}.{ext}` via `functions/timestamp.py`, and `config.KIND_DIRS` routes each kind to a folder (`caches/` for cache, errors CSV, and backup; `metrics/` for xlsx; `renders/` for PNG). Analyze and Render locate the *newest* cache for a header by parsing the timestamp out of the filename (`timestamp.latest_output`), so filename format is load-bearing. Analyze reuses the cache's timestamp for its xlsx so the pair can be matched.

All of these outputs are gitignored (`*.pkl`, `*.csv`, `*.xlsx`, `*.png`, `caches/`). The `.xlsx` and `.png` files under `metrics/` and `renders/` are committed examples that were force-added; don't expect new outputs to show up in `git status`.

### The cache is the data contract

The pickled cache shape is documented at the top of `functions/cache.py`. Everything downstream (analyze, render, curves, density) consumes `notes = {'time_ms': ndarray, 'lanes': ndarray uint8}` plus `spans = {'star_power': [(ms, ms)], 'solo': [...]}` per (song, instrument, level). Both parsers must emit exactly that shape.

**Lane encoding**: one `uint8` bitmask per note timestamp. Bits 0-4 are GRBYO frets, bit 7 is open. Bits 5-6 are reserved (chart tap/force modifiers) and unused. Strum/HOPO/tap state is deliberately discarded by both parsers.

**Retrieval codes** (`04821993XG`): 8 digits from a SHA1 of the resolved song folder path (with linear probing on collision), then a level letter (E/M/H/X) and an instrument letter (G/C/R/B/K). Assigned in `cache.assign_codes` at build time and stored in `cache['codes']`. Render accepts codes without leading zeros.

### Parsers (`parsers/`)

Build runs them in a fixed order for a reason: `ini_parser` first, because `multiplier_note`/`star_power_note` from `song.ini` tells `mid_parser` whether MIDI pitch 103 means star power (legacy) or solo. Then `mid_parser`, then `chart_parser`. When a song folder has both formats, **chart wins** (`build.build_note_index`).

- `parsers/timing.py` holds the shared tempo-map and tick-to-ms conversion used by both formats. Use `ticks_to_ms` (vectorized) for note arrays and `tick_to_ms` for the handful of span endpoints.
- `.chart` distinguishes level by section-name prefix (`ExpertSingle`, `HardDoubleBass`); `.mid` distinguishes level by pitch block within one track per instrument (`instruments.MID_PITCH_BASE`). Star power and solos are per-section in `.chart` but track-wide (shared across levels) in `.mid`.
- Songs that fail to parse are appended to an `errors` list as `(path, ErrorType, message)` and written to the errors CSV; a single bad file never aborts a build. Non-fatal data loss (unclosed solos, malformed SP, unknown-channel legacy opens) is tallied in `dropped` counters instead.

### `functions/instruments.py` is the single source of truth

Every instrument/level table lives there: canonical keys and iteration order, `.mid` track names, `.chart` section names (with legacy fallbacks), pitch bases, `song.ini` `diff_*` tags, code suffixes, open-note support, xlsx sheet grouping, and display labels. Adding an instrument means adding it here and adding a calibration group in `functions/formula.py`; nothing else should hardcode instrument names.

### `functions/difficulty.py` holds the shared difficulty block

`entry_difficulty(entry)` computes D/N/V/COV for the entry's own level plus the Expert-anchored `RemapDiff`/`CalcTier`. `render.py` and `web/graph.py` both call it; it was duplicated verbatim between them before.

### `functions/labels.py` holds every human-facing string

The abbreviated keys (`pNPS`, `medVPS`, `COV`, `DurationS`) are the data contract: they come out of `density.calc_metrics` and `formula.calc_nvcov`, flow through the dataframes in `analyze.py`, and become the xlsx headers. Nothing keyed off a column name should change. `labels.py` maps those keys to readable text at display time only, via `COLUMN_LABELS`, `COLUMN_HELP` (tooltips), `TIME_COLUMNS` (seconds shown as m:ss), and `UI` (interface wording for `serve.py`). `label()` falls back to the raw key, so a new metric column degrades gracefully instead of raising.

Only `serve.py` consumes it today. The xlsx headers and the render header are deliberately still raw keys, since changing them would alter committed example outputs and anything downstream that reads the spreadsheet by column name. Wiring either one up is a display-layer change through this module, not a rename in the pipeline.

### Metrics pipeline (`functions/density.py` -> `functions/formula.py`)

`density.window_arrays` slides a 1000 ms window in 250 ms steps from t=0 to the last note and produces raw NPS (note timestamps per window) and VPS (fret-change per window; see `fret_var`) samples. `calc_metrics` reduces those to peak/avg/median/std. `formula.calc_nvcov` turns them into `D = N * V * COV` and is instrument-agnostic.

**Expert anchoring**: `D` is computed per level, but `RemapDiff` (0-6 bins, per calibration group) and `CalcTier` (uncapped log tier) are computed once per (song, instrument) from the **Expert** level's D via `formula.anchor_remap_tier`, and that pair is shown on every E/M/H/X row. If an instrument has no Expert chart, both are `None`/NaN. This is because `song.ini` only has one `diff_*` tag per instrument. Guitar, Co-op, and Rhythm share the `guitar` calibration group.

The bin edges and CalcTier constants in `formula.py` are mirrored as tables in `Methodology.md`; update both together.

### Render path (`functions/curves.py` -> `functions/plot.py`)

Render recomputes from the cache rather than reading stored metrics. `curves.calc_curves` reuses `density.window_arrays`, converts to rates, and applies a zero-phase EMA (`TAU_MS = 2000`). The plotted "D" line is `sqrt(nps * vps)`, an approximation for display that omits COV, while the header's `D` value comes from the real formula. Appearance comes entirely from `config.RENDER_DEFAULT` + `config.RENDER_THEMES`; `plot.py` uses the Agg backend and never opens a window.

### `song.ini` backup and write-back (`functions/ini_updater.py`)

Build **always** appends new songs to `caches/{header}_BackupData.csv` (append-only, deduplicated by `song_path`, one column per `diff_*` tag) regardless of config. It never writes to `song.ini`. Analyze's write modes and Restore both go through `update_ini_values`, which patches matching `key = value` lines inside the `[song]` section in place, appends missing keys at the end of the section, and preserves the file's original encoding (utf-8 / utf-8-sig / utf-16 / cp1252) and newline style. Don't replace it with `configparser`; `song.ini` files routinely contain `%` and other characters that break it, which is also why `ini_parser.parse_ini` is hand-rolled.

## Conventions worth knowing

- `config.py` is user-edited configuration (paths, header, theme), not library code. The committed `SEARCH_PATH`/`HEADER` values are placeholders. `instrument_scan.py` is gitignored local scratch.
- `Difficulty` of `'-1'` (string in cache, int in xlsx) is the sentinel for "no `diff_*` tag in song.ini". `xlsx_format.BLANK_PREDICATES` keeps sentinels out of the color scales.
- `analyze.COLUMN_ORDER` defines xlsx column order; `xlsx_format.DEFAULT_HIDDEN_COLS` lists the diagnostic columns that are dropped unless `config.EXTRA_METRICS` is True. Excel sheet names are truncated to 31 chars.
- Song identity everywhere is the resolved absolute folder path (`song_path`), which is also the join key between the ini table, note streams, backup CSV, and codes.
- Terminal progress uses `tqdm`; keep long loops wrapped so multi-minute builds stay observable.

## Working with the repo

Hosted at `github.com/Staycation44/fretwork`, single maintainer. `main` is the only long-lived branch. There is no CI, no branch protection, and no `.github/` directory, so nothing gates a merge except the maintainer and a manual pipeline run.

- **Feature work goes on a staging branch** named for the feature (`five-fret-staging`, `EMHX-Staging`), branched from `main`. Before merging, merge `main` *into* the staging branch to absorb anything that landed meanwhile, then merge the staging branch into `main` with a merge commit, preferably via a GitHub PR. Delete the branch after it lands. Every feature branch so far has been deleted post-merge.
- **Merge commits only.** History is never rebased or squashed; WIP commits and self-merges are left as-is.
- **Small changes go straight to `main`.** README edits, one-line fixes, and calibration tweaks (e.g. "updated remap bins") are committed directly.
- **Releases are lightweight tags on `main`** (`v0.6.1` through `v0.8`), applied after the merge lands. There is no version constant in the code; the only "bump version" commit edited the README. Numbering is informal.
- **Outside contributions arrive as fork PRs** and are typically reworked after merging (PR #1 added a standalone restore script that was later folded into `analyze.py`).
- **Commit messages are short and informal**, one line, describing what changed. Larger refactors are sometimes bundled into a single commit.
- **Example outputs are tracked despite the gitignore.** The `.xlsx` in `metrics/` and `.png` in `renders/` were force-added; if you regenerate them, `git add -f` the new files and remove the stale ones in the same commit. Never commit caches, backup CSVs, or a real library's metrics.
- **Before merging parser or metrics changes**, run build, analyze, and render against a small song folder and compare the terminal summary and error CSV against the previous run, since there is no automated test to catch regressions.
