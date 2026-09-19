"""
PLOT - Renders selected song's curves to a PNG.

y-axis scales per song

Guitar/Bass/Keys: NPS/VPS/D share an axis by using D = sqrt(NPS * VPS)

Drums: Hands/Travel/Kicks/D share an axis, D = Hands + Travel + Kicks
    - Hands reuses the NPS color, Travel reuses the VPS color, Kick has a new color
    - a chart with 2x stacks a second chart underneath the 1x

Vocals: Pitch/Syllables/D share an axis, D approximated by R*A*Pitch + S_WEIGHT*Syllables
    - Pitch reuses the VPS color, Syllables reuses the NPS color, Percussion reuses Kick's color
    - Percussion is render-only (not part of D) and only drawn when the chart actually has any

Light/dark themes can be set in config

All three layouts share one set of helpers (axes styling, header, save) - only the curves differ
Text is drawn with parse_math off, so '$' in names prints literally instead of as mathtext
Fonts: DejaVu Sans (matplotlib's default) first, then whichever CJK-capable fonts are installed as
per-glyph fallbacks (matplotlib 3.6+) - Latin text renders exactly as before
"""

import contextlib
import pathlib
import re
import warnings

import matplotlib
matplotlib.use('Agg')  # no display in a batch render
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import MaxNLocator, FuncFormatter

import config
from functions import instruments, timestamp

# fixed header truncation limits - keeps PNG width consistent song to song
TITLE_LIMIT = 44      # applied to song title and artist separately
CHARTER_LIMIT = 28
RELEASE_LIMIT = 34

# small in-axes label distinguishing the two drum subplots
KICK_MODE_LABELS = {
    '1x': '1x (single pedal)',
    '2x': '2x (double pedal)',
}

# primary font + fallbacks for glyphs it doesn't have (Japanese/Chinese/Korean titles)
# only installed fonts are used, so missing ones never trigger 'font not found' warnings
FONT_CANDIDATES = [
    'DejaVu Sans',        # matplotlib default - all Latin text
    'Noto Sans CJK JP',   # Linux / manually installed
    'Noto Sans JP',
    'Yu Gothic',          # Windows
    'Meiryo',
    'Microsoft YaHei',
    'Malgun Gothic',
    'Hiragino Sans',      # macOS
    'Arial Unicode MS',
]
_FONT_FAMILY = None


def _font_family():
    global _FONT_FAMILY
    if _FONT_FAMILY is None:
        installed = {f.name for f in font_manager.fontManager.ttflist}
        _FONT_FAMILY = [name for name in FONT_CANDIDATES if name in installed] or ['DejaVu Sans']
    return _FONT_FAMILY


# fonts + quiet missing-glyph warnings (a glyph no installed font has still renders as a box)
@contextlib.contextmanager
def _render_context():
    with plt.rc_context({'font.family': _font_family()}), warnings.catch_warnings():
        warnings.filterwarnings('ignore', message=r'Glyph .* missing from')
        yield

#-------------
# Filename
#-------------
_UNSAFE = re.compile(r'[^A-Za-z0-9 _.-]')

# strips non-ASCII for display
def _safe(text, limit=60):
    cleaned = _UNSAFE.sub('', str(text)).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned[:limit] or 'unknown'

# code + artist + song title
def output_filename(entry):
    meta = entry.get('meta', {})
    return f"{entry['code']}_{_safe(meta.get('Artist'))} - {_safe(meta.get('Name'))}.png"

# combined EMHX level + instrument label
def level_instrument_label(entry):
    level_label = instruments.LEVEL_DISPLAY_NAMES.get(entry.get('level'), '')
    instrument_label = instruments.DISPLAY_NAMES.get(entry.get('instrument'), '')
    return f"{level_label} {instrument_label}".strip()

# RENDER_DEFAULT + the selected theme
def resolve_profile(profile=None):
    if profile is not None:
        return dict(profile)
    mode = config.RENDER_DEFAULT.get('mode', 'light')
    theme = config.RENDER_THEMES.get(mode, config.RENDER_THEMES['light'])
    return {**config.RENDER_DEFAULT, **theme}

# Header text
def _ellipsize(text, limit):
    text = str(text)
    if len(text) <= limit:
        return text
    return text[:limit - 3].rstrip() + '...'

# sets Release (Official tag)
def release_label(meta):
    release = str(meta.get('Release') or '').strip() or 'Custom'
    if release.lower() == 'custom':
        return 'Custom'
    tag = 'official' if meta.get('Official') else 'custom'
    return f"{_ellipsize(release, RELEASE_LIMIT)} ({tag})"

