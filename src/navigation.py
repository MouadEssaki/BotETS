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


def path_contains_route(url: str, route: str) -> bool:
    """Vrai seulement si le chemin contient /route. Un hash (#inscription) ne compte pas."""
    segment = route.strip("/").lower()
    if not segment:
        return False
    path = urlparse(url).path.lower().strip("/")
    return segment in path.split("/") if path else False


def _url_matches(page: Page, *fragments: str) -> bool:
    """Route Cheminot : le chemin de l'URL, pas le fragment (#inscription)."""
    return any(path_contains_route(page.url, fragment) for fragment in fragments)


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


def _goto_route(page: Page, base: str, route: str) -> bool:
    """Ouvre https://…/inscription (ou une autre route) par une vraie navigation.

    Le réseau de Cheminot reste souvent actif, donc un échec de networkidle
    ne doit pas annuler le goto ni basculer vers #inscription.
    """
    route = route.strip("/")
    url = f"{base.rstrip('/')}/{route}"
    logger.info("Ouverture directe {url}", url=url)
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
    except Exception as e:
        logger.warning("goto {url} échoué: {e}", url=url, e=e)
        return False
    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except Exception:
        logger.debug("networkidle ignoré pour {url}", url=url)
    if path_contains_route(page.url, route):
        logger.info("Route {route} ouverte — {url}", route=route, url=page.url)
        return True
    page.wait_for_timeout(1500)
    loaded = path_contains_route(page.url, route)
    if loaded:
        logger.info("Route {route} ouverte (retard SPA) — {url}", route=route, url=page.url)
    else:
        logger.warning("Route {route} non tenue — URL actuelle: {url}", route=route, url=page.url)
    return loaded


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
    """Clique un vrai lien vers /inscription. Un libellé seul ne change pas la page."""
    nav = config.navigation
    if nav.inscription_tab_selector:
        return _click_first_visible(page, nav.inscription_tab_selector)

    for selector in (
        "a[href='/inscription']",
        "a[href$='/inscription']",
        "a[href*='/inscription']",
        "[routerlink='/inscription']",
        "[routerlink*='inscription']",
    ):
        try:
            loc = page.locator(selector)
            count = min(loc.count(), 6)
        except Exception:
            count = 0
        for i in range(count):
            el = loc.nth(i)
            try:
                if el.is_visible(timeout=800):
                    el.click(timeout=5000)
                    logger.info("Clic lien inscription ({selector})", selector=selector)
                    return True
            except Exception:
                continue

    tab_re = re.compile(r"INSCRIPTION\s+AUTOMNE", re.I)
    if nav.inscription_tab_text:
        tab_re = re.compile(
            re.escape(nav.inscription_tab_text).replace(r"\ ", r"\s+"),
            re.I,
        )
    for role in ("link", "tab", "button"):
        try:
            candidates = page.get_by_role(role, name=tab_re)
            for i in range(min(candidates.count(), 5)):
                el = candidates.nth(i)
                if el.is_visible(timeout=800):
                    el.click(timeout=5000)
                    logger.info("Clic rôle {role} inscription", role=role)
                    return True
        except Exception:
            continue
    return False


