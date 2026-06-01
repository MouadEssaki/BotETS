"""Navigation Cheminot : accueil → consultation → inscription → horaire."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from urllib.parse import urlparse
from enum import Enum
from pathlib import Path

from loguru import logger
from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

from src.config_loader import AppConfig


class NavigationOutcome(Enum):
    HORAIRE_READY = "horaire_ready"
    COURSE_FULL_MODAL = "course_full_modal"
    FAILED = "failed"


@dataclass
class NavigationResult:
    outcome: NavigationOutcome
    message: str = ""


def _nav_screenshot(page: Page, config: AppConfig, name: str) -> Path | None:
    try:
        path = config.screenshots_dir() / f"{name}_{int(time.time())}.png"
        page.screenshot(path=str(path), full_page=True)
        logger.info("Capture navigation: {path}", path=path)
        return path
    except Exception as e:
        logger.warning("Screenshot échoué ({name}): {e}", name=name, e=e)
        return None


def _url_matches(page: Page, *fragments: str) -> bool:
    url = page.url.lower()
    return any(f.lower().lstrip("/") in url for f in fragments)


def _wait_url_contains(page: Page, fragment: str, timeout_ms: int = 30000) -> bool:
    """Attente URL via Playwright (fiable pour SPA) puis polling de secours."""
    pattern = re.compile(re.escape(fragment.lstrip("/")), re.I)
    try:
        page.wait_for_url(pattern, timeout=timeout_ms, wait_until="commit")
        return True
    except PlaywrightTimeout:
        pass
    deadline = time.time() + timeout_ms / 1000
    while time.time() < deadline:
        if fragment.lower() in page.url.lower():
            return True
        time.sleep(0.25)
    return _url_matches(page, fragment)


def _wait_for_spa_route(page: Page, route: str, timeout_ms: int = 60000) -> bool:
    """Attend que l'URL contienne la route (consultation, inscription, horaire)."""
    return _wait_url_contains(page, route, timeout_ms)


def _is_in_portal_session(page: Page, config: AppConfig) -> bool:
    """Déjà dans le flux Automne (consultation / inscription / horaire)."""
    if _url_matches(page, "consultation", "inscription", "horaire"):
        return True
    nav = config.navigation
    try:
        if page.get_by_text(re.compile(r"CONSULTATION\s+AUTOMNE", re.I)).first.is_visible(timeout=1500):
            return True
        if page.get_by_text(nav.inscription_tab_text, exact=False).first.is_visible(timeout=1500):
            return True
    except Exception:
        pass
    return False


def _goto_route(page: Page, base: str, route: str) -> None:
    """Navigation directe vers une route Cheminot (SPA)."""
    route = route.strip("/")
    for url in (
        f"{base.rstrip('/')}/{route}",
        f"{base.rstrip('/')}#{route}",
        f"{base.rstrip('/')}/#/{route}",
    ):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=25000)
            if _url_matches(page, route):
                logger.debug("Route {route} atteinte via {url}", route=route, url=url)
                return
        except Exception as e:
            logger.debug("goto {url} échoué: {e}", url=url, e=e)
    page.evaluate(
        """(path) => {
            const base = window.location.origin;
            if (window.history && window.history.pushState) {
                window.history.pushState({}, '', base + path);
                window.dispatchEvent(new PopStateEvent('popstate'));
            } else {
                window.location.assign(base + path);
            }
        }""",
        f"/{route}",
    )
    page.wait_for_timeout(1500)


def _click_first_visible(page: Page, locator_str: str, timeout_ms: int = 8000) -> bool:
    try:
        loc = page.locator(locator_str).first
        loc.wait_for(state="visible", timeout=timeout_ms)
        loc.click(timeout=timeout_ms)
        return True
    except Exception as e:
        logger.debug("Clic échoué ({loc}): {e}", loc=locator_str, e=e)
        return False


def _click_by_text(page: Page, text: str, exact: bool = False) -> bool:
    try:
        loc = page.get_by_text(text, exact=exact).first
        loc.wait_for(state="visible", timeout=8000)
        loc.click(timeout=8000)
        return True
    except Exception:
        return False


def _click_role_button(page: Page, name_pattern: str) -> bool:
    try:
        btn = page.get_by_role("button", name=re.compile(name_pattern, re.I)).first
        btn.wait_for(state="visible", timeout=8000)
        btn.click(timeout=8000)
        return True
    except Exception:
        return False


