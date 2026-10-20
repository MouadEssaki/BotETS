"""Installe BotEts en app Windows (dossier local + raccourcis Recherche / Bureau)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from src.paths import is_frozen, resource_root, user_data_dir


def installed_exe_path() -> Path:
    return user_data_dir() / "BotEts.exe"


def app_version() -> str:
    """Version livrée dans l'exe (fichier VERSION)."""
    for base in (resource_root(), Path(__file__).resolve().parent.parent):
        path = base / "VERSION"
        if path.is_file():
            return path.read_text(encoding="utf-8").strip() or "0.0.0"
    return "0.0.0"


def installed_version(install_dir: Path | None = None) -> str | None:
    path = (install_dir or user_data_dir()) / "VERSION"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _write_installed_version(install_dir: Path, version: str) -> None:
    (install_dir / "VERSION").write_text(version + "\n", encoding="utf-8")


def _known_folder(name: str) -> Path | None:
    """Desktop / Start Menu via PowerShell (noms localisés OK)."""
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"[Environment]::GetFolderPath('{name}')",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        text = (completed.stdout or "").strip()
        if text:
            return Path(text)
    except Exception:
        pass
    return None


def _create_shortcut(lnk: Path, target: Path, workdir: Path, icon: Path) -> None:
    lnk.parent.mkdir(parents=True, exist_ok=True)
    icon_path = icon if icon.is_file() else target
    # Escape single quotes for PowerShell single-quoted strings
    def q(p: Path) -> str:
        return str(p).replace("'", "''")

    script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{q(lnk)}'); "
        f"$s.TargetPath = '{q(target)}'; "
        f"$s.WorkingDirectory = '{q(workdir)}'; "
        f"$s.IconLocation = '{q(icon_path)}'; "
        "$s.Description = 'BotEts — surveillance Cheminot ÉTS'; "
        "$s.Save()"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            (completed.stderr or completed.stdout or "shortcut failed").strip()
        )


def _copy_icon(install_dir: Path) -> Path:
    dest = install_dir / "logo.ico"
    for name in ("logo.ico", "logo.png"):
        src = resource_root() / "assets" / name
        if not src.is_file():
            continue
        if name == "logo.ico":
            shutil.copy2(src, dest)
            return dest
        # Fallback: keep png for UI; shortcut can still point at exe
    return dest if dest.is_file() else install_dir / "BotEts.exe"


def ensure_windows_app(status_cb=None) -> Path | None:
    """
    Copie l'exe dans %LOCALAPPDATA%\\BotEts et crée les raccourcis
    Menu Démarrer + Bureau (apparaît dans la recherche Windows).

    Retourne le chemin de l'exe installé, ou None hors mode gelé.
    """
    if not is_frozen():
        return None

    def status(msg: str) -> None:
        if status_cb:
            status_cb(msg)

    install_dir = user_data_dir()
    installed = installed_exe_path()
    current = Path(sys.executable).resolve()
    version = app_version()
    prev = installed_version(install_dir)

    try:
        already_installed = current == installed.resolve()
    except OSError:
        already_installed = False

    # Nouveau téléchargement GitHub → remplace l'exe installé (mise à jour manuelle)
    if not already_installed:
        if prev and prev != version:
            status(f"Updating BotEts {prev} → {version}…")
        elif installed.is_file():
            status(f"Updating BotEts to {version}…")
        else:
            status(f"Installing BotEts {version}…")
        install_dir.mkdir(parents=True, exist_ok=True)
        # Copy to a temp name then replace (safer if antivirus locks the target)
        tmp = install_dir / "BotEts.exe.new"
        shutil.copy2(current, tmp)
        tmp.replace(installed)
        _write_installed_version(install_dir, version)
    elif prev != version:
        # Lancé depuis l'emplacement installé après rebuild / self-replace
        _write_installed_version(install_dir, version)

    icon = _copy_icon(install_dir)

    status("Adding Start Menu shortcut…")
    programs = _known_folder("Programs")
    if programs is None:
        programs = (
            Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
            / "Microsoft"
            / "Windows"
            / "Start Menu"
            / "Programs"
        )
    _create_shortcut(
        programs / "BotEts.lnk",
        installed,
        install_dir,
        icon if icon.suffix.lower() == ".ico" else installed,
    )

    desktop = _known_folder("Desktop")
    if desktop is not None:
        _create_shortcut(
            desktop / "BotEts.lnk",
            installed,
            install_dir,
            icon if icon.suffix.lower() == ".ico" else installed,
        )

    # App Paths: typing BotEts in Win+R / some search cases
    try:
        import winreg

        key_path = r"Software\Microsoft\Windows\CurrentVersion\App Paths\BotEts.exe"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, None, 0, winreg.REG_SZ, str(installed))
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, str(install_dir))
    except Exception:
        pass

    return installed
