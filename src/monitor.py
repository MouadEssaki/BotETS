"""Boucle de surveillance : navigation Cheminot, détection AJOUTER+ / groupes."""

from __future__ import annotations

import random
import re
import time
from dataclasses import replace
from enum import Enum
from pathlib import Path

from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from src import alarm
from src.notify import notify_place_available
from src.register import register_course
from src.capacity import parse_capacity
from src.config_loader import AppConfig
from src.navigation import (
    NavigationOutcome,
    NavigationResult,
    _group_rows_in_options,
    cycle_via_clicks,
    dismiss_full_course_modal,
    ensure_horaire_context,
    is_full_course_modal_visible,
    is_on_horaire_page,
)
from src.session import ensure_logged_in, is_logged_in
from src.timeutil import local_timestamp


class AvailabilityStatus(Enum):
    FULL = "full"
    AVAILABLE = "available"
    UNKNOWN = "unknown"


def _group_row_locator(page: Page, config: AppConfig):
    course = config.course
    rows = _group_rows_in_options(page, config)

    if course.has_exact_section():
        section = course.section.zfill(2)
        if config.selectors.course_row:
            return page.locator(config.selectors.course_row).first
        if config.navigation.group_row_selector:
            return rows.filter(has_text=re.compile(rf"\b{re.escape(section)}\b")).first
        for pattern in (
            f"tr:has-text('{section}')",
            f"[role='row']:has-text('{section}')",
        ):
            loc = page.locator(pattern).first
            try:
                if loc.count() > 0 and loc.is_visible(timeout=1500):
                    return loc
            except Exception:
                continue
        return rows.filter(has_text=re.compile(rf"\b{re.escape(section)}\b")).first

    try:
        if rows.count() > 0:
            return rows.first
    except Exception:
        pass
    return page.locator("body")


_CAPACITY_IN_ROW = re.compile(r"\d+\s*/\s*\d+")


def _add_button_locator(page: Page, config: AppConfig):
    nav = config.navigation
    text = nav.add_button_text
    return page.get_by_role("button", name=re.compile(rf"{re.escape(text)}", re.I)).first


def _is_add_button_enabled(page: Page, config: AppConfig) -> bool:
    try:
        btn = _add_button_locator(page, config)
        if not btn.is_visible(timeout=3000):
            return False
        if not btn.is_enabled():
            return False
        disabled = btn.get_attribute("disabled")
        aria_disabled = btn.get_attribute("aria-disabled")
        if disabled is not None or aria_disabled == "true":
            return False
        class_name = btn.get_attribute("class") or ""
        if "disabled" in class_name.lower():
            return False
        return True
    except Exception:
        return False


