# Explication du code du projet (Network Slicing 5G)

**Entrée « tout en simple » (liste des services et des fichiers) :** `GUIDE_SIMPLE_PROJET.md`

Ce document décrit **à quoi sert chaque partie du code** et comment les morceaux s’assemblent. Il complète `GUIDE_CI_MLOPS_ETUDIANT.md` (CI / Docker) et `IDEE_GENERALE_PROJET.md` (contexte métier).

---

## 1. Vue d’ensemble : que fait le projet ?

Le projet simule / démontre une **architecture microservices** pour du **réseau 5G découpé en tranches (slices)** :

- estimer la **qualité de service (QoS)** et le respect des **SLA** ;
- détecter des **anomalies** sur les tranches ;
- afficher un **tableau de bord** qui agrège les données ;
- enregistrer des **métriques de modèles** (gestion de modèles).

Tout cela s’appuie sur une base **MySQL** commune et sur des **API HTTP** (FastAPI). Les modèles ML sont des fichiers (souvent `.joblib` / `.pkl`) dans le dossier `ml/`.

---

## 2. Schéma des services (logique)

```text
                    +----------+
                    |  MySQL   |
                    +----+-----+
                         |
     +-------------------+-------------------+
     |                   |                   |
+----v----+         +----v----+         +----v----+
|  MS1    |         |  MS2    |         |  MS3    |
| QoS     |         | Anomaly |         |Dashboard|
+---------+         +---------+         +----+----+
                                            |
                                       +----v----+
                                       |  MS5    |
                                       | Models  |
                                       +---------+
```

- **MS1** écrit dans `qos_predictions`.
- **MS2** écrit dans `anomaly_detections` et utilise `ml/inference.py`.
- **MS3** lit surtout ces tables pour construire une réponse JSON pour le dashboard.
- **MS5** gère la table `model_metrics` (et peut créer / migrer la table au démarrage des routes).

---

## 3. Fichiers à la racine

### `config.py`

Fichier de **configuration centralisée** (variables d’environnement avec valeurs par défaut) :

- connexion **MySQL** (`DB_HOST`, `DB_USER`, etc.) ;
- chemins vers les **fichiers modèle** (`MODEL_PATH`, `SCALER_PATH`, `ENCODER_PATH`) ;
- paramètres **email / SMTP** pour les alertes ;
- **URLs** des autres services (`MS1_URL`, …) pour du code qui appellerait une autre API.

Les applications FastAPI **dupliquent souvent** un petit `DB_CONFIG` local dans leur `app.py` avec des défauts adaptés à Docker (`DB_HOST=mysql`). Ce n’est pas une erreur : c’est pour que chaque service soit **autonome** dans son conteneur.

---

### `app.py` — MS1 (prédiction QoS)

**Framework :** FastAPI.

**Rôle :** exposer l’API « principale » de prédiction QoS pour la 5G.

**Points clés :**

- `FastAPI()` + **CORS** ouvert (toutes origines) pour faciliter les démos / frontends.
- Gestionnaire d’erreur sur `RequestValidationError` → réponses **400** avec le détail des champs invalides.
- **`QoSPredictRequest` / `QoSPredictResponse`** : schémas Pydantic (voir `/docs`) ; **`extra="ignore"`** sur la requête pour compatibilité (champs obsolètes comme `is_broadband` ignorés sans 422).
- **`GET /health`** : indique que le service est vivant (utilisé par Docker et les tests).
- **`POST /predict/qos/5g`** :
  - calcule un **score QoS** et la congestion à partir de `plr`, `delay`, drapeaux alignés entraînement (`slice_inference` → mêmes features que `scripts/train_models.py` après sélection) ;
  - enregistre le résultat en base dans **`qos_predictions`** ;
  - renvoie le JSON de réponse typé.
- **`GET /predict/stats`** : compte les prédictions et le taux de conformité SLA en SQL.
- **`GET /`** : petite page d’info (nom du service, liens utiles).
- Bloc `if __name__ == "__main__"` : lance **uvicorn** pour un run local hors Docker.

**Fonction utilitaire :** `get_db_connection()` ouvre une connexion MySQL avec `mysql.connector`.

### `congestion_engine.py` (MS1)

**Rôle :** calculer une **pression / congestion** à partir des métriques et la classer (ex. faible / moyenne / forte). Utilisé par `app.py` pour l’affichage et la cohérence avec les seuils métier.

### `slice_inference.py` (MS1)

