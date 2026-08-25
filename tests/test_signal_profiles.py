"""Unit tests for analyzer.signal_profiles."""

from __future__ import annotations

import pytest

from analyzer.models import ActionRecord
from analyzer.signal_profiles import (
    BUILTIN_PROFILES,
    ProfileType,
    analyze_profile,
    detect_profile,
    find_address_field,
    find_direction_field,
)


# ---------------------------------------------------------------------------
# find_direction_field
# ---------------------------------------------------------------------------

def test_direction_field_perfect():
    """Bit 3 of byte 0 always flips → confidence = 1.0."""
    pairs = [
        (bytes([0x00, 0xAA]), bytes([0x08, 0xAA])),
        (bytes([0x00, 0xBB]), bytes([0x08, 0xBB])),
        (bytes([0x00, 0xCC]), bytes([0x08, 0xCC])),
        (bytes([0x00, 0xDD]), bytes([0x08, 0xDD])),
    ]
    fields = find_direction_field(pairs)
    assert fields, "Expected at least one field"
    best = fields[0]
    assert best.name == "direction"
    assert best.byte_pos == 0
    assert best.bit_high == 3
    assert best.bit_low == 3
    assert best.confidence == pytest.approx(1.0)


def test_direction_field_noisy():
    """3 of 4 pairs flip bit 3 → confidence = 0.75."""
    pairs = [
        (bytes([0x00]), bytes([0x08])),  # flips
        (bytes([0x00]), bytes([0x08])),  # flips
        (bytes([0x00]), bytes([0x08])),  # flips
        (bytes([0x00]), bytes([0x00])),  # does NOT flip
    ]
    fields = find_direction_field(pairs)
    match = [f for f in fields if f.byte_pos == 0 and f.bit_low == 3]
    assert match, "Expected a field at byte 0 bit 3"
    assert match[0].confidence == pytest.approx(0.75)


def test_direction_field_empty():
    assert find_direction_field([]) == []


def test_direction_field_below_threshold():
    """Only 1 of 4 pairs flips → confidence 0.25 → not returned."""
    pairs = [
        (bytes([0x00]), bytes([0x08])),  # flips
        (bytes([0x00]), bytes([0x00])),
        (bytes([0x00]), bytes([0x00])),
        (bytes([0x00]), bytes([0x00])),
    ]
    fields = find_direction_field(pairs)
    # bit 3 has confidence 0.25 — below 0.5 threshold
    match = [f for f in fields if f.byte_pos == 0 and f.bit_low == 3]
    assert not match


# ---------------------------------------------------------------------------
# find_address_field
# ---------------------------------------------------------------------------

def test_address_field_pearson():
    """Address 1–4 encoded in bits [3:0] of byte 0 → |r| ≈ 1.0."""
    samples = [
        (1, bytes([0x01, 0xAA])),
        (2, bytes([0x02, 0xAA])),
        (3, bytes([0x03, 0xAA])),
        (4, bytes([0x04, 0xAA])),
    ]
    fields = find_address_field(samples)
    assert fields, "Expected address field candidates"
    best = fields[0]
    assert best.name == "address"
    assert best.byte_pos == 0
    assert best.confidence >= 0.99


def test_address_field_insufficient():
    """Only 2 samples → returns []."""
    samples = [(1, bytes([0x01])), (2, bytes([0x02]))]
    assert find_address_field(samples) == []


def test_address_field_empty():
    assert find_address_field([]) == []


# ---------------------------------------------------------------------------
# analyze_profile — switch
# ---------------------------------------------------------------------------

def _make_switch_record(n: int, state: str) -> ActionRecord:
    """
    Synthetic switch record: address in byte[0] lower nibble,
    direction in byte[1] bit 3 (plus=1, minus=0).
    """
    dir_bit = 0x08 if state == "plus" else 0x00
    pkt = bytes([n & 0x0F, dir_bit, 0xFF])
    return ActionRecord(
        label           = f"sw_{n}_{state}",
        action_dominant = pkt,
    )


def test_analyze_switch_full():
    """8 records (sw_1..sw_4 × plus/minus) → finds direction + address fields."""
    records = []
    for n in range(1, 5):
        records.append(_make_switch_record(n, "plus"))
        records.append(_make_switch_record(n, "minus"))

    profile = BUILTIN_PROFILES[ProfileType.SWITCH]
    result  = analyze_profile(records, profile)

    assert result.matched_count == 8
    dir_fields  = [f for f in result.fields if f.name == "direction"]
    addr_fields = [f for f in result.fields if f.name == "address"]
    assert dir_fields,  "Expected direction field"
    assert addr_fields, "Expected address field"
    assert dir_fields[0].confidence >= 0.75
    assert addr_fields[0].confidence >= 0.75


def test_analyze_switch_insufficient_addresses():
    """Only one address → address field missing, direction may be found."""
    records = [
        _make_switch_record(1, "plus"),
        _make_switch_record(1, "minus"),
    ]
    profile = BUILTIN_PROFILES[ProfileType.SWITCH]
    result  = analyze_profile(records, profile)

    addr_fields = [f for f in result.fields if f.name == "address"]
    assert not addr_fields, "Should not find address field with only 1 address"
    assert any("≥3" in w or "address" in w.lower() for w in result.warnings)


def test_analyze_profile_no_records():
    """Empty input → matched_count=0, has warning."""
    profile = BUILTIN_PROFILES[ProfileType.SWITCH]
    result  = analyze_profile([], profile)
    assert result.matched_count == 0
    assert result.warnings


# ---------------------------------------------------------------------------
# detect_profile
# ---------------------------------------------------------------------------

def test_detect_profile_switch():
    """Labels sw_1_plus, sw_1_minus, sw_2_plus, sw_2_minus → SWITCH."""
    records = [
        ActionRecord(label="sw_1_plus"),
        ActionRecord(label="sw_1_minus"),
        ActionRecord(label="sw_2_plus"),
        ActionRecord(label="sw_2_minus"),
    ]
    assert detect_profile(records) == ProfileType.SWITCH


def test_detect_profile_none():
    """Random labels → None."""
    records = [ActionRecord(label="foo"), ActionRecord(label="bar")]
    assert detect_profile(records) is None


# ---------------------------------------------------------------------------
# BUILTIN_PROFILES sanity
# ---------------------------------------------------------------------------

def test_builtin_profiles_compile():
    """All built-in profiles have a compiled regex and valid min thresholds."""
    for ptype, profile in BUILTIN_PROFILES.items():
        assert profile.compiled is not None, f"{ptype} has no compiled regex"
        assert profile.min_addresses >= 1
        assert profile.min_states >= 1
        assert profile.ptype == ptype
