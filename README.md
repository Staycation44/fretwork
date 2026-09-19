# Fretwork - Full Band Difficulty Analyzer <!-- omit in toc -->

Fretwork is an analysis tool to calculate difficulty values for **Full Band (Guitar / Bass / Keys / Drums / Vocals)** from chart & midi files **(Guitar Hero / Rock Band / Clone Hero / YARG)** using metrics derived directly from the charted notes (See Methodology.md for details)

[Explainer video with some historical context](https://youtu.be/emoWMpDJ4ls)

Libraries required: **pandas, numpy, tqdm, mido, matplotlib, and openpyxl** 

![Render Example](https://github.com/Staycation44/fretwork/blob/main/renders/02139802XG_Dragonforce%20-%20Through%20The%20Fire%20Flames.png)

## Using Fretwork <!-- omit in toc -->
To use the tool setup **config** and run these in order:

1. **Build** - Scan a library, save everything into a cache file, & create a backup of original difficulties
2. **Analyze** - Turn Build's cache into an .xlsx spreadsheet including song metadata and calculated metrics for every song/instrument combo.
Optionally, applies calculated difficulty to `song.ini` files for use in-game, or restores them back to their originals from the backup
3. **Render** - Output a PNG graph of metrics over time for one or more song/instrument combos based on a retrieval code from the spreadsheet

## Index <!-- omit in toc -->
- [1. Setting up Config](#1-setting-up-config)
- [2. Building a cache](#2-building-a-cache)
- [3. Analyzing a cache](#3-analyzing-a-cache)
- [4. Rendering song graphs](#4-rendering-song-graphs)
- [5. Fixes/Extension Ideas](#5-fixesextension-ideas)
- [License](#license)

---

## 1. Setting up Config

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

`build.py` walks `SEARCH_PATH`, finds every `song.ini`, `notes.chart`, and `notes.mid`, reads them, and writes one cache file containing every song's note timing and metadata. A CSV containing per instrument original difficulties is also saved.

By default this will run on the `SEARCH_PATH` & `HEADER` set in the config.

Note state (strum/hopo/tap), note length, and star power/solo phrases are not parsed.

**If you ran a prior version, you will need to rebuild your cache with the addition of Drums / Vocals**

**Outputs:**

- `{header}_cache_{timestamp}.pkl`: The main output used by Analyze and Render
- `{header}_errors_{timestamp}.csv`: Only generated if some songs failed to parse, this lists which file failed and why (e.g. missing valid instruments, corrupt midi file)
- `{header}_BackupData.csv`: A backup that stores all difficulties that were found at the time of building

**Cache files are Python pickles** - loading one can run code, so only load caches you built yourself for safety.

Cache, errors, and backup all land in `caches/` & the metrics spreadsheet lands in `metrics/`.

**Optional arguments:**
- `--search-path`: scan a different folder than the one in `config.py`
- `--header`: name this run something other than `config.header`

---

## 3. Analyzing a cache

`analyze.py` loads the most recent cache for your config's `HEADER`, computes difficulty metrics for every song/instrument/selected level combo, and writes a **.xlsx spreadsheet**. This is the main output for browsing the library.

Optionally, `analyze.py` can also update each instrument's `song.ini` `diff_*` tag for use in-game. You can also restore all of them to the original assigned value. This option runs via args or `DIFF_WRITE_MODE` in the config.

**Outputs:**

An .xlsx spreadsheet named `{header}_metrics_{timestamp}.xlsx` with:
- **One tab per instrument group** that has data in the cache, filterable by `E`/`M`/`H`/`X` levels
- **Retrieval codes** - an 8-digit song hash plus a level letter (`E`/`M`/`H`/`X`) and an instrument letter (`G`/`C`/`R`/`B`/`K`/`D`/`V`), e.g. `04821993XG` for an Expert Guitar song - used to render graphs (Vocals codes always carry `X`)
- **Metadata** - Song Title, Artist, Level, Type (Instrument), Charter, Release/Source, Difficulty (song.ini diff tags)
- **D scores** & updated Remap/CalcTier numbers

Each tab is formatted for browsing using `xlsx_format.py`

Using `XLSX_LEVELS` in the config you can adjust the mix of Easy/Medium/Hard/Expert you want in the sheet.

The raw formula components are dropped by default but they can be included as hidden columns by using `EXTRA_METRICS = True` in the config.

**Full D formula, Remap tables, & CalcTier detail in `Methodology.md`**

In the metrics spreadsheet / render header, you'll see D translated two ways:
- **RemapDiff (0–6):** A manual grouping, calibrated to roughly match the percentage of official releases across the seven tiers & capped at 6.
- **CalcTier:** A continuous, log-scaled tiering calculation. Every set natural-log increase in D over a baseline value increments the tier by one. This value is not capped, so tiers can extend well past 6 to provide additional granularity. Guitar/Bass/Keys share one scale, Drums and Vocals each have their own.

**RemapDiff and CalcTier are computed once per song/instrument, from the Expert level D only** 
Drums use the 1x kick reading, Vocals only have the one D

**Optional arguments:**

- `--header`: analyze a different library's most recent cache
- `--cache`: point at a specific cache file, instead of most recent for the header (a bare filename is looked up in `caches/`)
- `--diff-mode`: `CalcTier`, `RemapDiff`, `Restore`, or `None` (not case sensitive)
  - `CalcTier`/`RemapDiff` writes selected value into every song's own `diff_*` tag, per instrument
  - `Restore` returns every instrument's `diff_*` values back to its `{header}_BackupData.csv` original, throws errors for songs moved/deleted
  - `None` leaves every `song.ini` alone for this run, even if `DIFF_WRITE_MODE`/`DIFF_WRITE_OVERRIDES` would write
- `--xlsx-levels`: which EMHX levels go in the spreadsheet for this run, e.g. `X`, `EX`, `EMHX`, or `ALL` (default: `XLSX_LEVELS` in the config). This only filters rows - `song.ini` writes use the Expert anchor either way

**Per-instrument exceptions:** `DIFF_WRITE_OVERRIDES` in the config lets individual instruments use a different mode than `--diff-mode`/`DIFF_WRITE_MODE`, or skip writing.
- Overrides still apply when `DIFF_WRITE_MODE` is `None` - only the listed instruments are written
- `Restore` always restores every instrument and ignores overrides (`Restore` isn't a valid override)
- An unknown mode or instrument key stops Analyze before anything runs

**How writes stay safe:**
- The spreadsheet is saved first, `song.ini` files are written last
- A value is only written where `{header}_BackupData.csv` already holds that song/instrument's original, anything else is reported as `not backed up (skipped)`
- Values that match the write aren't rewritten, so repeat runs report them as `unchanged`
- Band is only written for songs with a Band row (2+ core instruments with an Expert D score)

> **Upgrading from an earlier version:** Build now fills blank backup cells (e.g. the `diff_vocals` column added with Vocals) from the current `song.ini`. If you already wrote Vocals difficulties with an earlier version, those written values will be captured as the "original". Restore first with the old version before rebuilding.

**Note: After updating `song.ini` data, you MUST SCAN SONGS for the new metadata to work.**

---

## 4. Rendering song graphs

`python render.py [retrieval code]`

`render.py` draws one PNG graph of difficulty over time for a specific song/instrument/level combo, using its retrieval code.

**Make sure the header in config matches the spreadsheet/library you are rendering from.**

You can render several at once, any mix of instruments and levels:

`python render.py 04821993EG 71620045MB 09933120HD 23859937XV`

Or from a text file, one code per line:

`python render.py --codes-file picks.txt`

**Outputs:**

One PNG per code, named `{code}_{Artist} - {Song}.png`, showing:

**5 Fret**
- **D** - overall difficulty over time
- **Notes** - note density per second
- **Variability** - how much the fret pattern is changing per second

**Drums**
- **D** - overall difficulty over time
- **Hands** - Hand note density per second
- **Travel** - how much movement across the pads is happening per second
- **Kicks** - Kick note density per second

**Vocals codes are not renderable yet** - `V` is a valid retrieval code suffix and shows up in the spreadsheet, but `render.py` has no vocals graphing path built out. Coming soon!

Graphs are available in light or dark mode depending on the config.

**Optional arguments:**
- `--header` / `--cache`: pick which library/cache to pull from
- `--out-dir`: where to save the PNGs (defaults to `render_dir` in `config.py`)

---

## 5. Fixes/Extension Ideas
**Fixes:**
- Midi files misbehaving - *possibly parser drift / file corrruption/truncation?*

**Extension Ideas:**
- Vocal harmonies (`HARM1`-`HARM3`) - *doesn't seem worth the effort*
- RB style band diff once all instruments are in
  
**Fork Ideas:**
- Vocal harmonies (`HARM1`-`HARM3`)
- Pro Instruments
- Scoring by totals (as opposed to average), type of notes (singles by type/state, chords by type)
- D by section + Section names for renders
- Including strum/hopo/tap state by note in the cache
- Actually doing something with note state once it exists
- Star Power Difficulty (how hard are SP phrases to hit?)
- Rhythm changes/variability possibly easier than pattern recognition?
- Pattern recognition (chords, trills, runs, zigs, quads, quints, anchoring, etc) / Ngrams
- A strain-based difficulty metric splitting strum vs fret
- DDR Groove Radar style scoring (probably tied to patterns)

---

## License
**MIT** - see LICENSE for details.
