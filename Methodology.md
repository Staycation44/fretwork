
# The Difficulty Formulas <!-- omit in toc -->

## Index <!-- omit in toc -->
- [5-Fret Definitions](#5-fret-definitions)
- [5 Fret Math](#5-fret-math)
- [Drum Definitions](#drum-definitions)
- [Drum Math](#drum-math)
- [Vocal Definitions](#vocal-definitions)
- [Vocals Math](#vocals-math)
- [Binning Methodology](#binning-methodology)

## 5-Fret Definitions

Both families of metrics are derived from the song's chart or MIDI note events, each associated with a timestamp and a set of fret values, iterated over the duration of the song. Big thanks to TheNathannator for the extensive documentation on .ini, .chart, and .mid formats - would not have even started this project without that resource.

A sliding window of 1 second (1000ms) is swept over the note span in steps of 250ms. This deliberately includes silent intros and rests between sections, so that metrics reflect true density variations.

I am ignoring a lot of the data from the songs since this is mostly a proof of concept - see the Extensions section for ideas to include them.

### NPS (Notes Per Second) <!-- omit in toc -->

This is a pretty standard metric used on a lot of custom song sites. For each 1 second window, NPS is the count of note timestamps. This is counting notes the same way the games do - any frets played at the same time count as 1 note (whether chords or single frets).

### VPS (Variability Per Second) <!-- omit in toc -->

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

## 5 Fret Math

Difficulty (D) is calculated by adding together N (using median, average, and peak NPS for a song) and V (the same combination of VPS values), then multiplying by CoV (an interaction term that approximates how consistent through standard deviation, median, and average) and STAM (a gentle duration mod). The specific formula is described below.

$$
D = (N + V) \cdot CoV \cdot STAM
$$

> **v3 change:** D was previously multiplicative on N and V ($N \cdot V \cdot CoV \cdot STAM$). It's now additive, matching the shape Drums already used, so a fast/simple passage and a slow/complex one can't cancel each other toward zero the way a product would.

Median and standard deviation are computed over active windows only (windows containing at least one note). Including silent windows dragged the median toward 0 on any song with an intro or long rests, which underrated the active sections. Peak and average still run over every window, so rests continue to count against the average the way they should.

### Epsilon terms <!-- omit in toc -->

These are used during N & V calculations to prevent 0 medians from collapsing the entire D score, while being derived from the song's own average values for NPS & VPS.

$$
\varepsilon_N = 0.05\,a_{N}, \qquad \varepsilon_V = 0.05\,a_{V}
$$

### N & V <!-- omit in toc -->

Pseudo-geometric mean of the NPS & VPS metrics, they sit on similar scales and help to balance each other out. A slow/simple song with a tough solo will have a lower value than a fast/complex song with an unremarkable solo. Peak & average alone gave unsatisfactory results because peak can be an extreme single second, but instead of weighting values (endless tuning/optimization hell), adding modified median here as another way to account for the overall experience across the song's duration.

$$
N = \Big[(\mathrm{med}_N + \varepsilon_N)\cdot a_N \cdot p_N\Big]^{1/3}
$$

$$
V = \Big[(\mathrm{med}_V + \varepsilon_V)\cdot a_V \cdot p_V\Big]^{1/3}
$$

### Coefficients of variation <!-- omit in toc -->

A modified version of coefficient of variation. Using standard deviation and mean alone was too sensitive, so adding median helped balance it out. While median can still be low on sparse songs, average is never 0 due to charts without notes being excluded from reaching the difficulty calculation step.

$$
CV_N = \frac{\sigma_N}{a_N + \mathrm{med}_N}, \qquad
CV_V = \frac{\sigma_V}{a_V + \mathrm{med}_V}
$$

### Interaction Term <!-- omit in toc -->

CoV approximates how inconsistent the difficulty is and combines across NPS & VPS. CoV has a floor of 1 so worst case we get raw $N + V$ for an extremely consistent song, while most songs will score above 1. In practice this mostly buffs songs that have a lot of rest between sections which tank the averages.

$$
CoV = 1 + \sqrt{CV_N \cdot CV_V}
$$

### STAM (stamina) <!-- omit in toc -->

A sub-linear duration modifier: short songs are discounted, long ones slowly build a bonus. The exponent is deliberately small, giving roughly 66% at 30 seconds, 75% at 1 minute, 1x at the 230s reference (a typical 3-4 minute song), 1.1x at ~6 minutes and 1.2x at ~9.5 minutes.

$$
STAM = \left(\frac{\mathrm{Duration}}{t_{ref}}\right)^{s_{stam}}, \qquad t_{ref} = 230,\; s_{stam} = 0.20
$$

### Final D Formula <!-- omit in toc -->

$$
D = (N + V) \cdot CoV \cdot STAM
$$

---

## Drum Definitions

Drums share the same windowing idea as the 5 Fret instruments (a 1-second window swept in 250ms steps, deliberately including rests), but hands and kick are tracked as separate streams.

**HPS (Hands Per Second)** is NPS for drums: For each window, the count of simultaneous lanes struck at each timestamp, summed (a 2-lane hit counts as 2, same as two separate hits). Roll-lane sections (charted rolls/alt crashes) are excluded from the literal count and instead capped at a flat rate, since a roll-lane marker represents "keep going fast," not a note-for-note performance.

**KPS (Kicks Per Second)** is a straight note rate (like NPS), computed separately for single (1x) and double (2x) kick pedal charting, with the same windows as HPS/TPS.

**TPS (Travel Per Second)** is the VPS equivalent, with one difference from 5 Fret: only lanes newly struck count, as there is no release equivalent for drums.

>**Travel Examples** (lanes numbered 0-4 by chart lane: 0 red/snare, 1 yellow/hi-hat, 2 blue, 3 orange (5 lane) or green (4 lane), 4 green (5 lane)):
>
>Hat → Hat (lane 1 → 1) - same lane, nothing new struck, $t = 0$
>
>Hat → Hat+Snare (lane 1 → {0,1}) - 1 new lane, $t = 1$
>
>Snare → Green / Crash (lane 0 → 3 or 4) - 1 new lane, $t = 1$
>
>Hat+Snare → Blue+Green (lanes {0,1} → {2,3}) - 2 new lanes, $t = 2$
>
>Silence → Hat+Snare - nothing struck immediately before, $t = 2$

## Drum Math

Difficulty (D) is calculated by adding together H (using median, average, and peak HPS for a song), T (the same combination of TPS values), and K (the same combination of KPS values), then multiplying by CoV (the same interaction term as 5 Fret, taken across hands & kick) and STAM (the same duration mod). Same rough shape as 5 Fret, with the axes added rather than multiplied. The specific formula is described below.

$$
D = (H + T + K) \cdot CoV \cdot STAM
$$

As with 5 Fret, median and standard deviation are computed over active windows only. HPS & TPS both gate on hand-hit activity, and KPS gates on kick activity. TPS is gated on hand-hit activity rather than its own values, since travel legitimately reads 0 on a repeated lane and gating on that would throw away real windows.

### Epsilon terms <!-- omit in toc -->

Same guard as 5 Fret, one per axis, derived from each axis's own average.

$$
\varepsilon_H = 0.05\,a_{H}, \qquad \varepsilon_T = 0.05\,a_{T}, \qquad \varepsilon_K = 0.05\,a_{K}
$$

### H (Hands), T (Travel), & K (Kicks) <!-- omit in toc -->

The same pseudo-geometric mean 5 Fret's N & V use, applied to each raw metric (HPS, TPS, KPS).

$$
H = \Big[(\mathrm{med}_H + \varepsilon_H)\cdot a_H \cdot p_H\Big]^{1/3}
$$

$$
T = \Big[(\mathrm{med}_T + \varepsilon_T)\cdot a_T \cdot p_T\Big]^{1/3}
$$

$$
K = \Big[(\mathrm{med}_K + \varepsilon_K)\cdot a_K \cdot p_K\Big]^{1/3}
$$

$H$ (hit density) and $T$ (travel) are additive. A fast single-lane run and a slow wide-ranging one shouldn't collapse each other to zero the way a product would. Kick adds in the same way, for the same reason: a quiet kick under a busy hand part (or vice versa) shouldn't drag the whole song's difficulty toward zero.

$$
H + T + K
$$

### Coefficients of variation <!-- omit in toc -->

Same modified CV as 5 Fret, taken once per limb group. Travel doesn't get its own CV since it rides on the same hand windows as HPS.

$$
CV_H = \frac{\sigma_H}{a_H + \mathrm{med}_H}, \qquad
CV_K = \frac{\sigma_K}{a_K + \mathrm{med}_K}
$$

### Interaction Term <!-- omit in toc -->

Same construction as 5 Fret's, taken across the two limb groups. A song has to be uneven in both hands and feet to earn the full bonus. Scale value of 2 to boost its impact.

$$
CoV = 1 + c_{scale}\sqrt{CV_H \cdot CV_K}, \qquad c_{scale} = 2
$$

### STAM (stamina) <!-- omit in toc -->

Identical to 5 Fret's stamina term - sub-linear discount for short songs and slow boost for long ones.

$$
STAM = \left(\frac{\mathrm{Duration}}{t_{ref}}\right)^{s_{stam}}, \qquad t_{ref} = 230,\; s_{stam} = 0.20
$$

### Final D Formula <!-- omit in toc -->

$$
D = (H + T + K) \cdot CoV \cdot STAM
$$

$D$ is computed once per kick reading - `D_1x` for single pedal, `D_2x` for double kick variants where they exist. RemapDiff & CalcTier anchor to `D_1x`, since 1x is the reading every chart has.

A song with no kick notes at all still scores as $D = (H + T) \cdot STAM$.

### What's missing <!-- omit in toc -->

Nothing here has any memory of what came before. Every axis is a per hit or per second rate, so a steady groove repeated for several minutes scores its last loop exactly like its first. Long, busy, repetitive songs are consistently overrated as a result. This is something that can't really be fixed without adding pattern recognition of some kind.

---

## Vocal Definitions

Vocals use the same windowing idea (a 1-second window swept in 250ms steps, deliberately including rests), but there are no frets or lanes, and no EMHX levels - the games only ever have one lead vocal line (although some engines differ in strictness by level), so everything is treated as Expert. Only `PART VOCALS` from the .mid is read (.chart can't encode vocals, and harmonies aren't parsed).

The vocal track is split into three streams:
- **Sung notes** - pitched notes, including slides (`+`) and placeholders (`+$`)
- **Talkies** - rap/spoken/screamed segments. Two authoring conventions were uncovered: (RB-style) a pitched note paired with a lyric marked by `#` / `^` / `*`, & (GH-style) a lyric with no paired pitch
- **Percussion** - kept for duration & render only, otherwise treated as rest time

Authored talkie lengths are ignored so RB & GH style talkies can be treated equivalently. Every talkie gets a fixed length (133ms, estimated from official data), clipped so it never overlaps the next onset. This length is only used for song duration.

### PPS (Pitch-travel Per Second) <!-- omit in toc -->

Vocal's VPS equivalent. Each sung note is compared to the previous sung pitch, and the interval (in semitones) is its travel value. The raw interval is compressed by a square root so one big leap doesn't dominate a passage of many small steps. Unlike 5 Fret/Drums, the first note of a song has nothing to compare against, so it scores 0 rather than a pure addition.

>**Pitch Travel Examples** (MIDI pitch, C4 = 60):
>
>C4 → C4 - same pitch, $t = 0$
>
>C4 → D4 (60 → 62) - 2 semitones, $t = 2^{0.5} \approx 1.41$
>
>C4 → G4 (60 → 67) - 7 semitones, $t = 7^{0.5} \approx 2.65$
>
>C4 → C5 (60 → 72) - 12 semitones, $t = 12^{0.5} \approx 3.46$
>
>C4 → C6 (60 → 84) - 24 semitones, capped at 12, $t \approx 3.46$
>
>C4 → talkie → E4 - talkie skipped, compares 60 → 64, $t = 2$

### SPS (Syllables Per Second) <!-- omit in toc -->

Vocal's NPS equivalent - a straight rate of new syllables per window. A syllable is any sung note that isn't a slide or placeholder, plus every talkie. Slides and placeholders continue a syllable rather than starting a new one, so they add pitch travel but no syllables. Sung notes + talkies also defines `NoteCount`. This is mainly a rescue for talkie-heavy/talkie only songs.

### Static Features <!-- omit in toc -->

Two per-song values that aren't windowed, both from sung notes only & used to build R (Register):
- **Pitches** - count of distinct pitches used
- **maxPitch** - highest sung pitch

## Vocals Math

Difficulty (D) is calculated by multiplying P (using median, average, and peak PPS for a song) by R (register - where the line sits), adding S (the same combination of SPS values), then multiplying by CoV (the same interaction term, taken across pitch & syllables) and STAM (the same duration mod). Pitch movement is the main driver, with syllable rate as a secondary term. The specific formula is described below.

$$
D = (P \cdot R + S) \cdot CoV \cdot STAM
$$

Vocals is sort of a hybrid of lessons from 5 Fret & Drums due to the differences in vocals charting. Official tiering conventions are incredibly messy (officials don't agree on nearly anything, even comparing DLC vs main setlist), so this is the loosest fit to official difficulty of any instrument.

### Epsilon terms <!-- omit in toc -->

Same guard as 5 Fret/Drums.

$$
\varepsilon_P = 0.05\,a_{P}, \qquad \varepsilon_S = 0.05\,a_{S}
$$

### P (Pitch-travel) & S (Syllables) <!-- omit in toc -->

The same pseudo-geometric mean used everywhere else.

$$
P = \Big[(\mathrm{med}_P + \varepsilon_P)\cdot a_P \cdot p_P\Big]^{1/3}
$$

$$
S = \Big[(\mathrm{med}_S + \varepsilon_S)\cdot a_S \cdot p_S\Big]^{1/3}
$$

### R (Register) <!-- omit in toc -->

Where the vocal line tracks, not how fast it moves through it. Pitch vocabulary is square-root compressed, and the top of the line is measured against middle C (MIDI 60, the midpoint of the 36-84 chartable range). R is 0 when a song has no sung notes.

$$
R = \sqrt{\mathrm{Pitches}}\cdot\frac{\mathrm{maxPitch}}{60}
$$

### Coefficients of variation <!-- omit in toc -->

Same modified CV as 5 Fret/Drums, taken across pitch travel & syllables.

$$
CV_P = \frac{\sigma_P}{a_P + \mathrm{med}_P}, \qquad
CV_S = \frac{\sigma_S}{a_S + \mathrm{med}_S}
$$

### Interaction Term <!-- omit in toc -->

Similar to 5 Fret's interaction term. A song has to be uneven in both pitch movement and syllable rate to earn the full bonus.

$$
CoV = 1 + \sqrt{CV_P \cdot CV_S}
$$

### STAM (stamina) <!-- omit in toc -->

Identical to 5 Fret's stamina term - reused wholesale.

$$
STAM = \left(\frac{\mathrm{Duration}}{t_{ref}}\right)^{s_{stam}}, \qquad t_{ref} = 230,\; s_{stam} = 0.20
$$

### Final D Formula <!-- omit in toc -->

$$
D = \left(P \cdot \sqrt{\mathrm{Pitches}}\cdot\frac{\mathrm{maxPitch}}{60} + S\right) \cdot \left(1 + \sqrt{CV_P \cdot CV_S}\right) \cdot \left(\frac{\mathrm{Duration}}{230}\right)^{0.2}
$$

The only vocals-specific constant is middle C (60) - everything else is shared with 5 Fret/Drums.

### What's missing <!-- omit in toc -->

A lot of what makes vocals hard is familiarity with the song, lyrical awkwardness, obscured or strange vocal processing, and other things that just can't be picked up from midi note data.

---

## Binning Methodology

Reference for the calibration tables behind `fret_formula.py`, `drum_formula.py`, and `vocal_formula.py`.

### RemapDiff (0-6) Calibration <!-- omit in toc -->

`RemapDiff` buckets a song's calculated `D` into a 0-6 tiers, calibrated per instrument so that the distribution of remapped tiers roughly matches the distribution of that group's official `diff_*` tag values. Each row's `D range` is `(lower, upper]` against the **Expert-level D**.

#### Guitar (covers Co-op and Rhythm - `GUITAR_REMAP_BINS`) <!-- omit in toc -->

| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 7.2]       |    4.2%  |  4.9% |
| 1    | (7.2, 8.6]     |   10.5%  | 11.0% |
| 2    | (8.6, 10.3]    |   24.5%  | 24.2% |
| 3    | (10.3, 12.0]   |   24.6%  | 23.7% |
| 4    | (12.0, 14.0]   |   18.1%  | 17.2% |
| 5    | (14.0, 17.1]   |   11.7%  | 12.4% |
| 6    | (17.1, inf)    |    6.4%  |  6.7% |

#### Bass (`BASS_REMAP_BINS`) <!-- omit in toc -->

| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 5.1]       |    6.6%  |  6.5% |
| 1    | (5.1, 7.2]     |   23.1%  | 23.5% |
| 2    | (7.2, 8.6]     |   27.8%  | 28.0% |
| 3    | (8.6, 10.2]    |   23.7%  | 22.4% |
| 4    | (10.2, 11.9]   |   10.6%  | 11.1% |
| 5    | (11.9, 14.1]   |    5.7%  |  5.8% |
| 6    | (14.1, inf)    |    2.5%  |  2.6% |

#### Keys (`KEYS_REMAP_BINS`) <!-- omit in toc -->

| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 3.5]       |    8.7%  |  8.7% |
| 1    | (3.5, 6.0]     |   19.5%  | 19.7% |
| 2    | (6.0, 7.8]     |   18.3%  | 17.4% |
| 3    | (7.8, 9.7]     |   22.4%  | 22.6% |
| 4    | (9.7, 11.8]    |   14.9%  | 14.7% |
| 5    | (11.8, 13.6]   |    8.3%  |  8.7% |
| 6    | (13.6, inf)    |    7.9%  |  8.1% |

#### Drums (`DRUM_REMAP_BINS`) <!-- omit in toc -->


| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 9.8]       |    4.1%  |  4.2% |
| 1    | (9.8, 12.1]    |    9.9%  | 10.0% |
| 2    | (12.1, 13.6]   |   16.3%  | 16.4% |
| 3    | (13.6, 15.6]   |   26.3%  | 25.9% |
| 4    | (15.6, 18.5]   |   26.6%  | 26.8% |
| 5    | (18.5, 21.8]   |   12.4%  | 12.4% |
| 6    | (21.8, inf)    |    4.4%  |  4.3% |

#### Vocals (`VOCAL_REMAP_BINS`) <!-- omit in toc -->

Refit for the updated formula (official, tagged charts only: n=2857).

| Tier | D range        | Official | Remap |
|------|----------------|---------:|------:|
| 0    | (0, 12.0]      |    6.1%  |  6.0% |
| 1    | (12.0, 16.4]   |   14.0%  | 14.1% |
| 2    | (16.4, 21.5]   |   26.5%  | 26.4% |
| 3    | (21.5, 27.3]   |   30.4%  | 30.4% |
| 4    | (27.3, 32.6]   |   14.5%  | 14.7% |
| 5    | (32.6, 38.0]   |    5.9%  |  5.8% |
| 6    | (38.0, inf)    |    2.6%  |  2.6% |

### CalcTier Calibration <!-- omit in toc -->

`CalcTier` is an uncapped log-scaled tier, so very hard officials and many customs land at 7+.

`BASE_D` sets the tier 0 into tier 1 boundary. `LN_INC` sets the step size. This fit is developed using a minimum step size to try to keep the vast majority of songs under tier 7 for a comparable feel.

| Group  | BASE_D | LN_INC | D step per tier | Home |
|--------|-------:|-------:|----------------:|----------|
| G/B/K  |  7.101 | 0.1792 |            ~20% | `fret_formula.py` |
| Drums  | 10.115 | 0.1516 |            ~16% | `drum_formula.py` |
| Vocals | 14.000 | 0.1898 |            ~21% | `vocal_formula.py` |
