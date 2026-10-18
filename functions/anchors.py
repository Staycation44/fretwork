"""
ANCHORS - Expert-anchored RemapDiff/CalcTier for the EMHX instruments, shared by ANALYZE and RENDER

Each returns (expert_metrics, RemapDiff, CalcTier) - expert_metrics so the caller can reuse them for
the Expert row, (None, None, None) when there's no Expert chart. Pass expert_metrics when the caller
already has them (render at the Expert level) to skip the recompute

Vocals have no EMHX, so their RemapDiff/CalcTier come straight from their own D (vocal_formula)
"""

from functions import drum_density, drum_formula, fret_density, fret_formula


# guitar/coop/rhythm/bass/keys - calibration group picked by instrument_key
def fret(expert_notes, instrument_key, expert_metrics=None):
    if expert_metrics is None and expert_notes is not None:
        expert_metrics = fret_density.calc_metrics(expert_notes)
    return (expert_metrics, *fret_formula.anchor_remap_tier(expert_metrics, instrument_key))


# drums - anchored to the 1x reading, Expert roll spans needed for the hand metrics
def drum(expert_notes, expert_roll_spans=None, expert_metrics=None):
    if expert_metrics is None and expert_notes is not None:
        expert_metrics = drum_density.calc_drum_metrics(expert_notes, roll_spans=expert_roll_spans)
    return (expert_metrics, *drum_formula.anchor_remap_tier(expert_metrics))
