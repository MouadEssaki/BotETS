"""Processus / sous-processus enfant : un navigateur, un seul cours."""

from __future__ import annotations

import sys


def run_course_worker(sigle: str, *, auto_register: bool = False) -> int:
    from src.config_loader import worker_config_for
    from src.main import run_bot

    config = worker_config_for(sigle, auto_register=auto_register)
    return run_bot(config)


def run_course_process(sigle: str, start_event, browser_ready, auto_register: bool = False) -> None:
    """Ancien point d'entrée multiprocessing (conservé si appelé ailleurs)."""
    from src.config_loader import worker_config_for
    from src.main import run_bot

    config = worker_config_for(sigle, auto_register=auto_register)
    sys.exit(run_bot(config, start_event=start_event, browser_ready=browser_ready))


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python -m src.worker SIGLE [--auto-register]", file=sys.stderr)
        return 2
    sigle = args[0]
    auto = "--auto-register" in args
    return run_course_worker(sigle, auto_register=auto)


if __name__ == "__main__":
    raise SystemExit(main())
