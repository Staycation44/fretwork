
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

## The Math Part (D = N x V x CoV x STAM)

Difficulty (D) is calculated by multiplying together N (using median, average, and peak NPS for a song), V (the same combination of VPS values), CoV (an interaction term that approximates how consistent through standard deviation, median, and average) and STAM (a gentle duration mod). The specific formula is described below.

$$
D = N \cdot V \cdot CoV \cdot STAM
$$

Median and standard deviation are computed over **active windows only** - windows containing at least one note. Including silent windows dragged the median toward 0 on any song with an intro or long rests, which underrated the active sections. Peak and average still run over every window, so rests continue to count against the average the way they should.

### Epsilon terms

These are used during N & V calculations to prevent 0 medians from collapsing the entire $D$ score, while being derived from the song's own average values for NPS & VPS.

$$
\varepsilon_N = 0.05\,a_{N}, \qquad \varepsilon_V = 0.05\,a_{V}
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

A modified version of coefficient of variation. Using standard deviation and mean alone was too sensitive, so adding median helped balance it out. While median can still be low on sparse songs, average is never 0 due to charts without notes being excluded from reaching the difficulty calculation step.

$$
CV_N = \frac{\sigma_N}{a_N + \mathrm{med}_N}, \qquad
CV_V = \frac{\sigma_V}{a_V + \mathrm{med}_V}
$$

### Interaction Term 

CoV approximates how inconsistent the difficulty is and combines across NPS & VPS. CoV has a floor of 1 so worst case we get raw $N \cdot V$ for an extremely consistent song, while most songs will score above 1. In practice this mostly buffs songs that have a lot of rest between sections which tank the averages. $c_{scale}$ sets how much that inconsistency is worth - it's a tuning dial, currently 4.

$$
CoV = 1 + c_{scale}\sqrt{CV_N \cdot CV_V}, \qquad c_{scale} = 4
$$

### STAM (stamina)

A sub-linear duration modifier: short songs are discounted, long ones slowly build a bonus. The exponent is deliberately small, so this nudges rather than decides - roughly 66% at 30 seconds, 75% at 1 minute, 1x at the 230s reference (a typical 3-4 minute song), 1.1x at ~6 minutes and 1.2x at ~9.5 minutes.

$$
STAM = \left(\frac{\mathrm{Duration}}{t_{ref}}\right)^{s_{stam}}, \qquad t_{ref} = 230,\; s_{stam} = 0.20
$$

### Final D Formula

$$
D = N \cdot V \cdot CoV \cdot STAM
$$

---

## Drum Definitions: HPS, TPS, & KPS

Drums share the same windowing idea as the 5 Fret instruments (a 1-second window swept in 250ms steps, deliberately including rests), but hands and kick are tracked as separate streams, and a 5-lane hand kit needs a couple of ideas 5 Fret charts don't: which lanes are being hit, not just how many notes, and hands and kick tracked as separate streams that share one song duration, so their rates stay comparable.

**HPS (Hands Per Second)** is NPS for drums: For each window, the count of simultaneous lanes struck at each timestamp, summed (a 2-lane hit counts as 2, same as two separate hits). Roll-lane sections (charted rolls/alt crashes) are excluded from the literal count and instead capped at a flat rate, since a roll-lane marker represents "keep going fast," not a note-for-note performance.

**TPS (Travel Per Second)** is drum's VPS equivalent, but two things are different from 5 Fret . Only lanes newly struck count, not lanes that stop being hit (no release equivalent). Second, lane position matters: a hand moving from the hi-hat to a far crash cymbal is a bigger physical reach than a hand moving to the adjacent snare, so each newly-struck lane is priced by its distance (in lane positions, left to right) to the nearest lane already being hit. That raw distance is compressed by a square root so one big cross-kit reach doesn't dominate a passage of many small movements the way an uncompressed distance would.


>**Travel Examples** ($\gamma=0.5$, lanes numbered 0-4 left to right):
>
>Hat → Hat - same lane, nothing new struck, $t = 0$
>
>Hat → Hat+Snare (lane 0 → {0,1}) - 1 new lane, distance 1, $t = 1^{0.5} = 1$
>
>Hat → Crash (lane 0 → 4) - 1 new lane, distance 4, $t = 4^{0.5} = 2$
>
>Silence → Hat+Snare - nothing struck immediately before, pure addition, $t = 2$ (no compression)

**KPS (Kicks Per Second)** is a straight note rate (like NPS), computed separately for single (1x) and double (2x) kick pedal charting, with the same windows as HPS/TPS.

## The Drum Math Part (D = Base · CoV · STAM)

Three axes, one consistency term, one duration term. Same shape as the 5 Fret formula, with the axes summed rather than multiplied.

$$
D = (H + T + K)\cdot CoV_{overall}\cdot STAM
$$

### H, T, K

