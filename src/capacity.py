"""Parse TAILLE/MAX (ex. « 21 / 40 ») — informatif uniquement."""

from __future__ import annotations

import re
from dataclasses import dataclass

_CAPACITY_RE = re.compile(r"(\d+)\s*/\s*(\d+)")


@dataclass
class Capacity:
    current: int
    maximum: int

    @property
    def has_spots(self) -> bool:
        return self.current < self.maximum


def parse_capacity(text: str) -> Capacity | None:
    """Extrait la première occurrence « current / max » dans le texte."""
    match = _CAPACITY_RE.search(text)
    if not match:
        return None
    return Capacity(current=int(match.group(1)), maximum=int(match.group(2)))
