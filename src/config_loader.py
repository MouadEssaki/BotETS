"""Chargement de la configuration YAML et .env."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


@dataclass
class CourseConfig:
    sigle: str
    section: str
    session: str
    label: str
    group_mode: str  # any | first | exact
    auto_register: bool = False

    def has_exact_section(self) -> bool:
        return bool(self.section.strip()) and self.group_mode == "exact"

    def wants_any_group(self) -> bool:
        return self.group_mode in ("any", "first") or not self.section.strip()


@dataclass
class DelaysConfig:
    min_seconds: float
    max_seconds: float
    jitter_min_seconds: float
    jitter_max_seconds: float


@dataclass
class LoginConfig:
    manual_wait_seconds: int
    storage_state_path: str
    login_url_keywords: list[str]


@dataclass
class SelectorsConfig:
    logged_in: str
    logged_out: str
    course_row: str
    status_available: str
    status_full: str
    full_text_patterns: list[str]
    available_text_patterns: list[str]
    popup_close: str


@dataclass
class AlarmConfig:
    beep_frequency: int
    beep_duration_ms: int
    repeat: int
    wav_path: str


@dataclass
class NotificationsConfig:
    enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    ntfy_server: str
    ntfy_topic: str
    ntfy_priority: str

    def has_any_provider(self) -> bool:
        if self.telegram_bot_token.strip() and self.telegram_chat_id.strip():
            return True
        return bool(self.ntfy_topic.strip())


@dataclass
class PathsConfig:
    logs_dir: str
    screenshots_dir: str


@dataclass
class BrowserConfig:
    keep_open: bool
    stop_on_alarm: bool
    multi_bot: bool = False


@dataclass
class NavigationConfig:
    home_url: str
    consultation_url: str
    inscription_url: str
    horaire_url: str
    session_card_text: str
    session_label: str
    select_session_button_text: str
    select_session_button: str
    inscription_tab_text: str
    inscription_tab_selector: str
    course_node_text: str
    course_node_selector: str
    full_modal_text: str
    no_group_text: str
    options_panel_text: str
    add_button_text: str
    save_button_text: str
    modal_ok_text: str
    group_row_selector: str
    renavigate_each_cycle: bool
    # manual_clicks = vous naviguez au départ, le bot clique inscription + cours ensuite
    # auto = parcours automatisé depuis l'accueil (goto URL)
    mode: str
    manual_setup_seconds: int
    manual_finish_on_enter: bool
    reload_on_horaire_before_cycle: bool

    def course_node_label(self, sigle: str) -> str:
        return self.course_node_text.strip() or sigle

    def uses_manual_clicks(self) -> bool:
        return self.mode.strip().lower() in ("manual_clicks", "manual", "clicks")


@dataclass
class AppConfig:
    portal_url: str
    target_url: str
    course: CourseConfig
    courses: list[CourseConfig]
    navigation: NavigationConfig
    delays: DelaysConfig
    login: LoginConfig
    selectors: SelectorsConfig
    alarm: AlarmConfig
    notifications: NotificationsConfig
    paths: PathsConfig
    browser: BrowserConfig
    log_level: str
    timezone: str
    project_root: Path = field(default_factory=Path.cwd)
    is_worker: bool = False

    def courses_to_watch(self) -> list[CourseConfig]:
        return self.courses if self.courses else [self.course]

    def storage_state_path(self) -> Path:
        return self.project_root / self.login.storage_state_path

    def logs_dir(self) -> Path:
        p = self.project_root / self.paths.logs_dir
        p.mkdir(parents=True, exist_ok=True)
        return p

    def screenshots_dir(self) -> Path:
        p = self.project_root / self.paths.screenshots_dir
        p.mkdir(parents=True, exist_ok=True)
        return p


def _get(d: dict[str, Any], key: str, default: Any = None) -> Any:
    return d.get(key, default) if d else default


def _resolve_course_config(course_raw: dict[str, Any]) -> CourseConfig:
    sigle = _get(course_raw, "sigle", "COURS")
    section = (_get(course_raw, "section", "") or "").strip()
    group_mode = (_get(course_raw, "group_mode", "") or "").strip().lower()
    if not group_mode:
        group_mode = "exact" if section else "any"
    label = _get(course_raw, "label") or (f"{sigle}-{section}" if section else sigle)
    return CourseConfig(
        sigle=sigle,
        section=section,
        session=_get(course_raw, "session", ""),
        label=label,
        group_mode=group_mode,
        auto_register=bool(_get(course_raw, "auto_register", False)),
    )


def _safe_sigle(sigle: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", sigle.strip())
    return cleaned or "course"


def worker_storage_filename(sigle: str) -> str:
    """Fichier de session propre à un bot de cours (évite les écritures concurrentes)."""
    return f"storage_state_{_safe_sigle(sigle)}.json"


def config_with_bots(config: AppConfig, bots: list[tuple[str, bool]]) -> AppConfig:
    """Remplace la liste de cours par les bots choisis dans l'interface."""
    if not bots:
        raise ValueError("Ajoutez au moins un cours")
    session = config.navigation.session_label or config.course.session
    courses: list[CourseConfig] = []
    seen: set[str] = set()
    for sigle, auto_register in bots:
        code = sigle.strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        courses.append(
            CourseConfig(
                sigle=code,
                section="",
                session=session,
                label=code,
                group_mode="any",
                auto_register=bool(auto_register),
            )
        )
    if not courses:
        raise ValueError("Ajoutez au moins un cours")
    return replace(
        config,
        course=courses[0],
        courses=courses,
        browser=replace(config.browser, multi_bot=True),
        navigation=replace(config.navigation, mode="auto"),
    )


