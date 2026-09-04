# Fretwork v0.7 - Expert 5-Fret Difficulty Analyzer

This is an analysis tool intended to calculate Expert difficulty for Guitar/Bass/Keys from .chart & .mid files (Guitar Hero, Rock Band, Clone Hero, YARG) using Notes Per Second (note density) & Variability Per Second (fret change) metrics.

Every 5-fret instrument is supported: **Guitar, Co-op Guitar, Rhythm Guitar, Bass, and Keys** - each is parsed, cached, and scored independently, and a song can contribute a row for every instrument charted.

[Explainer video with some historical context](https://youtu.be/emoWMpDJ4ls)

Libraries required: **pandas, numpy, tqdm, mido, matplotlib, and openpyxl** 

![Render Example](https://github.com/Staycation44/fretwork/blob/main/renders/02139802G_Guitar_Dragonforce%20-%20Through%20The%20Fire%20Flames.png)

## Using Fretwork
To use the tool setup **config** and run these in order:

1. **Build** - Scan a library, save everything into a cache file, & creates a backup of original difficulties
2. **Analyze** - Turn Build's cache into an .xlsx spreadsheet including song metadata and calculated metrics for every song/instrument combo. Optionally, applies calculated difficulty to `song.ini` files for use in game, or restores them back to their originals from the backup
3. **Render** - Output a PNG graph of metrics over time for one or more song/instrument combos based on a retrieval code from the spreadsheet

## Index
- [Fretwork v0.7 - Expert 5-Fret Difficulty Analyzer](#fretwork-v07---expert-5-fret-difficulty-analyzer)
  - [Using Fretwork](#using-fretwork)
  - [Index](#index)
  - [1. Setup: `config.py`](#1-setup-configpy)
    - [Render appearance settings](#render-appearance-settings)
  - [2. Building a cache](#2-building-a-cache)
  - [3. Analyzing a cache](#3-analyzing-a-cache)
      - [5-Fret D Formula](#5-fret-d-formula)
  - [4. Rendering song graphs](#4-rendering-song-graphs)
  - [5. Fixes/Extension Ideas](#5-fixesextension-ideas)
  - [License](#license)

---

## 1. Setup: `config.py`

Before running anything, open `config.py` and check these values:

| Setting | What it does | Example |
|---|---|---|
| `SEARCH_PATH` | Sets the folder to cache/analyze | `r"C:\Users\[user]\Documents\Clone Hero\Songs"` |
| `HEADER` | A short name for the library, becomes the prefix on every output file | `"Library"` |
| `DIFF_WRITE_MODE` | Change from None to allow Analyze to write/restore your `song.ini` files | `"CalcTier"` |

`SEARCH_PATH` - this tool has only been tested on windows devices, but should work on Mac/Linux with updated file paths.

`HEADER` is how Build defines a cache of song data, and how Analyze & Render search that cache. If you keep multiple libraries, give each one its own `HEADER` so their outputs don't overwrite each other. 

All outputs are named: `{header}_{kind}_{timestamp}.{ext}`

ex. `Library_cache_08052026-0330.pkl`, `Library_metrics_08052026-0330.xlsx`.

You can also override `SEARCH_PATH` and `HEADER` on the command line (via `--search-path` / `--header`) instead of editing the file, if preferred.

### Render appearance settings

Under `RENDER_DEFAULT` and `RENDER_THEMES`, you can tweak how `render.py's` PNGs look:

- `mode`: `"dark"` or `"light"` to set overall color theme
- `color_d`, `color_nps`, `color_vps`, `color_star_power`: line/fill colors
- `figsize`, `dpi`: image size and resolution
- `show_solo_spans` / `show_star_power_spans`: whether solo and star power sections are displayed on the graph
- `fill_curves`, `fill_alpha`, `linewidth`, `grid_alpha`: general styling

---

## 2. Building a cache

`build.py` walks `SEARCH_PATH`, finds every `song.ini`, `notes.chart`, and `notes.mid`, reads them, and writes one cache file containing every song's note data and metadata. This is the slowest step (~10 minutes on a ~3k song library - more if more midi files, less if more charts).

By default this will run on the `SEARCH_PATH` & `HEADER` set in the config.

Additionally, this always backs up your original difficulties as it scans, regardless of anything set in `config.py` - Build never writes to `song.ini` itself, it only records what's there so Analyze can restore it later if you ever want to.

**Outputs:**

- A `{header}_cache_{timestamp}.pkl` file, the main output used by Analyze and Render
- A `{header}_errors_{timestamp}.csv` file, only generated if some songs failed to parse, this lists which file failed and why (e.g. missing guitar track, corrupt midi file)
- A `{header}_BackupData.csv` file, which is a back up that stores all difficulties that were found at the time of building
- A console summary: how many songs had a `song.ini`, how many had no readable guitar chart, how many errored, and how many made it into the cache

**Optional arguments:**
- `--search-path`: scan a different folder than the one in `config.py`
- `--header`: name this run something other than `config.header`

---

## 3. Analyzing a cache

`analyze.py` loads the most recent cache for your config's `HEADER`, computes density/difficulty metrics for every song/instrument combo in it, and writes a single **.xlsx spreadsheet**. This is the main output for browsing the library.

Optionally, `analyze.py` can also update each instrument's `diff_*` tag for use in game (`diff_guitar`, `diff_guitar_coop`, `diff_rhythm`, `diff_bass`, `diff_keys`). You can also restore all of them to the original backups from Build. This option runs via args or a setting in the config.

**Outputs:**

An .xlsx spreadsheet named `{header}_metrics_{timestamp}.xlsx`, with one tab per instrument group that has data in the cache (`Guitar` - combining Guitar/Co-op/Rhythm, `Bass`, `Keys`)


- **Retrieval code** - an 8-digit song hash plus a single-letter instrument suffix (`G`/`C`/`R`/`B`/`K`), used to render graphs
- Metadata: Song Title, Artist, Charter, Type (Lead/Co-op/Rhythm/Bass/Keys), Difficulty (song.ini diff tags), Release/Source
- The difficulty metrics & updated Remap/CalcTier numbers

Each tab is formatted for browsing. The raw NPS/VPS details and N/V/COV formula columns are included but hidden by default - unhide them if you want to see the components behind D.

#### 5-Fret D Formula

**Full formula details in `Methodology.md`**
$$
D = N \cdot V \cdot CoV
$$

**In the metrics spreadsheet / render header, you'll see D translated two ways:**

- **RemapDiff (0–6):** A manual grouping, calibrated to roughly match the percentage of official releases across the seven tiers. Roughly, how would this have been tiered in a Rock Band game (capped at 6). Guitar (plus Co-op/Rhythm), Bass, and Keys each have their own bin edges, fit against that instrument's own `diff_*` distribution.
- **CalcTier:** A continuous, log-scaled tiering calculation. Every 0.44 natural-log increase in D over a baseline value increments the tier by one. This value is not capped, so officials at Dragonforce level end up in 7+, and a lot of notable customs are 10+. Unlike RemapDiff, the baseline/increment constants are currently shared across all instruments rather than fit per-instrument.

**Optional arguments:**

- `--header`: analyze a different library's most recent cache
- `--cache`: point at a specific cache file, instead of most recent for the header
- `--diff-mode`: `CalcTier`, `RemapDiff`, or `Restore`.
  - `CalcTier`/`RemapDiff` writes that calculation's value into every song's own `diff_*` tag, per instrument
  - `Restore` returns every instrument's `diff_*` values back to its `{header}_BackupData.csv` original, throws errors for songs moved/deleted
  - If not supplied, falls back to `config.DIFF_WRITE_MODE` (default `None`, which leaves song.ini alone)

**Note: After updating `song.ini` data, you MUST SCAN SONGS for the new metadata to work.**



---

## 4. Rendering song graphs

`python render.py [retrieval code]`

`render.py` draws one PNG graph of difficulty over time for a specific song/instrument combo, using its retrieval code from the metrics spreadsheet. A retrieval code is the 8-digit song hash plus a single-letter instrument suffix (`G`, `C`, `R`, `B`, `K`). Make sure the header in config matches the spreadsheet/library you are rendering from.

**You can render several at once, any mix of instruments:**

`python render.py 04821993G 71620045B 09933120K`

**Or from a text file, one code per line:**

`python render.py --codes-file picks.txt`

**Outputs:**

One PNG per code, named `{code}_{Instrument}_{Artist} - {Song}.png`, showing three lines:

- **D** - overall difficulty over time (approx since it does not include CoV & has to be rescaled to fit on the same axis as N & V)
- **Notes** - note density per second
- **Variability** - how much the fret pattern is changing per second

Solo sections (and optionally star power, if enabled in the config) are shaded on the graph. The header of each image shows instrument, charter, source, file format, and the D value / tier numbers from the metrics spreadsheet. Available in a light or dark mode depending on the config.

**Optional arguments:**
- `--header` / `--cache`: pick which library/cache to pull from
- `--out-dir`: where to save the PNGs (defaults to `render_dir` in `config.py`)

---

## 5. Fixes/Extension Ideas
**Fixes:**
- Midi files misbehaving - *possibly parser drift / file corrruption/truncation?*

**Extension Ideas:**
- Adding Easy/Med/Hard
- Vocals (Unique data, new metric needs, new difficulty logic/calcs) - *design in progress*
- Drums (similar data, new metric needs, new difficulty logic/calcs) - *design in progress*
- RB style band diff once all instruments are in
- Retesting duration and ways to include it (GHVH outliers) - *very annoying*
- Negative weighting for long empty or long slow sections (related to duration changes) - *may make short songs worse?*
- scoring by totals (as opposed to average), type of notes (singles by type, chords by type)
- D by section - help sort out solo spikes even if not in a solo event (older GH games)
- Section names for renders
- Including strum/hopo/tap state by note in the cache
- Actually doing something with note state once it exists (ratios over the song was a good suggestion)
- Star Power Difficulty (how hard are SP phrases to hit?)
- Rhythm changes/variability possibly easier than pattern recognition?
- Pattern recognition (chords, trills, runs, zigs, quads, quints, anchoring, etc)
- A strain-based difficulty metric splitting strum vs fret
- DDR Groove Radar style scoring (probably tied to patterns)

---

## License
**MIT** - see LICENSE for details.
