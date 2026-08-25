"""
Correlation analysis — looks for numeric relationships between labelled
action values and byte/bit patterns in captured packets.

All results are labelled as candidates with a confidence score.
We never assert that a field IS something; we say it MIGHT BE.

Algorithm:
  1. User records N actions, each with a numeric value (e.g. speed=0,1,2…)
     and the dominant packet observed during that action.
  2. For each byte position and each bit range [hi:lo], extract the
     numeric value of those bits from each action's dominant packet.
  3. Compute Pearson correlation between the extracted bit-field values
     and the user-supplied numeric values.
  4. Report candidates with |r| > threshold.
"""

from __future__ import annotations

import math
from typing import Sequence

from analyzer.models import CorrelationCandidate


def _pearson(xs: list[float], ys: list[float]) -> float:
    """Return Pearson r for two equal-length lists.  Returns 0 on degenerate input."""
    n = len(xs)
    if n < 2:
        return 0.0

    mx = sum(xs) / n
    my = sum(ys) / n

    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx  = math.sqrt(sum((x - mx) ** 2 for x in xs))
    sy  = math.sqrt(sum((y - my) ** 2 for y in ys))

    if sx == 0 or sy == 0:
        return 0.0
    return cov / (sx * sy)


def _extract_bits(byte_val: int, bit_high: int, bit_low: int) -> int:
    """Extract bits [bit_high : bit_low] (both inclusive, 0=LSB)."""
    mask  = (1 << (bit_high - bit_low + 1)) - 1
    return (byte_val >> bit_low) & mask


def find_correlations(
    actions: list[tuple[str, float, bytes]],
    min_confidence: float = 0.80,
) -> list[CorrelationCandidate]:
    """
    `actions` — list of (label, numeric_value, dominant_packet_bytes).
    Only actions with a non-None dominant packet are used.
    `min_confidence` — minimum |r| to report.

    Returns CorrelationCandidate list sorted by confidence descending.
    """
    # Filter usable actions
    usable = [(label, val, pkt) for label, val, pkt in actions if pkt]
    if len(usable) < 3:
        return []   # Need at least 3 points for meaningful correlation

    numeric_values = [val for _, val, _ in usable]
    packets        = [pkt for _, _, pkt in usable]
    label          = usable[0][0].rsplit("_", 1)[0]   # e.g. "speed_1" → "speed"

    max_len = max(len(p) for p in packets)
    candidates: list[CorrelationCandidate] = []

    for byte_pos in range(max_len):
        for bit_high in range(7, -1, -1):
            for bit_low in range(0, bit_high + 1):
                bit_vals = []
                for pkt in packets:
                    if byte_pos >= len(pkt):
                        bit_vals.append(0)
                    else:
                        bit_vals.append(_extract_bits(pkt[byte_pos], bit_high, bit_low))

                r    = _pearson(bit_vals, numeric_values)
                conf = abs(r)

                if conf >= min_confidence:
                    # Avoid duplicates: single-bit fields appear in multi-bit
                    # ranges too.  Only emit the tightest range.
                    candidates.append(CorrelationCandidate(
                        label       = label,
                        byte_pos    = byte_pos,
                        bit_high    = bit_high,
                        bit_low     = bit_low,
                        correlation = r,
                        confidence  = conf,
                        note        = f"r={r:.3f}  (Pearson, n={len(usable)})",
                    ))

    # Remove dominated candidates: if a sub-range of another candidate has
    # equal or better confidence, keep only the sub-range (tighter hypothesis).
    candidates.sort(key=lambda c: (c.confidence, -(c.bit_high - c.bit_low)), reverse=True)

    filtered: list[CorrelationCandidate] = []
    seen_ranges: set[tuple[int, int, int]] = set()
    for c in candidates:
        key = (c.byte_pos, c.bit_high, c.bit_low)
        if key not in seen_ranges:
            seen_ranges.add(key)
            filtered.append(c)

    return filtered[:50]   # cap output
