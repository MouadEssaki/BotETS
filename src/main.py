"""Point d'entrée — Bot surveillance Cheminot ÉTS."""

from __future__ import annotations

import argparse
import multiprocessing as mp
import shutil
import sys
import time
from pathlib import Path

from loguru import logger

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.browser import BrowserSession
from src.config_loader import AppConfig, isolate_course, load_config, worker_storage_filename


def setup_logging(config: AppConfig) -> None:
    logs_dir = config.logs_dir()
    log_name = "bot.log"
    if config.is_worker:
        log_name = f"bot_{config.course.sigle}.log"
    log_file = logs_dir / log_name
    logger.remove()
    prefix = f"<cyan>[{config.course.sigle}]</cyan> | " if config.is_worker else ""
    logger.add(
        sys.stderr,
        level=config.log_level,
        format=prefix + "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )
    logger.add(
        log_file,
        rotation="10 MB",
        retention="7 days",
        level=config.log_level,
        encoding="utf-8",
    )
    logger.info("Logs fichier: {path}", path=log_file)


def _wait_before_close_browser(config: AppConfig) -> None:
    if config.is_worker:
        logger.info(
            "Navigateur {label} laissé ouvert. Ctrl+C dans la console principale pour tout fermer.",
            label=config.course.label,
        )
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            pass
        return

    logger.info("=" * 60)
    logger.info("Navigateur laissé ouvert — inscrivez-vous ou continuez à naviguer.")
    logger.info("Fermez la fenêtre Chrome manuellement, ou appuyez sur Entrée ici pour quitter.")
    logger.info("=" * 60)
    try:
        input()
    except (KeyboardInterrupt, EOFError):
        pass


def bootstrap_session(session: BrowserSession, config: AppConfig) -> None:
    """Ouvre Cheminot et exige le MFA si la session enregistrée est absente ou invalide."""
    page = session.page
    assert page is not None
    had_storage = config.storage_state_path().is_file()

    if config.navigation.uses_manual_clicks():
        page.goto(config.portal_url, wait_until="domcontentloaded", timeout=60000)
        if not had_storage:
            session.wait_for_manual_login(page)
        else:
            from src.session import is_logged_in

            if not is_logged_in(page, config):
                logger.warning("Session sauvegardée invalide — MFA requis")
                session.wait_for_manual_login(page)
        return

    if not had_storage:
        session.wait_for_manual_login(page)
        return

    page.goto(config.portal_url, wait_until="domcontentloaded", timeout=60000)
    session.dismiss_popup_if_configured(page)
    from src.session import is_logged_in

    if not is_logged_in(page, config):
        logger.warning("Session sauvegardée invalide — MFA requis")
        session.wait_for_manual_login(page)


def _log_startup(config: AppConfig) -> None:
    labels = ", ".join(c.label for c in config.courses_to_watch())
    logger.info("=== Bot Cheminot ÉTS — surveillance de places ===")
    logger.info("Cours surveillés : {labels}", labels=labels)
    if config.is_worker:
        logger.info("Bot dédié au cours {label}", label=config.course.label)
    auto = [c.label for c in config.courses_to_watch() if c.auto_register]
    if auto:
        logger.info(
            "Inscription automatique (premier groupe libre, horaire ignoré) : {labels}",
            labels=", ".join(auto),
        )
    if config.notifications.enabled:
        providers = []
        if config.notifications.ntfy_topic:
            providers.append("ntfy")
        if config.notifications.telegram_bot_token:
            providers.append("Telegram")
        logger.info("Notifications téléphone : {p}", p=", ".join(providers))
    else:
        logger.info("Notifications téléphone désactivées — voir .env.example")


def run_bot(config: AppConfig, start_event=None, browser_ready=None) -> int:
    from src.monitor import run_monitor_loop

    setup_logging(config)
    _log_startup(config)

    session = BrowserSession(config)
    exit_code = 0
    try:
        session.start()
        bootstrap_session(session, config)
        page = session.page
        assert page is not None
        if config.is_worker:
            try:
                page.evaluate(
                    "(label) => { document.title = 'BotETS — ' + label; }",
                    config.course.label,
                )
            except Exception:
                pass
        if browser_ready is not None:
            browser_ready.set()
        if start_event is not None:
            start_event.set()
        run_monitor_loop(page, config, session)
        session.save_storage_state()

    except KeyboardInterrupt:
        logger.info("Arrêt demandé par l'utilisateur (Ctrl+C)")
        exit_code = 0
    except Exception as e:
        if browser_ready is not None:
            try:
                browser_ready.set()
            except Exception:
                pass
        logger.exception("Erreur fatale: {e}", e=e)
        exit_code = 1
    finally:
        try:
            session.save_storage_state()
        except Exception:
            pass
        if config.browser.keep_open:
            _wait_before_close_browser(config)
        session.stop()

    return exit_code


def _ensure_shared_login(config: AppConfig) -> None:
    storage = config.storage_state_path()
    if storage.is_file():
        logger.info("Session partagée trouvée: {path}", path=storage)
        return
    logger.info("Aucune session — connexion MFA une fois, puis un navigateur par cours")
    session = BrowserSession(config)
    try:
        session.start()
        bootstrap_session(session, config)
        session.save_storage_state()
    finally:
        session.stop()
    logger.info("Fenêtre de connexion fermée — ouverture d'un navigateur par cours")


def _copy_worker_sessions(config: AppConfig) -> None:
    source = config.storage_state_path()
    if not source.is_file():
        logger.warning("Pas de session à copier — chaque bot demandera le MFA si besoin")
        return
    for course in config.courses_to_watch():
        dest = config.project_root / worker_storage_filename(course.sigle)
        shutil.copyfile(source, dest)
        logger.info("Session copiée pour {label}: {path}", label=course.label, path=dest)


def run_multi_bot(config: AppConfig, confirm=None, procs_out: list | None = None) -> int:
    """Lance un processus par cours. Navigation auto — pas de Window ready."""
    from src.worker import run_course_process

    setup_logging(config)
    courses = config.courses_to_watch()
    labels = ", ".join(c.label for c in courses)
    logger.info("Mode multi-bot — un navigateur par cours : {labels}", labels=labels)
    _ensure_shared_login(config)
    _copy_worker_sessions(config)

    ctx = mp.get_context("spawn")
    procs: list[mp.Process] = []
    for course in courses:
        start_event = ctx.Event()
        start_event.set()
        browser_ready = ctx.Event()
        proc = ctx.Process(
            target=run_course_process,
            args=(course.sigle, start_event, browser_ready),
            name=f"bot-{course.sigle}",
        )
        proc.start()
        procs.append(proc)
        logger.info("Bot {label} démarré (pid {pid})", label=course.label, pid=proc.pid)
    if procs_out is not None:
        procs_out.extend(procs)

    exit_code = 0
    try:
        logger.info("Les bots naviguent seuls (session → /inscription → cours). Ctrl+C pour arrêter.")
        for proc in procs:
            proc.join()
            if proc.exitcode not in (0, None):
                logger.error(
                    "{name} terminé avec le code {code}",
                    name=proc.name,
                    code=proc.exitcode,
                )
                exit_code = 1
    except KeyboardInterrupt:
        logger.info("Arrêt de tous les bots (Ctrl+C)")
        for proc in procs:
            if proc.is_alive():
                proc.terminate()
        for proc in procs:
            proc.join(timeout=5)
        exit_code = 0
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Surveillance Cheminot ÉTS")
    parser.add_argument(
        "--course",
        default="",
        help="Un seul sigle (ex. LOG200). Ignore le mode multi-bot.",
    )
    parser.add_argument(
        "--run",
        action="store_true",
        help="Lance les bots de config.yaml sans ouvrir l'interface.",
    )
    args = parser.parse_args(argv)

    if not args.run and not args.course.strip():
        from src.ui import run_ui

        run_ui()
        return 0

    config = load_config()

    if args.course.strip():
        try:
            config = isolate_course(config, args.course, as_worker=False)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 1
        return run_bot(config)

    courses = config.courses_to_watch()
    if config.browser.multi_bot and len(courses) > 1:
        return run_multi_bot(config)
    return run_bot(config)


if __name__ == "__main__":
    mp.freeze_support()
    sys.exit(main())
