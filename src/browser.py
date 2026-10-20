"""Lancement Playwright, connexion MFA manuelle, storage_state."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from loguru import logger
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from src.config_loader import AppConfig
from src.session import is_logged_in


class BrowserSession:
    """Encapsule Playwright, le contexte et la page active."""

    def __init__(self, config: AppConfig):
        self.config = config
        self._playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.page: Page | None = None

    def __enter__(self) -> "BrowserSession":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    def start(self) -> None:
        self._playwright = sync_playwright().start()
        self.browser = self._playwright.chromium.launch(headless=False)
        storage = self.config.storage_state_path()
        if storage.is_file():
            logger.info("Chargement de la session: {path}", path=storage)
            self.context = self.browser.new_context(storage_state=str(storage))
        else:
            logger.info("Aucune session sauvegardée — connexion MFA requise")
            self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def stop(self) -> None:
        if self.context:
            try:
                self.context.close()
            except Exception:
                pass
        if self.browser:
            try:
                self.browser.close()
            except Exception:
                pass
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass

    def save_storage_state(self) -> None:
        path = self.config.storage_state_path()
        if self.context:
            self.context.storage_state(path=str(path))
            logger.info("Session sauvegardée: {path}", path=path)

    def dismiss_popup_if_configured(self, page: Page) -> None:
        sel = self.config.selectors.popup_close
        if not sel:
            return
        try:
            btn = page.locator(sel).first
            if btn.is_visible(timeout=2000):
                btn.click()
                logger.debug("Popup fermée")
        except Exception:
            pass

    def wait_for_manual_login(self, page: Page) -> None:
        wait = self.config.login.manual_wait_seconds
        portal = self.config.portal_url
        logger.info(
            "Connectez-vous et complétez le MFA dans le navigateur ({wait}s)...",
            wait=wait,
        )
        logger.info("URL portail: {url}", url=portal)
        page.goto(portal, wait_until="domcontentloaded", timeout=60000)
        self.dismiss_popup_if_configured(page)
        for remaining in range(wait, 0, -15):
            if is_logged_in(page, self.config):
                logger.info("Connexion détectée ({remaining}s restantes)", remaining=remaining)
                break
            if remaining <= wait and remaining % 15 == 0:
                logger.info("En attente de connexion... ({remaining}s)", remaining=remaining)
            time.sleep(min(15, remaining))
        else:
            time.sleep(0)

        if not is_logged_in(page, self.config):
            logger.warning(
                "Connexion non confirmée après la pause — sauvegarde quand même si vous êtes connecté"
            )
        self.save_storage_state()

    def ensure_session(self, page: Page) -> None:
        """Navigue vers le portail si besoin et force MFA si session invalide."""
        if is_logged_in(page, self.config):
            return
        self.wait_for_manual_login(page)

    def wait_for_manual_navigation(self, page: Page) -> None:
        """Pause : l'utilisateur navigue lui-même (session, consultation, inscription, horaire)."""
        nav = self.config.navigation
        wait = nav.manual_setup_seconds
        watched = ", ".join(c.label for c in self.config.courses_to_watch())

        logger.info("=" * 60)
        finish_on_enter = nav.manual_finish_on_enter
        logger.info("PAUSE MANUELLE — max {wait}s", wait=wait)
        if finish_on_enter:
            logger.info("Appuyez sur ENTRÉE dans cette console dès que vous êtes prêt (avant la fin du délai).")
        logger.info("Rapidement : session Automne → INSCRIPTION AUTOMNE 2026 (graphe). Cours : {list}", list=watched)
        logger.info("=" * 60)

        if "cheminot" not in page.url.lower() or page.url == "about:blank":
            page.goto(self.config.portal_url, wait_until="domcontentloaded", timeout=60000)

        self.dismiss_popup_if_configured(page)

        if finish_on_enter:
            import threading

            done = threading.Event()

            def _wait_enter():
                try:
                    input()
                    done.set()
                except (KeyboardInterrupt, EOFError):
                    done.set()

            t = threading.Thread(target=_wait_enter, daemon=True)
            t.start()
            step = 5
            for remaining in range(wait, 0, -step):
                if done.is_set():
                    logger.info("Reprise — vous avez confirmé (Entrée).")
                    break
                if remaining <= wait:
                    logger.info("... {remaining}s (Entrée = démarrer)", remaining=remaining)
                time.sleep(min(step, remaining))
            else:
                if not done.is_set():
                    logger.info("Délai écoulé — démarrage automatique.")
        else:
            for remaining in range(wait, 0, -5):
                logger.info("... {remaining}s", remaining=remaining)
                time.sleep(min(5, remaining))

        self.save_storage_state()
        logger.info("Reprise bot — URL: {url}", url=page.url)

    def get_manual_login_callback(self) -> Callable[[Page], None]:
        def _callback(page: Page) -> None:
            self.wait_for_manual_login(page)
            if self.config.navigation.uses_manual_clicks() and not self.config.is_worker:
                self.wait_for_manual_navigation(page)

        return _callback
