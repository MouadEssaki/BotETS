"""Chemins app (dev) vs exe figé (PyInstaller) vs données utilisateur."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_root() -> Path:
    """Fichiers livrés avec l'app (config, assets, code)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def user_data_dir() -> Path:
    """Fichiers écrits (session, logs, launcher, navigateurs Playwright)."""
    if is_frozen():
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
        path = base / "BotEts"
    else:
        path = resource_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_user_config() -> Path:
    """Copie config.yaml / .env.example dans le dossier utilisateur au premier lancement."""
    data = user_data_dir()
    res = resource_root()
    for name in ("config.yaml",):
        dest = data / name
        src = res / name
        if not dest.is_file() and src.is_file():
            dest.write_bytes(src.read_bytes())
    env_dest = data / ".env"
    env_example = res / ".env.example"
    if not env_dest.is_file() and env_example.is_file():
        env_dest.write_bytes(env_example.read_bytes())
    return data
