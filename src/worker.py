"""Processus enfant : un navigateur, un seul cours.

Le point d'entrée est dans ce module (pas dans ``__main__``) pour que
``multiprocessing`` sur Windows puisse le réimporter.
"""

from __future__ import annotations

import sys


def run_course_process(sigle: str, start_event, browser_ready) -> None:
    from src.config_loader import isolate_course, load_config
    from src.main import run_bot

    config = isolate_course(load_config(), sigle, as_worker=True)
    sys.exit(run_bot(config, start_event=start_event, browser_ready=browser_ready))
