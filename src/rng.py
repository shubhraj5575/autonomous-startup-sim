"""Deterministic RNG management.

Each subsystem draws from its own named stream derived from the master seed so
that adding/removing systems does not shift other streams' sequences.
"""
from __future__ import annotations

import hashlib
import random


class RngManager:
    def __init__(self, master_seed: int):
        self.master_seed = int(master_seed)
        self._streams: dict[str, random.Random] = {}

    def stream(self, name: str) -> random.Random:
        if name not in self._streams:
            h = hashlib.sha256(f"{self.master_seed}:{name}".encode()).digest()
            seed_int = int.from_bytes(h[:8], "big")
            self._streams[name] = random.Random(seed_int)
        return self._streams[name]

    @property
    def state_fingerprint(self) -> str:
        """Hash of all stream states - used for determinism tests."""
        parts = []
        for k in sorted(self._streams):
            s = self._streams[k].getstate()
            parts.append(k + ":" + ",".join(map(str, s[1])))
        blob = "|".join(parts)
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def fmt_inr(x: float) -> str:
    """Indian-style currency formatting: lakh / crore."""
    x = float(x)
    sign = "-" if x < 0 else ""
    x = abs(x)
    if x >= 1_00_00_000:
        return f"{sign}\u20b9{x/1_00_00_000:.2f}Cr"
    if x >= 1_00_000:
        return f"{sign}\u20b9{x/1_00_000:.2f}L"
    return f"{sign}\u20b9{x:,.0f}"
