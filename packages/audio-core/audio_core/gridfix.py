"""Grid post-processing: drop isolated outlier beats and extrapolate over a beatless intro.

Both steps run once, right after beat tracking, and are recorded in the analysis ``models`` block
as ``grid_postprocess`` (see ``GRID_POSTPROCESS_VERSION``) so an analysis stays traceable.

Outlier rule. For every beat interval ``d_i`` the local median ``m`` is the median of the
intervals within ``OUTLIER_WINDOW`` positions on each side. An interval shorter than
``OUTLIER_RATIO`` (0.6) of ``m`` marks a beat pair that is too close, but only when it is
*isolated*: the interval before and the one after are both at least ``OUTLIER_RATIO`` of ``m``.
A genuine tempo change makes a run of short intervals, so it is left alone. Of the two beats, the
one nearer to where the steady run puts it (the next beat minus ``m``, or the previous plus ``m``
at the end) is kept. A removed downbeat hands its role to the beat that stays, so every downbeat
is always a kept beat.

Extrapolation rule. When the first detected beat lies after more than ``LEAD_IN_BARS`` (2) bars,
the grid is extended backwards from the first stable bar (one bar whose intervals are within
``STABLE_TOLERANCE`` of the median) with the median interval of up to ``STABLE_BARS`` (4) stable
bars, down to t >= 0. The downbeat phase is anchored on the first detected downbeat at or after
the first stable bar (not on a possibly unreliable first detected downbeat). From there bars are
laid out by time, one bar (beats per bar times the interval) at a time, rather than by counting
detected beats, and each is snapped to the nearest extrapolated beat when that is within
``DOWNBEAT_SNAP_RATIO`` (0.25) of an interval. ``Grid.extrapolated_until`` is the time of the
first detected beat.
"""

import numpy as np

from audio_core.models import Grid

GRID_POSTPROCESS_VERSION = "1"
OUTLIER_RATIO = 0.6
OUTLIER_WINDOW = 4
LEAD_IN_BARS = 2
STABLE_BARS = 4
STABLE_TOLERANCE = 0.12
# Beats up to this fraction of an interval from the first detected beat are not extrapolated.
MIN_GAP_RATIO = 0.5
# A laid-out bar start snaps to an extrapolated beat at most this fraction of an interval away.
DOWNBEAT_SNAP_RATIO = 0.25
_EPS = 1e-3


def _local_median(diffs: np.ndarray, i: int) -> float:
    lo, hi = max(0, i - OUTLIER_WINDOW), min(diffs.size, i + OUTLIER_WINDOW + 1)
    return float(np.median(diffs[lo:hi]))


def _steady_anchor(beats: np.ndarray, i: int, m: float) -> float | None:
    """Where the steady run puts the beat of pair (i, i+1): next minus ``m``, else previous plus."""
    if i + 2 < beats.size:
        return float(beats[i + 2] - m)
    if i > 0:
        return float(beats[i - 1] + m)
    return None


def remove_outlier_beats(
    beats: np.ndarray, downbeats: np.ndarray
) -> tuple[np.ndarray, np.ndarray, int]:
    """Drop isolated too-close beats; returns (beats, downbeats, removed_count)."""
    beats = np.asarray(beats, dtype=np.float64)
    downbeats = np.asarray(downbeats, dtype=np.float64)
    removed = 0
    # One removal per pass keeps the neighbourhood statistics honest; passes are few in practice.
    for _ in range(max(1, beats.size)):
        if beats.size < 4:
            break
        diffs = np.diff(beats)
        found = None
        for i in range(diffs.size):
            m = _local_median(diffs, i)
            if m <= 0 or diffs[i] >= OUTLIER_RATIO * m:
                continue
            before_ok = i == 0 or diffs[i - 1] >= OUTLIER_RATIO * m
            after_ok = i == diffs.size - 1 or diffs[i + 1] >= OUTLIER_RATIO * m
            if before_ok and after_ok:
                found = (i, m)
                break
        if found is None:
            break
        i, m = found
        # Pair (i, i+1): keep the one the steady run around it points at.
        anchor = _steady_anchor(beats, i, m)
        if anchor is None:
            drop, keep = i + 1, i
        elif abs(beats[i] - anchor) <= abs(beats[i + 1] - anchor):
            drop, keep = i + 1, i
        else:
            drop, keep = i, i + 1
        dropped_time, kept_time = beats[drop], beats[keep]
        beats = np.delete(beats, drop)
        # A downbeat on the dropped beat moves to the kept one (unless that one is already one).
        replaced = np.isclose(downbeats, dropped_time, atol=_EPS)
        if replaced.any():
            downbeats = downbeats[~replaced]
            if not np.isclose(downbeats, kept_time, atol=_EPS).any():
                downbeats = np.sort(np.append(downbeats, kept_time))
        removed += 1
    return beats, downbeats, removed


