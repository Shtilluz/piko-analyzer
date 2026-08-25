"""
Tests for correlation analysis.
"""

import pytest
from analyzer.correlation import find_correlations, _pearson, _extract_bits


class TestPearson:
    def test_perfect_positive(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [2.0, 4.0, 6.0, 8.0]
        assert abs(_pearson(xs, ys) - 1.0) < 1e-9

    def test_perfect_negative(self):
        xs = [1.0, 2.0, 3.0, 4.0]
        ys = [8.0, 6.0, 4.0, 2.0]
        assert abs(_pearson(xs, ys) + 1.0) < 1e-9

    def test_zero_variance(self):
        xs = [1.0, 1.0, 1.0]
        ys = [2.0, 3.0, 4.0]
        assert _pearson(xs, ys) == 0.0

    def test_too_short(self):
        assert _pearson([1.0], [1.0]) == 0.0


class TestExtractBits:
    def test_full_byte(self):
        assert _extract_bits(0xFF, 7, 0) == 0xFF

    def test_nibble_high(self):
        assert _extract_bits(0xA5, 7, 4) == 0x0A

    def test_nibble_low(self):
        assert _extract_bits(0xA5, 3, 0) == 0x05

    def test_single_bit(self):
        assert _extract_bits(0b10000000, 7, 7) == 1
        assert _extract_bits(0b01111111, 7, 7) == 0


class TestFindCorrelations:
    def _speed_actions(self) -> list[tuple[str, float, bytes]]:
        """
        Synthetic experiment: speed value is stored in bits 4..0 of BYTE 1.
        BYTE 0 is constant (0xA5), BYTE 2 is constant (0x80).
        """
        actions = []
        for speed in range(8):
            # Encode speed in bits [4:0] of BYTE 1
            byte1 = (speed & 0x1F)
            actions.append((f"speed_{speed}", float(speed), bytes([0xA5, byte1, 0x80])))
        return actions

    def test_perfect_linear_correlation_found(self):
        actions    = self._speed_actions()
        candidates = find_correlations(actions, min_confidence=0.90)

        # Should find something in BYTE 1 that correlates with speed
        byte1_hits = [c for c in candidates if c.byte_pos == 1]
        assert byte1_hits, f"No candidates in BYTE 1.  All: {candidates}"
        best = max(byte1_hits, key=lambda c: c.confidence)
        assert best.confidence > 0.99

    def test_constant_byte_not_correlated(self):
        actions    = self._speed_actions()
        candidates = find_correlations(actions, min_confidence=0.90)
        # BYTE 0 is constant → should not appear as a candidate
        byte0_hits = [c for c in candidates if c.byte_pos == 0]
        assert byte0_hits == []

    def test_too_few_actions(self):
        actions = [
            ("speed_1", 1.0, b"\x01"),
            ("speed_2", 2.0, b"\x02"),
        ]
        candidates = find_correlations(actions)
        assert candidates == []

    def test_negative_correlation_found(self):
        # Inverted: higher speed value → lower byte value
        actions = [
            (f"speed_{i}", float(i), bytes([10 - i]))
            for i in range(8)
        ]
        candidates = find_correlations(actions, min_confidence=0.90)
        hits = [c for c in candidates if c.byte_pos == 0]
        assert hits
        # Correlation should be negative (inverse relationship)
        assert any(c.correlation < -0.90 for c in hits)
