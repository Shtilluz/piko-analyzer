"""
Tests for checksum analysis.
"""

import pytest
from analyzer.checksum_analysis import (
    find_checksum_candidates,
    verify_checksum,
)


def _make_packets_with_xor_checksum(payloads: list[bytes]) -> list[tuple[bytes, int]]:
    """Append XOR of all bytes as last byte."""
    result = []
    for p in payloads:
        cs = 0
        for b in p:
            cs ^= b
        result.append((p + bytes([cs]), 1))
    return result


def _make_packets_with_sum8_checksum(payloads: list[bytes]) -> list[tuple[bytes, int]]:
    result = []
    for p in payloads:
        cs = sum(p) & 0xFF
        result.append((p + bytes([cs]), 1))
    return result


class TestVerifyChecksum:
    def test_xor_known(self):
        # 0xA5 ^ 0x12 ^ 0x03 = 0xB4
        data = bytes([0xA5, 0x12, 0x03, 0xA5 ^ 0x12 ^ 0x03])
        assert verify_checksum(data, position=3, algorithm="xor")

    def test_xor_wrong_algorithm(self):
        data = bytes([0xA5, 0x12, 0x03, 0xFF])
        assert not verify_checksum(data, position=3, algorithm="xor")

    def test_sum8(self):
        data = bytes([0x10, 0x20, 0x30, (0x10 + 0x20 + 0x30) & 0xFF])
        assert verify_checksum(data, position=3, algorithm="sum8")

    def test_invalid_position(self):
        assert not verify_checksum(b"\x01\x02", position=5, algorithm="xor")

    def test_unknown_algorithm(self):
        assert not verify_checksum(b"\x01", position=0, algorithm="nonexistent")


class TestFindChecksumCandidates:
    def test_xor_at_last_byte(self):
        payloads = [
            bytes([0xA5, 0x12, v])
            for v in [0x03, 0x13, 0x23, 0x33, 0x43]
        ]
        packets = _make_packets_with_xor_checksum(payloads)
        candidates = find_checksum_candidates(packets, min_match_pct=90.0)

        # At least one XOR candidate should be found at the last position
        xor_at_last = [
            c for c in candidates
            if c.algorithm == "xor" and c.byte_position == len(payloads[0])
        ]
        assert xor_at_last, f"XOR not found; candidates: {candidates}"
        assert xor_at_last[0].match_pct > 99.0

    def test_sum8_at_last_byte(self):
        payloads = [bytes([i, i + 1, i + 2]) for i in range(0, 50, 5)]
        packets  = _make_packets_with_sum8_checksum(payloads)
        candidates = find_checksum_candidates(packets, min_match_pct=90.0)

        sum_at_last = [
            c for c in candidates
            if c.algorithm == "sum8" and c.byte_position == 3
        ]
        assert sum_at_last
        assert sum_at_last[0].match_pct > 99.0

    def test_no_candidates_random(self):
        # All-zero packets with a random last byte won't match any checksum
        import random
        rng = random.Random(42)
        packets = [
            (bytes([0, 0, 0, rng.randint(1, 254)]), 1)
            for _ in range(20)
        ]
        candidates = find_checksum_candidates(packets, min_match_pct=90.0)
        # May have some matches by chance but very unlikely for 90%
        # (we check that XOR at pos 3 is not a 100% match)
        xor_100 = [
            c for c in candidates
            if c.algorithm == "xor" and c.byte_position == 3 and c.match_pct == 100.0
        ]
        assert not xor_100

    def test_empty_input(self):
        assert find_checksum_candidates([]) == []

    def test_sorted_by_match_pct(self):
        payloads = [bytes([i]) for i in range(10)]
        packets  = _make_packets_with_xor_checksum(payloads)
        candidates = find_checksum_candidates(packets)
        for i in range(len(candidates) - 1):
            assert candidates[i].match_pct >= candidates[i + 1].match_pct

    def test_weighted_counts(self):
        # packet b"\x01\x02\x03" appears 100 times; checksum = 0x01^0x02^0x03
        cs = 0x01 ^ 0x02 ^ 0x03
        packets = [(bytes([0x01, 0x02, 0x03, cs]), 100)]
        candidates = find_checksum_candidates(packets, min_match_pct=99.0)
        xor_c = [c for c in candidates if c.algorithm == "xor" and c.byte_position == 3]
        assert xor_c
        assert xor_c[0].match_pct == 100.0