def _stable_start(beats: np.ndarray, bpb: int) -> int | None:
    """Index of the first beat that starts a bar of steady intervals, or None."""
    diffs = np.diff(beats)
    if diffs.size < bpb:
        return None
    reference = float(np.median(diffs[: 2 * STABLE_BARS * bpb]))
    if reference <= 0:
        return None
    for s in range(diffs.size - bpb + 1):
        if np.all(np.abs(diffs[s : s + bpb] - reference) <= STABLE_TOLERANCE * reference):
            return s
    return None


def extrapolate_lead_in(grid: Grid, beats_per_bar: int) -> Grid:
    """Extend ``grid`` backwards over a beatless lead-in; returns ``grid`` unchanged if none."""
    if len(grid.beats) < beats_per_bar + 1 or not grid.downbeats:
        return grid
    beats = np.asarray(grid.beats, dtype=np.float64)
    start = _stable_start(beats, beats_per_bar)
    if start is None:
        return grid
    window = beats[start : start + STABLE_BARS * beats_per_bar + 1]
    interval = float(np.median(np.diff(window)))
    first = float(beats[0])
    if interval <= 0 or first <= LEAD_IN_BARS * beats_per_bar * interval:
        return grid

    # Chain back from the stable beat; skip beats too close to the first detected one.
    limit = first - MIN_GAP_RATIO * interval
    count = int(np.ceil(beats[start] / interval)) + 1
    chain = beats[start] - interval * np.arange(1, count + 1)
    extra = np.sort(chain[(chain >= -_EPS) & (chain < limit)])
    extra = np.maximum(extra, 0.0)
    if extra.size == 0:
        return grid

    merged = np.concatenate([extra, beats])
    # The bar phase comes from the first downbeat of the stable run, not from a possibly
    # unreliable first detected downbeat. Bars are laid out by time (one bar = beats_per_bar
    # intervals) rather than by counting detected beats, which may be missing in unstable spots.
    stable = [d for d in grid.downbeats if d >= beats[start] - _EPS]
    anchor_time = stable[0] if stable else grid.downbeats[-1]
    bar = beats_per_bar * interval
    lattice = anchor_time - bar * np.arange(1, int(anchor_time / bar) + 2)
    nearest = np.abs(extra[None, :] - lattice[:, None]).argmin(axis=1)
    close = np.abs(extra[nearest] - lattice) <= DOWNBEAT_SNAP_RATIO * interval
    extra_downbeats = np.unique(extra[nearest[close]])
    downbeats = np.concatenate([extra_downbeats, np.asarray(grid.downbeats)])
    return grid.model_copy(
        update={
            "beats": [round(float(t), 4) for t in merged],
            "downbeats": [round(float(t), 4) for t in downbeats],
            "extrapolated_until": round(first, 4),
            "notes": [
                *grid.notes,
                f"extrapolated {extra.size} beats over a {first:.1f} s lead-in "
                f"at {60.0 / interval:.1f} BPM",
            ],
        }
    )


def drop_extrapolated(grid: Grid) -> Grid:
    """The grid as detected: beats and downbeats before ``extrapolated_until`` removed."""
    if grid.extrapolated_until is None:
        return grid
    cut = grid.extrapolated_until - _EPS
    return grid.model_copy(
        update={
            "beats": [t for t in grid.beats if t >= cut],
            "downbeats": [t for t in grid.downbeats if t >= cut],
            "extrapolated_until": None,
        }
    )
