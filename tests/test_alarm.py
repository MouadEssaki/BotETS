"""Test manuel court — alarme sonore."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.alarm import trigger
from src.config_loader import load_config


def test_alarm_beep():
    config = load_config(_ROOT / "config.yaml")
    # Une seule répétition pour le test
    config.alarm.repeat = 2
    trigger(config.alarm)


if __name__ == "__main__":
    print("Déclenchement alarme (2 bips)...")
    test_alarm_beep()
    print("test_alarm OK")