Every raw metric above (HPS, TPS, KPS) goes through the same pseudo-geometric-mean combination 5 Fret's N/V use, with its own epsilon guard, and reports its own coefficient of variation:

$$
\mathrm{axis}(p,a,\mathrm{med}) = \Big[(\mathrm{med}+\varepsilon)\cdot a \cdot p\Big]^{1/3}, \qquad \varepsilon = 0.05\,a
$$

$$
H = \mathrm{axis}(p_H,a_H,\mathrm{med}_H), \quad
T = \mathrm{axis}(p_T,a_T,\mathrm{med}_T), \quad
K = \mathrm{axis}(p_K,a_K,\mathrm{med}_K)
$$

As with 5 Fret, median and standard deviation are taken over active windows only. TPS is gated on hand-hit activity rather than its own values, since travel legitimately reads 0 on a repeated lane and gating on that would throw away real windows.

### Base

$H$ (hit density) and $T$ (travel) are additive. A fast single-lane run and a slow wide-ranging one shouldn't collapse each other to zero the way a product would. Kick adds in the same way, for the same reason: a quiet kick under a busy hand part (or vice versa) shouldn't drag the whole song's difficulty toward zero.

$$
\mathrm{Base} = H + T + K
$$

### CoV (consistency)

Same construction as 5 Fret's, taken across the two limb groups. A song has to be uneven in both hands and feet to earn the full bonus.

$$
CV_H = \frac{\sigma_H}{a_H + \mathrm{med}_H}, \qquad
CV_K = \frac{\sigma_K}{a_K + \mathrm{med}_K}
$$

$$
CoV = 1 + c_{scale}\sqrt{CV_H \cdot CV_K}, \qquad c_{scale} = 2
$$

### STAM

Identical to 5 Fret's stamina term: a slow, sub-linear discount for short songs and boost for long ones.

$$
\mathrm{STAM} = \left(\frac{\mathrm{Duration}}{230}\right)^{0.20}
$$

### Final D Formula

$$
D = \mathrm{Base}\cdot CoV\cdot \mathrm{STAM}
$$

$D$ is computed once per kick reading - `D_1x` for single pedal, `D_2x` for double.

### What's missing

Nothing here has any memory of what came before. Every axis is a per hit or per second rate, so a steady groove repeated for several minutes scores its last loop exactly like its first. Long, busy, repetitive songs are consistently overrated as a result. This is something that can't really be fixed without adding pattern recognition of some kind.

---

## Binning Methodology

Reference for the calibration tables behind `fret_formula.py` and `drum_formula.py`.

> **Note: NEED TO FIX BIN EDGES FOR 5 FRET**

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

#### Drums (`drum_formula.DRUM_REMAP_BINS`)

Lives in `drum_formula.py`, not `fret_formula.py` - drums' D formula and its RemapDiff/CalcTier calibration are fully self-contained there rather than routed through fret_formula.py's guitar/bass/keys calibration-group machinery, since there's only one drum calibration group.

Fit against a 2646-song real drum library's `diff_drums` distribution, using
`D_1x` - same quantile-matching method as the three groups above.

| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 10.3]      |    4.0%  |  4.2% |
| 1    | (10.3, 12.3]   |    9.1%  |  8.9% |
| 2    | (12.3, 14.0]   |   15.6%  | 15.8% |
| 3    | (14.0, 16.2]   |   27.2%  | 27.6% |
| 4    | (16.2, 19.2]   |   27.5%  | 27.0% |
| 5    | (19.2, 22.8]   |   12.3%  | 12.3% |
| 6    | (22.8, inf)    |    4.3%  |  4.3% |

### CalcTier Calibration

`CalcTier` is a log-scaled tier (`floor(log(D / BASE_D) / LN_INC) + 1`, Tier 0 below `BASE_D`), uncapped, so very hard officials and many customs land at 7+.

`BASE_D` sits at each group's RemapDiff tier-0/1 boundary. `LN_INC` sets the step size.

| Group  | BASE_D | LN_INC | D step per tier | Lives in |
|--------|-------:|-------:|----------------:|----------|
| Guitar |   15.8 |   0.35 |            +42% | `fret_formula.py` |
| Bass   |   15.8 |   0.35 |            +42% | `fret_formula.py` |
| Keys   |   15.8 |   0.35 |            +42% | `fret_formula.py` |
| Drums  |   10.3 |   0.16 |            +17% | `drum_formula.py` |

Guitar/Bass/Keys share both constants despite different D scales since they're mechanically similar.

Drums needs its own fit because D is constructed differently. 5 Fret is multiplicative while drums is additive, so drum D spreads about half as far in log terms over a similar range of real difficulty.

### EMHX note

Both calibrations above were fit against each group's `diff_*` song.ini tag, assuming expert as the basis. So both `RemapDiff` and `CalcTier` are computed once per (song,instrument) from the **Expert** level's `D` only, and that single pair of values is shown on every EMHX row for that instrument in the metrics spreadsheet.