**Rôle :** construire le **vecteur de caractéristiques** (flags de tranche, etc.) aligné sur `scripts/train_models.py`, pour que la prédiction QoS utilise les **mêmes colonnes** qu’à l’entraînement.

### `templates/` et `static/` (MS1)

**Rôle :** pages HTML (Jinja2) et fichiers statiques pour les parcours **`/ui/...`** (formulaires, historique). Voir `WORKFLOW_TEST_GUIDE.md` pour les URL.

---

### `models.py`

Ce fichier n’est **pas** l’ORM « Modèle ML » : ce sont des **modèles d’accès aux données** (pattern classique maison).

- **`BaseModel`** : méthode statique `execute_query` qui ouvre une connexion, exécute une requête, renvoie un résultat ou `None` en cas d’erreur (message affiché dans la console).
- **`QoSPrediction`** : `create`, `get_recent`, `get_statistics` sur la table `qos_predictions`.
- **`AnomalyDetection`** : idem pour `anomaly_detections`.
- **`ModelMetrics`** : idem pour `model_metrics`.
- **`Alert`** : création / lecture / acquittement d’alertes dans `alerts`.

**Note :** MS1 et MS2 font souvent du **SQL directement dans `app.py`** au lieu d’utiliser ces classes. Les deux styles coexistent dans le projet : les classes `models.py` servent surtout quand un autre module (ex. alertes) veut une API Python propre.

---

### `alert_service.py`

**Rôle :** envoyer des **alertes par e-mail** (SMTP). Le constructeur lit `config` (`SMTP_SERVER`, `SMTP_PORT`, identifiants, `ALERT_EMAIL`).

- `send_email_alert(subject, message, severity)` construit un mail et l’envoie.
- Une variable globale `alert_service` est une **instance toute faite** pour import rapide.

---

### `init_db.py`

Script **manuel** pour développeurs : lit **`init.sql`**, se connecte à MySQL (sans sélectionner la base au départ), exécute les instructions une par une. Utile hors Docker ou pour recréer le schéma.

---

### `test_api.py`

**Tests d’intégration** avec **pytest** et **requests** :

- attend que chaque service réponde sur **`/health`** ;
- appelle les vraies routes (QoS, anomalie, dashboard, MS5) ;
- vérifie les codes HTTP et la présence de champs importants dans le JSON.

Les URLs viennent des variables d’environnement **`MS1_URL`**, etc., avec défaut sur `localhost` et les ports exposés par Docker.

---

## 4. Dossier `anomaly/` — MS2 (anomalies)

**Fichiers du dossier :** `app.py` (API), `Dockerfile`, `requirements.txt` (dont **TensorFlow CPU** pour charger un autoencodeur `.h5` si présent). Le `docker-compose` monte le dossier **`ml/`** dans le conteneur MS2 pour les poids et le code d’inférence.

### `anomaly/app.py`

**Rôle :** API d’**anomalie** sur une tranche.

- Même structure générale que MS1 : FastAPI, CORS, gestion 400, `DB_CONFIG`, `get_db_connection()`.
- **`POST /api/anomaly/detect`** :
  - reçoit un JSON avec `slice_id`, métriques **`packet_loss_rate`** (fraction 0–1), **`packet_delay`** (ms), et drapeaux binaires 0/1 alignés sur l’entraînement (`lte_5g`, `gbr`, etc.) ; champs inconnus ignorés (`extra="ignore"`) ;
  - construit le vecteur via **`training_aligned_feature_dict`** puis **`detect_anomaly(...)`** dans `ml/inference.py` ;
  - enregistre le résultat dans **`anomaly_detections`** ;
  - renvoie `status`, `data` (score, confiance, méthode).
- **`GET /api/anomaly/stats`** : agrégations SQL sur les détections des N derniers jours.
- **`GET /`** : métadonnées du service.

**Chemin Python :** le fichier ajoute le dossier parent au `sys.path` pour pouvoir importer `ml.inference` depuis la racine du projet.

---

## 5. Dossier `ml/` — inférence et artefacts

### `ml/inference.py`

**Rôle :** charger les artefacts ML et scorer une anomalie (utilisé par MS2).

- **`ModelManager`** :
  - chemins via variables d’environnement (`AUTOENCODER_PATH` pour un `.h5`, `SCALER_PATH`, `ENCODER_PATH` / `features.pkl`, `ISO_FOREST_PATH`, etc.) ;
  - `load()` : charge autoencodeur Keras et/ou joblibs selon la config ;
  - `predict()` : construit le vecteur, applique le scaler, calcule score (ex. erreur de reconstruction + forêt d’isolation) et compare à un **seuil** ;
  - renvoie `(is_anomaly, score, confidence)`.
