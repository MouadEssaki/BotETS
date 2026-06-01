# Sélecteurs Cheminot — flux réel ÉTS

## Parcours automatisé

| Étape | URL | Action bot |
|-------|-----|------------|
| 1 | `/` | **SÉLECTIONNER CETTE SESSION** (carte Inscription et consultation) |
| 2 | `/consultation` → `/inscription` | **goto /inscription** puis clic onglet **INSCRIPTION AUTOMNE 2026** si besoin |
| 3 | `/inscription` | Clic sigle cours (ex. **ATE085**) sur le graphe |
| 4 | `/horaire` | **AJOUTER+** actif + groupes visibles |

## Cours et groupe

Dans [`config.yaml`](config.yaml) :

```yaml
course:
  sigle: "ATE085"
  section: ""           # vide = numéro de groupe inconnu
  group_mode: "any"     # any | first | exact
  label: "ATE085"
```

| `group_mode` | Usage |
|--------------|--------|
| `any` | Alarme si **AJOUTER+** actif et au moins un groupe dans le tableau (défaut si `section` vide) |
| `first` | Sélectionne la première ligne groupe à la navigation |
| `exact` | Filtre le groupe `section` (ex. `01`) si vous le connaissez |

## Critère d'alarme

**AJOUTER+** cliquable et pas *« Aucun choix de groupe disponible »*.

## Sélecteurs CSS optionnels

| Champ `navigation:` | Si… |
|---------------------|-----|
| `inscription_tab_selector` | L'onglet INSCRIPTION ne réagit pas au goto/clic texte |
| `select_session_button` | Bouton session bleu introuvable |
| `course_node_selector` | Sigle introuvable sur le graphe |
| `group_row_selector` | Lignes groupe mal détectées |

## Timezone (Windows)

Installer les dépendances (`tzdata` dans `requirements.txt`). Variable `.env` :

```env
TIMEZONE=America/Montreal
```

Variantes acceptées : `america montreal`, `America/Toronto`. Sans tzdata, les logs utilisent l'heure locale `(local)` sans crasher.

## Captures en cas d'échec

`screenshots/nav_step1_failed.png`, `nav_step2_inscription_tab_failed.png`, etc.
