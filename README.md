# Fretwork v0.6 - Expert Guitar Difficulty Analyzer

This is an analysis tool intended to calculate Expert Guitar song difficulty from .chart & .mid files (Guitar Hero, Rock Band, Clone Hero, YARG) using Notes Per Second (note density) & Variability Per Second (fret change) metrics. This started as a way to learn python and see if I could even begin to calculate difficulty from song data. A few months later it is a much larger and more complex project than I first expected.

[Explainer video with some historical context](https://youtu.be/emoWMpDJ4ls)

Extension areas / Fixes:
- Ini parsing issues
- Midi files misbehaving
- Adding Easy/Med/Hard
- Other 5 Fret instruments (Co-op/Rhythm Guitar, Bass, Keys)
- Vocals (Unique data, new metric needs, new difficulty logic/calcs)
- Drums (similar data, new metric needs, new difficulty logic/calcs)
- Testing pattern recognition (chords, trills, runs, zigs, quads, quints, etc)
- A strain-based difficulty metric factoring in note state (strum/hopo/tap) and splitting strum vs fret.

Libraries required are **pandas, numpy, tqdm, mido, and matplotlib** - everything else is in the base python install (as of 3.14.4 where this was built/tested)

![Render Example](https://github.com/Staycation44/fretwork/blob/main/renders/02139802_Dragonforce%20-%20Through%20The%20Fire%20Flames.png)

To use the tool setup **config** and run these in order:

1. **Build** - scan a library and save everything into a cache file
2. **Analyze** - turn that cache into a CSV including song metadata and calculated metrics, one row per song - this step applies the difficulty formula
3. **Render** - output a PNG graph of metrics over time for one or more specific songs based on an ID from the CSV

---

## 1. Setup: `config.py`

Before running anything, open `config.py` and check these values:

| Setting | What it does | Example |
|---|---|---|
| `SEARCH_PATH` | Sets the folder to cache/analyze | `r"C:\Users\[user]\Documents\Clone Hero\Songs"` |
| `HEADER` | A short name for the library, becomes the prefix on every output file | `"Library"` |

`SEARCH_PATH` - this tool has only been tested on windows devices, but should work on Mac/Linux with updated file paths.

`HEADER` is how Build defines a cache of song data, and how Analyze & Render search that cache. If you keep multiple libraries, give each one its own `HEADER` so their outputs don't overwrite each other. 

All outputs are named: `{header}_{kind}_{timestamp}.{ext}`

ex. `Library_cache_08052026-0330.pkl`, `Library_metrics_08052026-0330.csv`.

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

**Outputs:**

- A `{header}_cache_{timestamp}.pkl` file, the main output used by Analyze and Render
- A `{header}_errors_{timestamp}.csv` file, only generated if some songs failed to parse, this lists which file failed and why (e.g. missing guitar track, corrupt midi file)
- A console summary: how many songs had a `song.ini`, how many had no readable guitar chart, how many errored, and how many made it into the cache

**Optional arguments:**
- `--search-path`: scan a different folder than the one in `config.py`
- `--header`: name this run something other than `config.header`

---

## 3. Analyzing a cache

`analyze.py` loads the most recent cache for your config's `HEADER`, computes difficulty metrics for every song in it, and writes a CSV. This is the main output for browsing the library.

**Outputs:**

A CSV named `{header}_metrics_{timestamp}.csv`, containing a row per song including:

- **Retrieval code** (an 8-digit ID used to render graphs)
- Metadata: Song Title, Artist, Charter, Difficulty (song.ini's guitar_diff), Release/source pack
- The difficulty metrics / updated tier numbers (described later)

**Optional arguments:**

- `--header`: analyze a different library's most recent cache
- `--cache`: point at a specific cache file, instead of most recent for the header

---

## 4. The Difficulty Formula

### Definitions: NPS and VPS

Both families of metrics are derived from the song's chart or MIDI note events, each associated with a timestamp and a set of fret values, iterated over the duration of the song. Big thanks to TheNathannator for the extensive documentation on .ini, .chart, and .mid formats - would not have even started this project without that resource.

A sliding window of 1 second (1000ms) is swept over the note span in steps of 250ms. This deliberately includes silent intros and rests between sections, so that metrics reflect true density variations.

I am ignoring a lot of the data from the songs since this is mostly a proof of concept. Difficulties other than Expert, Tap/HOPO/Sustains, etc. In theory these impact overall song difficulty - but it's a level of additional development that's outside my current skill/comfort level. A more refined model similar to the strain model used for games like osu! would be an interesting next step.

### NPS (Notes Per Second)

This is a pretty standard metric used on a lot of custom song sites. For each 1 second window, NPS is the count of note timestamps. This is counting notes the same way the games do - any frets played at the same time count as 1 note (whether chords or single frets).

### VPS (Variability Per Second)

This is a unique metric (as far as I can tell). VPS calculates fret movement between notes by assigning a change value to each time stamp. This is computed by comparing each note's frets to the previous and returning the largest value of frets *removed* or *added*. The first note of a song is treated as a pure addition from an empty fretboard. VPS is the iteration of this calculation across the same windows used for NPS.

>**Variability Examples:**
>
>G to G - no frets added or removed so v = 0
>
>G to Y - 1 fret removed, 1 fret added so v = 1
>
>G to GYB - 2 frets added so v = 2
>
>GYB back to G - 2 frets removed so v = 2
>
>GR to YBO - 2 frets removed, 3 frets added so v = 3
>
>If all of these happened within 1 second VPS would be 8

VPS adds value for calculating overall difficulty since it can differ so much from NPS. A fast picking section with an NPS of 12 could have low or almost no VPS if there aren't many fret changes, similarly, a complex solo with fast zigs and runs can have the same VPS & NPS. There are even rare cases where constant chord changes can push VPS over NPS. By using both NPS & VPS I think it's possible to get a better look into difficulty than either one alone.

## The Math Part

Difficulty (D) is calculated by multiplying together N (a combination of the median, average, and peak NPS values for a song), V (a combination of the median, average, and peak VPS values for a song) and COV (an interaction term that approximates how consistent a song is by adding in standard deviation for both NPS & VPS along with the median and average). The specific formula is described below.

$$
D = N \cdot V \cdot CoV
$$

### Epsilon terms

These are used during $N$ & $V$ calculations to prevent 0 medians from collapsing the entire $D$ score, while being derived from the song's overall peak values for NPS & VPS.

$$
\varepsilon_N = 0.05\,p_{N}, \qquad \varepsilon_V = 0.05\,p_{V}
$$

### N & V

Pseudo-geometric mean of the NPS & VPS metrics, they sit on similar scales and help to balance each other out. A slow/simple song with a tough solo will have a lower value than a fast/complex song with an unremarkable solo. Peak & average alone gave unsatisfactory results because peak can be an extreme single second, but instead of weighting values (endless tuning/optimization hell), adding modified median here as another way to account for the overall experience across the song's duration helped balance out the influence of peak.

$$
N = \Big[(\mathrm{med}_N + \varepsilon_N)\cdot a_N \cdot p_N\Big]^{1/3}
$$

$$
V = \Big[(\mathrm{med}_V + \varepsilon_V)\cdot a_V \cdot p_V\Big]^{1/3}
$$

### Coefficients of variation (kinda)

A modified version of coefficient of variation. Using standard deviation and mean alone was too sensitive, so adding median helped balance it out. While median can be 0 on sparse songs with a lot of empty or simple sections, average is never 0 due to charts without notes being excluded from reaching the difficulty calculation step.

$$
CV_N = \frac{\sigma_N}{a_N + \mathrm{med}_N}, \qquad
CV_V = \frac{\sigma_V}{a_V + \mathrm{med}_V}
$$

### Interaction Term 

COV approximate how inconsistent the difficulty is and combines across NPS & VPS. COV has a floor of 1 so worst case we get raw N * V for an extremely consistent song, while most songs will score above 1. In practice this mostly buffs songs that have a lot of rest between sections which tank the averages.

$$
CoV = 1 + \sqrt{CV_N \cdot CV_V}
$$

### Final D Formula

$$
D = N \cdot V \cdot CoV
$$



**In the metrics CSV / render header, you'll see D translated two ways:**

- **RemapDiff (0–6):** A manual grouping, calibrated to roughly match the percentage of official releases across the seven tiers. Roughly, how would this have been tiered in a Rock Band game (capped at 6).
- **CalcTier:** A continuous, log-scaled tiering calculation. Every 0.44 natural-log increase in D over a baseline value increments the tier by one. This value is not capped, so officials at Dragonforce level end up in 7+, and a lot of notable customs are 10+.

RemapDiff is a classic 0–6 grouping, CalcTier is an open ended calculation that keeps getting higher as songs get harder.


---

## 5. Rendering song graphs

`python render.py [retrival code]`

`render.py` draws one PNG graph of difficulty over time for a specific song, using its retrieval code from the metrics CSV. Make sure the header in config matches the CSV/library you are rendering from.

**You can render several at once:**

`python render.py 04821993 71620045 09933120`

**Or from a text file, one code per line:**

`python render.py --codes-file picks.txt`

**Outputs:**

One PNG per code, named `{code}_{Artist} - {Song}.png`, showing three lines:

- **D** - overall difficulty over time (approximated since it does not include the COV modifier & has to be rescaled to fit on the same axis as N & V)
- **Notes** - note density per second
- **Variability** - how much the fret pattern is changing per second

Solo sections (and optionally star power, if enabled in the config) are shaded on the graph. The header of each image shows the song title/artist, charter, source, file format, and the D value / tier numbers from the metrics CSV. Available in a light or dark mode depending on the config.

**Optional arguments:**
- `--header` / `--cache`: pick which library/cache to pull from
- `--out-dir`: where to save the PNGs (defaults to `render_dir` in `config.py`)

## License
**MIT** - see LICENSE for details.
