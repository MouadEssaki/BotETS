"""Notifications téléphone — Telegram et ntfy."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from loguru import logger

from src.config_loader import AppConfig, NotificationsConfig


def _ascii_header(value: str) -> str:
    """En-têtes HTTP = latin-1 seulement (évite crash sur —, accents, etc.)."""
    text = value.replace("\u2014", "-").replace("\u2013", "-")
    return text.encode("ascii", "replace").decode("ascii")


def _post_json(url: str, payload: dict, headers: dict | None = None) -> bool:
    data = json.dumps(payload).encode("utf-8")
    req_headers = {"Content-Type": "application/json"}
    if headers:
        req_headers.update(headers)
    request = urllib.request.Request(url, data=data, headers=req_headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        logger.warning("Notification HTTP {code}: {body}", code=e.code, body=e.read()[:500])
        return False
    except Exception as e:
        logger.warning("Notification échouée: {e}", e=e)
        return False


def _send_ntfy(title: str, message: str, notif: NotificationsConfig) -> bool:
    topic = notif.ntfy_topic.strip()
    if not topic:
        return False
    base = notif.ntfy_server.rstrip("/")
    from urllib.parse import quote

    url = f"{base}/{quote(topic, safe='')}"
    body = f"{title}\n\n{message}" if title else message
    headers = {
        "Title": _ascii_header(title)[:200],
        "Priority": _ascii_header(notif.ntfy_priority),
        "Tags": "bell",
        "Content-Type": "text/plain; charset=utf-8",
    }
    data = body.encode("utf-8")
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            ok = 200 <= resp.status < 300
            if ok:
                logger.info("Notification ntfy envoyée (topic {topic})", topic=topic)
            return ok
    except urllib.error.HTTPError as e:
        body_err = e.read()[:300] if e.fp else b""
        logger.warning("ntfy HTTP {code}: {err}", code=e.code, err=body_err)
        return False
    except Exception as e:
        logger.warning("ntfy échoué: {e}", e=e)
        return False


def _send_telegram(title: str, message: str, notif: NotificationsConfig) -> bool:
    token = notif.telegram_bot_token.strip()
    chat_id = notif.telegram_chat_id.strip()
    if not token or not chat_id:
        return False
    text = f"{title}\n\n{message}"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    ok = _post_json(url, payload)
    if ok:
        logger.info("Notification Telegram envoyée")
    return ok


def notify_place_available(course_label: str, detail: str, config: AppConfig) -> None:
    """Envoie une notification sur le téléphone si configuré."""
    notif = config.notifications
    if not notif.enabled:
        return
    if not notif.has_any_provider():
        logger.debug("Notifications activées mais aucun fournisseur configuré (.env)")
        return

    title = f"Cheminot - place {course_label}"
    message = detail or f"AJOUTER+ actif pour {course_label}. Ouvrez Cheminot sur votre PC."

    sent = False
    if notif.ntfy_topic:
        sent = _send_ntfy(title, message, notif) or sent
    if notif.telegram_bot_token and notif.telegram_chat_id:
        sent = _send_telegram(title, message, notif) or sent

    if not sent:
        logger.warning("Aucune notification téléphone n'a pu être envoyée")
