# Guide simple — tout comprendre vite

Ce fichier résume **en mots simples** tout le projet : à quoi il sert, quels programmes parlent entre eux, et **où se trouvent les fichiers**.  
Pour le vocabulaire (SLA, NOC), voir aussi `IDEE_GENERALE_PROJET.md`. Pour les détails du code, `EXPLICATION_CODE_PROJET.md`.

---

## 1. En une minute : c’est quoi ce projet ?

Imagine un **petit opérateur 5G** qui doit surveiller des **tranches réseau** (des « slices »).

- Il veut savoir si la **qualité (QoS)** sera bonne et si les **engagements clients (SLA)** tiennent.
- Il veut repérer des **comportements bizarres** (anomalies).
- Il veut un **écran central** pour l’équipe d’exploitation (comme un **NOC**).
- Il veut **noter quels modèles ML** sont utilisés et leurs scores.

Ce dépôt montre tout ça avec des **services séparés** (microservices), une **base de données commune**, et **Docker** pour tout lancer pareil partout. L’**entraînement** s’appuie sur **MLflow** (suivi d’expériences) ; la stack **Elasticsearch / Kibana** reste surtout une **supervision** infra optionnelle.

---

## 2. Les services : qui fait quoi ?


| Nom                    | Rôle en langage simple                                                                                        | Port côté machine (souvent) |
| ---------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------- |
| **MySQL**              | Stocke l’historique : prédictions, anomalies, alertes, métriques de modèles.                                  | 3306                        |
| **MS1**                | « Cerveau QoS » : reçoit des mesures réseau, calcule score / congestion, enregistre en base. Pages web + API. | 5001                        |
| **MS2**                | « Détecteur d’anomalies » : reçoit des infos sur une tranche, répond si c’est suspect ou non.                 | 5000                        |
| **MS3**                | « Écran NOC » : connexion, tableau de bord, alertes, opérations (tranches, seuils).                           | 5003                        |
| **MS5**                | « Carnet des modèles » : liste et enregistrement des métriques de modèles en base.                            | 5005                        |
| **Nginx**              | « Porte d’entrée » : une seule adresse web (80/443) qui renvoie vers les bons services.                       | 80, 443                     |
| **MLflow**             | **Requis** pour l’entraînement : trace des expériences (métriques, artefacts, registre).                      | 5006                        |
| **Elasticsearch**      | Base de données de recherche / logs pour les métriques collectées.                                            | 9200                        |
| **Kibana**             | Site web pour **voir** les données dans Elasticsearch (tableaux de bord).                                     | 5601                        |
| **Metricbeat**         | Petit programme qui **envoie** l’utilisation CPU, mémoire, Docker, etc. vers Elasticsearch.                   | (pas d’URL directe)         |
| **ci** (profil Docker) | Image utilisée pour **tests et qualité de code**, pas pour les utilisateurs finaux.                           | —                           |


Les services **MS1 à MS5** et **MySQL** sont le cœur métier. **MLflow** accompagne le **pipeline d’entraînement** (MLOps). **Elastic + Kibana + Metricbeat** servent surtout à la **supervision technique** (optionnelle).

---

## 3. Fichiers par zone (carte rapide)

### Racine du projet (MS1 + partagé)