# D display - 5 Fret/vocals is just "D" / drums is "D_1x" or "D_1x / D_2x"
def _d_display(difficulty):
    if 'D_1x' in difficulty:
        d_1x = difficulty['D_1x']
        d_2x = difficulty.get('D_2x')
        if d_2x is not None:
            return f"D {d_1x:.2f} / {d_2x:.2f}"
        return f"D {d_1x:.2f}"
    return f"D {difficulty['D']:.2f}"

# 'diff' shown in the header:
#   original_diff is the backup CSV cell for this song/instrument, or None when the song isn't backed up
#   backed up    -> the original value ('-' when blank, or when song.ini had no tag)
#   not backed up -> the value song.ini had at Build, marked '(ini)' since it may be a written value
def _diff_label(meta, instrument_key, original_diff):
    if original_diff is not None:
        return original_diff if original_diff not in ('', 'missing') else '-'
    ini_diff = (meta.get('Difficulty') or {}).get(instrument_key)
    return f"{ini_diff} (ini)" if ini_diff is not None else '-'


# metadata line - level+instrument / charter / release (tag) / file type / D / calc tier / remap bin
def meta_header(entry, difficulty, original_diff=None):
    meta = entry.get('meta', {})
    instrument_key = entry.get('instrument')

    bits = [
        level_instrument_label(entry),
        f"charter {_ellipsize(meta.get('Charter', 'unk'), CHARTER_LIMIT)}",
        release_label(meta),
        str(entry.get('source_format', '?')),
    ]

    # meta.Difficulty is a per-instrument dict set from song.ini at last Build (Expert-referenced)
    if difficulty is not None:
        remap = difficulty.get('RemapDiff')
        calc_tier = difficulty.get('CalcTier')
        bits.append(_d_display(difficulty))
        bits.append(f"diff {_diff_label(meta, instrument_key, original_diff)}")
        bits.append(f"remap bin {remap if remap is not None else '-'}")
        bits.append(f"calc tier {calc_tier if calc_tier is not None else '-'}")

    return '  |  '.join(bits)

# seconds to m:ss output for time axis
def _format_time(value, pos=None):
    total = max(int(round(value)), 0)
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}"

#------------
# Shared drawing helpers - one layout for 5 Fret / Vocals / Drums, only the curves differ
#------------

def _time_seconds(curves):
    return [ms / 1000.0 for ms in curves['time_ms']]


# figure + list of axes, themed background
def _new_figure(profile, n_rows=1, height=None):
    width, base_height = tuple(profile['figsize'])
    fig, axes = plt.subplots(n_rows, 1, figsize=(width, height or base_height), dpi=profile['dpi'])
    fig.patch.set_facecolor(profile['figure_bg'])
    return fig, ([axes] if n_rows == 1 else list(axes))


# D as a filled backdrop + dotted component lines, then the shared axis styling
# lines: [(values, profile color key, legend label), ...]
def _style_axes(ax, time_s, profile, d_curve, lines, show_xlabel=True):
    ax.set_facecolor(profile['axes_bg'])

    # D: filled backdrop
    ax.plot(time_s, d_curve, color=profile['color_d'],
            linewidth=profile['linewidth'], zorder=3, label='~D')
    if profile.get('fill_curves'):
        ax.fill_between(time_s, d_curve, color=profile['color_d'],
                        alpha=profile['fill_alpha'], linewidth=0, zorder=2)

    # components: dotted lines
    for values, color_key, label in lines:
        ax.plot(time_s, values, color=profile[color_key],
                linewidth=profile['linewidth'], linestyle=':', zorder=3, label=label)

    ax.set_ylabel('per second', fontsize=profile['label_size'], color=profile['text_color'])
    ax.tick_params(labelsize=profile['tick_size'], colors=profile['text_color'])
    ax.set_ylim(bottom=0)
    ax.grid(True, alpha=profile['grid_alpha'], linewidth=0.6, color=profile['grid_color'])
    ax.margins(x=0)
    for spine in ax.spines.values():
        spine.set_color(profile['spine_color'])

    # x-axis: M:SS time scale
    ax.xaxis.set_major_formatter(FuncFormatter(_format_time))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
    if show_xlabel:
        ax.set_xlabel('Time (m:ss)', fontsize=profile['label_size'], color=profile['text_color'])


# Legend - horizontal below the axes
def _legend(ax, profile, ncol, handles=None, labels=None):
    extra = {} if handles is None else {'handles': handles, 'labels': labels}
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.08),
              ncol=ncol, frameon=False,
              fontsize=profile['tick_size'], labelcolor=profile['text_color'], **extra)


