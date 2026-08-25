"""
Tests for packet statistics module.
"""

import pytest
from analyzer.statistics import PacketStats


def _make_stats(packets: list[tuple[int, bytes]]) -> PacketStats:
    """Helper: create a PacketStats and feed it a list of (ts, data)."""
    ps = PacketStats()
    for ts, data in packets:
        ps.add_packet(ts, data)
    return ps


class TestPacketStats:
    def test_empty(self):
        ps = PacketStats()
        assert ps.total_count == 0
        assert ps.unique_count == 0
        assert ps.records_by_count() == []

    def test_single_packet(self):
        ps = _make_stats([(1000, b"\xA5\x12\x03\x80\x01")])
        assert ps.total_count == 1
        assert ps.unique_count == 1
        rec = ps.records_by_count()[0]
        assert rec.data == b"\xA5\x12\x03\x80\x01"
        assert rec.count == 1

    def test_duplicate_packets(self):
        data = b"\xA5\x12\x03\x80\x01"
        ps = _make_stats([(i * 1000, data) for i in range(100)])
        assert ps.total_count == 100
        assert ps.unique_count == 1
        assert ps.records_by_count()[0].count == 100

    def test_sorted_by_count(self):
        ps = PacketStats()
        for _ in range(5):
            ps.add_packet(0, b"\xAA")
        for _ in range(3):
            ps.add_packet(0, b"\xBB")
        for _ in range(8):
            ps.add_packet(0, b"\xCC")

        records = ps.records_by_count()
        assert records[0].data == b"\xCC"
        assert records[1].data == b"\xAA"
        assert records[2].data == b"\xBB"

    def test_percentage(self):
        ps = PacketStats()
        for _ in range(3):
            ps.add_packet(0, b"\x01")
        for _ in range(1):
            ps.add_packet(0, b"\x02")

        recs = {r.data: r for r in ps.records_by_count()}
        assert abs(ps.percentage(recs[b"\x01"]) - 75.0) < 0.01
        assert abs(ps.percentage(recs[b"\x02"]) - 25.0) < 0.01

    def test_reset(self):
        ps = _make_stats([(0, b"\x01"), (1, b"\x02")])
        ps.reset()
        assert ps.total_count == 0
        assert ps.unique_count == 0

    def test_empty_data_ignored(self):
        ps = PacketStats()
        ps.add_packet(0, b"")
        assert ps.total_count == 0

    def test_first_last_seen(self):
        data = b"\xA5"
        ps   = PacketStats()
        ps.add_packet(1000, data)
        ps.add_packet(2000, data)
        rec = ps.records_by_count()[0]
        assert rec.first_seen == 1000
        assert rec.last_seen  == 2000

    def test_hex_str(self):
        ps = _make_stats([(0, b"\xA5\x12")])
        assert ps.records_by_count()[0].hex_str == "A5 12"

    def test_snapshot_structure(self):
        ps = _make_stats([(0, b"\xAA\xBB")])
        snap = ps.snapshot()
        assert "total_count"  in snap
        assert "unique_count" in snap
        assert "records"      in snap
        assert snap["records"][0]["hex"] == "AA BB"
