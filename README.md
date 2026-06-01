# BotETS — Surveillance Cheminot (ÉTS)

Bot Python ([Playwright](https://playwright.dev/python/)) qui surveille [Cheminot](https://cheminotn.etsmtl.ca) pour **plusieurs cours**, détecte quand **AJOUTER+** est actif sur la page horaire, et vous alerte sur **PC** (son) et **téléphone** (ntfy / Telegram).

## Fonctionnalités

- Connexion **MFA manuelle** + sauvegarde de session (`storage_state.json`)
- Mode **manuel** : vous naviguez une fois sur le graphe, le bot enchaîne les **clics** (pas de navigation par URL)
- **Plusieurs cours** par ronde (ex. LOG200, GTI350)
- **Alarme sonore** Windows + notification **ntfy** ou **Telegram**
- Navigateur **reste ouvert** après une alerte
- Intervalle configurable entre les rondes (défaut : **10 s**)

## Déroulement typique

```text
1. Lancement → navigateur Cheminot
2. Pause manuelle (~10 s ou Entrée quand prêt)
   → Vous : MFA, session Automne 2026, onglet INSCRIPTION AUTOMNE 2026 (graphe)
3. Boucle automatique (toutes les 10 s par défaut) :
   Pour chaque cours dans courses: :
     - Clic onglet INSCRIPTION AUTOMNE 2026
     - Clic sur le sigle (LOG200, puis GTI350, …)
     - Si modal « tous les groupes complets » → OK → cours complet
     - Sinon page horaire → si AJOUTER+ actif → ALARME + notification ntfy
4. Vous vous inscrivez manuellement sur le PC (AJOUTER+ → SAUVEGARDER)
```

Le bot **ne s'inscrit pas** à votre place ; il surveille et alerte seulement.

## Prérequis

- Windows 10/11 (alarme `winsound`)
- Python 3.11+
- Compte Cheminot ÉTS (MFA)

## Installation

```powershell
cd c:\Users\mouad\BotETS
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
```

## Configuration

### Cours — [`config.yaml`](config.yaml)

```yaml
courses:
  - sigle: "LOG200"
    section: ""          # vide = n'importe quel groupe
    group_mode: "any"    # any | first | exact
    label: "LOG200"
  - sigle: "GTI350"
    section: ""
    group_mode: "any"
    label: "GTI350"
```

Ajoutez un bloc par cours à surveiller. Pas besoin du numéro de groupe si vous ne le connaissez pas.

### Délais et navigation

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `delays.min_seconds` / `max_seconds` | `10` | Pause entre chaque **ronde** (tous les cours) |
| `navigation.mode` | `manual_clicks` | Vous naviguez au départ ; le bot clique ensuite |
| `navigation.manual_setup_seconds` | `10` | Temps max avant le bot (ou **Entrée** plus tôt) |
| `navigation.manual_finish_on_enter` | `true` | Appuyez sur Entrée dans la console pour démarrer tout de suite |
| `browser.keep_open` | `true` | Chrome reste ouvert après une alerte |
| `browser.stop_on_alarm` | `false` | Continue les autres cours / rondes après une alarme |

Pour l’ancien mode qui ouvre les pages par URL : `navigation.mode: "auto"`.

**Attention :** des délais très courts (10 s) augmentent le risque de limitation par l’ÉTS. Pour un usage plus prudent : `min_seconds: 180`, `max_seconds: 300`.

### Notifications téléphone — [`.env`](.env)

Copiez [`.env.example`](.env.example) vers `.env` (ne jamais committer `.env`).

#### ntfy (recommandé)

1. Installez l’app [ntfy](https://ntfy.sh/) (iOS / Android).
2. Abonnez-vous à un **topic** (ex. `BotEts`) — **même orthographe** que dans `.env`.
3. Dans `.env` :

```env
NTFY_SERVER=https://ntfy.sh
NTFY_TOPIC=BotEts
NTFY_PRIORITY=urgent
```

Test :

```powershell
python -m tests.test_notify
```

#### Telegram (optionnel)

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Voir `.env.example` pour les étapes BotFather / getUpdates.

Dans `config.yaml` : `notifications.enabled: true`.

## Lancement

```powershell
.\.venv\Scripts\Activate.ps1
python -m src.main
```

1. Le navigateur s’ouvre sur Cheminot.
2. Message **PAUSE MANUELLE** : connectez-vous, allez sur **INSCRIPTION AUTOMNE 2026**, puis **Entrée** (ou attendez ~10 s).
3. Le bot tourne ; les logs sont dans `logs/bot.log`.

**Première connexion** : MFA (~60 s dans `login.manual_wait_seconds`). La session est enregistrée dans `storage_state.json`.

**Place détectée** : bip PC, notification ntfy, capture `screenshots/place_available_SIGLE.png`.

## Structure du projet

```text
BotETS/
├── config.yaml          # cours, délais, navigation
├── .env                 # secrets ntfy / Telegram (local)
├── storage_state.json   # session Cheminot (généré, ne pas committer)
├── src/
│   ├── main.py          # point d'entrée
│   ├── monitor.py       # boucle de surveillance
│   ├── navigation.py    # clics inscription → cours → horaire
│   ├── notify.py        # ntfy / Telegram
│   ├── browser.py       # Playwright, pause manuelle
│   └── ...
├── logs/bot.log
└── screenshots/
```

## Tests

```powershell
python -m tests.test_config
python -m tests.test_navigation_config
python -m tests.test_timeutil
python -m tests.test_capacity_parse
python -m tests.test_alarm
python -m tests.test_notify      # envoi test ntfy
```

## Dépannage

| Problème | Piste |
|----------|--------|
| Pas de notification ntfy | `python -m tests.test_notify` ; topic identique dans l’app et `.env` ; voir `logs/bot.log` |
| Navigateur se ferme | `browser.keep_open: true` ; à la fin, Entrée dans la console ferme le script |
| Clic cours échoue | Sigle visible sur le graphe ; `navigation.course_node_selector` (F12) |
| Onglet INSCRIPTION non cliqué | `navigation.inscription_tab_selector` (F12) |
| Statut `unknown` | `screenshots/unknown_*.png` ; voir [`selectors.md`](selectors.md) |
| AJOUTER+ grisé | Normal si déjà inscrit — le bot attend une place **actionnable** |
| Crash timezone | `pip install tzdata` ; `TIMEZONE=America/Montreal` dans `.env` |
| Blocage / déconnexion ÉTS | Augmenter `delays` (ex. 180–300 s) |

## Avertissement

Usage **personnel** uniquement. Respectez les conditions d’utilisation de l’ÉTS. Évitez de surcharger le site (délais trop courts, plusieurs machines sur la même IP).
