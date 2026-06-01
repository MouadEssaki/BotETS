"""Détection et gestion de l'état de session."""

from __future__ import annotations

from playwright.sync_api import Page

from src.config_loader import AppConfig
from loguru import logger


def url_indicates_login(page: Page, config: AppConfig) -> bool:
    url_lower = page.url.lower()
    return any(kw in url_lower for kw in config.login.login_url_keywords)


def is_logged_in(page: Page, config: AppConfig, timeout_ms: int = 5000) -> bool:
    """
    Détermine si l'utilisateur est connecté.
    Combine URL, sélecteur logged_in / logged_out et heuristiques.
    """
    if url_indicates_login(page, config):
        logger.debug("Session invalide (URL login): {url}", url=page.url)
        return False

    sel = config.selectors

    if sel.logged_out:
        try:
            loc = page.locator(sel.logged_out).first
            if loc.is_visible(timeout=2000):
                logger.debug("Session invalide (sélecteur logged_out visible)")
                return False
        except Exception:
            pass

    if sel.logged_in:
        try:
            loc = page.locator(sel.logged_in).first
            if loc.is_visible(timeout=timeout_ms):
                return True
            logger.debug("Session invalide (sélecteur logged_in absent)")
            return False
        except Exception:
            logger.debug("Session invalide (sélecteur logged_in erreur)")
            return False

    # Heuristique : page Cheminot horaire sans redirection login
    if "cheminot" in page.url.lower() and not url_indicates_login(page, config):
        return True

    return not url_indicates_login(page, config)


def ensure_logged_in(page: Page, config: AppConfig, manual_login_callback) -> None:
    """Vérifie la session ; appelle manual_login_callback si expirée."""
    if is_logged_in(page, config):
        return
    logger.warning("Session expirée ou non connecté — nouvelle connexion requise")
    manual_login_callback(page)
