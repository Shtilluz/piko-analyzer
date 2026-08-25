"""
Universal Signal Finder — profile-driven analysis of accessory decoder signals.

A "profile" describes a class of controllable devices (switch, signal, relay…)
by a label naming convention.  Given a set of recorded ActionRecord experiments
whose labels match the profile pattern, the module finds:

  - direction field  — bit(s) that flip between two states of the same address
  - address field    — bit range whose value correlates with the device number

Adding a new device type requires only a new ProfileDefinition entry in
BUILTIN_PROFILES — no algorithmic changes needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# Reuse well-tested math from the existing correlation module.
# These helpers are module-level functions (leading underscore = convention only).
from analyzer.correlation import _extract_bits, _pearson
from analyzer.models import ActionRecord


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

class ProfileType(Enum):
    LOCOMOTIVE = "locomotive"
    SWITCH     = "switch"   # стрелки:  sw_N_plus  / sw_N_minus
    SIGNAL     = "signal"   # светофоры: sig_N_red / sig_N_green / sig_N_yellow
    RELAY      = "relay"    # реле:     relay_N_on / relay_N_off
    CUSTOM     = "custom"


@dataclass
class ProfileDefinition:
    """
    Describes how to recognise and analyse one class of device labels.
    label_pattern is compiled to _compiled in __post_init__.
    """
    ptype:         ProfileType
    name:          str
    label_pattern: str          # regex; groups: addr_group, state_group
    addr_group:    int          # regex capture group index for address number (0 = none)
    state_group:   int          # regex capture group index for state name
    state_map:     dict[str, int]   # maps state name → numeric value
    min_addresses: int = 2
    min_states:    int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "_compiled", re.compile(self.label_pattern))

    @property
    def compiled(self) -> re.Pattern:
        return object.__getattribute__(self, "_compiled")


@dataclass
class SignalField:
    """One discovered protocol field."""
    name:       str     # "address" | "direction" | "state"
    byte_pos:   int
    bit_high:   int     # inclusive, 0 = LSB
    bit_low:    int     # inclusive, 0 = LSB
    confidence: float   # 0.0–1.0
    note:       str


@dataclass
class ProfileAnalysisResult:
    profile:        ProfileDefinition
    matched_count:  int
    fields:         list[SignalField]   # sorted by confidence desc
    warnings:       list[str]
    missing_states: list[str]


# ---------------------------------------------------------------------------
# Built-in profiles
# ---------------------------------------------------------------------------

BUILTIN_PROFILES: dict[ProfileType, ProfileDefinition] = {
    ProfileType.SWITCH: ProfileDefinition(
        ptype         = ProfileType.SWITCH,
        name          = "Switch / Point",
        label_pattern = r"^sw_(\d+)_(plus|minus)$",
        addr_group    = 1,
        state_group   = 2,
        state_map     = {"plus": 1, "minus": 0},
        min_addresses = 2,
        min_states    = 2,
    ),
    ProfileType.SIGNAL: ProfileDefinition(
        ptype         = ProfileType.SIGNAL,
        name          = "Railway Signal",
        label_pattern = r"^sig_(\d+)_(red|green|yellow)$",
        addr_group    = 1,
        state_group   = 2,
        state_map     = {"red": 0, "green": 1, "yellow": 2},
        min_addresses = 2,
        min_states    = 2,
    ),
    ProfileType.RELAY: ProfileDefinition(
        ptype         = ProfileType.RELAY,
        name          = "Relay",
        label_pattern = r"^relay_(\d+)_(on|off)$",
        addr_group    = 1,
        state_group   = 2,
        state_map     = {"on": 1, "off": 0},
        min_addresses = 2,
        min_states    = 2,
    ),
    ProfileType.LOCOMOTIVE: ProfileDefinition(
        ptype         = ProfileType.LOCOMOTIVE,
        name          = "Locomotive",
        label_pattern = r"^(speed_\d+|f\d+_(on|off)|forward|reverse)$",
        addr_group    = 0,
        state_group   = 0,
        state_map     = {},
        min_addresses = 1,
        min_states    = 3,
    ),
}


# ---------------------------------------------------------------------------
# Core algorithms
# ---------------------------------------------------------------------------

def find_direction_field(
    pairs: list[tuple[bytes, bytes]],
) -> list[SignalField]:
    """
    Find bits that consistently flip between state-A and state-B packets.

    pairs: list of (dominant_state_0, dominant_state_1) for the same address.
    Returns SignalField list (bit-level, bit_high == bit_low) sorted by
    confidence descending.  confidence = fraction of pairs where the bit flips.
    """
    if not pairs:
        return []

    min_len = min(min(len(a), len(b)) for a, b in pairs)
    if min_len == 0:
        return []

    n = len(pairs)
    candidates: list[SignalField] = []

    for byte_pos in range(min_len):
        flip_counts = [0] * 8
        for pkt_a, pkt_b in pairs:
            xor = pkt_a[byte_pos] ^ pkt_b[byte_pos]
            for bit in range(8):
                if xor & (1 << bit):
                    flip_counts[bit] += 1

        for bit in range(8):
            confidence = flip_counts[bit] / n
            if confidence >= 0.5:
                candidates.append(SignalField(
                    name       = "direction",
                    byte_pos   = byte_pos,
                    bit_high   = bit,
                    bit_low    = bit,
                    confidence = confidence,
                    note       = f"flips in {flip_counts[bit]}/{n} pairs",
                ))

    candidates.sort(key=lambda f: -f.confidence)
    return candidates


def find_address_field(
    samples: list[tuple[int, bytes]],
    min_confidence: float = 0.75,
) -> list[SignalField]:
    """
    Find bit ranges whose value correlates (Pearson) with the device address number.

    samples: list of (address_int, dominant_packet).
    Requires >= 3 samples.  Returns SignalField list sorted by confidence desc.
    """
    valid = [(addr, pkt) for addr, pkt in samples if pkt]
    if len(valid) < 3:
        return []

    addr_values = [float(addr) for addr, _ in valid]
    packets     = [pkt for _, pkt in valid]
    max_len     = max(len(p) for p in packets)

    candidates: list[SignalField] = []

    for byte_pos in range(max_len):
        for bit_high in range(7, -1, -1):
            for bit_low in range(0, bit_high + 1):
                bit_vals = []
                for pkt in packets:
                    bv = pkt[byte_pos] if byte_pos < len(pkt) else 0
                    bit_vals.append(float(_extract_bits(bv, bit_high, bit_low)))

                r    = _pearson(bit_vals, addr_values)
                conf = abs(r)

                if conf >= min_confidence:
                    candidates.append(SignalField(
                        name       = "address",
                        byte_pos   = byte_pos,
                        bit_high   = bit_high,
                        bit_low    = bit_low,
                        confidence = conf,
                        note       = f"Pearson r={r:.3f} (n={len(valid)})",
                    ))

    # Keep only the tightest bit range per (byte_pos, bit_low) cluster
    candidates.sort(key=lambda f: (-f.confidence, f.bit_high - f.bit_low))
    seen: set[tuple[int, int, int]] = set()
    filtered: list[SignalField] = []
    for c in candidates:
        key = (c.byte_pos, c.bit_high, c.bit_low)
        if key not in seen:
            seen.add(key)
            filtered.append(c)

    return filtered[:20]


# ---------------------------------------------------------------------------
# High-level analysis
# ---------------------------------------------------------------------------

def _dominant(rec: ActionRecord) -> Optional[bytes]:
    """Return the best available dominant packet from a record."""
    return rec.action_dominant or rec.baseline_dominant


def analyze_profile(
    records: list[ActionRecord],
    profile: ProfileDefinition,
) -> ProfileAnalysisResult:
    """
    Analyse all records matching `profile` and return discovered fields.

    Works for any profile type that has addr_group and state_group > 0.
    For LOCOMOTIVE (addr_group=0) only direction/state fields are attempted.
    """
    compiled = profile.compiled
    matched  = [r for r in records if compiled.match(r.label)]

    warnings:       list[str] = []
    missing_states: list[str] = []

    if not matched:
        return ProfileAnalysisResult(
            profile       = profile,
            matched_count = 0,
            fields        = [],
            warnings      = [f"No records match pattern {profile.label_pattern!r}"],
            missing_states= [],
        )

    # Group by (address, state)
    # addr_val → state_name → dominant_packet
    groups: dict[str, dict[str, Optional[bytes]]] = {}
    for rec in matched:
        m = compiled.match(rec.label)
        if m is None:
            continue
        addr  = m.group(profile.addr_group) if profile.addr_group else "0"
        state = m.group(profile.state_group) if profile.state_group else rec.label
        pkt   = _dominant(rec)
        if addr not in groups:
            groups[addr] = {}
        if state not in groups[addr] or groups[addr][state] is None:
            groups[addr][state] = pkt
        if pkt is None:
            warnings.append(f"Record '{rec.label}' has no dominant packet — skipped")

    # Check for missing states
    all_states = set(profile.state_map.keys()) or {"on", "off"}
    for addr, state_dict in groups.items():
        for expected_state in all_states:
            if expected_state not in state_dict:
                missing_states.append(
                    f"Address {addr}: missing state '{expected_state}'"
                )

    # Build direction pairs: same address, state_0 vs state_1
    state_names = list(profile.state_map.keys())
    pairs: list[tuple[bytes, bytes]] = []
    if len(state_names) >= 2:
        s0, s1 = state_names[0], state_names[1]
        for addr, state_dict in groups.items():
            pkt0 = state_dict.get(s0)
            pkt1 = state_dict.get(s1)
            if pkt0 and pkt1:
                pairs.append((pkt0, pkt1))

    # Build address samples: canonical state (state_names[0]), one per address
    canonical = state_names[0] if state_names else None
    addr_samples: list[tuple[int, bytes]] = []
    if canonical and profile.addr_group:
        for addr_str, state_dict in groups.items():
            pkt = state_dict.get(canonical)
            if pkt:
                try:
                    addr_samples.append((int(addr_str), pkt))
                except ValueError:
                    pass

    # Run algorithms
    dir_fields  = find_direction_field(pairs) if len(pairs) >= 2 else []
    addr_fields = find_address_field(addr_samples) if len(addr_samples) >= 3 else []

    if not dir_fields:
        warnings.append(
            "Not enough paired experiments for direction field — "
            f"need ≥2 addresses with both states, got {len(pairs)}"
        )
    if profile.addr_group and not addr_fields:
        warnings.append(
            f"Need ≥3 distinct addresses for address field — got {len(addr_samples)}"
        )

    all_fields = sorted(dir_fields + addr_fields, key=lambda f: -f.confidence)

    return ProfileAnalysisResult(
        profile       = profile,
        matched_count = len(matched),
        fields        = all_fields,
        warnings      = warnings,
        missing_states= missing_states,
    )


def detect_profile(
    records: list[ActionRecord],
) -> Optional[ProfileType]:
    """
    Auto-detect the most likely profile type from the label set.
    Tries SWITCH, SIGNAL, RELAY, LOCOMOTIVE in that order.
    Returns the first match with enough records.
    """
    priority = [
        ProfileType.SWITCH,
        ProfileType.SIGNAL,
        ProfileType.RELAY,
        ProfileType.LOCOMOTIVE,
    ]
    for ptype in priority:
        profile = BUILTIN_PROFILES[ptype]
        matched = sum(1 for r in records if profile.compiled.match(r.label))
        threshold = profile.min_addresses * profile.min_states
        if matched >= threshold:
            return ptype
    return None
