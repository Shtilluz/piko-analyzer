"""
Tests for transition analysis.
"""

import pytest
from analyzer.transition_analysis import TransitionTracker


class TestTransitionTracker:
    def test_empty(self):
        tt = TransitionTracker()
        assert tt.transitions_for_byte(0) == []
        assert tt.active_byte_positions() == []

    def test_single_packet_no_transitions(self):
        tt = TransitionTracker()
        tt.feed_packet(b"\xA5\x03")
        assert tt.transitions_for_byte(0) == []  # no previous packet to compare

    def test_two_identical_packets(self):
        tt = TransitionTracker()
        tt.feed_packet(b"\xA5\x03")
        tt.feed_packet(b"\xA5\x03")
        assert tt.transitions_for_byte(0) == []
        assert tt.transitions_for_byte(1) == []

    def test_byte_change_recorded(self):
        tt = TransitionTracker()
        tt.feed_packet(b"\xA5\x03")
        tt.feed_packet(b"\xA5\x13")
        # BYTE 0 unchanged, BYTE 1 changed 0x03 → 0x13
        assert tt.transitions_for_byte(0) == []
        results = tt.transitions_for_byte(1)
        assert len(results) == 1
        fv, tv, cnt = results[0]
        assert fv == 0x03
        assert tv == 0x13
        assert cnt == 1

    def test_repeated_transition_accumulates(self):
        tt = TransitionTracker()
        for _ in range(5):
            tt.feed_packet(b"\x00")
            tt.feed_packet(b"\x01")
        results = tt.transitions_for_byte(0)
        by_pair = {(fv, tv): cnt for fv, tv, cnt in results}
        # 0→1 happens 5 times, 1→0 happens 4 times
        assert by_pair[(0x00, 0x01)] == 5
        assert by_pair[(0x01, 0x00)] == 4

    def test_sorted_by_count(self):
        tt = TransitionTracker()
        for _ in range(3):
            tt.feed_packet(b"\x01")
            tt.feed_packet(b"\x02")
        for _ in range(10):
            tt.feed_packet(b"\x05")
            tt.feed_packet(b"\x06")

        results = tt.transitions_for_byte(0)
        # Most frequent transitions should come first
        assert results[0][2] >= results[1][2]

    def test_reset(self):
        tt = TransitionTracker()
        tt.feed_packet(b"\x01")
        tt.feed_packet(b"\x02")
        tt.reset()
        assert tt.active_byte_positions() == []

    def test_snapshot_format(self):
        tt = TransitionTracker()
        tt.feed_packet(b"\xAA")
        tt.feed_packet(b"\xBB")
        snap = tt.snapshot()
        assert 0 in snap
        assert "AA->BB" in snap[0]
