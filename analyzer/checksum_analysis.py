"""
Checksum candidate finder.

Tests several common algorithms against all observed unique packets and
reports which (algorithm, byte_position) pairs explain the last (or any)
byte as a checksum of the remaining bytes.

All results are presented as candidates with a match percentage.
A 100% match is strong evidence; < 100% means the hypothesis is wrong
or the algorithm covers only part of the packet.
"""

from __future__ import annotations

from typing import Callable, Sequence

from analyzer.models import ChecksumCandidate


# ---- CRC-8 tables --------------------------------------------------------

def _make_crc8_table(poly: int) -> list[int]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ poly) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
        table.append(crc)
    return table


_CRC8_TABLE       = _make_crc8_table(0x07)   # CRC-8 / SMBUS
_CRC8_MAXIM_TABLE = _make_crc8_table(0x31)   # CRC-8 / MAXIM (1-Wire)


def _crc8(data: bytes, table: list[int]) -> int:
    crc = 0x00
    for b in data:
        crc = table[crc ^ b]
    return crc


# ---- Algorithm implementations -------------------------------------------

def _xor(data: bytes) -> int:
    result = 0
    for b in data:
        result ^= b
    return result & 0xFF


def _sum8(data: bytes) -> int:
    return sum(data) & 0xFF


def _sum8_neg(data: bytes) -> int:
    # One's complement (bitwise NOT of sum)
    return (~sum(data)) & 0xFF


def _sum8_comp2(data: bytes) -> int:
    # Two's complement (negate sum)
    return (-(sum(data))) & 0xFF


def _crc8_smbus(data: bytes) -> int:
    return _crc8(data, _CRC8_TABLE)


def _crc8_maxim(data: bytes) -> int:
    return _crc8(data, _CRC8_MAXIM_TABLE)


# Map name → function
_ALGORITHMS: dict[str, Callable[[bytes], int]] = {
    "xor":       _xor,
    "sum8":      _sum8,
    "sum8_neg":  _sum8_neg,
    "sum8_comp2": _sum8_comp2,
    "crc8":      _crc8_smbus,
    "crc8_maxim": _crc8_maxim,
}


# ---- Main analysis -------------------------------------------------------

def find_checksum_candidates(
    packets: Sequence[tuple[bytes, int]],
    algorithms: list[str] | None = None,
    min_match_pct: float = 50.0,
) -> list[ChecksumCandidate]:
    """
    Try each algorithm × each byte position as checksum target.

    For each combination we test whether the checksum of all OTHER bytes
    equals the byte at `position`.

    `packets` — list of (data_bytes, count) weighted by count.
    Returns candidates sorted by match_pct descending.
    """
    if not packets:
        return []

    alg_names = algorithms or list(_ALGORITHMS.keys())
    alg_fns   = {name: _ALGORITHMS[name] for name in alg_names if name in _ALGORITHMS}

    max_len = max(len(data) for data, _ in packets)
    total   = sum(cnt for _, cnt in packets)

    candidates: list[ChecksumCandidate] = []

    for pos in range(max_len):
        for alg_name, alg_fn in alg_fns.items():
            match_count = 0
            for data, cnt in packets:
                if pos >= len(data):
                    continue
                # Compute checksum over all bytes EXCEPT the one at `pos`
                payload     = bytes(b for i, b in enumerate(data) if i != pos)
                expected    = alg_fn(payload)
                if expected == data[pos]:
                    match_count += cnt

            match_pct = 100.0 * match_count / total if total else 0.0
            if match_pct >= min_match_pct:
                candidates.append(ChecksumCandidate(
                    algorithm      = alg_name,
                    byte_position  = pos,
                    match_count    = match_count,
                    total_count    = total,
                ))

    candidates.sort(key=lambda c: c.match_pct, reverse=True)
    return candidates


def verify_checksum(data: bytes, position: int, algorithm: str) -> bool:
    """Single-packet checksum verification for interactive use."""
    fn = _ALGORITHMS.get(algorithm)
    if fn is None or position >= len(data):
        return False
    payload = bytes(b for i, b in enumerate(data) if i != position)
    return fn(payload) == data[position]
