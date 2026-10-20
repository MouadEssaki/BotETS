"""Point d'entrée de BotEts.exe — installe Chromium au besoin, puis ouvre l'UI."""

from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import sys
import threading
import traceback
from pathlib import Path


def _prepare_sys_path() -> None:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))


def _crash_log_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "BotEts"
    base.mkdir(parents=True, exist_ok=True)
    return base / "crash.log"


def _log_crash(exc: BaseException) -> Path:
    path = _crash_log_path()
    path.write_text(
        "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
        encoding="utf-8",
    )
    return path


def _show_error(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("BotEts", message)
        root.destroy()
    except Exception:
        pass


def _browsers_ready(browsers_dir: Path) -> bool:
    if not browsers_dir.is_dir():
        return False
    return any(browsers_dir.rglob("chrome.exe"))


def _install_chromium(browsers_dir: Path) -> None:
    import tkinter as tk
    from tkinter import ttk

    browsers_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)

    splash = tk.Tk()
    splash.title("BotEts")
    splash.geometry("440x170")
    splash.resizable(False, False)
    frame = ttk.Frame(splash, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="BotEts", font=("Segoe UI", 18, "bold")).pack()
    status = tk.StringVar(value="Downloading Chromium (one-time, ~150 MB)…")
    ttk.Label(frame, textvariable=status, wraplength=400).pack(pady=12)
    ttk.Label(frame, text="This only happens once. Keep this window open.").pack()

    result: dict = {"ok": False, "error": ""}

    def work() -> None:
        try:
            from playwright._impl._driver import compute_driver_executable, get_driver_env

            # Returns (node.exe, cli.js) — not a single path
            node, cli = compute_driver_executable()
            env = get_driver_env()
            env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
            completed = subprocess.run(
                [node, cli, "install", "chromium"],
                env=env,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(
                    (completed.stderr or completed.stdout or "playwright install failed").strip()
                )
            result["ok"] = True
        except Exception as exc:
            result["error"] = str(exc)
            _log_crash(exc)
        splash.after(0, splash.quit)

    threading.Thread(target=work, daemon=True).start()
    splash.mainloop()
    try:
        splash.destroy()
    except Exception:
        pass

    if not result["ok"]:
        raise RuntimeError(
            "Could not download Chromium.\n\n"
            f"{result['error']}\n\n"
            f"Details: {_crash_log_path()}"
        )


def ensure_chromium() -> None:
    _prepare_sys_path()
    from src.paths import user_data_dir

    browsers_dir = user_data_dir() / "ms-playwright"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    if not _browsers_ready(browsers_dir):
        _install_chromium(browsers_dir)


def main() -> int:
    mp.freeze_support()
    # Child processes used by multi-bot must not open the UI again.
    if mp.current_process().name != "MainProcess":
        return 0

    try:
        _prepare_sys_path()
        ensure_chromium()
        from src.ui import run_ui

        run_ui()
        return 0
    except Exception as exc:
        path = _log_crash(exc)
        _show_error(f"BotEts failed to start.\n\n{exc}\n\nLog saved to:\n{path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
