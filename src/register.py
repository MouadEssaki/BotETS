"""Inscription automatique : premier groupe avec une place, puis AJOUTER+ et SAUVEGARDER."""

from __future__ import annotations

import re
from dataclasses import dataclass

from loguru import logger
from playwright.sync_api import Page

from src.capacity import parse_capacity
from src.config_loader import AppConfig
from src.navigation import (
    _group_rows_in_options,
    dismiss_full_course_modal,
    is_full_course_modal_visible,
)

_ERROR_RE = re.compile(
    r"conflit|incompatible|impossible|erreur|éche?c|complet|déjà inscrit|deja inscrit",
    re.I,
)
_SUCCESS_RE = re.compile(r"sauvegard|enregistr|réussie|reussie", re.I)


@dataclass
class RegisterResult:
    ok: bool
    message: str


def choose_group_indexes(row_texts: list[str], *, group_mode: str, section: str) -> list[int]:
    """Choisit les lignes à essayer. L'horaire n'entre pas en compte — seulement la place libre."""
    section = section.strip()
    if group_mode == "exact" and section:
        keys = {section, section.zfill(2), section.lstrip("0") or section}
        found: list[int] = []
        for i, text in enumerate(row_texts):
            if any(re.search(rf"\b{re.escape(key)}\b", text) for key in keys if key):
                found.append(i)
        return found

    with_room: list[int] = []
    unknown: list[int] = []
    for i, text in enumerate(row_texts):
        cap = parse_capacity(text)
        if cap is None:
            unknown.append(i)
        elif cap.has_spots:
            with_room.append(i)
    return with_room + unknown


def _dialog_text(page: Page) -> str:
    try:
        dialog = page.get_by_role("dialog").last
        if dialog.is_visible(timeout=800):
            return dialog.inner_text(timeout=1500)
    except Exception:
        return ""
    return ""


def _dismiss_dialog(page: Page, config: AppConfig) -> None:
    label = config.navigation.modal_ok_text or "OK"
    try:
        dialog = page.get_by_role("dialog").last
        if not dialog.is_visible(timeout=500):
            return
        btn = dialog.get_by_role("button", name=re.compile(re.escape(label), re.I)).first
        if btn.is_visible(timeout=500):
            btn.click(timeout=3000)
            return
    except Exception:
        pass
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass


def _click_labeled(page: Page, text: str, timeout_ms: int = 4000) -> bool:
    pattern = re.compile(re.escape(text), re.I)
    for role in ("button", "link"):
        try:
            loc = page.get_by_role(role, name=pattern).first
            if loc.is_visible(timeout=timeout_ms) and loc.is_enabled():
                loc.click(timeout=timeout_ms)
                return True
        except Exception:
            continue
    try:
        loc = page.get_by_text(pattern).first
        if loc.is_visible(timeout=1000):
            loc.click(timeout=timeout_ms)
            return True
    except Exception:
        return False
    return False


def _add_button_enabled(page: Page, config: AppConfig) -> bool:
    text = config.navigation.add_button_text
    try:
        btn = page.get_by_role("button", name=re.compile(re.escape(text), re.I)).first
        if not btn.is_visible(timeout=2500) or not btn.is_enabled():
            return False
        if btn.get_attribute("disabled") is not None:
            return False
        if btn.get_attribute("aria-disabled") == "true":
            return False
        class_name = (btn.get_attribute("class") or "").lower()
        return "disabled" not in class_name
    except Exception:
        return False


def _select_row(row) -> None:
    for sel in ("input[type='radio']", "input[type='checkbox']", "[role='radio']"):
        try:
            loc = row.locator(sel).first
            if loc.count() > 0 and loc.is_visible(timeout=400):
                loc.click(timeout=2000)
                return
        except Exception:
            continue
    row.click(timeout=3000)


def _row_snippet(text: str) -> str:
    line = " ".join(text.split())
    return line[:80] if line else "groupe"


def register_course(page: Page, config: AppConfig) -> RegisterResult:
    """Sélectionne un groupe libre (horaire ignoré), clique AJOUTER+ puis SAUVEGARDER."""
    course = config.course
    nav = config.navigation

    if is_full_course_modal_visible(page, config):
        dismiss_full_course_modal(page, config)
        return RegisterResult(False, "tous les groupes sont complets")

    rows = _group_rows_in_options(page, config)
    try:
        count = min(rows.count(), 30)
    except Exception:
        count = 0

    texts: list[str] = []
    for i in range(count):
        try:
            texts.append(rows.nth(i).inner_text(timeout=2000))
        except Exception:
            texts.append("")

    indexes = choose_group_indexes(texts, group_mode=course.group_mode, section=course.section)
    if course.group_mode == "exact" and course.section.strip() and not indexes:
        return RegisterResult(False, f"groupe {course.section} introuvable")
    if not indexes:
        indexes = [-1]

    last_error = "AJOUTER+ ou SAUVEGARDER introuvable"
    for index in indexes:
        snippet = "sélection courante"
        if index >= 0:
            snippet = _row_snippet(texts[index] if index < len(texts) else "")
            try:
                row = rows.nth(index)
                row.scroll_into_view_if_needed(timeout=2000)
                _select_row(row)
                page.wait_for_timeout(400)
            except Exception as e:
                logger.debug("Sélection groupe échouée ({snippet}): {e}", snippet=snippet, e=e)
                continue

        if is_full_course_modal_visible(page, config):
            dismiss_full_course_modal(page, config)
            last_error = "modal cours complet"
            continue

        if not _add_button_enabled(page, config):
            last_error = f"AJOUTER+ inactif pour {snippet}"
            continue

        if not _click_labeled(page, nav.add_button_text):
            last_error = f"clic AJOUTER+ échoué ({snippet})"
            continue
        logger.info("AJOUTER+ cliqué — {label} / {snippet}", label=course.label, snippet=snippet)
        page.wait_for_timeout(1000)

        dialog = _dialog_text(page)
        if dialog and _ERROR_RE.search(dialog):
            logger.info("Groupe refusé ({snippet}): {dialog}", snippet=snippet, dialog=dialog[:160])
            _dismiss_dialog(page, config)
            last_error = f"refusé: {snippet}"
            continue

        if not _click_labeled(page, nav.save_button_text, timeout_ms=6000):
            last_error = f"SAUVEGARDER introuvable après {snippet}"
            continue
        logger.info("SAUVEGARDER cliqué — {label}", label=course.label)
        page.wait_for_timeout(1200)

        dialog = _dialog_text(page)
        if dialog and _ERROR_RE.search(dialog) and not _SUCCESS_RE.search(dialog):
            logger.info("Sauvegarde refusée: {dialog}", dialog=dialog[:160])
            _dismiss_dialog(page, config)
            last_error = f"sauvegarde refusée ({snippet})"
            continue
        if dialog:
            _dismiss_dialog(page, config)

        return RegisterResult(True, f"inscrit via {snippet}")

    return RegisterResult(False, last_error)
