"""Tests unitaires — chargement configuration."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.config_loader import load_config


def test_load_config_defaults():
    config = load_config(_ROOT / "config.yaml")
    assert config.course.sigle
    assert config.delays.min_seconds >= 10
    assert config.delays.max_seconds >= config.delays.min_seconds
    assert config.login.manual_wait_seconds >= 60
    assert "cheminot" in config.portal_url.lower()
    assert config.navigation.horaire_url.endswith("/horaire")
    assert config.course.sigle == "LOG200"
    assert config.course.group_mode in ("any", "first", "exact")


if __name__ == "__main__":
    test_load_config_defaults()
    print("test_config OK")
