"""Tests — sigles Cheminot et bots choisis dans l'interface."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.catalog import extract_sigles, load_launcher_state, save_launcher_state
from src.config_loader import config_with_bots, load_config


def test_extract_sigles_keeps_order_and_dedupes():
    text = "Graphe LOG200 puis gti350 et encore LOG200."
    assert extract_sigles(text) == ["LOG200", "GTI350"]


def test_config_with_bots_replaces_courses():
    config = load_config(_ROOT / "config.yaml")
    updated = config_with_bots(config, [("log200", True), ("GTI350", False), ("log200", False)])
    assert [c.sigle for c in updated.courses_to_watch()] == ["LOG200", "GTI350"]
    assert updated.courses[0].auto_register is True
    assert updated.courses[1].auto_register is False
    assert updated.browser.multi_bot is True


def test_launcher_state_roundtrip(tmp_path=None):
    path = _ROOT / "logs" / "_launcher_test.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    save_launcher_state(path, ["LOG200", "GTI350"], [("LOG200", True)])
    sigles, bots = load_launcher_state(path)
    path.unlink(missing_ok=True)
    assert sigles == ["LOG200", "GTI350"]
    assert bots == [("LOG200", True)]


def test_offered_sigles_skips_taken_path_courses():
    from src.catalog import offered_sigles, taken_sigles

    text = """
    Cours d'intégration
    INF120
    Cours obligatoire
    MAT115
    Cours de concentration
    GPA666
    Cours offerts à la prochaine session
    LOG200
    GTI350
    MAT115
    GPA666
    Cours hors-cheminement
    ATE085
    """
    assert taken_sigles(text) == ["INF120", "MAT115"]
    assert offered_sigles(text) == ["LOG200", "GTI350", "GPA666"]


def test_offered_sigles_empty_without_section():
    from src.catalog import offered_sigles

    assert offered_sigles("INF120 MAT115 LOG200") == []


if __name__ == "__main__":
    test_extract_sigles_keeps_order_and_dedupes()
    test_config_with_bots_replaces_courses()
    test_launcher_state_roundtrip()
    test_offered_sigles_skips_taken_path_courses()
    test_offered_sigles_empty_without_section()
    print("test_catalog OK")
