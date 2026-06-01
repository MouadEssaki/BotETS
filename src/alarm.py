"""Alarme sonore Windows."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from src.config_loader import AlarmConfig


def trigger(alarm: AlarmConfig) -> None:
    """Déclenche l'alarme (fichier WAV ou bips système)."""
    if sys.platform != "win32":
        logger.warning("Alarme winsound disponible uniquement sur Windows — bip console")
        for _ in range(alarm.repeat):
            print("\a", end="", flush=True)
        return

    import winsound

    wav = alarm.wav_path.strip()
    if wav:
        path = Path(wav)
        if path.is_file():
            for i in range(alarm.repeat):
                winsound.PlaySound(str(path.resolve()), winsound.SND_FILENAME | winsound.SND_ASYNC)
                winsound.PlaySound(None, winsound.SND_PURGE)
                if i < alarm.repeat - 1:
                    import time

                    time.sleep(0.3)
            logger.info("Alarme WAV jouée ({repeat}x)", repeat=alarm.repeat)
            return
        logger.warning("Fichier WAV introuvable: {path}", path=wav)

    for i in range(alarm.repeat):
        winsound.Beep(alarm.beep_frequency, alarm.beep_duration_ms)
        if i < alarm.repeat - 1:
            import time

            time.sleep(0.2)
    logger.info("Alarme Beep jouée ({repeat}x)", repeat=alarm.repeat)
