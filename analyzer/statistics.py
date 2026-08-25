"""
Packet-level statistics.

Tracks unique packets, their occurrence counts, and timing metadata.
No field meaning is assigned — that is the job of correlation.py.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Iterator

from analyzer.models import PacketRecord
from analyzer import config


class PacketStats:
    """
    Maintains a dictionary of unique packet payloads → PacketRecord.

    Thread safety: all mutations go through add_packet() which the
    caller should protect with a lock when used from a non-GUI thread.
    (In practice the GUI thread calls this via Qt signal → slot, so
    no explicit lock is needed as long as we stay on the main thread.)
    """

    def __init__(self):
        self._records: dict[bytes, PacketRecord] = {}
        self._total_count = 0
        self._start_time  = 0   # timestamp_us of first packet

    # ---- Mutation ----

    def add_packet(self, timestamp_us: int, data: bytes) -> None:
        if not data:
            return

        if self._total_count == 0:
            self._start_time = timestamp_us

        self._total_count += 1

        if data in self._records:
            rec = self._records[data]
            rec.count    += 1
            rec.last_seen = timestamp_us
        else:
            if len(self._records) >= config.MAX_UNIQUE_PACKETS:
                # Guard against noise filling memory indefinitely.
                return
            self._records[data] = PacketRecord(
                data       = data,
                count      = 1,
                first_seen = timestamp_us,
                last_seen  = timestamp_us,
            )

    def reset(self) -> None:
        self._records.clear()
        self._total_count = 0
        self._start_time  = 0

    # ---- Queries ----

    @property
    def total_count(self) -> int:
        return self._total_count

    @property
    def unique_count(self) -> int:
        return len(self._records)

    @property
    def start_time_us(self) -> int:
        return self._start_time

    def records_by_count(self) -> list[PacketRecord]:
        """Return all records sorted by count descending."""
        return sorted(self._records.values(), key=lambda r: r.count, reverse=True)

    def most_common(self, n: int = 10) -> list[PacketRecord]:
        return self.records_by_count()[:n]

    def percentage(self, record: PacketRecord) -> float:
        if self._total_count == 0:
            return 0.0
        return 100.0 * record.count / self._total_count

    def all_packets_iter(self) -> Iterator[PacketRecord]:
        yield from self._records.values()

    def snapshot(self) -> dict:
        """Serialisable snapshot for session saving."""
        return {
            "total_count":  self._total_count,
            "unique_count": self.unique_count,
            "start_time_us": self._start_time,
            "records": [
                {
                    "hex":        rec.hex_str,
                    "data":       list(rec.data),
                    "count":      rec.count,
                    "first_seen": rec.first_seen,
                    "last_seen":  rec.last_seen,
                }
                for rec in self.records_by_count()
            ],
        }
