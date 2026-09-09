# Fretwork - 5-Fret Difficulty Analyzer <!-- omit in toc -->

Fretwork is an analysis tool to calculate difficulty values across Easy/Medium/Hard/Expert for Guitar/Bass/Keys from notes.chart & notes.mid files (Guitar Hero, Rock Band, Clone Hero, YARG) using Notes Per Second (note density) & Variability Per Second (fret change) metrics.

[Explainer video with some historical context](https://youtu.be/emoWMpDJ4ls)

Libraries required: **pandas, numpy, tqdm, mido, matplotlib, and openpyxl** 

![Render Example](https://github.com/Staycation44/fretwork/blob/main/renders/02139802G_Guitar_Dragonforce%20-%20Through%20The%20Fire%20Flames.png)

## Using Fretwork <!-- omit in toc -->
To use the tool setup **config** and run these in order:

1. **Build** - Scan a library, save everything into a cache file, & creates a backup of original difficulties
2. **Analyze** - Turn Build's cache into an .xlsx spreadsheet including song metadata and calculated metrics for every song/instrument combo. 
Optionally, applies calculated difficulty to `song.ini` files for use in-game, or restores them back to their originals from the backup
3. **Render** - Output a PNG graph of metrics over time for one or more song/instrument combos based on a retrieval code from the spreadsheet

## Index <!-- omit in toc -->
- [1. Setup your Config](#1-setup-your-config)
- [2. Building a cache](#2-building-a-cache)
- [3. Analyzing a cache](#3-analyzing-a-cache)
- [4. Rendering song graphs](#4-rendering-song-graphs)
- [5. Fixes/Extension Ideas](#5-fixesextension-ideas)
- [License](#license)

---

## 1. Setup your Config

Before running anything, open `config.py` and check these values:

| Setting | What it does | Example |
|---|---|---|
| `SEARCH_PATH` | Sets the folder to cache/analyze | `r"C:\Users\[user]\Documents\Clone Hero\Songs"` |
| `HEADER` | A short name for the library, becomes the prefix on every output file | `"Library"` |
| `DIFF_WRITE_MODE` | Change from None to allow Analyze to write/restore your `song.ini` files | `"CalcTier"` |

`SEARCH_PATH` - this tool has only been tested on windows devices, but should work on Mac/Linux with OS-correct file paths.

`HEADER` is how Build defines a cache of song data, and how Analyze & Render search that cache. If you keep multiple libraries, give each one its own `HEADER`.

All outputs are named: `{header}_{kind}_{timestamp}.{ext}`

ex. `Library_cache_08052026-0330.pkl`, `Library_metrics_08052026-0330.xlsx`.

**Render appearance settings**

Under `RENDER_DEFAULT` and `RENDER_THEMES`, you can tweak how `render.py's` PNGs look:

- `mode`: `"dark"` or `"light"` to set overall color theme
- adjust hex value colors

---

## 2. Building a cache

`build.py` walks `SEARCH_PATH`, finds every `song.ini`, `notes.chart`, and `notes.mid`, reads them, and writes one cache file containing every song's note timing and metadata. Note state (strum/hopo/tap), note length, and star power/solo phrases are not parsed. Every level (Easy/Medium/Hard/Expert) charted for each instrument is cached. Currently caches drum notes, but doesn't do anything with them downstream in Analyze/Render.

By default this will run on the `SEARCH_PATH` & `HEADER` set in the config.

Additionally, this always backs up your original difficulties as it scans - Build never writes to `song.ini` itself, it only records what's there so Analyze can restore it later if you want to.

**Outputs:**

- A `{header}_cache_{timestamp}.pkl` file, the main output used by Analyze and Render
- A `{header}_errors_{timestamp}.csv` file, only generated if some songs failed to parse, this lists which file failed and why (e.g. missing guitar track, corrupt midi file)
- A `{header}_BackupData.csv` file, which is a back up that stores all difficulties that were found at the time of building

Cache, errors, and backup all land in `caches/`; the metrics spreadsheet lands in `metrics/`. Both are set in `OUTPUT_DIRS` in `config.py`.

**Optional arguments:**
- `--search-path`: scan a different folder than the one in `config.py`
- `--header`: name this run something other than `config.header`

---

## 3. Analyzing a cache

`analyze.py` loads the most recent cache for your config's `HEADER`, computes difficulty metrics for every song/instrument/selected level combo, and writes a **.xlsx spreadsheet**. This is the main output for browsing the library.

Optionally, `analyze.py` can also update each instrument's `song.ini` `diff_*` tag for use in-game. You can also restore all of them to the original assigned value. This option runs via args or `DIFF_WRITE_MODE` in the config.

**Outputs:**

An .xlsx spreadsheet named `{header}_metrics_{timestamp}.xlsx` with:
- One tab per instrument group that has data in the cache (`Guitar` - combining Guitar/Co-op/Rhythm, `Bass`, `Keys`). Easy/Medium/Hard/Expert share the same tab in the `Level` column
- **Retrieval codes** - an 8-digit song hash plus a level letter (`E`/`M`/`H`/`X`) and an instrument letter (`G`/`C`/`R`/`B`/`K`), e.g. `04821993XG` for an Expert Guitar song - used to render graphs
- Metadata: Song Title, Artist, Level, Type (Lead/Co-op/Rhythm/Bass/Keys), Charter, Release/Source, Difficulty (song.ini diff tags)
- The difficulty metrics & updated Remap/CalcTier numbers

Each tab is formatted for browsing using `xlsx_format.py`

Using `XLSX_LEVELS` in the config you can adjust the mix of Easy/Medium/Hard/Expert you want in the sheet.

The raw NPS/VPS details and N/V/COV formula components are dropped, but they can be included as hidden columns by using `EXTRA_METRICS = True` in the config for diagnostics/comparison.

**Full D formula, Remap tables, & CalcTier detail in `Methodology.md`**

In the metrics spreadsheet / render header, you'll see D translated two ways:
- **RemapDiff (0–6):** A manual grouping, calibrated to roughly match the percentage of official releases across the seven tiers. Roughly, how would this have been tiered in a Rock Band game (capped at 6). Guitar (plus Co-op/Rhythm), Bass, and Keys each have their own bin edges, fit against that instrument's own `diff_*` distribution.
- **CalcTier:** A continuous, log-scaled tiering calculation. Every 0.44 natural-log increase in D over a baseline value increments the tier by one. This value is not capped, so officials at Dragonforce level end up in 7+, and a lot of notable customs are 10+. Unlike RemapDiff, the baseline/increment constants are currently shared across all instruments rather than fit per-instrument.

**RemapDiff and CalcTier are computed once per song/instrument, from the Expert level's D only**

**Optional arguments:**

- `--header`: analyze a different library's most recent cache
- `--cache`: point at a specific cache file, instead of most recent for the header
- `--diff-mode`: `CalcTier`, `RemapDiff`, or `Restore`.
  - `CalcTier`/`RemapDiff` writes selected value into every song's own `diff_*` tag, per instrument
  - `Restore` returns every instrument's `diff_*` values back to its `{header}_BackupData.csv` original, throws errors for songs moved/deleted
  - If not supplied, falls back to `config.DIFF_WRITE_MODE` (default `None`, which leaves song.ini alone)
- `--xlsx-levels`: which EMHX levels to write rows for. If not supplied, falls back to `config.XLSX_LEVELS`

**Note: After updating `song.ini` data, you MUST SCAN SONGS for the new metadata to work.**

---

## 4. Rendering song graphs

`python render.py [retrieval code]`

`render.py` draws one PNG graph of difficulty over time for a specific song/instrument/level combo, using its retrieval code. A retrieval code is an 8-digit song hash plus a level letter (`E`/`M`/`H`/`X`) then an instrument letter (`G`, `C`, `R`, `B`, `K`) available on the metrics spreadsheet from Analyze. 

**Make sure the header in config matches the spreadsheet/library you are rendering from.**

**You can render several at once, any mix of instruments and levels:**

`python render.py 04821993XG 71620045HB 09933120EK`

**Or from a text file, one code per line:**

`python render.py --codes-file picks.txt`

**Outputs:**

One PNG per code, named `{code}_{Artist} - {Song}.png`, showing three lines:

- **D** - overall difficulty over time (approx since it does not include CoV & has to be rescaled to fit on the same axis as N & V)
- **Notes** - note density per second
- **Variability** - how much the fret pattern is changing per second

Graphs are available in light or dark mode depending on the config.

**Optional arguments:**
- `--header` / `--cache`: pick which library/cache to pull from
- `--out-dir`: where to save the PNGs (defaults to `render_dir` in `config.py`)

---

## 5. Fixes/Extension Ideas
**Fixes:**
- Midi files misbehaving - *possibly parser drift / file corrruption/truncation?*

**Extension Ideas:**
- Vocals (Unique data, new metric needs, new difficulty logic/calcs) - *design in progress*
- Drums (similar data, new metric needs, new difficulty logic/calcs) - *design in progress*
- RB style band diff once all instruments are in
- Retesting duration and ways to include it (GHVH outliers) - *very annoying, short song downscaling is not bad but calibration for long is tough*
  
**Bigger rebuilds**
- Scoring by totals (as opposed to average), type of notes (singles by type/state, chords by type)
- D by section + Section names for renders - *parsing sections is a lot of extra data for the cache*
- Including strum/hopo/tap state by note in the cache - *not adding until there's plan to use them*
- Actually doing something with note state once it exists - *Ratios over the song was a good suggestion*
- Star Power Difficulty (how hard are SP phrases to hit?) - *SP no longer parsed*
- Rhythm changes/variability possibly easier than pattern recognition?
- Pattern recognition (chords, trills, runs, zigs, quads, quints, anchoring, etc)
- A strain-based difficulty metric splitting strum vs fret
- DDR Groove Radar style scoring (probably tied to patterns)

---

## License
**MIT** - see LICENSE for details.