# Header - title row, metadata row under (parse_math off: '$' in names prints as-is)
def _draw_header(ax, entry, difficulty, original_diff, profile):
    meta = entry.get('meta', {})
    title = (f"{_ellipsize(meta.get('Name', 'unk'), TITLE_LIMIT)}"
             f" - {_ellipsize(meta.get('Artist', 'unk'), TITLE_LIMIT)}")
    ax.set_title(title, fontsize=profile['title_size'], loc='left',
                 color=profile['text_color'], pad=profile['title_pad'], parse_math=False)
    ax.text(0.0, 1.01, meta_header(entry, difficulty, original_diff),
            transform=ax.transAxes, ha='left', va='bottom',
            fontsize=profile['tick_size'], color=profile['muted_text_color'], parse_math=False)


def _save(fig, entry, out_dir, bottom_margin=0.06):
    fig.tight_layout(rect=(0, bottom_margin, 1, 1))
    out_path = out_dir / output_filename(entry)
    fig.savefig(out_path, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def _resolve_out_dir(out_dir):
    out_dir = pathlib.Path(out_dir) if out_dir else timestamp.project_path(config.RENDER_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir

#------------
# Rendering - 5 Fret / Vocals / Drums
#------------
# Shared arguments:
#    entry: cache_mod.entries_by_code() result - a flattened song+instrument+level entry
#    curves: output of the matching functions.curves calc_*_curves
#    difficulty: optional dict for the header (D values + Expert-anchored RemapDiff/CalcTier)
#    original_diff: backup CSV cell for this instrument, None if the song isn't backed up
#    profile: style dict, defaults to RENDER_DEFAULT merged with the selected theme

# render each Fret song - Notes / Variability
def render_song(entry, curves, difficulty=None, original_diff=None, profile=None, out_dir=None):
    profile = resolve_profile(profile)
    out_dir = _resolve_out_dir(out_dir)

    with _render_context():
        fig, (ax,) = _new_figure(profile)
        _style_axes(ax, _time_seconds(curves), profile, curves['d_raw'], [
            (curves['nps'], 'color_nps', 'Notes'),
            (curves['vps'], 'color_vps', 'Variability'),
        ])
        _legend(ax, profile, ncol=3)
        _draw_header(ax, entry, difficulty, original_diff, profile)
        return _save(fig, entry, out_dir)

# render one vocals song - Pitch / Syllables (+ Percussion when charted)
def render_vocal_song(entry, curves, difficulty=None, original_diff=None, profile=None, out_dir=None):
    profile = resolve_profile(profile)
    out_dir = _resolve_out_dir(out_dir)
    has_perc = curves.get('has_perc', False)

    lines = [
        (curves['pps'], 'color_vps', 'Pitch'),
        (curves['sps'], 'color_nps', 'Syllables'),
    ]
    # Percussion: only drawn when the chart actually has any
    if has_perc:
        lines.append((curves['perc'], 'color_kps', 'Percussion'))

    with _render_context():
        fig, (ax,) = _new_figure(profile)
        _style_axes(ax, _time_seconds(curves), profile, curves['d_raw'], lines)
        _legend(ax, profile, ncol=4 if has_perc else 3)
        _draw_header(ax, entry, difficulty, original_diff, profile)
        return _save(fig, entry, out_dir)

# render one drums song - Hands / Travel / Kicks, 2x stacked under 1x when charted
def render_drum_song(entry, curves, difficulty=None, original_diff=None, profile=None, out_dir=None):
    profile = resolve_profile(profile)
    out_dir = _resolve_out_dir(out_dir)
    has_2x = curves.get('has_2x', False)
    time_s = _time_seconds(curves)

    # stacked layout gets close to double height
    base_height = tuple(profile['figsize'])[1]
    fig_height = base_height * 1.9 if has_2x else base_height
    modes = ['1x', '2x'] if has_2x else ['1x']

    with _render_context():
        fig, axes = _new_figure(profile, n_rows=len(modes), height=fig_height)
        for mode, ax in zip(modes, axes):
            _style_axes(ax, time_s, profile, curves['d_raw'][mode], [
                (curves['hps'], 'color_nps', 'Hands'),
                (curves['tps'], 'color_vps', 'Travel'),
                (curves['kps'][mode], 'color_kps', 'Kicks'),
            ])
            # tag to id 1x/2x
            if has_2x:
                ax.text(0.995, 0.96, KICK_MODE_LABELS[mode], transform=ax.transAxes,
                        ha='right', va='top', fontsize=profile['tick_size'],
                        color=profile['muted_text_color'])

        # one shared legend below the bottom axes
        handles, labels = axes[0].get_legend_handles_labels()
        _legend(axes[-1], profile, ncol=4, handles=handles, labels=labels)
        _draw_header(axes[0], entry, difficulty, original_diff, profile)
        return _save(fig, entry, out_dir, bottom_margin=0.06 * (base_height / fig_height))
