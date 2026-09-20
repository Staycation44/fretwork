"""
BAND FORMULA - Cross-instrument per-song band placement (RemapBandDiff / CalcBandTier)
built from each instrument's own Expert-anchored RemapDiff / CalcTier - no D, nothing re-derived

One rule for both scales - the mean of the two hardest core placements, floored
    core = lead (guitar, else keys) + bass + drums, whichever are present
    RemapBandDiff = rule over RemapDiff
    CalcBandTier  = rule over CalcTier

Leans toward the song's hardest parts without one outlier setting the band
floors so the band never sits above what its two hardest parts average to (a 2-core song just averages both)

Needs >= 2 core instruments to mean anything - otherwise no band row / no write
Vocals and non-lead keys don't feed the band, they only show in the Instruments column
"""

import math

# -------------
# Participants
# -------------
LEAD_PRIORITY = ['guitar', 'keys']    # first present wins the lead/core slot
CORE_SUPPORT = ['bass', 'drums']      # always core, when present

# fixed left-to-right order for the xlsx 'Instruments' column
# excl coop/rhythm
BAND_ROLE_ORDER = ['guitar', 'bass', 'drums', 'keys', 'vocals']

# how many of the hardest core placements the band averages
TOP_N = 2


def _lead_key(present):
    for key in LEAD_PRIORITY:
        if key in present:
            return key
    return None


# mean of the TOP_N hardest placements, floored - same rule for RemapDiff and CalcTier
def _place(core):
    top = sorted(core)[-TOP_N:]
    return math.floor(sum(top) / len(top))


# placements_by_instrument: {instrument_key: {'RemapDiff': int, 'CalcTier': int}}
# only instruments with an Expert anchor have an entry
def calc_band(placements_by_instrument):
    lead = _lead_key(placements_by_instrument)
    core_keys = [k for k in ([lead] + CORE_SUPPORT) if k in placements_by_instrument]
    if len(core_keys) < 2:
        return {'RemapBandDiff': None, 'CalcBandTier': None}

    return {
        'RemapBandDiff': _place([placements_by_instrument[k]['RemapDiff'] for k in core_keys]),
        'CalcBandTier':  _place([placements_by_instrument[k]['CalcTier'] for k in core_keys]),
    }
