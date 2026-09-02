"""
PLOT - Renders selected song's curves to a PNG.

y-axis scales per song

NPS/VPS/D share an axis by using D = sqrt(NPS * VPS)

Includes star power and solo spans where available & based on config selections

Header spacing is checked so title/artist don't collide with the metadata output

Light/dark themes can be set for visualization from config.py
"""

import pathlib
import re

import matplotlib
matplotlib.use('Agg')  # no display in a batch render
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
from matplotlib.ticker import MaxNLocator, FuncFormatter

import config
from functions import instruments

AVG_CHAR_EM = 0.55

#-------------
# Filename
#-------------
_UNSAFE = re.compile(r'[^A-Za-z0-9 _.-]')

# strips non-ASCII for display
def _safe(text, limit=60):
    cleaned = _UNSAFE.sub('', str(text)).strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned[:limit] or 'unknown'

# code + instrument + artist + song title
def output_filename(entry):
    meta = entry.get('meta', {})
    instrument_label = instruments.DISPLAY_NAMES.get(entry.get('instrument'), '')
    return (f"{entry['code']}_{_safe(instrument_label)}_"
            f"{_safe(meta.get('Artist'))} - {_safe(meta.get('Name'))}.png")

# Theme resolution
def resolve_theme(profile):
    mode = profile.get('mode', 'light')
    return config.RENDER_THEMES.get(mode, config.RENDER_THEMES['light'])

# Header text
def _ellipsize(text, limit):
    text = str(text)
    if limit is None or len(text) <= limit:
        return text
    if limit <= 3:
        return text[:max(limit, 0)]
    return text[:limit - 3].rstrip() + '...'

# sets Release (Official tag) - 'Rock Band 3 (official)' or 'Carpal Tunnerl Hero (Custom)'
def release_label(meta, limit=None):
    release = str(meta.get('Release') or '').strip() or 'Custom'
    if release.lower() == 'custom':
        return 'Custom'
    tag = 'official' if meta.get('Official') else 'custom'
    return f"{_ellipsize(release, limit)} ({tag})"

# right side metatdata header - instrument / charter / release (tag) / file type / D / calc tier / remap bin
def meta_header(entry, difficulty, profile, original_diff=None):
    meta = entry.get('meta', {})
    instrument_key = entry.get('instrument')
    instrument_label = instruments.DISPLAY_NAMES.get(instrument_key, '')

    bits = [
        instrument_label,
        f"charter {_ellipsize(meta.get('Charter', 'unk'), profile.get('charter_limit'))}",
        release_label(meta, profile.get('release_limit')),
        str(entry.get('source_format', '?')),
    ]

# meta.Difficulty is a per-instrument dict set from song.ini at last Build (usually official)
    if difficulty is not None:
        remap = difficulty.get('RemapDiff')
        ini_diff = (meta.get('Difficulty') or {}).get(instrument_key, '-')
        diff_value = original_diff if original_diff is not None else ini_diff
        bits.append(f"D {difficulty['D']:.2f}")
        bits.append(f"diff {diff_value}")
        bits.append(f"remap bin {remap if remap is not None else '-'}")
        bits.append(f"calc tier {difficulty['CalcTier']}")
    return '  |  '.join(bits)

# flat average distance for header fitting
def _est_width(fig, text, fontsize):
    return len(text) * fontsize * AVG_CHAR_EM * fig.dpi / 72.0

# to apply after tight
def _ax_width(fig, ax):
    return ax.get_position().width * fig.get_figwidth() * fig.dpi

# truncates Title - Artist to prevent metadata collision
def _fit_meta_header(fig, ax, name, artist, meta_header, profile):
    title_size = profile['title_size']
    min_chars = profile.get('title_min_chars', 10)

    axes_px = _ax_width(fig, ax)
    gap_px = profile.get('header_gap_frac', 0.03) * axes_px
    available = axes_px - _est_width(fig, meta_header, profile['tick_size']) - gap_px

    available = max(available, axes_px * 0.2)

    name, artist = str(name), str(artist)
    n_lim, a_lim = len(name), len(artist)

    def compose(n, a):
        return f"{_ellipsize(name, n)} - {_ellipsize(artist, a)}"

    def shrink():
        nonlocal n_lim, a_lim
        if n_lim >= a_lim and n_lim > min_chars:
            n_lim -= 1
            return True
        if a_lim > min_chars:
            a_lim -= 1
            return True
        return False

    text = compose(n_lim, a_lim)
    while _est_width(fig, text, title_size) > available:
        if not shrink():
            break
        text = compose(n_lim, a_lim)

    return text

# seconds to m:ss output for time axis
def _format_time(value, pos=None):
    total = max(int(round(value)), 0)
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}"

#------------
# Rendering
#------------

