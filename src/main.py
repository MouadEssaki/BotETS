"""Point d'entrée — Bot surveillance Cheminot ÉTS."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.browser import BrowserSession
from src.config_loader import load_config
from src.monitor import run_monitor_loop


def setup_logging(config) -> None:
    logs_dir = config.logs_dir()
    log_file = logs_dir / "bot.log"
    logger.remove()
    logger.add(
        sys.stderr,
        level=config.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        level=config.log_level,
        encoding="utf-8",
    )
    logger.info("Logs fichier: {path}", path=log_file)


def _wait_before_close_browser() -> None:
    logger.info("=" * 60)
    logger.info("Navigateur laissé ouvert — inscrivez-vous ou continuez à naviguer.")
    logger.info("Fermez la fenêtre Chrome manuellement, ou appuyez sur Entrée ici pour quitter.")
    logger.info("=" * 60)
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


def main() -> int:
    config = load_config()
    setup_logging(config)

    labels = ", ".join(c.label for c in config.courses_to_watch())
    logger.info("=== Bot Cheminot ÉTS — surveillance de places ===")
    logger.info("Cours surveillés : {labels}", labels=labels)
    if config.notifications.enabled:
        providers = []
        if config.notifications.ntfy_topic:
            providers.append("ntfy")
        if config.notifications.telegram_bot_token:
            providers.append("Telegram")
        logger.info("Notifications téléphone : {p}", p=", ".join(providers))
    else:
        logger.info("Notifications téléphone désactivées — voir .env.example")

    storage = config.storage_state_path()
    had_storage = storage.is_file()

    session = BrowserSession(config)
    exit_code = 0
    try:
        session.start()
        page = session.page
        assert page is not None

        if config.navigation.uses_manual_clicks():
            page.goto(config.portal_url, wait_until="domcontentloaded", timeout=60000)
            if not had_storage:
                session.wait_for_manual_login(page)
            else:
                from src.session import is_logged_in

                if not is_logged_in(page, config):
                    logger.warning("Session sauvegardée invalide — MFA requis")
                    session.wait_for_manual_login(page)
        else:
            if not had_storage:
                session.wait_for_manual_login(page)
            else:
                page.goto(config.portal_url, wait_until="domcontentloaded", timeout=60000)
                session.dismiss_popup_if_configured(page)
                from src.session import is_logged_in

                if not is_logged_in(page, config):
                    logger.warning("Session sauvegardée invalide — MFA requis")
                    session.wait_for_manual_login(page)

        run_monitor_loop(page, config, session)
        session.save_storage_state()

    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur (Ctrl+C)")
        exit_code = 0
    except Exception as e:
        logger.exception("Erreur fatale: {e}", e=e)
        exit_code = 1
    finally:
        try:
            session.save_storage_state()
        except Exception:
            pass
        if config.browser.keep_open:
            _wait_before_close_browser()
        session.stop()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
