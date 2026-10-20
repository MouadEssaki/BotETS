"""Tests — configuration navigation et group_mode."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.config_loader import load_config
from src.navigation import path_contains_route


def test_navigation_config_loaded():
    config = load_config(_ROOT / "config.yaml")
    nav = config.navigation
    assert nav.home_url == "https://cheminotn.etsmtl.ca"
    assert "/horaire" in nav.horaire_url
    assert nav.inscription_tab_selector == "" or isinstance(nav.inscription_tab_selector, str)


def test_group_mode_any_without_section():
    config = load_config(_ROOT / "config.yaml")
    assert config.course.sigle == "LOG200"
    assert config.course.section == ""
    assert config.course.group_mode == "any"
    assert config.course.wants_any_group()
    assert not config.course.has_exact_section()
    assert config.course.label == "LOG200"
    assert len(config.courses_to_watch()) >= 1
    assert config.browser.keep_open is True


def test_auto_navigation_mode():
    config = load_config(_ROOT / "config.yaml")
    assert not config.navigation.uses_manual_clicks()
    assert config.navigation.mode == "auto"


def test_inscription_url_is_the_path_not_the_hash():
    assert path_contains_route("https://cheminotn.etsmtl.ca/inscription", "inscription")
    assert path_contains_route("https://cheminotn.etsmtl.ca/inscription?x=1", "inscription")
    assert not path_contains_route("https://cheminotn.etsmtl.ca#inscription", "inscription")
    assert not path_contains_route("https://cheminotn.etsmtl.ca/#/inscription", "inscription")
    assert not path_contains_route("https://cheminotn.etsmtl.ca/consultation", "inscription")


if __name__ == "__main__":
    test_navigation_config_loaded()
    test_group_mode_any_without_section()
    test_auto_navigation_mode()
    test_inscription_url_is_the_path_not_the_hash()
    print("test_navigation_config OK")
