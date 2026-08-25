"""
Transition analysis — tracks how byte values change between consecutive packets.

This is useful for identifying state-machine-like fields (speed, function
toggles, etc.) where values step through a predictable sequence.

No meaning is assigned.  Results are described as "transition patterns", not
"speed encoder" or anything else until correlation experiments confirm it.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence


class TransitionTracker:
    """
    Maintains per-byte-position transition tables.

    `feed_packet(data)` should be called for EVERY received packet in
    chronological order, including duplicates.  This differs from the
    deduplicated statistics in statistics.py.
    """

    def __init__(self):
        # transitions[byte_pos][(from_val, to_val)] = count
        self._transitions: dict[int, dict[tuple[int, int], int]] = defaultdict(
            lambda: defaultdict(int)
        )
        self._prev: bytes | None = None
        self._total_transitions  = 0

    def feed_packet(self, data: bytes) -> None:
        if self._prev is None:
            self._prev = data
            return

        common_len = min(len(self._prev), len(data))
        for pos in range(common_len):
            fv = self._prev[pos]
            tv = data[pos]
            if fv != tv:
                self._transitions[pos][(fv, tv)] += 1
                self._total_transitions += 1

        self._prev = data

    def reset(self) -> None:
        self._transitions.clear()
        self._prev = None
        self._total_transitions = 0

    # ---- Queries ----

    def transitions_for_byte(
        self, byte_pos: int, top_n: int = 20
    ) -> list[tuple[int, int, int]]:
        """
        Return [(from_val, to_val, count), ...] sorted by count desc.
        """
        raw = self._transitions.get(byte_pos, {})
        return sorted(
            ((fv, tv, cnt) for (fv, tv), cnt in raw.items()),
            key=lambda x: x[2],
            reverse=True,
        )[:top_n]

    def active_byte_positions(self) -> list[int]:
        """Positions that have at least one recorded transition."""
        return sorted(self._transitions.keys())

    def snapshot(self) -> dict:
        return {
            pos: {
                f"{fv:02X}->{tv:02X}": cnt
                for (fv, tv), cnt in tbl.items()
            }
            for pos, tbl in self._transitions.items()
        }
