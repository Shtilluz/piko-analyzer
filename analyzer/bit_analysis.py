"""
Bit-level and byte-level analysis of observed packet data.

Input: a stream of PacketRecord or raw (bytes, count) pairs.
Output: ByteStats and BitStats collections.

No semantic meaning is assigned here.  Labels like CONSTANT /
MOSTLY_CONSTANT / VARIABLE describe observed statistics only.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from analyzer.models import ByteStats, BitStats


def compute_byte_stats(packets: Sequence[tuple[bytes, int]]) -> list[ByteStats]:
    """
    Compute per-byte-position statistics.

    `packets` is a list of (data_bytes, count) pairs — the count is
    the number of times that byte string was observed, so statistics
    are properly weighted.

    Returns one ByteStats per byte position (position 0 … max_len-1).
    """
    if not packets:
        return []

    max_len = max(len(data) for data, _ in packets)
    stats   = [ByteStats(position=pos) for pos in range(max_len)]

    # First pass: value_counts
    for data, count in packets:
        for pos, byte_val in enumerate(data):
            stats[pos].value_counts[byte_val] = (
                stats[pos].value_counts.get(byte_val, 0) + count
            )

    # Second pass: transitions (sequential pairs within each unique packet
    # stream are not available here, so transitions are computed separately
    # in transition_analysis.py).  We still populate the field on ByteStats
    # to have a unified place for the data; the caller may update it.

    return stats


def compute_bit_stats(packets: Sequence[tuple[bytes, int]]) -> list[list[BitStats]]:
    """
    Compute per-bit statistics for each byte position.

    Returns a 2D list: result[byte_pos][bit_pos] where bit_pos 0 = LSB.
    """
    if not packets:
        return []

    max_len = max(len(data) for data, _ in packets)

    # result[pos][bit] = BitStats
    result: list[list[BitStats]] = [
        [BitStats(byte_pos=pos, bit_pos=bit) for bit in range(8)]
        for pos in range(max_len)
    ]

    for data, count in packets:
        for pos, byte_val in enumerate(data):
            for bit in range(8):
                if byte_val & (1 << bit):
                    result[pos][bit].count_1 += count
                else:
                    result[pos][bit].count_0 += count

    return result


def compute_bit_transitions(ordered_packets: Sequence[bytes]) -> list[list[int]]:
    """
    Compute bit transition counts from an ORDERED sequence of packets.

    `ordered_packets` is a time-ordered list of raw byte strings
    (each occurrence, not deduplicated).

    Returns result[byte_pos][bit_pos] = number of transitions.
    """
    if len(ordered_packets) < 2:
        return []

    max_len = max(len(p) for p in ordered_packets)
    transitions = [[0] * 8 for _ in range(max_len)]

    prev = ordered_packets[0]
    for curr in ordered_packets[1:]:
        common_len = min(len(prev), len(curr), max_len)
        for pos in range(common_len):
            diff = prev[pos] ^ curr[pos]
            for bit in range(8):
                if diff & (1 << bit):
                    transitions[pos][bit] += 1
        prev = curr

    return transitions


def most_variable_bytes(byte_stats: list[ByteStats], top_n: int = 5) -> list[int]:
    """Return positions of the `top_n` most variable byte positions."""
    scored = sorted(
        range(len(byte_stats)),
        key=lambda i: byte_stats[i].unique_count,
        reverse=True,
    )
    return scored[:top_n]
