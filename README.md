<div align="center">
  <img src="assets/logo.png" alt="BotETS logo" width="180">

  <h1>BotETS</h1>

  <p><strong>Surveillance Cheminot (ÉTS)</strong></p>

  <p>
    <img alt="Version" src="https://img.shields.io/badge/version-1.0.0-0B5FFF?style=for-the-badge">
    <img alt="Python" src="https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white">
    <img alt="Platform" src="https://img.shields.io/badge/platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white">
  </p>
</div>

Bot Python ([Playwright](https://playwright.dev/python/)) qui surveille [Cheminot](https://cheminotn.etsmtl.ca). Par défaut, **un navigateur par cours**. Pour un cours marqué `auto_register`, il choisit **le premier groupe qui a une place** (l'horaire est ignoré), clique **AJOUTER+** puis **SAUVEGARDER**, et vous alerte sur **PC** (son) et **téléphone** (ntfy / Telegram). Les autres cours restent en alerte seulement.

## Fonctionnalités

- Connexion **MFA manuelle** + sauvegarde de session (`storage_state.json`)
- Mode **manuel** : vous naviguez une fois sur le graphe, le bot enchaîne les **clics** (pas de navigation par URL)
- **Un bot par cours** (`browser.multi_bot`) : chaque sigle a son propre navigateur, au lieu d'une seule fenêtre qui passe de cours en cours
- **Inscription auto** par cours (`auto_register: true`) : premier groupe libre, sans tenir compte de l'horaire
- **Alarme sonore** Windows + notification **ntfy** ou **Telegram**
- Navigateur **reste ouvert** après une alerte
- Intervalle configurable entre les rondes (défaut : **10 s**)

## Déroulement typique

```text
1. Lancement
2. S'il n'y a pas encore de session : une fenêtre pour le MFA, puis elle se ferme
3. multi_bot : une fenêtre Chrome par cours
   → Pour chaque fenêtre : graphe INSCRIPTION, puis Entrée dans la console
4. Chaque bot ne s'occupe que de son sigle (il ne passe plus au cours suivant) :
     - Si modal « tous les groupes complets » → cours complet
     - Sinon, si AJOUTER+ est actif :
       - auto_register: true → premier groupe avec une place → AJOUTER+ → SAUVEGARDER → alarme, ce bot s'arrête
       - sinon → alarme seulement, vous cliquez vous-même
```

`auto_register` est **par cours**. Un cours sans ce drapeau n'est jamais inscrit par le bot.

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
    auto_register: true  # inscrit le premier groupe libre (horaire ignoré)
  - sigle: "GTI350"
    section: ""
    group_mode: "any"
    label: "GTI350"
    auto_register: false # alerte seulement
```

Ajoutez un bloc par cours à surveiller. Pas besoin du numéro de groupe si vous ne le connaissez pas.

| `auto_register` | Effet quand AJOUTER+ est actif |
|-----------------|--------------------------------|
| `true` | Clique le premier groupe qui a encore de la place, puis **AJOUTER+** et **SAUVEGARDER**. Si ce groupe est refusé (conflit), le bot essaie le suivant. Ce bot s'arrête après une inscription envoyée. |
| `false` | Alarme et notification seulement. |

`browser.multi_bot: true` lance **un processus et un Chrome par cours** (`logs/bot_LOG200.log`, `logs/bot_GTI350.log`). La session est copiée depuis `storage_state.json`. La console demande ensuite Entrée **pour chaque fenêtre**, une fois le graphe d'inscription affiché. Avec un seul cours, ou avec `python -m src.main --course LOG200`, un seul bot démarre.

### Délais et navigation

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `delays.min_seconds` / `max_seconds` | `10` | Pause entre chaque **ronde** (tous les cours) |
| `navigation.mode` | `manual_clicks` | Vous naviguez au départ ; le bot clique ensuite |
| `navigation.manual_setup_seconds` | `10` | Temps max avant le bot (ou **Entrée** plus tôt) |
| `navigation.manual_finish_on_enter` | `true` | Appuyez sur Entrée dans la console pour démarrer tout de suite |
| `browser.keep_open` | `true` | Chrome reste ouvert après une alerte |
| `browser.stop_on_alarm` | `false` | Continue les autres cours / rondes après une alerte |
| `browser.multi_bot` | `true` | Un navigateur par cours |
| `navigation.save_button_text` | `SAUVEGARDER` | Bouton cliqué après AJOUTER+ si `auto_register` |

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

Double-cliquez [`launch.bat`](launch.bat). La première fois, il crée `.venv`, installe les dépendances et Chromium, puis ouvre la fenêtre **BotETS**.

1. **Load my courses** ouvre Cheminot, clique **Sélectionner cette session**, puis va à `/inscription` (sans étape manuelle). MFA une fois si demandé.
2. Choisissez un cours, cochez **Auto-register** ou non, puis **Add bot**.
3. **Start** : un Chrome par cours, navigation seule (session → `/inscription` → sigle). Pas de **Window ready**.

`python -m src.main --run` lance les cours de `config.yaml` sans l'interface.

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
│   ├── ui.py            # fenêtre : cours, auto-register, Start
│   ├── catalog.py       # sigles lus sur Cheminot après connexion
│   ├── worker.py        # processus enfant (un cours)
│   ├── register.py      # AJOUTER+ puis SAUVEGARDER
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
python -m tests.test_register
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
