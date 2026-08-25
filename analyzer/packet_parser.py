"""
Packet parser — converts raw edges into candidate packets.

IMPORTANT: We do NOT know the protocol framing yet.
Two strategies are implemented:

  1. EdgeAccumulator  — accumulates RawEdge objects and emits a
                        hypothetical packet when a long silence is
                        detected (PACKET_GAP_US).  The timing of
                        HIGH/LOW phases determines probable bit values,
                        but these are GUESSES until confirmed by
                        correlation experiments.

  2. HexLineParser    — accepts PKT: lines from Arduino that already
                        contain hex data (used when Arduino firmware is
                        upgraded to a packet-framing mode).

Both return (timestamp_us, bytes) or None.
"""

from __future__ import annotations

from collections import deque
from typing import Optional

from analyzer.models import RawEdge
from analyzer import config


class EdgeAccumulator:
    """
    Heuristic packet boundary detector based on inter-edge silence.

    When no edge arrives for PACKET_GAP_US microseconds, the accumulated
    edges are flushed as one candidate packet.

    Bit encoding heuristic (purely exploratory — unknown until experiments):
      - We measure the duration of each pulse.
      - We bucket durations into "short" and "long" and try to assign
        bit values.
      - The bucketing uses k=2 median clustering on observed durations.
      - Result is labelled as HYPOTHESIS, not fact.

    If timing analysis cannot produce a stable bucket split, the packet
    is emitted as raw_edges only (no byte data).
    """

    def __init__(self, gap_us: int = config.PACKET_GAP_US or 5_000):
        self._gap_us     = gap_us
        self._edges: list[RawEdge] = []
        self._last_ts    = 0
        self._callbacks  = []   # list[Callable[[int, bytes, list[RawEdge]], None]]

    def on_packet(self, cb) -> None:
        """Register a callback: cb(timestamp_us, data_bytes, raw_edges)."""
        self._callbacks.append(cb)

    def feed(self, edge: RawEdge) -> None:
        """Feed one edge.  May trigger a packet callback if a gap is detected."""
        if self._edges:
            silence = edge.timestamp_us - self._last_ts
            if silence >= self._gap_us:
                self._flush()

        self._edges.append(edge)
        self._last_ts = edge.timestamp_us

    def flush_now(self) -> None:
        """Force-flush any pending edges (e.g., when stopping capture)."""
        if self._edges:
            self._flush()

    def _flush(self) -> None:
        edges       = self._edges[:]
        timestamp   = edges[0].timestamp_us
        data        = _edges_to_bytes(edges)
        self._edges = []

        for cb in self._callbacks:
            cb(timestamp, data, edges)


def _edges_to_bytes(edges: list[RawEdge]) -> bytes:
    """
    Heuristic conversion of a raw edge sequence into bytes.

    Since the protocol is unknown, this is EXPLORATORY — results are
    hypotheses to be verified by experiment.

    Strategy:
      1. Use all edges (don't filter aggressively — avoids empty output).
      2. Quantize durations: short → 1, long → 0  (common NRZ convention).
         The split point is the median of all durations.
      3. Pack bits MSB-first into bytes.
      4. If the edge group is too small for even 1 byte, encode the timing
         fingerprint directly (duration values) so the packet table still
         shows SOMETHING the user can compare across captures.

    IMPORTANT: The byte values here may be completely wrong.
    They become meaningful only after correlation experiments confirm
    which bytes change when which actions are performed.
    """
    if not edges:
        return bytes()

    # Include ALL edges (even very short ones) — filtering is too aggressive
    # before we know the protocol's bit timing.
    durations = [e.duration_us for e in edges]
    levels    = [e.level       for e in edges]

    # Remove zero-duration first edge (Arduino doesn't know duration at startup)
    if durations and durations[0] == 0:
        durations = durations[1:]
        levels    = levels[1:]

    if not durations:
        return bytes()

    n = len(durations)

    if n < 8:
        # Not enough edges for a proper byte decode.
        # Return a compact timing fingerprint so the packet table fills up.
        # Encode: [edge_count, median_dur_hi, median_dur_lo, level_mask]
        median = sorted(durations)[n // 2]
        lvl_byte = sum(1 << i for i, v in enumerate(levels[:8]) if v)
        return bytes([
            min(n, 255),
            (median >> 8) & 0xFF,
            median & 0xFF,
            lvl_byte,
        ])

    sorted_durs = sorted(durations)
    median = sorted_durs[n // 2]
    if median == 0:
        median = 1

    # short pulse (< median) → bit 1,  long pulse (≥ median) → bit 0
    bits = [0 if d >= median else 1 for d in durations]

    # Pack bits into bytes, MSB first
    byte_list = []
    for i in range(0, len(bits) - 7, 8):
        byte_val = 0
        for b in range(8):
            byte_val = (byte_val << 1) | bits[i + b]
        byte_list.append(byte_val)

    if not byte_list:
        # Had >= 8 edges but all landed in the same timing bucket.
        # Encode edge count + level pattern as fallback.
        lvl_byte = sum(1 << i for i, v in enumerate(levels[:8]) if v)
        return bytes([min(n, 255), lvl_byte])

    return bytes(byte_list)


class RingBuffer:
    """
    Fixed-size ring buffer for RawEdge objects.
    Oldest entries are silently dropped when the buffer is full.
    Used to keep a rolling window of recent edges without unbounded RAM use.
    """

    def __init__(self, maxlen: int = config.LIVE_RING_SIZE):
        self._buf: deque[RawEdge] = deque(maxlen=maxlen)

    def append(self, edge: RawEdge) -> None:
        self._buf.append(edge)

    def snapshot(self) -> list[RawEdge]:
        """Return a copy of all buffered edges (oldest first)."""
        return list(self._buf)

    def clear(self) -> None:
        self._buf.clear()

    def __len__(self) -> int:
        return len(self._buf)