- **`get_model_manager()`** : **singleton** (une seule instance chargée pour tout le process).
- **`detect_anomaly(features)`** : point d’entrée pour MS2 ; si le modèle n’est pas chargé, bascule sur **`_heuristic_detection`** (indices sur délai / PLR / flags).

Les fichiers sous `ml/` sont produits par `scripts/train_models.py` ou copiés manuellement ; sans eux, MS2 s’appuie sur l’heuristique.

---

## 6. Dossier `ms3/` — MS3 (dashboard / NOC)

### `ms3/app.py`

**Rôle :** console opérateur : **authentification par session**, pages HTML et **API JSON** pour agréger MySQL.

- **`_json_safe_value` / `_json_safe_row`** : convertissent les types MySQL en JSON pour FastAPI.
- **UI :** `GET /login`, `POST /login`, `GET /logout`, `GET /dashboard`, `GET /ops` (opérations tranches / seuils / alertes).
- **API :** `GET /api/dashboard-data` (résumé + listes QoS / anomalies / alertes sur 24 h), `POST /api/sync/prediction` (sync depuis MS1), `GET /api/alerts`, `POST /api/alerts/{id}/acknowledge`, routes `POST` sous `/ops/...` pour slices et seuils.
- **`GET /health`**, **`GET /`** : santé et métadonnées.

### `ms3/templates/`

Pages Jinja2 : `login.html`, `dashboard.html`, `ops.html`, `base.html`, `error.html`.

---

## 7. Dossier `ms5_model_management/` — MS5 (modèles)

### `ms5_model_management/app.py`

**Rôle :** **registre** de métriques de modèles en base.

- **`ensure_model_metrics_schema()`** : si la table `model_metrics` n’existe pas, elle est **créée** ; sinon migration légère (ex. ajout de la colonne `precision` si absente). Cela évite d’échouer si le schéma MySQL est ancien.
- **`GET /models`** : liste les lignes de `model_metrics`.
- **`POST /models/register`** : insère une nouvelle ligne à partir du corps JSON (`model_name`, `accuracy`, etc.).
- **`GET /models/{model_id}/metrics`** : détail d’une ligne.

Même style que les autres services : CORS, validation Pydantic, `DB_CONFIG`, helpers JSON-safe.

### `ms5_model_management/templates/`

Interface minimale (ex. `dashboard.html`) pour parcourir l’inventaire des modèles.

---

## 8. Base de données : `init.sql`

Fichier SQL exécuté au démarrage du conteneur MySQL (monté dans `docker-compose`).

Il crée la base **`network_slicing_5g`** et les tables :

| Table | Contenu principal |
|-------|-------------------|
| `qos_predictions` | Historique des prédictions QoS (MS1). |
| `anomaly_detections` | Scores / méthode / features d’anomalie (MS2). |
| `model_metrics` | Métriques d’entraînement ou de suivi (MS5 / init). |
| `alerts` | Alertes métier ou techniques. |
| `system_logs` | Logs applicatifs possibles. |

Il crée aussi l’utilisateur **`network_user`** et lui donne les droits sur la base (valeurs par défaut du projet).

---

## 9. Dossier `scripts/` — entraînement et MLOps

### `scripts/train_models.py`

**Rôle :** **pipeline d’apprentissage** complet (hors API) :

- chargement CSV (`TRAIN_DATA_PATH`, défaut `./data/train_dataset.csv`) ;
- prétraitement, bruit sur les labels, features, sélection de variables ;
- entraînement **Random Forest**, **XGBoost**, **MLP**, **Isolation Forest** ;
- évaluation, vérification **SLA**, sauvegarde des **`.pkl`** / joblib et d’un **`metadata.json`** dans `ml/`.

Par défaut, le script **journalise métriques et modèles** via `scripts/mlflow_integration.py`. Seuls les tests rapides ou le débogage définissent `DISABLE_MLFLOW` pour court-circuiter MLflow.

### `scripts/mlflow_integration.py`

**Rôle :** fonctions utilitaires pour **MLflow** : URI de tracking, expérience, aplatissement des métriques, enregistrement des modèles dans le **Model Registry**, fichier pointeur `ml/mlflow_last_run.json`.

### `scripts/version_models.py`

**Rôle :** **registre local** JSON (`ml/registry.json`) : enregistrer les versions de modèles à partir de `metadata.json`, lister, activer une version, rollback, ou afficher un résumé MLflow en ligne de commande.

### `scripts/push_metadata_to_elasticsearch.py`

