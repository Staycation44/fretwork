
# The Difficulty Formula

## Definitions: NPS and VPS

Both families of metrics are derived from the song's chart or MIDI note events, each associated with a timestamp and a set of fret values, iterated over the duration of the song. Big thanks to TheNathannator for the extensive documentation on .ini, .chart, and .mid formats - would not have even started this project without that resource.

A sliding window of 1 second (1000ms) is swept over the note span in steps of 250ms. This deliberately includes silent intros and rests between sections, so that metrics reflect true density variations.

I am ignoring a lot of the data from the songs since this is mostly a proof of concept - see the Extensions section for ideas to include them.

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

## The Math Part (D = N x V x CoV)

Difficulty (D) is calculated by multiplying together N (a combination of the median, average, and peak NPS values for a song), V (a combination of the median, average, and peak VPS values for a song) and CoV (an interaction term that approximates how consistent a song is by adding in standard deviation for both NPS & VPS along with the median and average). The specific formula is described below.

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

CoV approximate how inconsistent the difficulty is and combines across NPS & VPS. COV has a floor of 1 so worst case we get raw N * V for an extremely consistent song, while most songs will score above 1. In practice this mostly buffs songs that have a lot of rest between sections which tank the averages.

$$
CoV = 1 + \sqrt{CV_N \cdot CV_V}
$$

### Final D Formula

$$
D = N \cdot V \cdot CoV
$$


## Binning Methodology

Reference for the calibration tables behind `functions/formula.py`.

### RemapDiff (0-6) Calibration

`RemapDiff` buckets a song's calculated `D` into a 0-6 label, calibrated per instrument group so that the *distribution* of RemapDiff labels across the reference official library roughly matches the distribution of that group's official `diff_*` tag values. Each row's `D range` is `(lower, upper]` against the **Expert-level D**

#### Guitar (covers Co-op and Rhythm - `GUITAR_REMAP_BINS`)

| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 8.0]       |    4.3%  |  4.3% |
| 1    | (8.0, 13.7]    |   10.6%  | 10.5% |
| 2    | (13.7, 21.2]   |   24.0%  | 24.2% |
| 3    | (21.2, 29.0]   |   25.1%  | 25.2% |
| 4    | (29.0, 38.2]   |   17.7%  | 17.6% |
| 5    | (38.2, 55.2]   |   12.0%  | 12.0% |
| 6    | (55.2, inf)    |    6.2%  |  6.3% |

#### Bass (`BASS_REMAP_BINS`)

| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 3.5]       |    6.7%  |  6.9% |
| 1    | (3.5, 8.3]     |   22.8%  | 22.5% |
| 2    | (8.3, 13.1]    |   27.6%  | 27.5% |
| 3    | (13.1, 19.1]   |   23.9%  | 23.9% |
| 4    | (19.1, 25.6]   |   10.9%  | 11.1% |
| 5    | (25.6, 36.2]   |    5.8%  |  5.7% |
| 6    | (36.2, inf)    |    2.4%  |  2.5% |

#### Keys (`KEYS_REMAP_BINS`)

| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 1.3]       |    8.7%  |  9.3% |
| 1    | (1.3, 4.8]     |   19.5%  | 19.1% |
| 2    | (4.8, 9.6]     |   18.3%  | 17.8% |
| 3    | (9.6, 16.3]    |   22.4%  | 22.6% |
| 4    | (16.3, 25.2]   |   14.9%  | 14.9% |
| 5    | (25.2, 35.2]   |    8.3%  |  8.3% |
| 6    | (35.2, inf)    |    7.9%  |  7.9% |



### CalcTier Calibration

`CalcTier` is a continuous log-scaled tier (`floor(log(D / BASE_D) / LN_INC) + 1`, 0 below `BASE_D`), uncapped, so very hard officials and many customs land at 7+. All three groups currently share the same constants:

| Group  | BASE_D | LN_INC |
|--------|-------:|-------:|
| Guitar |    7.6 |   0.44 |
| Bass   |    7.6 |   0.44 |
| Keys   |    7.6 |   0.44 |

These aren't separately fit per group yet, and aren't planned - these are all mechanically similar at this point and do a decent job of representing the actual difficulty.

### EMHX note

Both calibrations above were fit against each group's `diff_*` song.ini tag, assuming expert as the basis. So both `RemapDiff` and `CalcTier` are computed once per (song,instrument) from the **Expert** level's `D` only, and that single pair of values is shown on every EMHX row for that instrument in the metrics spreadsheet.