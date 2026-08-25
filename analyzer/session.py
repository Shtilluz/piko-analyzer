"""
Session save/load — persists a complete analysis snapshot to JSON.

A session contains:
  - metadata (date, duration, port)
  - packet statistics snapshot
  - byte statistics
  - bit statistics
  - transition statistics
  - action records
  - checksum candidates
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Any

from analyzer import config


class SessionManager:
    """
    Coordinates data from all analysis modules and serialises to JSON.
    """

    def __init__(self, session_dir: str = config.SESSION_DIR):
        self._session_dir = session_dir

    def save(
        self,
        *,
        packet_stats,
        byte_stats,
        bit_stats,
        transition_tracker,
        action_recorder,
        checksum_candidates,
        port: str = "",
        duration_s: float = 0.0,
        extra: dict | None = None,
    ) -> str:
        """
        Save a session snapshot to a timestamped JSON file.
        Returns the path of the saved file.
        """
        os.makedirs(self._session_dir, exist_ok=True)
        ts       = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(self._session_dir, f"session_{ts}.json")

        doc: dict[str, Any] = {
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "port":       port,
                "duration_s": duration_s,
                "app":        "PIKO SmartControl Protocol Analyzer",
            },
            "packet_statistics":    packet_stats.snapshot(),
            "byte_statistics":      _serialize_byte_stats(byte_stats),
            "bit_statistics":       _serialize_bit_stats(bit_stats),
            "transition_statistics": transition_tracker.snapshot(),
            "actions":              _serialize_actions(action_recorder.records),
            "checksum_candidates":  [
                {
                    "algorithm":     c.algorithm,
                    "byte_position": c.byte_position,
                    "match_pct":     round(c.match_pct, 2),
                    "match_count":   c.match_count,
                    "total_count":   c.total_count,
                }
                for c in checksum_candidates
            ],
        }
        if extra:
            doc["extra"] = extra

        with open(filename, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=2)

        return filename

    def load(self, path: str) -> dict:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def list_sessions(self) -> list[str]:
        if not os.path.isdir(self._session_dir):
            return []
        files = [
            os.path.join(self._session_dir, f)
            for f in os.listdir(self._session_dir)
            if f.startswith("session_") and f.endswith(".json")
        ]
        return sorted(files, reverse=True)

    def export_csv(self, packet_stats, path: str) -> None:
        """Export unique packet statistics as CSV."""
        import csv
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["hex", "count", "pct", "first_seen_us", "last_seen_us"])
            total = packet_stats.total_count
            for rec in packet_stats.records_by_count():
                pct = 100.0 * rec.count / total if total else 0.0
                writer.writerow([
                    rec.hex_str,
                    rec.count,
                    f"{pct:.2f}",
                    rec.first_seen,
                    rec.last_seen,
                ])


# ---- Serialisation helpers ----

def _serialize_byte_stats(byte_stats) -> list[dict]:
    if not byte_stats:
        return []
    result = []
    for bs in byte_stats:
        result.append({
            "position":    bs.position,
            "variability": bs.variability_label,
            "unique_count": bs.unique_count,
            "total":        bs.total,
            "value_counts": {f"{k:02X}": v for k, v in bs.value_counts.items()},
        })
    return result


def _serialize_bit_stats(bit_stats_2d) -> list[list[dict]]:
    if not bit_stats_2d:
        return []
    result = []
    for byte_row in bit_stats_2d:
        row = []
        for bs in byte_row:
            row.append({
                "byte_pos":      bs.byte_pos,
                "bit_pos":       bs.bit_pos,
                "count_0":       bs.count_0,
                "count_1":       bs.count_1,
                "pct_1":         round(bs.pct_1, 2),
                "transitions":   bs.transitions,
                "transition_pct": round(bs.transition_pct, 2),
            })
        result.append(row)
    return result


def _serialize_actions(records) -> list[dict]:
    return [
        {
            "label":       r.label,
            "description": r.description,
            "timestamp":   r.timestamp,
            "baseline_dominant": list(r.baseline_dominant) if r.baseline_dominant else None,
            "action_dominant":   list(r.action_dominant)   if r.action_dominant   else None,
        }
        for r in records
    ]