**Rôle :** envoyer le contenu de **`ml/metadata.json`** dans un index **Elasticsearch** (HTTP, bibliothèque standard). Appelé depuis `train_models.py` sauf si `DISABLE_ELASTICSEARCH_PUSH` est défini. Variables utiles : `ELASTICSEARCH_URL`, `ELASTICSEARCH_INDEX`.

---

## 10. Dossier `tests/`

### `tests/unit/`

- **`test_config.py`** : vérifie que `config.DB_CONFIG` contient les bonnes clés et réagit aux variables d’environnement.
- **`test_mlflow_helpers.py`** : teste des fonctions pures (`flatten_metrics`, `project_root`, etc.).
- **`test_train_smoke.py`** : lance un **mini entraînement** dans un dossier temporaire avec `tests/fixtures/ci_train.csv` pour vérifier que le pipeline produit bien `metadata.json` et les modèles (avec `DISABLE_MLFLOW=1` pour ne pas exiger le serveur MLflow).

### `tests/fixtures/ci_train.csv`

Petit jeu de données **versionné** pour que la CI puisse entraîner sans dépendre d’un gros fichier externe.

---

## 11. Docker, Nginx et observabilité

### `docker-compose.yml` (aperçu)

| Service | Rôle court |
|---------|------------|
| **mysql** | Base `network_slicing_5g`, montage de `init.sql`. |
| **ms1** … **ms5** | Microservices métier (ports mappés 5001, 5000, 5003, 5005 — conteneur écoute en général sur 5000). |
| **nginx** | Front HTTP ; monte `nginx.conf`, `ssl/`, **`workflow_ui/`** (page `/workflow/`). |
| **mlflow** | Suivi d’expériences (**requis** pour l’entraînement nominal ; port **5006**). |
| **elasticsearch** | Stockage des métriques / documents (port **9200**). |
| **kibana** | UI Elastic (port **5601**). |
| **metricbeat** | Collecte system + Docker → Elasticsearch ; config dans **`metricbeat/metricbeat.yml`**. |
| **ci** | Profil **`ci`** : image outils + pytest / ruff (ne démarre pas avec `up` sans `--profile ci`). |

### Autres fichiers utiles

- **`Dockerfile`** (racine) : **MS1** — **uvicorn** `app:app`.
- **`Dockerfile.ci`** : `requirements.txt` + **`requirements-dev.txt`**.
- **`Dockerfile.mlflow`** : serveur MLflow.
- **`nginx.conf`** : routes `/api/ms*`, `/noc/`, `/prediction/`, `/workflow/`, etc.
- **`pyproject.toml`** : **ruff**, **black**, **pytest**.
- **`bandit.yaml`** : configuration Bandit en CI.

*(CI détaillée : `GUIDE_CI_MLOPS_ETUDIANT.md`.)*

---

## 12. Comment lire le code efficacement (conseils étudiant)

1. Commence par **`app.py` (MS1)** : tu vois le modèle d’une API FastAPI + écriture SQL.
2. Passe à **`anomaly/app.py` + `ml/inference.py`** : tu comprends le lien **requête HTTP → ML → base**.
3. Lis **`ms3/app.py`** : lecture seule + agrégation = pattern **dashboard**.
4. Regarde **`init.sql`** : une table = un type de donnée métier.
5. Ouvre **`scripts/train_models.py`** par blocs (chargement, preprocessing, `train_models`, `save_models`) sans tout mémoriser du premier coup.

---

## 13. Résumé en une page

| Zone | Idée à retenir |
|------|----------------|
| MS1 `app.py` + `congestion_engine` + `slice_inference` | API QoS / congestion + UI ; table `qos_predictions`. |
| MS2 `anomaly/app.py` | API anomalie + `ml/inference` + table `anomaly_detections`. |
| MS3 | Pages NOC + `GET /api/dashboard-data` + sync / alertes / ops. |
| MS5 | Métriques modèles dans `model_metrics` + petite UI. |
| `models.py` | Helpers SQL réutilisables. |
| `ml/inference.py` | Chargement modèles / autoencodeur + score ou heuristique. |
| `scripts/train_models.py` | Entraînement → `ml/` ; pousse optionnel vers MS5 / Elasticsearch. |
| `metricbeat/` + Elastic | Métriques infra dans Kibana. |
| `init.sql` | Schéma relationnel partagé. |

---

*En cas d’écart avec ta branche locale, se référer au code source actuel. Pour une carte lisible en premier : `GUIDE_SIMPLE_PROJET.md`.*