def isolate_course(config: AppConfig, sigle: str, *, as_worker: bool) -> AppConfig:
    """Réduit la config à un seul cours. Un worker a sa propre copie de session."""
    wanted = sigle.strip().upper()
    matches = [c for c in config.courses_to_watch() if c.sigle.upper() == wanted]
    if not matches:
        known = ", ".join(c.sigle for c in config.courses_to_watch()) or "(aucun)"
        raise ValueError(f"Cours introuvable: {sigle} (config: {known})")

    course = matches[0]
    login = config.login
    navigation = config.navigation
    if as_worker:
        login = replace(login, storage_state_path=worker_storage_filename(course.sigle))
        # Workers always navigate alone — never wait for "Window ready"
        navigation = replace(navigation, mode="auto")
    return replace(
        config,
        course=course,
        courses=[course],
        login=login,
        navigation=navigation,
        is_worker=as_worker,
    )


def _resolve_timezone() -> str:
    from src.timeutil import normalize_timezone_key

    return normalize_timezone_key(os.getenv("TIMEZONE", "America/Montreal"))


def _resolve_notifications(raw: dict[str, Any]) -> NotificationsConfig:
    enabled_yaml = bool(_get(raw, "enabled", True))
    token = os.getenv("TELEGRAM_BOT_TOKEN", "") or ""
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "") or ""
    ntfy_topic = os.getenv("NTFY_TOPIC", "") or ""
    has_credentials = bool((token and chat_id) or ntfy_topic)
    return NotificationsConfig(
        enabled=enabled_yaml and has_credentials,
        telegram_bot_token=token,
        telegram_chat_id=chat_id,
        ntfy_server=os.getenv("NTFY_SERVER", "https://ntfy.sh") or "https://ntfy.sh",
        ntfy_topic=ntfy_topic,
        ntfy_priority=os.getenv("NTFY_PRIORITY", "urgent") or "urgent",
    )