def dismiss_full_course_modal(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    try:
        modal = page.get_by_text(nav.full_modal_text, exact=False).first
        if not modal.is_visible(timeout=2000):
            return False
        logger.info("Modal cours complet détecté")
        ok = page.get_by_role("button", name=re.compile(nav.modal_ok_text, re.I)).first
        if ok.is_visible(timeout=2000):
            ok.click()
        elif _click_by_text(page, nav.modal_ok_text, exact=True):
            pass
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return True
    except Exception:
        return False


def is_full_course_modal_visible(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    try:
        return page.get_by_text(nav.full_modal_text, exact=False).first.is_visible(timeout=1500)
    except Exception:
        return False


def _options_panel_locator(page: Page, config: AppConfig):
    nav = config.navigation
    return page.get_by_text(nav.options_panel_text, exact=False).first.locator(
        "xpath=ancestor::*[self::div or self::section][1]"
    )


def _group_rows_in_options(page: Page, config: AppConfig):
    """Lignes du tableau des groupes sous le panneau options."""
    nav = config.navigation
    if nav.group_row_selector:
        return page.locator(nav.group_row_selector)
    try:
        panel = _options_panel_locator(page, config)
        rows = panel.locator("tr").filter(has_text=re.compile(r"\d+\s*/\s*\d+"))
        if rows.count() > 0:
            return rows
        return panel.locator("tr").filter(has_text=re.compile(r"^\s*0?\d+\s*$|GROUPE", re.I))
    except Exception:
        return page.locator("tr").filter(has_text=re.compile(r"\d+\s*/\s*\d+"))


def _click_session_select_button(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    btn_re = re.compile(nav.select_session_button_text.replace(" ", r"\s+"), re.I)

    if nav.select_session_button:
        if _click_first_visible(page, nav.select_session_button):
            return True

    card_patterns = [
        nav.session_card_text,
        r"\+?\s*Inscription et consultation",
        r"Inscription et consultation",
    ]
    for card_pat in card_patterns:
        try:
            card = page.locator("div, section, article").filter(
                has_text=re.compile(card_pat, re.I)
            ).first
            card.wait_for(state="visible", timeout=8000)
            btn = card.get_by_role("button", name=btn_re).first
            btn.click(timeout=10000)
            logger.debug("Clic session via carte: {pat}", pat=card_pat)
            return True
        except Exception:
            continue

    try:
        buttons = page.get_by_role("button", name=btn_re)
        count = buttons.count()
        for i in range(count):
            btn = buttons.nth(i)
            if btn.is_visible(timeout=2000):
                btn.click(timeout=10000)
                logger.debug("Clic session bouton index {i}", i=i)
                return True
    except Exception:
        pass

    return _click_role_button(page, nav.select_session_button_text)


def _step_select_session(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    logger.info("Étape 1 — Sélection session inscription/consultation")
    logger.info("URL avant étape 1: {url}", url=page.url)

    if _is_in_portal_session(page, config):
        logger.info("Étape 1 ignorée — déjà dans le portail session ({url})", url=page.url)
        return True

    page.goto(nav.home_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_load_state("networkidle", timeout=30000)

    if not _click_session_select_button(page, config):
        if _url_matches(page, "consultation"):
            logger.info("Étape 1 OK — déjà sur consultation sans clic")
            return True
        _nav_screenshot(page, config, "nav_step1_failed")
        logger.error("Étape 1 — bouton session introuvable")
        return False

    page.wait_for_load_state("networkidle", timeout=30000)
    if _wait_for_spa_route(page, "consultation", 60000):
        logger.info("Étape 1 OK — URL: {url}", url=page.url)
        return True

    # Re-vérification : SPA parfois plus lente que wait_for_url
    page.wait_for_timeout(2000)
    if _url_matches(page, "consultation", "inscription", "horaire"):
        logger.info("Étape 1 OK (retard SPA) — URL: {url}", url=page.url)
        return True

    _nav_screenshot(page, config, "nav_step1_failed")
    logger.error("Étape 1 échouée — URL actuelle: {url}", url=page.url)
    return False


def _portal_origin(config: AppConfig) -> str:
    parsed = urlparse(config.navigation.home_url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return "https://cheminotn.etsmtl.ca"


def _click_inscription_main_tab(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    tab_re = re.compile(r"INSCRIPTION\s+AUTOMNE\s+2026", re.I)
    if nav.inscription_tab_text:
        tab_re = re.compile(
            re.escape(nav.inscription_tab_text).replace(r"\ ", r"\s+"),
            re.I,
        )

    if nav.inscription_tab_selector:
        return _click_first_visible(page, nav.inscription_tab_selector)

    # Onglet principal (barre noire) — pas le sous-menu INFO. GÉNÉRALES
    try:
        top_bar = page.locator(
            "header, nav, [role='banner'], [class*='toolbar'], [class*='header'], [class*='nav']"
        ).first
        for loc in (
            top_bar.locator("a").filter(has_text=tab_re),
            top_bar.locator("button").filter(has_text=tab_re),
            top_bar.get_by_text(tab_re),
        ):
            try:
                el = loc.first
                if el.is_visible(timeout=2000):
                    el.click(timeout=8000)
                    return True
            except Exception:
                continue
    except Exception:
        pass

    for role in ("tab", "link", "button"):
        try:
            candidates = page.get_by_role(role, name=tab_re)
            for i in range(min(candidates.count(), 5)):
                el = candidates.nth(i)
                if el.is_visible(timeout=1000):
                    el.click(timeout=8000)
                    return True
        except Exception:
            continue

    try:
        page.locator("a[href*='inscription'], [routerlink*='inscription']").first.click(timeout=8000)
        return True
    except Exception:
        pass

    return _click_by_text(page, nav.inscription_tab_text, exact=False)


def _step_open_inscription_tab(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    origin = _portal_origin(config)
    logger.info("Étape 2 — Onglet {tab}", tab=nav.inscription_tab_text)
    logger.info("URL avant étape 2: {url}", url=page.url)

    if _url_matches(page, "inscription"):
        logger.info("Étape 2 OK (déjà sur inscription) — URL: {url}", url=page.url)
        return True

    if not _url_matches(page, "consultation"):
        _goto_route(page, origin, "consultation")
        if not _url_matches(page, "consultation"):
            page.goto(nav.consultation_url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=25000)

    logger.info("Navigation directe vers /inscription")
    _goto_route(page, origin, "inscription")
    if _wait_for_spa_route(page, "inscription", 45000):
        logger.info("Étape 2 OK (goto/route) — URL: {url}", url=page.url)
        return True

    logger.info("Tentative clic onglet INSCRIPTION (barre principale)")
    if _click_inscription_main_tab(page, config):
        page.wait_for_load_state("networkidle", timeout=25000)
        if _wait_for_spa_route(page, "inscription", 30000):
            logger.info("Étape 2 OK (clic onglet) — URL: {url}", url=page.url)
            return True

    page.wait_for_timeout(2000)
    if _url_matches(page, "inscription"):
        logger.info("Étape 2 OK (retard SPA) — URL: {url}", url=page.url)
        return True

    _nav_screenshot(page, config, "nav_step2_inscription_tab_failed")
    logger.error("Étape 2 échouée — URL actuelle: {url}", url=page.url)
    return False


def _click_course_node(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    sigle = config.course.sigle
    node_label = nav.course_node_label(sigle)
    logger.info("Étape 3 — Clic cours {sigle}", sigle=node_label)

    if nav.course_node_selector:
        return _click_first_visible(page, nav.course_node_selector)

    patterns = [
        lambda: page.get_by_text(node_label, exact=True).first.click(timeout=10000),
        lambda: page.locator(f"text={node_label}").first.click(timeout=10000),
        lambda: page.get_by_text(node_label, exact=False).first.click(timeout=10000),
    ]
    for click_fn in patterns:
        try:
            click_fn()
            page.wait_for_timeout(800)
            return True
        except Exception:
            continue
    _nav_screenshot(page, config, "nav_step3_course_failed")
    logger.error("Nœud cours {sigle} introuvable sur le graphe", sigle=node_label)
    return False


def _select_group_if_needed(page: Page, config: AppConfig) -> None:
    course = config.course
    if course.group_mode == "any" and not course.section.strip():
        return

    rows = _group_rows_in_options(page, config)
    try:
        count = rows.count()
    except Exception:
        count = 0

    if count == 0:
        return

    if course.group_mode in ("any", "first") or not course.section.strip():
        try:
            rows.first.click(timeout=3000)
            logger.debug("Premier groupe sélectionné (mode {mode})", mode=course.group_mode)
        except Exception:
            pass
        return

    section = course.section.lstrip("0") or course.section
    section_padded = course.section.zfill(2)
    for sec in (section_padded, course.section, section):
        try:
            row = rows.filter(has_text=re.compile(rf"\b{re.escape(sec)}\b")).first
            if row.is_visible(timeout=2000):
                row.click()
                logger.debug("Groupe {sec} sélectionné", sec=sec)
                return
        except Exception:
            continue


def cycle_via_clicks(page: Page, config: AppConfig) -> NavigationResult:
    """
    Un cycle de surveillance par clics uniquement (pas de goto URL).
    Inscription (onglet) → cours sur le graphe → page horaire / modal.
    """
    nav = config.navigation
    sigle = config.course.sigle
    logger.info("Cycle clics — onglet inscription puis cours {sigle}", sigle=sigle)

    if nav.reload_on_horaire_before_cycle and is_on_horaire_page(page, config):
        try:
            logger.debug("Rafraîchissement de la page horaire courante")
            page.reload(wait_until="domcontentloaded", timeout=60000)
            page.wait_for_load_state("networkidle", timeout=25000)
        except Exception as e:
            logger.warning("Reload horaire échoué: {e}", e=e)

    tab_clicked = _click_inscription_main_tab(page, config)
    if tab_clicked:
        logger.info("Onglet inscription cliqué")
        page.wait_for_timeout(1500)
        page.wait_for_load_state("networkidle", timeout=20000)
    else:
        logger.warning(
            "Onglet inscription non cliqué — poursuite (graphe peut-être déjà visible)"
        )

    if not _click_course_node(page, config):
        _nav_screenshot(page, config, "cycle_course_click_failed")
        return NavigationResult(
            NavigationOutcome.FAILED,
            f"Impossible de cliquer le cours {sigle} sur le graphe",
        )

    page.wait_for_timeout(1200)

    if is_full_course_modal_visible(page, config):
        dismiss_full_course_modal(page, config)
        return NavigationResult(
            NavigationOutcome.COURSE_FULL_MODAL,
            "Tous les groupes complets (modal)",
        )

    try:
        page.get_by_text(nav.options_panel_text, exact=False).first.wait_for(
            state="visible", timeout=20000
        )
    except PlaywrightTimeout:
        if not is_on_horaire_page(page, config):
            _nav_screenshot(page, config, "cycle_horaire_panel_missing")
            return NavigationResult(
                NavigationOutcome.FAILED,
                "Panneau horaire non visible après clic cours",
            )
        logger.warning("Panneau options non visible — vérification quand même")

    logger.info("Cycle clics terminé — URL: {url}", url=page.url)
    return NavigationResult(NavigationOutcome.HORAIRE_READY, "Cycle clics OK")


def navigate_to_course_horaire(page: Page, config: AppConfig) -> NavigationResult:
    nav = config.navigation

    step1_ok = _step_select_session(page, config)
    if not step1_ok and not _url_matches(page, "consultation", "inscription", "horaire"):
        return NavigationResult(NavigationOutcome.FAILED, "Échec sélection session")
    if not step1_ok:
        logger.warning(
            "Étape 1 non confirmée — poursuite depuis {url}",
            url=page.url,
        )

    if not _step_open_inscription_tab(page, config):
        return NavigationResult(NavigationOutcome.FAILED, "Échec onglet inscription")

    if not _click_course_node(page, config):
        return NavigationResult(NavigationOutcome.FAILED, "Échec clic cours")

    page.wait_for_timeout(1000)

    if is_full_course_modal_visible(page, config):
        dismiss_full_course_modal(page, config)
        return NavigationResult(
            NavigationOutcome.COURSE_FULL_MODAL,
            "Tous les groupes complets (modal)",
        )

    try:
        page.wait_for_url(re.compile(r".*/horaire.*", re.I), timeout=20000)
    except PlaywrightTimeout:
        if "/horaire" not in page.url.lower():
            page.goto(nav.horaire_url, wait_until="domcontentloaded", timeout=60000)

    _select_group_if_needed(page, config)

    try:
        page.get_by_text(nav.options_panel_text, exact=False).first.wait_for(
            state="visible", timeout=15000
        )
    except PlaywrightTimeout:
        logger.warning("Panneau options d'horaires non visible — poursuite quand même")

    if is_full_course_modal_visible(page, config):
        dismiss_full_course_modal(page, config)
        return NavigationResult(NavigationOutcome.COURSE_FULL_MODAL, "Modal complet sur horaire")

    logger.info("Navigation terminée — URL: {url}", url=page.url)
    return NavigationResult(NavigationOutcome.HORAIRE_READY, "Page horaire atteinte")


def is_on_horaire_page(page: Page, config: AppConfig) -> bool:
    return "/horaire" in page.url.lower()


def ensure_horaire_context(page: Page, config: AppConfig) -> NavigationResult:
    nav = config.navigation
    if nav.uses_manual_clicks():
        return cycle_via_clicks(page, config)

    if nav.renavigate_each_cycle or not is_on_horaire_page(page, config):
        return navigate_to_course_horaire(page, config)

    try:
        panel = page.get_by_text(nav.options_panel_text, exact=False).first
        if panel.is_visible(timeout=3000):
            return NavigationResult(NavigationOutcome.HORAIRE_READY, "Déjà sur horaire")
    except Exception:
        pass

    return navigate_to_course_horaire(page, config)
