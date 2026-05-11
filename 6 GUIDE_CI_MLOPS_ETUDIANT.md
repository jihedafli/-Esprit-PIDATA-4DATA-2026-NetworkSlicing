# Guide simple : CI, Docker et MLOps dans ce projet

**Vue d’ensemble de tout le projet (pas seulement la CI) :** `GUIDE_SIMPLE_PROJET.md`

Ce document explique **avec des mots simples** ce que fait la configuration automatique du dépôt. Tu peux le lire dans l’ordre ou sauter aux sections qui t’intéressent.

---

## 1. Deux idées à retenir

**CI (Intégration continue)**  
À chaque fois que tu envoies du code sur GitHub (`push`) ou que tu proposes une fusion (`pull request`), des **vérifications automatiques** se lancent : qualité du code, tests, parfois entraînement du modèle. Tu n’as rien à lancer à la main sur le site GitHub : c’est le fichier **workflow** (dans `.github/workflows/`) qui décide quoi faire.

**Pourquoi Docker ici ?**  
Au lieu d’installer Python et toutes les bibliothèques **sur ton PC** ou **sur le serveur GitHub**, on utilise une **image Docker** : une « boîte » qui contient déjà Python et les bons paquets. Comme ça, tout le monde (et la CI) utilise **le même environnement**.

---

## 2. Les fichiers importants (carte rapide)

| Fichier / dossier | Rôle en une phrase |
|-------------------|---------------------|
| `.github/workflows/ci.yml` | Déclenche sur `main` / `jihed` : qualité du code + tests unitaires + tests API avec Docker. |
| `.github/workflows/ml-pipeline.yml` | Lance l’**entraînement** du modèle (planifié, manuel, ou si certains fichiers changent). |
| `.github/workflows/cd-manual.yml` | Déclenchement **manuel** : build / push d’images Docker Hub ; entraînement **avec MLflow** (requis pour un run d’entraînement nominal). |
| `Dockerfile.ci` | Recette pour construire l’image **`ci`** : Python + dépendances du projet + outils de dev (ruff, black, etc.). |
| `docker-compose.yml` | Décrit les services (MySQL, MS1, MS2, …) et le service **`ci`** (profil `ci`). |
| `Makefile` | Raccourcis du type `make lint`, `make test` qui appellent Docker pour toi. |
| `requirements.txt` | Bibliothèques nécessaires pour **faire tourner l’application**. |
| `requirements-dev.txt` | Outils **en plus** pour développer et pour la CI (pytest, ruff, black, bandit, pip-audit). |
| `tests/unit/` | Petits **tests unitaires** (rapides, sans toute la stack). |
| `test_api.py` | **Tests d’intégration** : vérifie que les vrais services répondent sur le réseau. |
| `scripts/train_models.py` | Pipeline d’**entraînement** des modèles. |
| `tests/fixtures/ci_train.csv` | Petit jeu de données pour faire un entraînement **court** en CI. |

---

## 3. Le service Docker `ci` (le cœur de la méthode)

- Dans `docker-compose.yml`, il y a un service nommé **`ci`** avec **`profiles: ["ci"]`**.
- **Profil** = ce service ne démarre **pas** avec un simple `docker compose up` habituel ; on l’utilise quand on en a besoin avec `--profile ci`.
- Cette image installe **à l’intérieur** `requirements.txt` **et** `requirements-dev.txt`.  
  → **Tu n’as pas besoin de faire `pip install` sur ton Windows pour la CI locale** si tu passes par `make` / `docker compose`.

**Commande type :**

```text
docker compose --profile ci run --rm --no-deps ci <commande>
```

- **`run`** : lance un conteneur **temporaire** pour exécuter une commande.  
- **`--rm`** : le conteneur est supprimé après.  
- **`--no-deps`** : ne démarre pas MySQL / MS1 / etc. (utile pour `ruff` ou `pytest tests/unit`).  
- Pour les **tests API**, la stack doit déjà tourner (`docker compose up -d`) ; le conteneur `ci` est sur le **même réseau** et utilise des URLs du type `http://ms1:5000` (définies dans `docker-compose.yml`).

---

## 4. Ce que fait chaque outil dans le job « qualité »

