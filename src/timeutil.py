"""Horodatage local sans crash si tzdata / ZoneInfo indisponible (Windows)."""

from __future__ import annotations

from datetime import datetime

from loguru import logger


def normalize_timezone_key(raw: str) -> str:
    """Normalise TIMEZONE (.env) vers une clé IANA."""
    key = (raw or "").strip()
    if not key:
        return "America/Montreal"
    lowered = key.lower().replace(" ", "_")
    aliases = {
        "america_montreal": "America/Montreal",
        "america/toronto": "America/Toronto",
        "est": "America/Toronto",
        "edt": "America/Toronto",
    }
    return aliases.get(lowered, key.replace(" ", "_") if " " in key else key)


def local_timestamp(timezone_key: str) -> str:
    """
    Retourne un horodatage lisible. Ne lève jamais :
    ZoneInfo + tzdata → heure Montréal ; sinon heure locale système.
    """
    iana = normalize_timezone_key(timezone_key)
    try:
        from zoneinfo import ZoneInfo

        tz = ZoneInfo(iana)
        return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception as e:
        logger.debug("ZoneInfo indisponible pour {iana}: {e}", iana=iana, e=e)
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S (local)")
