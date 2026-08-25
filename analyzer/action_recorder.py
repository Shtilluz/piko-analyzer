"""
Action recorder — manages the experiment workflow.

Workflow:
  1. User types a label (e.g. "speed_3") and a numeric value.
  2. User clicks START → program collects a baseline window.
  3. User performs ONE physical action on the controller.
  4. User clicks STOP → program collects the action window.
  5. Program computes the diff and stores the ActionRecord.
  6. Accumulated records are available for correlation analysis.

Persistence: records are saved to data/actions.json so they survive
across sessions.  The file is append-friendly; old records are NOT
overwritten.
"""

from __future__ import annotations

import json
import os
import time
from collections import Counter
from typing import Optional

from analyzer.models import ActionRecord


class ActionRecorder:
    """
    Manages recording state and stores ActionRecord objects.

    Not a Qt object — lives on the main thread, called from GUI slots.
    """

    BASELINE = "baseline"
    RECORDING = "recording"
    IDLE = "idle"

    def __init__(self, action_file: str):
        self._action_file = action_file
        self._records:   list[ActionRecord] = []
        self._state      = self.IDLE
        self._current:   Optional[ActionRecord] = None
        self._baseline_pkts: list[bytes] = []
        self._action_pkts:   list[bytes] = []

        self._load()

    # ---- Recording state machine ----

    def start_baseline(self, label: str, description: str = "") -> None:
        self._state         = self.BASELINE
        self._baseline_pkts = []
        self._action_pkts   = []
        self._current       = ActionRecord(
            label       = label,
            description = description,
            timestamp   = int(time.time() * 1_000_000),
        )

    def switch_to_action(self) -> None:
        """Call when the user performs the physical action."""
        if self._state == self.BASELINE:
            self._state = self.RECORDING

    def stop_recording(self) -> Optional[ActionRecord]:
        """
        Finalise the recording.  Returns the completed ActionRecord or None.
        """
        if self._state == self.IDLE or self._current is None:
            return None

        rec = self._current
        rec.baseline    = list(self._baseline_pkts)
        rec.action_pkts = list(self._action_pkts)
        rec.baseline_dominant = _dominant(self._baseline_pkts)
        rec.action_dominant   = _dominant(self._action_pkts)

        self._records.append(rec)
        self._save()

        self._state    = self.IDLE
        self._current  = None
        self._baseline_pkts = []
        self._action_pkts   = []
        return rec

    def cancel(self) -> None:
        self._state   = self.IDLE
        self._current = None

    def feed_packet(self, data: bytes) -> None:
        """Feed a packet into whichever window is currently open."""
        if self._state == self.BASELINE:
            self._baseline_pkts.append(data)
        elif self._state == self.RECORDING:
            self._action_pkts.append(data)

    # ---- Queries ----

    @property
    def state(self) -> str:
        return self._state

    @property
    def records(self) -> list[ActionRecord]:
        return list(self._records)

    def compare_dominant(
        self, rec: ActionRecord
    ) -> list[tuple[int, int, int]]:
        """
        Compare dominant baseline vs dominant action packet byte by byte.

        Returns list of (byte_pos, baseline_val, action_val) for positions
        where the values differ.
        """
        b = rec.baseline_dominant
        a = rec.action_dominant
        if not b or not a:
            return []

        diffs = []
        for pos in range(max(len(b), len(a))):
            bv = b[pos] if pos < len(b) else None
            av = a[pos] if pos < len(a) else None
            if bv != av:
                diffs.append((pos, bv, av))
        return diffs

    def records_for_correlation(
        self,
    ) -> list[tuple[str, float, bytes]]:
        """
        Return (label, numeric_value, dominant_packet) for all records
        that have a numeric value embedded in their label (e.g. "speed_3"
        → 3.0) and a non-empty action dominant packet.

        Records without a numeric suffix are skipped.
        """
        result = []
        for rec in self._records:
            val = _extract_numeric(rec.label)
            if val is not None and rec.action_dominant:
                result.append((rec.label, val, rec.action_dominant))
        return result

    # ---- Persistence ----

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._action_file), exist_ok=True)
        data = [_record_to_dict(r) for r in self._records]
        with open(self._action_file, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    def _load(self) -> None:
        if not os.path.exists(self._action_file):
            return
        try:
            with open(self._action_file, encoding="utf-8") as fh:
                data = json.load(fh)
            self._records = [_dict_to_record(d) for d in data]
        except (json.JSONDecodeError, KeyError, TypeError):
            self._records = []


# ---- Helpers ----

def _dominant(pkts: list[bytes]) -> Optional[bytes]:
    if not pkts:
        return None
    counter = Counter(pkts)
    return counter.most_common(1)[0][0]


def _extract_numeric(label: str) -> Optional[float]:
    """'speed_3' → 3.0,  'f0_on' → 1.0,  'f0_off' → 0.0,  'reverse' → None"""
    parts = label.rsplit("_", 1)
    if len(parts) == 2:
        try:
            return float(parts[1])
        except ValueError:
            if parts[1] == "on":
                return 1.0
            if parts[1] == "off":
                return 0.0
    return None


def _record_to_dict(rec: ActionRecord) -> dict:
    return {
        "label":        rec.label,
        "description":  rec.description,
        "timestamp":    rec.timestamp,
        "profile_type": rec.profile_type,
        "baseline":     [list(p) for p in rec.baseline],
        "action_pkts":  [list(p) for p in rec.action_pkts],
        "baseline_dominant": list(rec.baseline_dominant) if rec.baseline_dominant else None,
        "action_dominant":   list(rec.action_dominant)   if rec.action_dominant   else None,
    }


def _dict_to_record(d: dict) -> ActionRecord:
    return ActionRecord(
        label        = d["label"],
        description  = d.get("description", ""),
        timestamp    = d.get("timestamp", 0),
        profile_type = d.get("profile_type", ""),
        baseline     = [bytes(p) for p in d.get("baseline", [])],
        action_pkts  = [bytes(p) for p in d.get("action_pkts", [])],
        baseline_dominant = bytes(d["baseline_dominant"]) if d.get("baseline_dominant") else None,
        action_dominant   = bytes(d["action_dominant"])   if d.get("action_dominant")   else None,
    )
