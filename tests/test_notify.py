"""Test d'envoi notification ntfy (lit .env)."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from src.config_loader import load_config
from src.notify import notify_place_available


def test_send_ntfy():
    config = load_config()
    if not config.notifications.ntfy_topic:
        print("NTFY_TOPIC vide dans .env — rien a envoyer")
        return
    print(f"Envoi test vers topic: {config.notifications.ntfy_topic}")
    notify_place_available(
        "TEST",
        "Message de test BotETS. Si vous voyez ceci sur ntfy, ca fonctionne.",
        config,
    )
    print("Termine — verifiez l'app ntfy (abonnement au meme topic)")


if __name__ == "__main__":
    test_send_ntfy()
