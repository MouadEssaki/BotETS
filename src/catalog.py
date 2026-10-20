"""Sigles visibles sur Cheminot après connexion (le site public est la page Microsoft)."""

from __future__ import annotations

import json
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from src.config_loader import AppConfig

_SIGLE_RE = re.compile(r"\b([A-Za-z]{3}\d{3})\b")


@dataclass
class CatalogResult:
    sigles: list[str]
    message: str


def extract_sigles(text: str) -> list[str]:
    """Retourne les sigles ÉTS (3 lettres + 3 chiffres), sans doublon, dans l'ordre."""
    seen: list[str] = []
    for match in _SIGLE_RE.finditer(text):
        sigle = match.group(1).upper()
        if sigle not in seen:
            seen.append(sigle)
    return seen


def launcher_state_path(config: AppConfig) -> Path:
    return config.project_root / "launcher.json"


def load_launcher_state(path: Path) -> tuple[list[str], list[tuple[str, bool]]]:
    if not path.is_file():
        return [], []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], []
    sigles = extract_sigles(" ".join(raw.get("sigles") or []))
    bots: list[tuple[str, bool]] = []
    for item in raw.get("bots") or []:
        code = str(item.get("sigle", "")).strip().upper()
        if not re.fullmatch(r"[A-Z]{3}\d{3}", code):
            continue
        bots.append((code, bool(item.get("auto_register"))))
    return sigles, bots


def save_launcher_state(path: Path, sigles: list[str], bots: list[tuple[str, bool]]) -> None:
    payload = {
        "sigles": sigles,
        "bots": [{"sigle": sigle, "auto_register": auto} for sigle, auto in bots],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _read_course_text(page) -> str:
    """Lit le texte visible, y compris les nœuds dans un shadow DOM."""
    deadline = time.time() + 12
    last = ""
    script = """() => {
        const chunks = [];
        const collect = (root) => {
            if (!root) return;
            if (root.innerText) chunks.push(root.innerText);
            const nodes = root.querySelectorAll ? root.querySelectorAll("*") : [];
            for (const el of nodes) {
                const label = el.getAttribute && (el.getAttribute("aria-label") || el.getAttribute("title"));
                if (label) chunks.push(label);
                if (el.shadowRoot) collect(el.shadowRoot);
            }
        };
        collect(document.body);
        return chunks.join("\\n");
    }"""
    while time.time() < deadline:
        try:
            last = page.evaluate(script) or ""
        except Exception:
            last = ""
        if extract_sigles(last):
            return last
        try:
            page.wait_for_timeout(500)
        except Exception:
            time.sleep(0.5)
    return last


def _wait_for_login_here(page, config: AppConfig, session) -> None:
    """Attend le MFA sans quitter la page ouverte."""
    from src.session import is_logged_in, url_indicates_login

    if is_logged_in(page, config) and not url_indicates_login(page, config):
        return
    wait = config.login.manual_wait_seconds
    logger.info("Connexion Microsoft — la fenêtre reste sur cette page ({wait}s)", wait=wait)
    deadline = time.time() + wait
    while time.time() < deadline:
        if is_logged_in(page, config) and not url_indicates_login(page, config):
            session.save_storage_state()
            return
        time.sleep(2)
    session.save_storage_state()


def _section_between(text: str, start_marker: str, end_markers: tuple[str, ...]) -> str:
    lowered = text.lower()
    start = lowered.find(start_marker.lower())
    if start < 0:
        return ""
    chunk = text[start:]
    chunk_lower = chunk.lower()
    end = len(chunk)
    for marker in end_markers:
        pos = chunk_lower.find(marker.lower())
        if pos >= 0:
            end = min(end, pos)
    return chunk[:end]


def taken_sigles(text: str) -> list[str]:
    """Cours d'intégration / obligatoires déjà sur le cheminement (souvent déjà faits)."""
    chunks = [
        _section_between(text, "cours d'intégration", ("cours obligatoire", "cours de concentration", "cours offerts")),
        _section_between(text, "cours obligatoire", ("cours de concentration", "cours offerts", "cheminement")),
    ]
    seen: list[str] = []
    for chunk in chunks:
        for sigle in extract_sigles(chunk):
            if sigle not in seen:
                seen.append(sigle)
    return seen


def offered_sigles(text: str) -> list[str]:
    """Uniquement « Cours offerts à la prochaine session », sans les cours déjà pris."""
    chunk = _section_between(
        text,
        "cours offerts",
        ("cours hors", "hors-cheminement", "panier"),
    )
    if not chunk:
        # Pas de repli sur toute la page : ça mélangeait les cours déjà réussis.
        return []
    offered = extract_sigles(chunk)
    taken = set(taken_sigles(text))
    return [sigle for sigle in offered if sigle not in taken]


def _load_on_page(session, config: AppConfig) -> CatalogResult:
    from src.navigation import ensure_inscription_catalog_page
    from src.session import url_indicates_login

    page = session.page
    assert page is not None
    page.goto(config.portal_url, wait_until="domcontentloaded", timeout=60000)
    if url_indicates_login(page, config):
        _wait_for_login_here(page, config, session)
    if url_indicates_login(page, config):
        return CatalogResult([], "Sign in in the Cheminot window. It stays open.")
    if not ensure_inscription_catalog_page(page, config):
        return CatalogResult(
            [],
            f"Could not open the course list (still on {page.url}). Try Load again after sign-in.",
        )
    text = _read_course_text(page)
    sigles = offered_sigles(text)
    skipped = len(set(taken_sigles(text)) & set(extract_sigles(
        _section_between(text, "cours offerts", ("cours hors", "hors-cheminement", "panier"))
    )))
    session.save_storage_state()
    if not sigles:
        return CatalogResult([], f"On {page.url} but no offered course codes were found.")
    closed = "inscription est ferm" in text.lower()
    message = f"OK — loaded {len(sigles)} available courses."
    if skipped:
        message += f" Hid {skipped} already in your path."
    if closed:
        message += " Registration is closed for now; you can still pick courses."
    return CatalogResult(sigles, message)


class _CatalogBrowser:
    """Un seul Chrome pour le chargement des cours. Il ne se ferme pas après le goto."""

    def __init__(self) -> None:
        self._commands: queue.Queue = queue.Queue()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def load(self, config: AppConfig) -> CatalogResult:
        self._ensure_thread()
        reply: queue.Queue = queue.Queue(maxsize=1)
        self._commands.put(("load", config, reply))
        return reply.get()

    def stop(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            return
        reply: queue.Queue = queue.Queue(maxsize=1)
        self._commands.put(("stop", None, reply))
        try:
            reply.get(timeout=5)
        except queue.Empty:
            pass

    def _ensure_thread(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._loop, name="catalog-browser", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        from src.browser import BrowserSession

        session = None
        while True:
            command, config, reply = self._commands.get()
            if command == "stop":
                if session is not None:
                    session.stop()
                    session = None
                reply.put(None)
                return
            try:
                if session is None:
                    session = BrowserSession(config)
                    session.start()
                reply.put(_load_on_page(session, config))
            except Exception as exc:
                logger.warning("Chargement des cours échoué: {e}", e=exc)
                reply.put(CatalogResult([], f"Could not open /inscription: {exc}"))


_catalog_browser = _CatalogBrowser()


def fetch_accessible_courses(config: AppConfig) -> CatalogResult:
    """Ouvre /inscription une fois et laisse la fenêtre ouverte."""
    return _catalog_browser.load(config)


def close_catalog_browser() -> None:
    _catalog_browser.stop()
