"""
PLOT - Renders selected song's curves to a PNG.

y-axis scales per song

NPS/VPS/D share an axis by using D = sqrt(NPS * VPS)

Light/dark themes can be set for visualization from config.py\
"""

import pathlib
import re

import matplotlib
matplotlib.use('Agg')  # no display in a batch render
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator, FuncFormatter

import config
from functions import instruments

# fixed header truncation limits - keeps PNG width consistent song to song
TITLE_LIMIT = 44      # applied to song title and artist separately
CHARTER_LIMIT = 28
RELEASE_LIMIT = 34

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
        ini_diff = (meta.get('Difficulty') or {}).get(instrument_key, '-')
        diff_value = original_diff if original_diff is not None else ini_diff
        bits.append(f"D {difficulty['D']:.2f}")
        bits.append(f"diff {diff_value}")
        bits.append(f"remap bin {remap if remap is not None else '-'}")
        bits.append(f"calc tier {calc_tier if calc_tier is not None else '-'}")

    return '  |  '.join(bits)

# seconds to m:ss output for time axis
def _format_time(value, pos=None):
    total = max(int(round(value)), 0)
    minutes, seconds = divmod(total, 60)
    return f"{minutes}:{seconds:02d}"

#------------
# Rendering
#------------

# render each song
#    entry: cache_mod.entries_by_code() result - a flattened song+instrument+level entry
#    curves: output of functions.curves.calc_curves
#    difficulty: optional dict (D/N/V/COV + Expert-anchored RemapDiff/CalcTier), for header
#    original_diff: optional backed-up original diff_* value for this instrument, for header
#    profile: style dict, defaults to RENDER_DEFAULT merged with the selected theme
#    Returns the written path.
def render_song(entry, curves, difficulty=None, original_diff=None, profile=None, out_dir=None):
    profile = resolve_profile(profile)
    out_dir = pathlib.Path(out_dir or config.RENDER_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    time_s = [ms / 1000.0 for ms in curves['time_ms']]
    meta = entry.get('meta', {})

    fig, ax_nv = plt.subplots(
        figsize=tuple(profile['figsize']),
        dpi=profile['dpi'],
    )

    fig.patch.set_facecolor(profile['figure_bg'])
    ax_nv.set_facecolor(profile['axes_bg'])

    #D: filled backdrop
    ax_nv.plot(time_s, curves['d_raw'], color=profile['color_d'],
               linewidth=profile['linewidth'], zorder=3, label='~D')
    if profile.get('fill_curves'):
        ax_nv.fill_between(time_s, curves['d_raw'], color=profile['color_d'],
                           alpha=profile['fill_alpha'], linewidth=0, zorder=2)

    #NPS / VPS: dotted lines
    ax_nv.plot(time_s, curves['nps'], color=profile['color_nps'],
               linewidth=profile['linewidth'], linestyle=':',
               zorder=3, label='Notes')
    ax_nv.plot(time_s, curves['vps'], color=profile['color_vps'],
               linewidth=profile['linewidth'], linestyle=':',
               zorder=3, label='Variability')

    ax_nv.set_ylabel('per second', fontsize=profile['label_size'],
                     color=profile['text_color'])
    ax_nv.tick_params(labelsize=profile['tick_size'], colors=profile['text_color'])
    ax_nv.set_ylim(bottom=0)
    ax_nv.grid(True, alpha=profile['grid_alpha'], linewidth=0.6,
               color=profile['grid_color'])
    ax_nv.margins(x=0)
    for spine in ax_nv.spines.values():
        spine.set_color(profile['spine_color'])

    # x-axis: M:SS time scale
    ax_nv.xaxis.set_major_formatter(FuncFormatter(_format_time))
    ax_nv.xaxis.set_major_locator(MaxNLocator(nbins=10, integer=True))
    ax_nv.set_xlabel('Time (m:ss)', fontsize=profile['label_size'],
                     color=profile['text_color'])

    # Legend - horizontal below the axes
    ax_nv.legend(loc='upper center', bbox_to_anchor=(0.5, -0.08),
                 ncol=3, frameon=False,
                 fontsize=profile['tick_size'], labelcolor=profile['text_color'])

    # Header - title row, metadata row under
    title = (f"{_ellipsize(meta.get('Name', 'unk'), TITLE_LIMIT)}"
             f" - {_ellipsize(meta.get('Artist', 'unk'), TITLE_LIMIT)}")
    ax_nv.set_title(title, fontsize=profile['title_size'], loc='left',
                    color=profile['text_color'], pad=profile['title_pad'])
    ax_nv.text(0.0, 1.01, meta_header(entry, difficulty, original_diff),
               transform=ax_nv.transAxes, ha='left', va='bottom',
               fontsize=profile['tick_size'], color=profile['muted_text_color'])

    fig.tight_layout(rect=(0, 0.06, 1, 1))

    out_path = out_dir / output_filename(entry)
    fig.savefig(out_path, bbox_inches='tight', facecolor=fig.get_facecolor())
    plt.close(fig)

    return out_path