def _has_no_group_message(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    try:
        return page.get_by_text(nav.no_group_text, exact=False).first.is_visible(timeout=2000)
    except Exception:
        return False


def _has_visible_group_row(page: Page, config: AppConfig) -> bool:
    if _has_no_group_message(page, config):
        return False

    rows = _group_rows_in_options(page, config)
    try:
        count = rows.count()
    except Exception:
        count = 0

    if count > 0:
        for i in range(min(count, 5)):
            try:
                text = rows.nth(i).inner_text(timeout=2000)
                if _CAPACITY_IN_ROW.search(text) or config.course.wants_any_group():
                    return rows.nth(i).is_visible(timeout=1000)
            except Exception:
                continue

    row = _group_row_locator(page, config)
    try:
        if not row.is_visible(timeout=2000):
            return False
        text = row.inner_text(timeout=3000)
        if _CAPACITY_IN_ROW.search(text):
            return True
        if config.course.wants_any_group() and text.strip():
            return "GROUPE" in text.upper() or bool(re.search(r"\b0?\d+\b", text))
    except Exception:
        pass
    return False


def check_availability_horaire(page: Page, config: AppConfig) -> AvailabilityStatus:
    """Critère principal : AJOUTER+ cliquable et groupe(s) visible(s)."""
    if is_full_course_modal_visible(page, config):
        dismiss_full_course_modal(page, config)
        return AvailabilityStatus.FULL

    if _has_no_group_message(page, config):
        return AvailabilityStatus.FULL

    if config.selectors.status_available:
        try:
            loc = page.locator(config.selectors.status_available).first
            if loc.is_visible(timeout=2000) and loc.is_enabled():
                return AvailabilityStatus.AVAILABLE
        except Exception:
            pass

    if config.selectors.status_full:
        try:
            loc = page.locator(config.selectors.status_full).first
            if loc.is_visible(timeout=2000):
                return AvailabilityStatus.FULL
        except Exception:
            pass

    row = _group_row_locator(page, config)
    try:
        cap = parse_capacity(row.inner_text(timeout=3000))
        if cap:
            logger.debug(
                "Capacité {label}: {cur}/{max}",
                label=config.course.label,
                cur=cap.current,
                max=cap.maximum,
            )
    except Exception:
        pass

    add_enabled = _is_add_button_enabled(page, config)
    has_group = _has_visible_group_row(page, config)

    if add_enabled and has_group:
        return AvailabilityStatus.AVAILABLE

    if add_enabled and not _has_no_group_message(page, config):
        return AvailabilityStatus.AVAILABLE

    if _has_no_group_message(page, config) or not add_enabled:
        return AvailabilityStatus.FULL

    return AvailabilityStatus.UNKNOWN


def _random_delay(config: AppConfig) -> float:
    base = random.uniform(config.delays.min_seconds, config.delays.max_seconds)
    jitter = random.uniform(config.delays.jitter_min_seconds, config.delays.jitter_max_seconds)
    return base + jitter


def _screenshot(page: Page, config: AppConfig, name: str) -> Path:
    path = config.screenshots_dir() / f"{name}_{int(time.time())}.png"
    page.screenshot(path=str(path), full_page=True)
    logger.info("Capture: {path}", path=path)
    return path


def _run_check_cycle(page: Page, config: AppConfig) -> NavigationResult:
    """Exécute un cycle de vérification selon le mode configuré."""
    if config.navigation.uses_manual_clicks():
        return cycle_via_clicks(page, config)
    return ensure_horaire_context(page, config)


def run_monitor_loop(
    page: Page,
    config: AppConfig,
    browser_session,
    iteration_callback=None,
) -> None:
    """Boucle principale — un ou plusieurs cours, navigateur reste ouvert."""
    manual_login = browser_session.get_manual_login_callback()
    watched = config.courses_to_watch()
    labels = ", ".join(c.label for c in watched)
    manual = config.navigation.uses_manual_clicks()

    logger.info("Démarrage surveillance — cours: {labels}", labels=labels)
    if manual and not config.is_worker:
        logger.info(
            "Mode manuel : pause initiale, puis pour chaque cours : inscription → sigle → horaire"
        )
        browser_session.wait_for_manual_navigation(page)
    elif manual:
        logger.info(
            "Bot dédié {label} : inscription → {sigle} → horaire",
            label=config.course.label,
            sigle=config.course.sigle,
        )
    else:
        logger.info(
            "Mode auto : accueil → consultation → inscription → {sigle} → horaire",
            sigle=config.course.sigle,
        )

    ensure_logged_in(page, config, manual_login)

    if manual and not config.is_worker:
        nav_result = NavigationResult(
            NavigationOutcome.HORAIRE_READY,
            "Prêt après navigation manuelle",
        )
    else:
        nav_result = ensure_horaire_context(page, config)
        if nav_result.outcome == NavigationOutcome.FAILED:
            logger.error("Navigation initiale échouée: {msg}", msg=nav_result.message)
            _screenshot(page, config, "navigation_failed")

    iteration = 0
    registered: set[str] = set()
    while True:
        iteration += 1
        ts = local_timestamp(config.timezone)
        logger.info("[{ts}] Vérification #{n} — {count} cours", ts=ts, n=iteration, count=len(watched))

        if not is_logged_in(page, config):
            _screenshot(page, config, "session_expired")
            ensure_logged_in(page, config, manual_login)
            browser_session.save_storage_state()
            if manual:
                logger.warning("Reconnectez-vous manuellement si besoin — pause 45s")
                time.sleep(45)

        for idx, course in enumerate(watched):
            if course.sigle in registered:
                continue
            course_cfg = replace(config, course=course)
            logger.info("--- Cours {i}/{total} : {label} ---", i=idx + 1, total=len(watched), label=course.label)

            nav_result = _run_check_cycle(page, course_cfg)
            browser_session.dismiss_popup_if_configured(page)

            if nav_result.outcome == NavigationOutcome.COURSE_FULL_MODAL:
                status = AvailabilityStatus.FULL
            elif nav_result.outcome == NavigationOutcome.FAILED and not is_on_horaire_page(page, course_cfg):
                status = AvailabilityStatus.UNKNOWN
            else:
                status = check_availability_horaire(page, course_cfg)

            if iteration_callback:
                iteration_callback(iteration, status)

            if status == AvailabilityStatus.AVAILABLE:
                logger.success(
                    "PLACE DISPONIBLE (AJOUTER+ actif) pour {label} à {ts}!",
                    label=course.label,
                    ts=ts,
                )
                _screenshot(page, course_cfg, f"place_available_{course.sigle}")
                if course.auto_register:
                    result = register_course(page, course_cfg)
                    if result.ok:
                        logger.success(
                            "Inscription envoyée pour {label}: {msg}",
                            label=course.label,
                            msg=result.message,
                        )
                        _screenshot(page, course_cfg, f"registered_{course.sigle}")
                        alarm.trigger(config.alarm)
                        notify_place_available(
                            course.label,
                            f"Inscription envoyée ({result.message}) à {ts}. Vérifiez Cheminot.",
                            config,
                        )
                        registered.add(course.sigle)
                        if (
                            config.is_worker
                            or config.browser.stop_on_alarm
                            or len(registered) == len(watched)
                        ):
                            logger.info("Cours {label} inscrit — arrêt de ce bot.", label=course.label)
                            return
                    else:
                        logger.warning(
                            "Inscription auto échouée pour {label}: {msg}",
                            label=course.label,
                            msg=result.message,
                        )
                        _screenshot(page, course_cfg, f"register_failed_{course.sigle}")
                        alarm.trigger(config.alarm)
                        notify_place_available(
                            course.label,
                            f"Place ouverte pour {course.label}, inscription auto échouée ({result.message}). "
                            f"Inscrivez-vous sur le PC ({ts}).",
                            config,
                        )
                else:
                    alarm.trigger(config.alarm)
                    notify_place_available(
                        course.label,
                        f"AJOUTER+ actif sur Cheminot ({ts}). Inscrivez-vous sur le PC.",
                        config,
                    )
                    logger.info(
                        "Inscrivez-vous manuellement pour {label}. Le navigateur reste ouvert.",
                        label=course.label,
                    )
                    if config.browser.stop_on_alarm:
                        logger.info("stop_on_alarm=true — arrêt du script.")
                        return
            elif status == AvailabilityStatus.UNKNOWN:
                logger.warning("Statut indéterminé pour {label}", label=course.label)
                _screenshot(page, course_cfg, f"unknown_{course.sigle}")
            else:
                logger.info("Cours {label} : pas de place actionnable ({status})", label=course.label, status=status.value)

            if idx < len(watched) - 1:
                page.wait_for_timeout(800)

        delay = _random_delay(config)
        logger.info(
            "Fin du cycle — prochaine ronde dans {delay:.0f}s (~{min:.1f} min)",
            delay=delay,
            min=delay / 60,
        )
        time.sleep(delay)
