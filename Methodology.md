
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
