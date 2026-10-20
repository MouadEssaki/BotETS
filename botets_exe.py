"""Point d'entrée de BotEts.exe — splash immédiat, Chromium si besoin, puis UI."""

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


def _resource_logo() -> Path | None:
    _prepare_sys_path()
    from src.paths import resource_root

    for name in ("logo.ico", "logo.png"):
        path = resource_root() / "assets" / name
        if path.is_file():
            return path
    return None


def _apply_icon(window) -> None:
    logo = _resource_logo()
    if not logo:
        return
    try:
        import tkinter as tk

        # Keep a reference on the window so Tk doesn't garbage-collect it
        window._botets_icon = tk.PhotoImage(file=str(logo.with_suffix(".png") if logo.suffix == ".ico" else logo))
        # Prefer PNG for iconphoto; ico may not load as PhotoImage
        png = logo if logo.suffix.lower() == ".png" else logo.with_suffix(".png")
        if png.is_file():
            window._botets_icon = tk.PhotoImage(file=str(png))
            window.iconphoto(True, window._botets_icon)
    except Exception:
        pass


def _browsers_ready(browsers_dir: Path) -> bool:
    if not browsers_dir.is_dir():
        return False
    return any(browsers_dir.rglob("chrome.exe"))


class Splash:
    """Fenêtre visible dès le double-clic (évite l'impression que rien ne se passe)."""

    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self._tk = tk
        self.root = tk.Tk()
        self.root.title("BotEts")
        self.root.geometry("460x200")
        self.root.resizable(False, False)
        _apply_icon(self.root)

        frame = ttk.Frame(self.root, padding=20)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="BotEts", font=("Segoe UI", 20, "bold")).pack()
        self.status = tk.StringVar(value="Starting BotEts…")
        ttk.Label(frame, textvariable=self.status, wraplength=420).pack(pady=(14, 6))
        ttk.Label(
            frame,
            text="First launch installs shortcuts + Chromium (once). Later launches are fast.",
            wraplength=420,
        ).pack()
        self.root.update_idletasks()
        self.root.update()

    def set_status(self, text: str) -> None:
        self.status.set(text)
        try:
            self.root.update_idletasks()
            self.root.update()
        except Exception:
            pass

    def close(self) -> None:
        try:
            self.root.destroy()
        except Exception:
            pass


def _install_chromium(browsers_dir: Path, splash: Splash) -> None:
    browsers_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    splash.set_status("Downloading Chromium (one-time, ~150 MB)…")

    result: dict = {"ok": False, "error": ""}

    def work() -> None:
        try:
            from playwright._impl._driver import compute_driver_executable, get_driver_env

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
        splash.root.after(0, splash.root.quit)

    threading.Thread(target=work, daemon=True).start()
    splash.root.mainloop()

    if not result["ok"]:
        raise RuntimeError(
            "Could not download Chromium.\n\n"
            f"{result['error']}\n\n"
            f"Details: {_crash_log_path()}"
        )


def ensure_chromium(splash: Splash) -> None:
    _prepare_sys_path()
    from src.paths import user_data_dir

    browsers_dir = user_data_dir() / "ms-playwright"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    if _browsers_ready(browsers_dir):
        splash.set_status("Opening BotEts…")
        return
    _install_chromium(browsers_dir, splash)
    # After install mainloop, recreate a short status splash if destroyed
    splash.set_status("Opening BotEts…")


def ensure_app_shortcuts(splash: Splash) -> None:
    """Installe l'exe + raccourcis Menu Démarrer / Bureau (recherche Windows)."""
    _prepare_sys_path()
    from src.windows_install import ensure_windows_app

    try:
        ensure_windows_app(status_cb=splash.set_status)
    except Exception as exc:
        # Non bloquant : l'app fonctionne quand même depuis le .exe téléchargé
        _log_crash(exc)
        splash.set_status("Shortcuts skipped — opening BotEts…")


def main() -> int:
    mp.freeze_support()
    if mp.current_process().name != "MainProcess":
        return 0

    splash: Splash | None = None
    try:
        # Show UI feedback immediately (before heavy imports / Chromium check)
        splash = Splash()
        splash.set_status("Preparing…")
        _prepare_sys_path()
        ensure_app_shortcuts(splash)
        ensure_chromium(splash)
        splash.set_status("Loading interface…")
        from src.ui import run_ui

        splash.close()
        splash = None
        run_ui()
        return 0
    except Exception as exc:
        if splash is not None:
            splash.close()
        path = _log_crash(exc)
        _show_error(f"BotEts failed to start.\n\n{exc}\n\nLog saved to:\n{path}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
