"""Petite fenêtre pour choisir les cours et lancer un bot par cours."""

from __future__ import annotations

import multiprocessing as mp
import re
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.catalog import (
    close_catalog_browser,
    extract_sigles,
    fetch_accessible_courses,
    launcher_state_path,
    load_launcher_state,
    save_launcher_state,
)
from src.config_loader import config_with_bots, load_config
from src.main import run_multi_bot

_SIGLE_OK = re.compile(r"^[A-Z]{3}\d{3}$")


def _logo_path() -> Path:
    from src.paths import resource_root

    return resource_root() / "assets" / "logo.png"


class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("BotEts")
        self.root.minsize(440, 520)
        self.root.configure(bg="#f4f5f7")
        self._logo_image = None

        self.config = load_config()
        self.state_path = launcher_state_path(self.config)
        saved_sigles, saved_bots = load_launcher_state(self.state_path)
        # Pas de bots pré-remplis — l'utilisateur ajoute.
        self.sigles = list(saved_sigles)
        self.bots: list[tuple[str, bool]] = list(saved_bots)

        self._procs: list = []
        self._busy = False

        self.status = tk.StringVar(
            value="Load courses, type a code (autocomplete), Add bot, then Start."
        )
        self.auto_var = tk.BooleanVar(value=True)
        self.course_var = tk.StringVar(value="")

        self._apply_window_icon()
        self._build()
        self._refresh_bots()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_window_icon(self) -> None:
        logo = _logo_path()
        if not logo.is_file():
            return
        try:
            self._logo_image = tk.PhotoImage(file=str(logo))
            self.root.iconphoto(True, self._logo_image)
        except tk.TclError:
            self._logo_image = None

    def _build(self) -> None:
        pad = {"padx": 12, "pady": 4}
        frame = ttk.Frame(self.root, padding=12)
        frame.pack(fill="both", expand=True)

        header = ttk.Frame(frame)
        header.pack(fill="x", pady=(0, 10))

        logo_file = _logo_path()
        if logo_file.is_file():
            try:
                raw = tk.PhotoImage(file=str(logo_file))
                # Keep a reasonable header size
                scale = max(1, raw.width() // 120)
                self._header_logo = raw.subsample(scale, scale) if scale > 1 else raw
                ttk.Label(header, image=self._header_logo).pack()
            except tk.TclError:
                self._header_logo = None
        else:
            self._header_logo = None

        ttk.Label(header, text="BotEts", font=("Segoe UI", 22, "bold")).pack(pady=(8, 0))
        ttk.Label(
            header,
            text="Type a course code to search. Unknown codes can still be added.",
            wraplength=400,
            justify="center",
        ).pack(pady=(4, 0))

        self.load_btn = ttk.Button(frame, text="Load my courses", command=self._on_load)
        self.load_btn.pack(anchor="w", **pad)

        row = ttk.Frame(frame)
        row.pack(fill="x", **pad)
        ttk.Label(row, text="Course").pack(side="left")
        self.course_box = ttk.Combobox(
            row,
            textvariable=self.course_var,
            values=self.sigles,
            width=18,
        )
        self.course_box.pack(side="left", padx=(8, 0))
        # Filter only when opening the list — updating values on each key
        # steals focus / interrupts typing on Windows.
        self.course_box.bind("<Button-1>", self._on_course_dropdown)
        self.course_box.bind("<Down>", self._on_course_dropdown)
        self.course_box.bind("<Return>", lambda _e: self._on_add())

        ttk.Checkbutton(
            frame,
            text="Auto-register (first open group)",
            variable=self.auto_var,
        ).pack(anchor="w", **pad)

        ttk.Button(frame, text="Add bot", command=self._on_add).pack(anchor="w", **pad)

        ttk.Label(frame, text="Bots").pack(anchor="w", padx=12, pady=(8, 0))
        self.bot_list = tk.Listbox(frame, height=8, activestyle="dotbox")
        self.bot_list.pack(fill="both", expand=True, padx=12, pady=4)
        ttk.Button(frame, text="Remove", command=self._on_remove).pack(anchor="w", **pad)

        actions = ttk.Frame(frame)
        actions.pack(fill="x", **pad)
        self.start_btn = ttk.Button(actions, text="Start", command=self._on_start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(actions, text="Stop", command=self._on_stop)
        self.stop_btn.pack(side="left", padx=8)
        self.stop_btn.state(["disabled"])

        ttk.Label(frame, textvariable=self.status, wraplength=390).pack(anchor="w", padx=12, pady=(8, 0))

    def _filter_suggestions(self, typed: str) -> list[str]:
        query = typed.strip().upper()
        if not query:
            return list(self.sigles)
        return [sigle for sigle in self.sigles if query in sigle]

    def _on_course_dropdown(self, event=None) -> None:
        matches = self._filter_suggestions(self.course_var.get())
        self.course_box.configure(values=matches or list(self.sigles))

    def _refresh_bots(self) -> None:
        self.bot_list.delete(0, "end")
        for sigle, auto in self.bots:
            mode = "auto-register" if auto else "alert only"
            self.bot_list.insert("end", f"{sigle}    {mode}")
        self.course_box.configure(values=list(self.sigles))

    def _persist(self) -> None:
        save_launcher_state(self.state_path, self.sigles, self.bots)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = ["disabled"] if busy else ["!disabled"]
        self.load_btn.state(state)
        self.start_btn.state(state)

    def _on_load(self) -> None:
        if self._busy:
            return
        self._set_busy(True)
        self.status.set("Loading courses from Cheminot…")

        def work() -> None:
            try:
                result = fetch_accessible_courses(self.config)
            except Exception as exc:
                message = f"Could not open Cheminot: {exc}"
                self.root.after(0, lambda m=message: self._load_done([], m))
                return
            self.root.after(0, lambda: self._load_done(result.sigles, result.message))

        threading.Thread(target=work, daemon=True).start()

    def _load_done(self, sigles: list[str], message: str) -> None:
        if sigles:
            # Remplace la liste (pas de fusion avec d'anciens cours déjà pris)
            self.sigles = list(sigles)
            self.course_var.set("")
            self._persist()
        self.status.set(message)
        self._refresh_bots()
        self._set_busy(False)

    def _on_add(self) -> None:
        raw = self.course_var.get().strip().upper()
        found = extract_sigles(raw)
        sigle = found[0] if found else raw
        if not _SIGLE_OK.match(sigle):
            self.status.set("Enter a course code like LOG200.")
            return
        if any(existing == sigle for existing, _auto in self.bots):
            self.status.set(f"{sigle} is already in the list.")
            return
        known = sigle in self.sigles
        self.bots.append((sigle, bool(self.auto_var.get())))
        if not known:
            self.sigles.append(sigle)
            self.sigles.sort()
        self.course_var.set("")
        self._persist()
        self._refresh_bots()
        mode = "auto-register" if self.auto_var.get() else "alert only"
        if known:
            self.status.set(f"Added {sigle} ({mode}).")
        else:
            self.status.set(f"Added {sigle} ({mode}) — not in loaded list, trusted.")

    def _on_remove(self) -> None:
        selection = self.bot_list.curselection()
        if not selection:
            return
        del self.bots[selection[0]]
        self._persist()
        self._refresh_bots()

    def _on_start(self) -> None:
        if self._busy or not self.bots:
            if not self.bots:
                self.status.set("Add at least one bot.")
            return
        try:
            config = config_with_bots(self.config, self.bots)
        except ValueError as exc:
            self.status.set(str(exc))
            return
        self._procs.clear()
        self._set_busy(True)
        self.stop_btn.state(["!disabled"])
        self.status.set("Starting bots…")

        def work() -> None:
            try:
                run_multi_bot(config, procs_out=self._procs)
            except Exception as exc:
                message = f"Bots stopped: {exc}"
                self.root.after(0, lambda m=message: self.status.set(m))
            finally:
                self.root.after(0, self._on_bots_finished)

        threading.Thread(target=work, daemon=True).start()

    def _on_stop(self) -> None:
        for proc in list(self._procs):
            if proc.is_alive():
                proc.terminate()
        self.status.set("Stopping bots…")

    def _on_bots_finished(self) -> None:
        self.stop_btn.state(["disabled"])
        self._set_busy(False)
        if "Stopping" not in self.status.get():
            self.status.set("Bots finished. Close the Chrome windows when you are done.")

    def _on_close(self) -> None:
        self._on_stop()
        close_catalog_browser()
        self.root.destroy()


def run_ui() -> None:
    root = tk.Tk()
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    LauncherApp(root)
    root.mainloop()


if __name__ == "__main__":
    mp.freeze_support()
    run_ui()
