"""Tests unitaires — parse TAILLE/MAX."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.capacity import parse_capacity


def test_parse_capacity_standard():
    cap = parse_capacity("GROUPE 01  Lun 18:00  21 / 40")
    assert cap is not None
    assert cap.current == 21
    assert cap.maximum == 40
    assert cap.has_spots is True


def test_parse_capacity_full():
    cap = parse_capacity("40 / 40")
    assert cap is not None
    assert cap.has_spots is False


def test_parse_capacity_none():
    assert parse_capacity("aucun nombre") is None


if __name__ == "__main__":
    test_parse_capacity_standard()
    test_parse_capacity_full()
    test_parse_capacity_none()
    print("test_capacity_parse OK")