# draw solos + star power spans
def _draw_spans(ax, spans, profile, solo_color):
    if profile.get('show_solo_spans', True):
        for start_ms, end_ms in spans.get('solo', []):
            ax.axvspan(start_ms / 1000.0, end_ms / 1000.0,
                       color=solo_color, alpha=profile['span_alpha'],
                       linewidth=0, zorder=0)

    if profile.get('show_star_power_spans', True):
        for start_ms, end_ms in spans.get('star_power', []):
            ax.axvspan(start_ms / 1000.0, end_ms / 1000.0,
                       color=profile['color_star_power'], alpha=profile['span_alpha'],
                       linewidth=1, zorder=1)


# render each song
#    entry: cache_mod.entries_by_code() result - a flattened song+instrument entry
#    curves: output of functions.curves.compute_curves
#    difficulty: optional dict from formula.compute_difficulty, for header
#    original_diff: optional backed-up original diff_* value for this instrument, for header
#    profile: style dict + theme
#    Returns the written path.
def render_song(entry, curves, difficulty=None, original_diff=None, profile=None, out_dir=None):
    profile = dict(profile) if profile else dict(config.RENDER_DEFAULT)
    theme = resolve_theme(profile)
    out_dir = pathlib.Path(out_dir or config.RENDER_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    time_s = [ms / 1000.0 for ms in curves['time_ms']]
    spans = entry.get('spans', {}) or {}
    meta = entry.get('meta', {})

    fig, ax_nv = plt.subplots(
        figsize=tuple(profile['figsize']),
        dpi=profile['dpi'],
    )

    fig.patch.set_facecolor(theme['figure_bg'])
    ax_nv.set_facecolor(theme['axes_bg'])

    _draw_spans(ax_nv, spans, profile, solo_color=theme['color_solo'])

    #D: filled backdrop
    d_line, = ax_nv.plot(time_s, curves['d_raw'], color=profile['color_d'],
                        linewidth=profile['linewidth'], zorder=3, label='~D')
    if profile.get('fill_curves'):
        ax_nv.fill_between(time_s, curves['d_raw'], color=profile['color_d'],
                        alpha=profile['fill_alpha'], linewidth=0, zorder=2)

    #NPS / VPS: dotted lines
    nps_line, = ax_nv.plot(time_s, curves['nps'], color=profile['color_nps'],
                        linewidth=profile['linewidth'], linestyle=':',
                        zorder=3, label='Notes')
    vps_line, = ax_nv.plot(time_s, curves['vps'], color=profile['color_vps'],
                        linewidth=profile['linewidth'], linestyle=':',
                        zorder=3, label='Variability')
    ax_nv.set_ylabel('per second', fontsize=profile['label_size'],
                    color=theme['text_color'])
    ax_nv.tick_params(labelsize=profile['tick_size'], colors=theme['text_color'])
    ax_nv.set_ylim(bottom=0)
    ax_nv.grid(True, alpha=profile['grid_alpha'], linewidth=0.6,
            color=theme['grid_color'])
    ax_nv.margins(x=0)
    for spine in ax_nv.spines.values():
        spine.set_color(theme['spine_color'])

    # --- x-axis: M:SS time scale
    time_format = profile.get('time_axis_format', 'mmss')
    if time_format == 'mmss':
        ax_nv.xaxis.set_major_formatter(FuncFormatter(_format_time))
        ax_nv.set_xlabel('Time (m:ss)', fontsize=profile['label_size'],
                         color=theme['text_color'])
        ax_nv.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
    else:
        ax_nv.set_xlabel('Time (s)', fontsize=profile['label_size'],
                         color=theme['text_color'])

    # Legend - in a horizontal strip below the axes
    handles = [d_line, nps_line, vps_line]
    if profile.get('show_star_power_spans', True) and spans.get('star_power'):
        handles.append(Patch(facecolor=profile['color_star_power'],
                             alpha=profile['span_alpha'], label='Star power'))
    if profile.get('show_solo_spans', True) and spans.get('solo'):
        handles.append(Patch(facecolor=theme['color_solo'],
                             alpha=profile['span_alpha'], label='Solo'))
    ax_nv.legend(handles, [h.get_label() for h in handles],
                 loc='upper center', bbox_to_anchor=(0.5, -0.08),
                 ncol=len(handles), frameon=False,
                 fontsize=profile['tick_size'], labelcolor=theme['text_color'])

    # Metadata Header
    right_text = meta_header(entry, difficulty, profile, original_diff)
    ax_nv.set_title(' ', fontsize=profile['title_size'], loc='left')
    ax_nv.set_title(' ', fontsize=profile['tick_size'], loc='right')

    fig.tight_layout(rect=(0, 0.06, 1, 1))

    title = _fit_meta_header(fig, ax_nv,
                              meta.get('Name', 'unk'), meta.get('Artist', 'unk'),
                              right_text, profile)
    ax_nv.set_title(title, fontsize=profile['title_size'], loc='left',
                    color=theme['text_color'])
    ax_nv.set_title(right_text, fontsize=profile['tick_size'],
                    loc='right', color=theme['muted_text_color'])

    out_path = out_dir / output_filename(entry)

    fig.savefig(out_path, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)

    return out_path
