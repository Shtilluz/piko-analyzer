"""
Tests for byte and bit analysis.
"""

import pytest
from analyzer.bit_analysis import (
    compute_byte_stats,
    compute_bit_stats,
    compute_bit_transitions,
    most_variable_bytes,
)
from analyzer.models import ByteStats


# ---- Synthetic test data ----
# Simulates a 5-byte protocol where:
#   BYTE 0 is always 0xA5 (CONSTANT)
#   BYTE 1 is always 0x12 (CONSTANT)
#   BYTE 2 varies 0x03/0x13/0x23 (VARIABLE)
#   BYTE 3 is mostly 0x80 (MOSTLY_CONSTANT, one exception)
#   BYTE 4 is always 0x01 (CONSTANT)

SYNTHETIC = [
    (b"\xA5\x12\x03\x80\x01", 80),
    (b"\xA5\x12\x13\x80\x01", 10),
    (b"\xA5\x12\x23\x80\x01", 10),
    (b"\xA5\x12\x03\x81\x01", 1),   # BYTE 3 exception
]


class TestByteStats:
    def test_constant_byte(self):
        stats = compute_byte_stats(SYNTHETIC)
        assert stats[0].is_constant
        assert stats[1].is_constant
        assert 0xA5 in stats[0].value_counts
        assert stats[0].value_counts[0xA5] == 101   # 80+10+10+1

    def test_variable_byte(self):
        stats = compute_byte_stats(SYNTHETIC)
        assert not stats[2].is_constant
        assert stats[2].unique_count == 3

    def test_variability_labels(self):
        stats = compute_byte_stats(SYNTHETIC)
        assert stats[0].variability_label == "CONSTANT"
        assert stats[2].variability_label == "VARIABLE"

    def test_total_weighted(self):
        stats = compute_byte_stats(SYNTHETIC)
        # Total for BYTE 0: 80+10+10+1 = 101
        assert stats[0].total == 101

    def test_empty_input(self):
        assert compute_byte_stats([]) == []


class TestBitStats:
    def test_constant_byte_bits(self):
        # BYTE 0 = 0xA5 = 1010_0101 always
        stats = compute_bit_stats(SYNTHETIC)
        byte0 = stats[0]

        # BIT 7 should be 100% 1  (0xA5 bit7=1)
        assert byte0[7].count_1 == 101
        assert byte0[7].count_0 == 0
        assert abs(byte0[7].pct_1 - 100.0) < 0.01

        # BIT 6 should be 100% 0  (0xA5 bit6=0)
        assert byte0[6].count_0 == 101
        assert byte0[6].count_1 == 0

    def test_variable_byte_bits(self):
        # BYTE 2: 0x03=0000_0011, 0x13=0001_0011, 0x23=0010_0011
        # BIT 0 always 1 → 100%
        stats   = compute_bit_stats(SYNTHETIC)
        byte2   = stats[2]
        bit0    = byte2[0]
        assert bit0.count_1 == 101  # all packets have bit0=1

    def test_bit_positions_consistent(self):
        stats = compute_bit_stats(SYNTHETIC)
        for byte_row in stats:
            assert len(byte_row) == 8

    def test_empty_input(self):
        assert compute_bit_stats([]) == []


class TestBitTransitions:
    def test_no_transitions_constant(self):
        ordered = [b"\xA5\x12\x03\x80\x01"] * 10
        trans = compute_bit_transitions(ordered)
        # All bits constant → zero transitions
        for byte_row in trans:
            for cnt in byte_row:
                assert cnt == 0

    def test_single_bit_toggle(self):
        # Alternates between 0x00 and 0x01 → BIT0 transitions 9 times
        ordered = [bytes([i & 1]) for i in range(10)]
        trans   = compute_bit_transitions(ordered)
        assert trans[0][0] == 9   # bit 0 transitions

    def test_requires_two_packets(self):
        assert compute_bit_transitions([b"\x00"]) == []


class TestMostVariableBytes:
    def test_order(self):
        stats = compute_byte_stats(SYNTHETIC)
        top   = most_variable_bytes(stats, top_n=1)
        assert top[0] == 2   # BYTE 2 has 3 unique values
