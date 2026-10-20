<div align="center">
  <div style="background: white;">
    <img src="assets/logo.png" alt="BotETS logo" width="180">
  </div>

  <h1>BotETS</h1>

  <p><strong>Surveillance Cheminot (ÉTS)</strong></p>

  <p>
    <img alt="Version" src="https://img.shields.io/badge/version-1.0.0-0B5FFF?style=for-the-badge">
    <img alt="Python" src="https://img.shields.io/badge/python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white">
    <img alt="Platform" src="https://img.shields.io/badge/platform-Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white">
  </p>
</div>

Bot Python ([Playwright](https://playwright.dev/python/)) qui surveille [Cheminot](https://cheminotn.etsmtl.ca). Une **fenêtre d’interface** permet de charger vos cours, d’ajouter des bots, puis de lancer **un navigateur par cours**. Avec `auto_register`, le bot prend le **premier groupe libre** (horaire ignoré), clique **AJOUTER+** puis **SAUVEGARDER**, et vous alerte sur **PC** (son) et **téléphone** (ntfy / Telegram).

## Fonctionnalités

- Interface **BotETS** : Load courses, recherche / autocomplete, Add bot, Start / Stop
- Connexion **MFA** une fois + session sauvegardée (`storage_state.json`)
- Navigation **auto** : accueil → **Sélectionner cette session** → `/inscription` → sigle (pas de clic manuel, pas de Window ready)
- **Un bot par cours** (`browser.multi_bot`)
- **Inscription auto** optionnelle (`auto_register`) : premier groupe avec une place
- Liste de cours filtrée (section « Cours offerts », hors intégration / obligatoires déjà sur le cheminement)
- **Alarme sonore** Windows + **ntfy** / **Telegram**
- Navigateur **reste ouvert** après une alerte
- Intervalle configurable entre les rondes (défaut : **10 s**)

## Déroulement typique

```text
1. Double-clic launch.bat → fenêtre BotETS
2. Load my courses → MFA si besoin → session → /inscription → liste de cours
3. Tapez un sigle (autocomplete), cochez Auto-register ou non, Add bot
   (un code absent de la liste peut quand même être ajouté)
4. Start → un Chrome par bot, navigation seule
5. Si AJOUTER+ est actif :
   - auto_register → premier groupe libre → AJOUTER+ → SAUVEGARDER → alarme
   - sinon → alarme seulement
```

## Prérequis

- Windows 10/11 (alarme `winsound`)
- Python 3.11+ (dans le PATH)
- Compte Cheminot ÉTS (MFA)

## Release GitHub (fichier `.exe`)

Les utilisateurs téléchargent **un seul fichier** `BotEts.exe` (pas de zip) :

1. [Releases](https://github.com/MouadEssaki/BotETS/releases) → **BotEts.exe**
2. Double-clic
3. Au **premier lancement**, Chromium est téléchargé une fois (~150 Mo) dans `%LOCALAPPDATA%\BotEts`
4. L’UI **BotEts** s’ouvre (logo + titre)

Aucun Python à installer pour l’utilisateur final.

Pour publier :

```powershell
# 1. Mettre à jour VERSION, commit + push sur main
# 2. Tag :
git tag v1.0.0
git push origin v1.0.0
```

Le workflow [`.github/workflows/release.yml`](.github/workflows/release.yml) construit `BotEts.exe` sur Windows et l’attache à la release.

Build local :

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_exe.ps1
# → dist\BotEts.exe
```

Développeurs : `launch.bat` / `python -m src.ui` reste disponible.

## Installation / lancement

Le plus simple : double-cliquer [`launch.bat`](launch.bat). La première fois, il crée `.venv`, installe les dépendances et Chromium, puis ouvre l’interface **BotEts** (logo en haut).

Installation manuelle :

```powershell
cd chemin\vers\BotETS
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
copy .env.example .env
python -m src.ui
```

Sans interface (cours de `config.yaml`) :

```powershell
python -m src.main --run
```

Un seul cours :

```powershell
python -m src.main --course LOG200
```

## Configuration

### Interface (recommandé)

Les bots choisis dans l’UI sont mémorisés dans `launcher.json` (non versionné). La liste de sigles est remplie par **Load my courses**.

### Cours — [`config.yaml`](config.yaml) (mode `--run`)

```yaml
courses:
  - sigle: "LOG200"
    section: ""          # vide = n'importe quel groupe
    group_mode: "any"    # any | first | exact
    label: "LOG200"
    auto_register: true  # premier groupe libre (horaire ignoré)
  - sigle: "GTI350"
    section: ""
    group_mode: "any"
    label: "GTI350"
    auto_register: false # alerte seulement
```

| `auto_register` | Effet quand AJOUTER+ est actif |
|-----------------|--------------------------------|
| `true` | Premier groupe libre → **AJOUTER+** → **SAUVEGARDER**. En cas de refus, essai du suivant. Le bot s’arrête après une inscription envoyée. |
| `false` | Alarme et notification seulement. |

### Délais et navigation

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| `delays.min_seconds` / `max_seconds` | `10` | Pause entre chaque ronde |
| `navigation.mode` | `auto` | Session → `/inscription` → cours automatiquement |
| `navigation.session_label` | `Hiver 2027` | Session d’inscription ciblée |
| `browser.keep_open` | `true` | Chrome reste ouvert après une alerte |
| `browser.stop_on_alarm` | `false` | Continue les autres bots après une alarme |
| `browser.multi_bot` | `true` | Un navigateur par cours |
| `navigation.save_button_text` | `SAUVEGARDER` | Bouton après AJOUTER+ si `auto_register` |

Mode ancien (clics manuels au départ) : `navigation.mode: "manual_clicks"`.

**Attention :** des délais très courts (10 s) augmentent le risque de limitation par l’ÉTS. Usage plus prudent : `min_seconds: 180`, `max_seconds: 300`.

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

Test : `python -m tests.test_notify`

#### Telegram (optionnel)

```env
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Voir `.env.example`. Dans `config.yaml` : `notifications.enabled: true`.

**Place détectée** : bip PC, notification ntfy, capture `screenshots/place_available_SIGLE.png`.

## Structure du projet

```text
BotETS/
├── launch.bat           # double-clic → interface
├── assets/logo.png      # logo README
├── config.yaml          # délais, navigation, cours (--run)
├── launcher.json        # bots / sigles de l'UI (local)
├── .env                 # ntfy / Telegram (local)
├── storage_state.json   # session Cheminot (généré)
├── src/
│   ├── ui.py            # fenêtre BotETS
│   ├── catalog.py       # Load courses depuis Cheminot
│   ├── main.py          # point d'entrée / multi-bot
│   ├── worker.py        # un processus par cours
│   ├── register.py      # AJOUTER+ puis SAUVEGARDER
│   ├── monitor.py       # boucle de surveillance
│   ├── navigation.py    # session → /inscription → horaire
│   ├── notify.py        # ntfy / Telegram
│   └── browser.py       # Playwright
├── logs/
└── screenshots/
```

## Tests

```powershell
python -m tests.test_config
python -m tests.test_navigation_config
python -m tests.test_catalog
python -m tests.test_register
python -m tests.test_timeutil
python -m tests.test_capacity_parse
python -m tests.test_alarm
python -m tests.test_notify
```

## Dépannage

| Problème | Piste |
|----------|--------|
| Load courses vide | MFA terminé ? Session choisie ? Voir `screenshots/inscription_catalog_failed_*.png` |
| Pas de notification ntfy | `python -m tests.test_notify` ; topic identique app / `.env` ; `logs/bot.log` |
| Navigateur se ferme | `browser.keep_open: true` |
| Clic cours échoue | Sigle sur le graphe ; `navigation.course_node_selector` (F12) |
| Statut `unknown` | `screenshots/unknown_*.png` ; [`selectors.md`](selectors.md) |
| AJOUTER+ grisé | Normal si déjà inscrit — place non actionnable |
| Crash timezone | `pip install tzdata` ; `TIMEZONE=America/Montreal` dans `.env` |
| Blocage / déconnexion ÉTS | Augmenter `delays` (ex. 180–300 s) |

## Avertissement

Usage **personnel** uniquement. Respectez les conditions d’utilisation de l’ÉTS. Évitez de surcharger le site (délais trop courts, plusieurs machines sur la même IP).