def load_config(config_path: Path | None = None) -> AppConfig:
    root = Path(__file__).resolve().parent.parent
    if config_path is None:
        config_path = root / "config.yaml"

    load_dotenv(root / ".env")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    course_raw = _get(raw, "course", {}) or {}
    courses_raw = _get(raw, "courses", None)
    browser_raw = _get(raw, "browser", {}) or {}
    delays_raw = _get(raw, "delays", {}) or {}
    login_raw = _get(raw, "login", {}) or {}
    selectors_raw = _get(raw, "selectors", {}) or {}
    alarm_raw = _get(raw, "alarm", {}) or {}
    notifications_raw = _get(raw, "notifications", {}) or {}
    paths_raw = _get(raw, "paths", {}) or {}
    nav_raw = _get(raw, "navigation", {}) or {}

    course = _resolve_course_config(course_raw)
    if courses_raw and isinstance(courses_raw, list):
        courses = [_resolve_course_config(c or {}) for c in courses_raw]
    else:
        courses = [course]

    horaire_url = _get(nav_raw, "horaire_url", "https://cheminotn.etsmtl.ca/horaire")
    home_url = _get(nav_raw, "home_url", "https://cheminotn.etsmtl.ca")

    return AppConfig(
        portal_url=_get(raw, "portal_url", home_url),
        target_url=_get(raw, "target_url", horaire_url),
        navigation=NavigationConfig(
            home_url=home_url,
            consultation_url=_get(nav_raw, "consultation_url", "https://cheminotn.etsmtl.ca/consultation"),
            inscription_url=_get(nav_raw, "inscription_url", "https://cheminotn.etsmtl.ca/inscription"),
            horaire_url=horaire_url,
            session_card_text=_get(nav_raw, "session_card_text", "Inscription et consultation"),
            session_label=_get(nav_raw, "session_label", "Automne 2026"),
            select_session_button_text=_get(nav_raw, "select_session_button_text", "SÉLECTIONNER CETTE SESSION"),
            select_session_button=_get(nav_raw, "select_session_button", "") or "",
            inscription_tab_text=_get(nav_raw, "inscription_tab_text", "INSCRIPTION AUTOMNE 2026"),
            inscription_tab_selector=_get(nav_raw, "inscription_tab_selector", "") or "",
            course_node_text=_get(nav_raw, "course_node_text", "") or "",
            course_node_selector=_get(nav_raw, "course_node_selector", "") or "",
            full_modal_text=_get(
                nav_raw,
                "full_modal_text",
                "Tous les groupes de ce cours sont actuellement complets",
            ),
            no_group_text=_get(nav_raw, "no_group_text", "Aucun choix de groupe disponible"),
            options_panel_text=_get(
                nav_raw,
                "options_panel_text",
                "Options d'horaires pour le cours sélectionné",
            ),
            add_button_text=_get(nav_raw, "add_button_text", "AJOUTER"),
            save_button_text=_get(nav_raw, "save_button_text", "SAUVEGARDER"),
            modal_ok_text=_get(nav_raw, "modal_ok_text", "OK"),
            group_row_selector=_get(nav_raw, "group_row_selector", "") or "",
            renavigate_each_cycle=bool(_get(nav_raw, "renavigate_each_cycle", False)),
            mode=_get(nav_raw, "mode", "manual_clicks"),
            manual_setup_seconds=int(_get(nav_raw, "manual_setup_seconds", 30)),
            manual_finish_on_enter=bool(_get(nav_raw, "manual_finish_on_enter", True)),
            reload_on_horaire_before_cycle=bool(
                _get(nav_raw, "reload_on_horaire_before_cycle", True)
            ),
        ),
        course=courses[0],
        courses=courses,
        delays=DelaysConfig(
            min_seconds=float(_get(delays_raw, "min_seconds", 180)),
            max_seconds=float(_get(delays_raw, "max_seconds", 300)),
            jitter_min_seconds=float(_get(delays_raw, "jitter_min_seconds", 5)),
            jitter_max_seconds=float(_get(delays_raw, "jitter_max_seconds", 15)),
        ),
        login=LoginConfig(
            manual_wait_seconds=int(_get(login_raw, "manual_wait_seconds", 75)),
            storage_state_path=_get(login_raw, "storage_state_path", "storage_state.json"),
            login_url_keywords=list(
                _get(login_raw, "login_url_keywords", ["login", "microsoft", "adfs", "oauth", "signin"])
            ),
        ),
        selectors=SelectorsConfig(
            logged_in=_get(selectors_raw, "logged_in", "") or "",
            logged_out=_get(selectors_raw, "logged_out", "") or "",
            course_row=_get(selectors_raw, "course_row", "") or "",
            status_available=_get(selectors_raw, "status_available", "") or "",
            status_full=_get(selectors_raw, "status_full", "") or "",
            full_text_patterns=list(
                _get(selectors_raw, "full_text_patterns", ["complet", "aucune place", "0 place"])
            ),
            available_text_patterns=list(
                _get(selectors_raw, "available_text_patterns", ["s'inscrire", "inscrire"])
            ),
            popup_close=_get(selectors_raw, "popup_close", "") or "",
        ),
        alarm=AlarmConfig(
            beep_frequency=int(_get(alarm_raw, "beep_frequency", 1000)),
            beep_duration_ms=int(_get(alarm_raw, "beep_duration_ms", 500)),
            repeat=int(_get(alarm_raw, "repeat", 10)),
            wav_path=_get(alarm_raw, "wav_path", "") or "",
        ),
        notifications=_resolve_notifications(notifications_raw),
        paths=PathsConfig(
            logs_dir=_get(paths_raw, "logs_dir", "logs"),
            screenshots_dir=_get(paths_raw, "screenshots_dir", "screenshots"),
        ),
        browser=BrowserConfig(
            keep_open=bool(_get(browser_raw, "keep_open", True)),
            stop_on_alarm=bool(_get(browser_raw, "stop_on_alarm", False)),
            multi_bot=bool(_get(browser_raw, "multi_bot", False)),
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        timezone=_resolve_timezone(),
        project_root=root,
    )
