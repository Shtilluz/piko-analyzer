"""
Tests for action recorder — experiment workflow and diff logic.
"""

import os
import json
import tempfile
import pytest

from analyzer.action_recorder import ActionRecorder, _extract_numeric, _dominant


class TestExtractNumeric:
    def test_speed_labels(self):
        assert _extract_numeric("speed_0")  == 0.0
        assert _extract_numeric("speed_3")  == 3.0
        assert _extract_numeric("speed_10") == 10.0

    def test_on_off(self):
        assert _extract_numeric("f0_on")  == 1.0
        assert _extract_numeric("f0_off") == 0.0

    def test_no_suffix(self):
        assert _extract_numeric("forward") is None
        assert _extract_numeric("reverse") is None

    def test_custom_numeric(self):
        assert _extract_numeric("throttle_7") == 7.0


class TestDominant:
    def test_returns_most_common(self):
        pkts = [b"\x01", b"\x01", b"\x01", b"\x02"]
        assert _dominant(pkts) == b"\x01"

    def test_empty(self):
        assert _dominant([]) is None


class TestActionRecorder:
    def _recorder(self, tmp_path) -> ActionRecorder:
        return ActionRecorder(str(tmp_path / "actions.json"))

    def test_idle_initial_state(self, tmp_path):
        rec = self._recorder(tmp_path)
        assert rec.state == ActionRecorder.IDLE
        assert rec.records == []

    def test_full_workflow(self, tmp_path):
        rec = self._recorder(tmp_path)

        # Baseline
        rec.start_baseline("speed_1", "first experiment")
        assert rec.state == ActionRecorder.BASELINE

        for _ in range(5):
            rec.feed_packet(b"\xA5\x12\x03\x80\x01")

        # Action
        rec.switch_to_action()
        assert rec.state == ActionRecorder.RECORDING

        for _ in range(5):
            rec.feed_packet(b"\xA5\x12\x13\x80\x01")

        # Stop
        result = rec.stop_recording()
        assert result is not None
        assert result.label == "speed_1"
        assert rec.state == ActionRecorder.IDLE
        assert len(rec.records) == 1

    def test_dominant_packets(self, tmp_path):
        rec = self._recorder(tmp_path)
        rec.start_baseline("speed_2")
        for _ in range(8):
            rec.feed_packet(b"\xA5\x03")
        rec.feed_packet(b"\xA5\xFF")   # noise
        rec.switch_to_action()
        for _ in range(6):
            rec.feed_packet(b"\xA5\x13")

        result = rec.stop_recording()
        assert result.baseline_dominant == b"\xA5\x03"
        assert result.action_dominant   == b"\xA5\x13"

    def test_diff_detects_changed_byte(self, tmp_path):
        rec = self._recorder(tmp_path)
        rec.start_baseline("speed_3")
        rec.feed_packet(b"\xA5\x12\x03\x80\x01")
        rec.switch_to_action()
        rec.feed_packet(b"\xA5\x12\x13\x80\x01")
        result = rec.stop_recording()

        diffs = rec.compare_dominant(result)
        assert len(diffs) == 1
        pos, bv, av = diffs[0]
        assert pos == 2
        assert bv  == 0x03
        assert av  == 0x13

    def test_cancel_does_not_save(self, tmp_path):
        rec = self._recorder(tmp_path)
        rec.start_baseline("test")
        rec.feed_packet(b"\xAA")
        rec.cancel()
        assert rec.state == ActionRecorder.IDLE
        assert len(rec.records) == 0

    def test_persistence(self, tmp_path):
        path = str(tmp_path / "actions.json")
        rec  = ActionRecorder(path)
        rec.start_baseline("speed_5")
        rec.feed_packet(b"\x05")
        rec.switch_to_action()
        rec.feed_packet(b"\x06")
        rec.stop_recording()

        # Reload
        rec2 = ActionRecorder(path)
        assert len(rec2.records) == 1
        assert rec2.records[0].label == "speed_5"

    def test_records_for_correlation_filters_non_numeric(self, tmp_path):
        rec = self._recorder(tmp_path)

        for label, pkt in [("speed_1", b"\x01"), ("speed_2", b"\x02"),
                            ("speed_3", b"\x03"), ("forward", b"\xFF")]:
            rec.start_baseline(label)
            rec.feed_packet(b"\x00")
            rec.switch_to_action()
            rec.feed_packet(pkt)
            rec.stop_recording()

        triples = rec.records_for_correlation()
        labels = [t[0] for t in triples]
        assert "forward" not in labels
        assert all(lab.startswith("speed_") for lab in labels)
