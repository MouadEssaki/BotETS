"""Point d'entrée de BotEts.exe — installe Chromium au besoin, puis ouvre l'UI."""

from __future__ import annotations

import multiprocessing as mp
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk


def _prepare_sys_path() -> None:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent
    if str(base) not in sys.path:
        sys.path.insert(0, str(base))


def _browsers_ready(browsers_dir: Path) -> bool:
    if not browsers_dir.is_dir():
        return False
    return any(browsers_dir.rglob("chrome.exe"))


def _install_chromium(browsers_dir: Path, status: tk.StringVar, root: tk.Tk) -> None:
    browsers_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    status.set("Downloading Chromium (one-time, ~150 MB)…")
    root.update_idletasks()

    def work() -> None:
        try:
            from playwright._impl._driver import compute_driver_executable, get_driver_env

            driver = str(compute_driver_executable())
            env = get_driver_env()
            env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
            completed = subprocess.run(
                [driver, "install", "chromium"],
                env=env,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                raise RuntimeError(completed.stderr or completed.stdout or "playwright install failed")
        except Exception as exc:
            message = f"Download failed: {exc}"
            root.after(0, lambda m=message: status.set(m))
            root.after(3000, root.destroy)
            return
        root.after(0, root.destroy)

    threading.Thread(target=work, daemon=True).start()
    root.mainloop()


def ensure_chromium() -> None:
    _prepare_sys_path()
    from src.paths import user_data_dir

    browsers_dir = user_data_dir() / "ms-playwright"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    if _browsers_ready(browsers_dir):
        return

    splash = tk.Tk()
    splash.title("BotEts")
    splash.geometry("420x160")
    splash.resizable(False, False)
    frame = ttk.Frame(splash, padding=20)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="BotEts", font=("Segoe UI", 18, "bold")).pack()
    status = tk.StringVar(value="Preparing first launch…")
    ttk.Label(frame, textvariable=status, wraplength=380).pack(pady=12)
    ttk.Label(frame, text="This only happens once.").pack()
    splash.after(100, lambda: _install_chromium(browsers_dir, status, splash))
    splash.mainloop()


def main() -> int:
    mp.freeze_support()
    _prepare_sys_path()
    ensure_chromium()
    from src.ui import run_ui

    run_ui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