| Fichier / dossier      | À quoi ça sert (simple)                                                                   |
| ---------------------- | ----------------------------------------------------------------------------------------- |
| `app.py`               | Application principale MS1 (API FastAPI + pages UI QoS / historique).                     |
| `congestion_engine.py` | Règles / calculs pour dire si le réseau est peu, moyennement ou très congestionné.        |
| `slice_inference.py`   | Prépare les bonnes **variables** pour que le modèle comprenne une tranche.                |
| `config.py`            | Paramètres lus depuis l’environnement (base de données, SMTP, etc.).                      |
| `models.py`            | Fonctions Python pour lire/écrire dans les tables (pas le « modèle ML »).                 |
| `alert_service.py`     | Envoie des alertes par **e-mail** (SMTP).                                                 |
| `init_db.py`           | Recrée le schéma SQL à la main en lisant `init.sql`.                                      |
| `test_api.py`          | Tests qui appellent les vrais services (intégration).                                     |
| `init.sql`             | Définition des **tables** MySQL au premier démarrage du conteneur.                        |
| `docker-compose.yml`   | Liste de **tous** les conten/*-                                                           |
| `Dockerfile`           | Recette de l’image **MS1**.                                                               |
| `Dockerfile.ci`        | Recette de l’image **outils + tests**.                                                    |
| `Dockerfile.mlflow`    | Recette du serveur **MLflow**.                                                            |
| `nginx.conf`           | Règles de Nginx (chemins `/api/...`, `/noc/`, etc.).                                      |
| `requirements.txt`     | Bibliothèques Python pour faire tourner les services.                                     |
| `Makefile`             | Raccourcis (`make test`, `make lint`, …).                                                 |
| `workflow_ui/`         | Fichiers statiques servis par Nginx (page **workflow** sur `http://localhost/workflow/`). |
| `templates/`           | Modèles HTML Jinja2 pour l’UI de **MS1**.                                                 |
| `static/`              | CSS, JS, images pour **MS1**.                                                             |


### Dossier `anomaly/` (MS2)


| Fichier            | À quoi ça sert                                                     |
| ------------------ | ------------------------------------------------------------------ |
| `app.py`           | API FastAPI : détection d’anomalie, stats, santé.                  |
| `Dockerfile`       | Image Docker de MS2 (inclut TensorFlow CPU pour certains modèles). |
| `requirements.txt` | Dépendances de MS2.                                                |


### Dossier `ms3/` (NOC / dashboard)


| Fichier            | À quoi ça sert                                                            |
| ------------------ | ------------------------------------------------------------------------- |
| `app.py`           | Login, dashboard, API des données agrégées, alertes, page **Operations**. |
| `templates/*.html` | Pages web : login, dashboard, opérations, erreurs.                        |
| `Dockerfile`       | Image Docker de MS3.                                                      |
| `requirements.txt` | Dépendances de MS3.                                                       |


### Dossier `ms5_model_management/` (MS5)


| Fichier                    | À quoi ça sert                                                    |
| -------------------------- | ----------------------------------------------------------------- |
| `app.py`                   | API + petite UI : liste des modèles, enregistrement de métriques. |
| `templates/dashboard.html` | Page d’inventaire des modèles.                                    |
| `Dockerfile`               | Image Docker de MS5.                                              |
| `requirements.txt`         | Dépendances de MS5.                                               |


### Dossier `ml/`


| Contenu                                    | À quoi ça sert                                                               |
| ------------------------------------------ | ---------------------------------------------------------------------------- |
| Fichiers `.pkl`, `.joblib`, `.h5`, `.json` | **Modèles entraînés**, scalers, seuils, métadonnées.                         |
| `inference.py`                             | Code partagé : charger les modèles et calculer un score d’anomalie pour MS2. |


*Sans ces fichiers (après un clone), il faut souvent lancer un entraînement — voir `WORKFLOW_TEST_GUIDE.md`.*

### Dossier `scripts/`


| Fichier                             | À quoi ça sert                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------------- |
| `train_models.py`                   | Entraîne les modèles à partir d’un CSV et remplit `ml/`.                          |
| `mlflow_integration.py`             | Branche l’entraînement sur **MLflow** (sauf `DISABLE_MLFLOW` pour tests rapides). |
| `version_models.py`                 | Gère un petit **registre** de versions en JSON (`ml/registry.json`).              |
| `push_metadata_to_elasticsearch.py` | Envoie `ml/metadata.json` dans Elasticsearch pour **Kibana**.                     |


### Dossier `metricbeat/`


| Fichier          | À quoi ça sert                                                       |
| ---------------- | -------------------------------------------------------------------- |
| `metricbeat.yml` | Dit à Metricbeat **quoi mesurer** et **où envoyer** (Elasticsearch). |


### Dossier `tests/`


| Zone                          | À quoi ça sert                                       |
| ----------------------------- | ---------------------------------------------------- |
| `tests/unit/`                 | Petits tests rapides (config, helpers, smoke train). |
| `tests/fixtures/ci_train.csv` | Mini jeu de données pour la CI.                      |


### Dossier `.github/workflows/`


| Fichier           | À quoi ça sert                                                     |
| ----------------- | ------------------------------------------------------------------ |
| `ci.yml`          | Qualité du code + tests quand tu pousses sur GitHub.               |
| `ml-pipeline.yml` | Entraînement court en CI avec le petit CSV.                        |
| `cd-manual.yml`   | Déploiement manuel (images Docker Hub ; entraînement avec MLflow). |


---

## 4. Comment les données circulent ?

1. Un utilisateur ou un script appelle **MS1** ou **MS2** avec des mesures.
2. Le service calcule un résultat et **écrit une ligne** dans **MySQL**.
3. **MS3** lit MySQL et **affiche** tout sur le dashboard.
4. Si une situation est grave, **MS1** (ou d’autres morceaux) peuvent déclencher des **alertes** (e-mail) ou des lignes dans la table `alerts`.
5. **MS5** enregistre ce qu’on sait sur les **modèles** (précision, etc.).
6. **Metricbeat** envoie l’état des machines/containers vers **Elasticsearch** ; **Kibana** permet de visualiser.

---

## 5. Démarrer vite (rappel)

À la racine du dépôt, avec Docker installé :

```bash
docker compose up -d --build
```

Puis ouvre par exemple `http://localhost:5001/docs` (MS1) ou suis les URLs dans `WORKFLOW_TEST_GUIDE.md`. Le premier démarrage d’Elasticsearch peut prendre une minute.

---

## 6. Quel document lire pour aller plus loin ?


| Besoin                                       | Document                     |
| -------------------------------------------- | ---------------------------- |
| **Vue d’ensemble simple (ce fichier)**       | `GUIDE_SIMPLE_PROJET.md`     |
| Idée générale + SLA + NOC                    | `IDEE_GENERALE_PROJET.md`    |
| Détail du code et des routes                 | `EXPLICATION_CODE_PROJET.md` |
| Lancer Docker, ports, Nginx                  | `INFRASTRUCTURE.md`          |
| Liste fichiers infra                         | `FILE_MANIFEST.md`           |
| CI / Makefile / image `ci`                   | `GUIDE_CI_MLOPS_ETUDIANT.md` |
| Parcours dans le navigateur, jeux de données | `WORKFLOW_TEST_GUIDE.md`     |
| Déploiement en anglais                       | `DOCKER_README.md`           |
| Objectifs longs + exemples API               | `Roadmap.md`                 |


---

*Astuce : commence par ce fichier, puis `WORKFLOW_TEST_GUIDE.md` si tu veux **voir** le système tourner dans le navigateur.*