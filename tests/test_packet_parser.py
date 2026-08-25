"""
Tests for packet parser — edge accumulator and ring buffer.
"""

import pytest
from analyzer.models       import RawEdge
from analyzer.packet_parser import EdgeAccumulator, RingBuffer, _edges_to_bytes


class TestRingBuffer:
    def test_basic_append(self):
        buf = RingBuffer(maxlen=5)
        for i in range(3):
            buf.append(RawEdge(i * 100, 50, i % 2))
        assert len(buf) == 3

    def test_overflow_drops_oldest(self):
        buf = RingBuffer(maxlen=3)
        for i in range(5):
            buf.append(RawEdge(i * 100, 50, 0))
        assert len(buf) == 3
        snap = buf.snapshot()
        # The 3 newest should be i=2,3,4
        assert snap[0].timestamp_us == 200
        assert snap[2].timestamp_us == 400

    def test_clear(self):
        buf = RingBuffer(maxlen=10)
        for i in range(5):
            buf.append(RawEdge(i, 10, 0))
        buf.clear()
        assert len(buf) == 0
        assert buf.snapshot() == []


class TestEdgeAccumulator:
    def _make_edge(self, ts: int, dur: int, level: int) -> RawEdge:
        return RawEdge(timestamp_us=ts, duration_us=dur, level=level)

    def test_gap_triggers_packet_callback(self):
        received = []
        acc = EdgeAccumulator(gap_us=1000)
        acc.on_packet(lambda ts, data, edges: received.append((ts, data, edges)))

        # First group of edges
        for i in range(8):
            acc.feed(self._make_edge(ts=i * 10, dur=10, level=i % 2))

        # Large gap → packet
        acc.feed(self._make_edge(ts=10000, dur=50, level=0))

        assert len(received) == 1
        assert received[0][0] == 0   # timestamp of first edge in group

    def test_flush_now(self):
        received = []
        acc = EdgeAccumulator(gap_us=5000)
        acc.on_packet(lambda ts, data, edges: received.append(data))

        for i in range(8):
            acc.feed(self._make_edge(ts=i * 10, dur=10, level=i % 2))

        assert len(received) == 0
        acc.flush_now()
        assert len(received) == 1

    def test_no_callback_no_packet_below_8_edges(self):
        received = []
        acc = EdgeAccumulator(gap_us=100)
        acc.on_packet(lambda ts, data, edges: received.append(data))

        # Only 3 edges, then large gap
        for i in range(3):
            acc.feed(self._make_edge(ts=i * 10, dur=10, level=0))
        acc.feed(self._make_edge(ts=10000, dur=50, level=0))

        # Callback was called but data should be empty (< 8 edges)
        assert len(received) == 1
        assert received[0] == bytes()


class TestEdgesToBytes:
    def test_short_pulse_returns_empty(self):
        """Fewer than 8 usable edges → empty bytes."""
        edges = [RawEdge(i * 10, 1, 0) for i in range(4)]  # dur=1 < MIN_PULSE_US
        assert _edges_to_bytes(edges) == bytes()

    def test_returns_bytes_for_16_edges(self):
        """16 edges with valid durations should yield 2 bytes."""
        edges = []
        for i in range(16):
            dur = 50 if i % 2 == 0 else 100  # alternating short/long
            edges.append(RawEdge(i * 100, dur, i % 2))
        result = _edges_to_bytes(edges)
        assert len(result) == 2