| Outil | Rôle simple |
|-------|-------------|
| **Ruff** | Cherche des problèmes dans le code Python (erreurs, mauvaises pratiques). |
| **Black** | Vérifie que le **formatage** du code est cohérent (espaces, retours à la ligne). |
| **Bandit** | Cherche des **risques de sécurité** dans le code (patterns dangereux). |
| **pip-audit** | Vérifie si des paquets installés ont des **failles connues** (CVE). |

Ces commandes s’exécutent **dans l’image `ci`**, pas sur ton Python global.

---

## 5. Les tests : deux niveaux

**Tests unitaires** (`tests/unit/`)  
- Très **rapides**.  
- Testent des **petits morceaux** (config, helpers, parfois un entraînement minimal avec un petit CSV).  
- **Pas besoin** que tous les microservices soient démarrés.

**Tests d’intégration** (`test_api.py`)  
- Il faut que **Docker Compose** fasse tourner MS1, MS2, MS3, MS5 (et MySQL).  
- Les tests appellent les **URLs** des services. Sur ton PC, ce sont souvent `localhost` et des ports ; **dans le conteneur `ci`**, les variables `MS1_URL`, etc. pointent vers les **noms de services** (`ms1`, `ms2`, …).

---

## 6. Makefile : ce que tu peux taper au quotidien

*(Docker doit être installé ; pour `make test`, la stack doit être déjà `up`.)*

| Commande | Effet |
|----------|--------|
| `make lint` | Ruff sur le projet (dans Docker `ci`). |
| `make format-check` | Vérifie le formatage Black. |
| `make security` | Bandit + pip-audit. |
| `make test-unit` | Pytest sur `tests/unit`. |
| `make test` | Pytest sur `test_api.py` (API). |
| `make train-ci` | Entraînement court avec `tests/fixtures/ci_train.csv`. |

---

## 7. Sur GitHub : que se passe-t-il sans que tu cliques ?

1. Tu **pushes** sur `main` ou `jihed`.  
2. Le workflow **`CI`** (`ci.yml`) démarle **3 jobs en parallèle** (en gros) :  
   - **quality** : ruff, black, bandit, pip-audit dans Docker ;  
   - **unit** : pytest `tests/unit` dans Docker ;  
   - **integration** : démarre toute la stack avec `docker compose up`, attend que les `/health` répondent, puis lance `test_api.py` **dans** le conteneur `ci`.  
3. Le workflow **`ML pipeline`** (`ml-pipeline.yml`) peut lancer l’entraînement :  
   - **manuellement** (bouton *Run workflow*),  
   - **chaque lundi** (cron),  
   - ou quand certains fichiers (scripts, fixture CSV, etc.) changent.

Tu suis l’avancement dans l’onglet **Actions** du dépôt.

---

## 8. Schéma mental (une image = une phrase)

```text
  [Ton code sur GitHub]
           |
           v
  [GitHub Actions lit .github/workflows/*.yml]
           |
           +--> Build image Dockerfile.ci  -->  ruff, black, bandit, pip-audit, pytest unit
           |
           +--> docker compose up (MS1, MS2, ...)  -->  pytest test_api dans `ci`
           |
           +--> (autre workflow) entraînement  -->  train_models.py + artefacts ml/
```

---

## 9. Si quelque chose échoue : par où commencer ?

1. **Onglet Actions** → ouvre le run en rouge → lis **quel job** a échoué (quality, unit, integration).  
2. **Quality** : message Ruff / Black / Bandit / pip-audit → corrige le fichier indiqué ou mets à jour une dépendance si c’est une CVE.  
3. **Unit** : ouvre le log pytest → le nom du test et la ligne d’erreur.  
4. **Integration** : souvent **timeout** ou service pas prêt → regarde les logs Docker ; vérifie que les healthchecks passent en local avec `docker compose up -d`.  
5. En local, **reproduis** avec la même commande que le Makefile (`make test-unit`, `make test`, etc.).

---

## 10. Glossaire express

- **Workflow** : fichier YAML qui dit à GitHub *quand* et *quoi* exécuter.  
- **Job** : bloc de travail dans un workflow (ex. « quality »).  
- **Artifact** : fichier produit par la CI (ex. modèles `.pkl`) que tu peux télécharger depuis GitHub.  
- **MLOps** : automatiser entraînement, suivi des modèles, tests — ici **MLflow** est le socle du suivi d’entraînement, avec scripts et pipeline GitHub.

---

*Bonne lecture : en repassant une fois sur les sections 1, 2, 5 et 7, tu as déjà l’essentiel pour expliquer le projet à l’oral.*
