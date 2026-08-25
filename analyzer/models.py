"""
Shared data structures.  No analysis logic here — pure containers.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RawEdge:
    """One edge captured by Arduino in RAW mode."""
    timestamp_us: int
    duration_us:  int
    level:        int   # 0 or 1 — pin state AFTER the edge


@dataclass
class RawPacket:
    """
    A sequence of bytes extracted from raw edges by the parser.
    The parser may be wrong — treat this as a hypothesis, not fact.
    """
    timestamp_us: int          # timestamp of the first edge in this packet
    data: bytes
    edge_count: int = 0        # how many raw edges contributed


@dataclass
class PacketRecord:
    """Statistics entry for one unique packet payload."""
    data:       bytes
    count:      int      = 0
    first_seen: int      = 0   # timestamp_us
    last_seen:  int      = 0   # timestamp_us

    @property
    def hex_str(self) -> str:
        return " ".join(f"{b:02X}" for b in self.data)


@dataclass
class ActionRecord:
    """One labelled experiment recorded by the user."""
    label:        str
    description:  str          = ""
    # Packets seen in the baseline window (before the action)
    baseline:     list[bytes]  = field(default_factory=list)
    # Packets seen in the action window (after the button press)
    action_pkts:  list[bytes]  = field(default_factory=list)
    # Dominant packet in baseline (most frequent)
    baseline_dominant: Optional[bytes] = None
    # Dominant packet in action window
    action_dominant:   Optional[bytes] = None
    timestamp:    int          = 0
    # Optional profile tag (e.g. "switch", "signal", "relay", "locomotive")
    profile_type: str          = ""


@dataclass
class ByteStats:
    """Statistics for one byte position across all packets."""
    position:        int
    value_counts:    dict[int, int]  = field(default_factory=dict)
    transition_counts: dict[tuple[int, int], int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.value_counts.values())

    @property
    def unique_count(self) -> int:
        return len(self.value_counts)

    @property
    def is_constant(self) -> bool:
        return self.unique_count <= 1

    @property
    def variability_label(self) -> str:
        if self.unique_count <= 1:
            return "CONSTANT"
        if self.total == 0:
            return "CONSTANT"
        # Fraction of packets covered by the single most-common value.
        dominant_pct = max(self.value_counts.values()) / self.total
        if dominant_pct >= 0.90:
            return "MOSTLY_CONSTANT"
        return "VARIABLE"


@dataclass
class BitStats:
    """Statistics for one bit inside one byte position."""
    byte_pos: int
    bit_pos:  int       # 0 = LSB
    count_0:  int = 0
    count_1:  int = 0
    transitions: int = 0   # number of times the bit value changed between consecutive packets

    @property
    def total(self) -> int:
        return self.count_0 + self.count_1

    @property
    def pct_1(self) -> float:
        return 100.0 * self.count_1 / self.total if self.total else 0.0

    @property
    def pct_0(self) -> float:
        return 100.0 * self.count_0 / self.total if self.total else 0.0

    @property
    def transition_pct(self) -> float:
        return 100.0 * self.transitions / max(self.total - 1, 1)


@dataclass
class ChecksumCandidate:
    algorithm: str
    byte_position: int
    match_count: int
    total_count: int

    @property
    def match_pct(self) -> float:
        return 100.0 * self.match_count / self.total_count if self.total_count else 0.0


@dataclass
class CorrelationCandidate:
    """
    A hypothesis that a range of bits in a byte correlates with
    a numeric value from labelled actions.
    """
    label:        str           # e.g. "speed"
    byte_pos:     int
    bit_high:     int           # MSB of the bit range (inclusive)
    bit_low:      int           # LSB of the bit range (inclusive)
    correlation:  float         # Pearson r or rank correlation
    confidence:   float         # 0.0 – 1.0
    note:         str = ""
