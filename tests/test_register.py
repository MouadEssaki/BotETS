"""Tests — choix de groupe et isolation multi-bot."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.config_loader import isolate_course, load_config
from src.register import choose_group_indexes


def test_choose_group_ignores_schedule_and_skips_full():
    rows = [
        "01 Lundi 9h 40 / 40",
        "02 Mardi 13h 21 / 40",
        "03 Jeudi 8h 10 / 40",
    ]
    indexes = choose_group_indexes(rows, group_mode="any", section="")
    assert indexes[0] == 1
    assert 0 not in indexes
    assert indexes == [1, 2]


def test_choose_exact_section():
    rows = ["Groupe 01 10 / 40", "Groupe 02 10 / 40"]
    assert choose_group_indexes(rows, group_mode="exact", section="2") == [1]


def test_isolate_worker_is_one_course():
    config = load_config(_ROOT / "config.yaml")
    one = isolate_course(config, "gti350", as_worker=True)
    assert one.course.sigle == "GTI350"
    assert [c.sigle for c in one.courses] == ["GTI350"]
    assert one.is_worker is True
    assert one.navigation.mode == "auto"
    assert not one.navigation.uses_manual_clicks()
    assert one.login.storage_state_path == "storage_state_GTI350.json"
    assert one.course.auto_register is False


def test_isolate_cli_keeps_navigation_mode():
    config = load_config(_ROOT / "config.yaml")
    one = isolate_course(config, "LOG200", as_worker=False)
    assert one.is_worker is False
    assert one.navigation.mode == config.navigation.mode
    assert one.course.auto_register is True
    assert one.login.storage_state_path == config.login.storage_state_path


def test_unknown_course():
    config = load_config(_ROOT / "config.yaml")
    try:
        isolate_course(config, "ZZZ999", as_worker=True)
    except ValueError as e:
        assert "ZZZ999" in str(e)
        return
    raise AssertionError("cours inconnu aurait dû lever ValueError")


if __name__ == "__main__":
    test_choose_group_ignores_schedule_and_skips_full()
    test_choose_exact_section()
    test_isolate_worker_is_one_course()
    test_isolate_cli_keeps_navigation_mode()
    test_unknown_course()
    print("test_register OK")
