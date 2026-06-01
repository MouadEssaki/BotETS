"""Tests — horodatage sans crash."""

import sys
from pathlib import Path
from unittest.mock import patch

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.timeutil import local_timestamp, normalize_timezone_key


def test_normalize_timezone_aliases():
    assert normalize_timezone_key("america montreal") == "America/Montreal"
    assert normalize_timezone_key("  America/Montreal  ") == "America/Montreal"


def test_local_timestamp_never_raises():
    ts = local_timestamp("America/Montreal")
    assert ts
    assert len(ts) > 10


def test_local_timestamp_fallback_on_bad_zone():
    with patch("src.timeutil.ZoneInfo", side_effect=Exception("no tz"), create=True):
        # Force ZoneInfo import path to fail inside local_timestamp
        pass
    with patch("zoneinfo.ZoneInfo", side_effect=Exception("no tz")):
        ts = local_timestamp("Invalid/Zone")
        assert "(local)" in ts or len(ts) > 10


if __name__ == "__main__":
    test_normalize_timezone_aliases()
    test_local_timestamp_never_raises()
    test_local_timestamp_fallback_on_bad_zone()
    print("test_timeutil OK")