def _step_open_inscription_tab(page: Page, config: AppConfig) -> bool:
    nav = config.navigation
    origin = _portal_origin(config)
    logger.info("Étape 2 — /inscription")
    logger.info("URL avant étape 2: {url}", url=page.url)

    if path_contains_route(page.url, "inscription"):
        logger.info("Étape 2 OK (déjà sur inscription) — URL: {url}", url=page.url)
        return True

    if _goto_route(page, origin, "inscription"):
        logger.info("Étape 2 OK (goto /inscription) — URL: {url}", url=page.url)
        return True

    logger.info("Goto /inscription non tenu — clic du lien, puis nouvel essai")
    if _click_inscription_main_tab(page, config):
        if _wait_url_contains(page, "inscription", 8000) and path_contains_route(page.url, "inscription"):
            logger.info("Étape 2 OK (clic lien) — URL: {url}", url=page.url)
            return True
        logger.info("Le clic n'a pas changé le chemin — nouvel appel à {url}", url=nav.inscription_url)

    if _goto_route(page, origin, "inscription"):
        logger.info("Étape 2 OK (second goto) — URL: {url}", url=page.url)
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

    if not path_contains_route(page.url, "inscription"):
        tab_clicked = _click_inscription_main_tab(page, config)
        if tab_clicked:
            logger.info("Lien inscription cliqué")
            page.wait_for_timeout(1000)
        if not path_contains_route(page.url, "inscription"):
            logger.info("Le clic n'a pas ouvert /inscription — navigation directe")
            _goto_route(page, _portal_origin(config), "inscription")
    else:
        logger.info("Déjà sur /inscription")

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

    if not ensure_inscription_catalog_page(page, config):
        return NavigationResult(NavigationOutcome.FAILED, "Échec ouverture /inscription")

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


def page_has_course_list(page: Page) -> bool:
    """Vrai si la page affiche « Cours offerts » ou des sigles (graphe / liste)."""
    try:
        text = page.inner_text("body", timeout=5000)
    except Exception:
        return False
    if "cours offerts" in text.lower():
        return True
    return bool(re.search(r"\b[A-Za-z]{3}\d{3}\b", text))


def click_inscription_registration_session(page: Page) -> bool:
    """Premier « Sélectionner cette session » = carte Inscription (ex. Hiver 2027)."""
    try:
        body = page.inner_text("body", timeout=5000)
    except Exception:
        return False
    if "sélectionner cette session" not in body.lower() and "selectionner cette session" not in body.lower():
        return False
    logger.info("Clic session — Inscription et consultation")
    page.get_by_role("button", name=re.compile(r"s[ée]lectionner cette session", re.I)).first.click(
        timeout=10000
    )
    try:
        page.wait_for_url(re.compile(r"/(consultation|inscription)", re.I), timeout=15000)
    except PlaywrightTimeout:
        page.wait_for_timeout(1500)
    return True


def ensure_inscription_catalog_page(page: Page, config: AppConfig) -> bool:
    """Ouvre la liste de cours.

    Sur Cheminot, ``/inscription`` seul ne suffit pas : sans « Sélectionner
    cette session » sur l'accueil, la page revient sans graphe. Ordre forcé :
    accueil → session Inscription → ``/inscription``.
    """
    nav = config.navigation

    if path_contains_route(page.url, "inscription") and page_has_course_list(page):
        logger.info("Déjà sur /inscription avec cours visibles")
        return True

    logger.info("Accueil → Sélectionner cette session → /inscription")
    page.goto(nav.home_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(800)
    clicked = click_inscription_registration_session(page)
    if not clicked and not _is_in_portal_session(page, config):
        # Bouton peut être absent si la session est déjà choisie
        logger.info("Pas de bouton session — essai direct /inscription")
    page.goto(nav.inscription_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    if page_has_course_list(page):
        logger.info("Cours visibles sur {url}", url=page.url)
        return True

    # Second essai : carte session puis onglet
    page.goto(nav.home_url, wait_until="domcontentloaded", timeout=60000)
    _click_session_select_button(page, config)
    page.wait_for_timeout(1500)
    page.goto(nav.inscription_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    if page_has_course_list(page):
        return True

    _click_inscription_main_tab(page, config)
    page.wait_for_timeout(1000)
    page.goto(nav.inscription_url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1200)
    ok = page_has_course_list(page)
    if not ok:
        logger.warning("Liste de cours absente — URL: {url}", url=page.url)
        _nav_screenshot(page, config, "inscription_catalog_failed")
    return ok


def open_inscription_board(page: Page, config: AppConfig) -> bool:
    return ensure_inscription_catalog_page(page, config)


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
