# Guide : jeu de données et tests du workflow complet

**Vue générale simple (services + fichiers) :** `GUIDE_SIMPLE_PROJET.md`

Ce document répond à deux points : **où mettre les données**, et **comment exécuter tout le workflow** (stack Docker, CI, entraînement). Les vérifications **navigateur (UI)** sont décrites en premier ; les exemples **API / curl** restent en complément pour le débogage ou l’automatisation.

---

## 1. Faut-il mettre le dataset dans le projet ?

### Ce qui est déjà versionné (obligatoire pour la CI / smoke train)

- `**tests/fixtures/ci_train.csv`** — petit CSV commité dans le repo. Il sert à :
  - l’entraînement CI local via **Docker Compose** (voir §9 — même `TRAIN_DATA_PATH` que le workflow)
  - le workflow GitHub **ML pipeline** (variable `TRAIN_DATA_PATH=tests/fixtures/ci_train.csv`)
  - les tests unitaires d’entraînement (`tests/unit/test_train_smoke.py`)

**Tu n’as pas besoin d’ajouter un second dataset pour valider la CI** si ce fichier te suffit pour démontrer l’entraînement.

### Grand jeu d’entraînement

- Par défaut, `scripts/train_models.py` lit `**./data/train_dataset.csv`** (dataset versionné dans ce dépôt), sauf si tu définis `**TRAIN_DATA_PATH**` (voir `.env.example`).
- Pour un CSV **plus volumineux ou confidentiel**, garde-le hors dépôt et pointe `TRAIN_DATA_PATH` vers ce chemin.

**Recommandation :**

- Entraînement local avec le dépôt tel quel :
  ```env
  TRAIN_DATA_PATH=./data/train_dataset.csv
  ```
  ou un chemin absolu vers un autre fichier. Ne commite un gros CSV **que si** ton encadrement l’exige (sinon : `.gitignore` + documentation interne sur l’emplacement).
- Pour **Docker / reproduction** : après entraînement, les artefacts attendus sous `**ml/`** (`.pkl`, `metadata.json`, etc.) sont montés dans les conteneurs. Si MS2 ne trouve pas `mlp_model.pkl` / `scaler.pkl` / `features.pkl`, lance au moins l’**entraînement CI** (§9, commandes `docker compose` avec `ci_train.csv`) sur la machine de dev pour régénérer les fichiers produits par `train_models.py`.

---

## 2. Prérequis


| Prérequis                        | Rôle                                                                                                                        |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Docker + Docker Compose          | Stack MS1–MS5, MySQL, Nginx, MLflow, **stack monitoring ELK** (Elasticsearch + Kibana + Metricbeat), option `ci`            |
| Copie de `.env.example` → `.env` | Variables DB, MS3, MS5, chemins ML, **MLflow** (`MLFLOW_`*), **Elasticsearch** (`ELASTICSEARCH_URL`, `ELASTICSEARCH_INDEX`) |
| Ports libres                     | `80`, `3306`, `5000`–`5003`, `5005`, `**5006` (MLflow)**, `**9200` (Elasticsearch)**, `**5601` (Kibana)**                   |


Racine du projet (où se trouve `docker-compose.yml`) :

```bash
cd /chemin/vers/NetworkSlicing
```

Les exemples `curl` (sections plus bas) utilisent la **continuation de ligne `^`** (invite **cmd.exe**). Sous **bash**, mets la commande sur une seule ligne ou utilise `\` en fin de ligne. Sous **PowerShell**, préfère une seule ligne ou le backtick ```.

---

## 3. Parcours par l’interface (navigateur)

**Prérequis :** `docker compose up -d --build`, puis attendre que les services soient prêts (icônes vertes ou `docker compose ps`).

### 3.1 Vue d’ensemble du workflow


| Page                            | URL (hôte)                                                        | Rôle                                                                                                                                                                                                               |
| ------------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Carte workflow + liens          | `http://localhost/workflow/`                                      | Schéma statique et raccourcis vers les services (Nginx doit être démarré).                                                                                                                                         |
| MS1 — formulaire de prédiction  | `http://localhost:5001/ui/dashboard`                              | Saisie métrique, lancement QoS / congestion, graphique, historique.                                                                                                                                                |
| MS1 — historique                | `http://localhost:5001/ui/history`                                | Dernières lignes `qos_predictions` en tableau.                                                                                                                                                                     |
| MS1 — doc API interactive       | `http://localhost:5001/docs`                                      | Swagger / OpenAPI.                                                                                                                                                                                                 |
| MS3 — login NOC                 | `http://localhost:5003/login` **ou** `http://localhost/noc/login` | Authentification opérateur (via Nginx : préfixe `/noc/`).                                                                                                                                                          |
| MS3 — tableau de bord           | Après login : **Dashboard**                                       | Résumé, prédictions, anomalies, alertes.                                                                                                                                                                           |
| MS3 — opérations                | Lien **Operations** dans le NOC                                   | Tranches, seuils `operator_thresholds`, liste d’alertes / acquittement.                                                                                                                                            |
| MS5 — inventaire modèles        | `http://localhost:5005/ui`                                        | Liste des modèles enregistrés côté MS5.                                                                                                                                                                            |
| MS5 — doc API                   | `http://localhost:5005/docs`                                      | Si exposé par le service.                                                                                                                                                                                          |
| MS2 — doc API (pas d’UI métier) | `http://localhost:5000/docs`                                      | Tester **POST** `/api/anomaly/detect` depuis Swagger si tu ne veux pas utiliser `curl`.                                                                                                                            |
| MLflow                          | `http://localhost:5006`                                           | Service **requis** pour tracer l’entraînement ; démarré avec `docker compose up -d` (ou `docker compose up -d mlflow`).                                                                                            |
| **Kibana — supervision ELK**    | `**http://localhost:5601`**                                       | Tableaux de bord et explorateur **Discover** sur les indices `metricbeat-*` (CPU / mémoire / réseau host + conteneurs) et `network-slicing-metrics` (accuracy modèles indexée par CD). Premier démarrage ~60–90 s. |
| **Elasticsearch — API moteur**  | `**http://localhost:9200`**                                       | API REST brute (santé cluster, recherche indices). Utilisée par Metricbeat (`output.elasticsearch`) et `scripts/push_metadata_to_elasticsearch.py`.                                                                |


**MS1 derrière Nginx :** le fichier `nginx.conf` expose aussi `http://localhost/prediction/...` vers MS1. En l’état, **sans** variable d’environnement `MS1_PUBLIC_PREFIX=/prediction` sur le service **ms1**, les formulaires et fichiers statiques du dashboard MS1 sont prévus pour le port direct **5001**. Pour un parcours UI simple, **utilise `http://localhost:5001/ui/dashboard`**. (Si tu configures `MS1_PUBLIC_PREFIX=/prediction` sur ms1 et redémarres le conteneur, tu peux alors tout enchaîner via `http://localhost/prediction/ui/dashboard`.)

### 3.2 Formulaire MS1 (`/ui/dashboard`) — champs et rôle

Le formulaire **Run prediction** envoie les mêmes informations que l’API JSON documentée dans Swagger (`QoSPredictRequest` dans `app.py`). Les valeurs ci-dessous reprennent les **valeurs par défaut** du template ; tu peux les modifier selon ton scénario.


| Champ                          | Exemple     | Rôle                                                                                                                                                                                                                                                                                                                                                                             |
| ------------------------------ | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Slice id**                   | `slice_001` | Identifiant libre (inventaire, corrélation logs, affichage NOC). **Ne choisit pas** les seuils SLA : le profil de congestion utilise `slice_type` explicite ou la prédiction RF (voir ci-dessous).                                                                                                                                                                               |
| **Time (hour)**                | `12`        | Heure de la journée **0–23**, enregistrée avec la ligne en base (`qos_predictions`) pour l’historique et le graphique de tendance.                                                                                                                                                                                                                                               |
| **PLR**                        | `0.001`     | *Packet Loss Rate* en **fraction** entre 0 et 1 (ex. `0.001` ≈ 0,1 %). Entre dans le moteur de congestion et dans les features ML via **log₁₀(PLR)** (aligné sur `scripts/train_models.py`).                                                                                                                                                                                     |
| **Delay (ms)**                 | `50`        | Latence paquet en millisecondes. Entre dans la classification congestion / pression, le score QoS dérivé, et le vecteur ML.                                                                                                                                                                                                                                                      |
| **LTE/5G cat**                 | `0`         | Champ optionnel hérité du jeu d’entraînement (catégorie LTE/5G). Si `**lte_5g`** vaut 0 et que cette valeur est **non nulle**, le backend peut quand même marquer la ligne comme LTE/5G pour les features (`slice_inference.build_engineered_feature_row`).                                                                                                                      |
| **Jitter (ms)**                | `0`         | Variation de délai. Toute valeur **strictement positive** augmente l’**indice de pression** dans `congestion_engine` (pondération du score jitter). À 0, ce terme ne contribue pas.                                                                                                                                                                                              |
| **Slice type (1–3, optional)** | *(vide)*    | Type de tranche « notebook » : **1 = eMBB**, **2 = mMTC**, **3 = URLLC**. Si tu le renseignes, ce choix **prime** sur la sortie RF pour le **profil de congestion** et les références SLA (`congestion_slice_profile`). Laisser vide = le moteur s’appuie sur les modèles RF (artefacts `ml/`) ou sur un repli (`slice_type_hint` côté API, non exposé dans ce formulaire HTML). |


**Drapeaux service (0 ou 1)** — Bloc replié « Service flags » : chaque case vaut **0** (non) ou **1** (oui). Ils reproduisent les colonnes binaires du dataset d’entraînement et alimentent le modèle de type de tranche (RF / XGB / MLP) ainsi que des features dérivées (`**Is_Critical`**, `**Is_IoT_Service**`, `**QoS_Score**`) calculées côté serveur comme à l’entraînement.

- `**lte_5g**` — Présence / usage LTE ou 5G pour la tranche (feature « LTE/5G »).
- `**gbr**` — Service à **G**aranteed **B**it **R**ate (GBR).
- `**ar_vr_gaming`**, `**healthcare**`, `**industry_4_0**`, `**iot_devices**`, `**public_safety**`, `**smart_city_home**`, `**smart_transportation**`, `**smartphone**` — Segments d’usage ; les combinaisons servent à la prédiction de classe 1–3 et aux flags critiques / IoT (ex. santé, sécurité publique et transport « intelligents » participent à `**Is_Critical**` ; IoT, ville connectée et industrie 4.0 à `**Is_IoT_Service**`).

Avec **tous les drapeaux à 0** (comme les défauts du formulaire), tu testes un cas « neutre » côté services ; tu peux passer un ou plusieurs flags à **1** pour rapprocher la requête d’un cas métier réel ou du CSV d’entraînement.

### 3.3 Scénario : prédiction QoS puis constat dans le NOC (UI seule)

1. Ouvre `**http://localhost:5001/ui/dashboard`**.
2. Laisse le mode **5G QoS** (ou choisis **Congestion** pour l’autre pipeline).
3. Renseigne au minimum **Slice id** (ex. `ui_demo_01`), **PLR**, **Delay**, etc., puis clique **Predict**.
4. Vérifie la carte **Last result** (score QoS, congestion, pression, SLA).
5. Ouvre `**http://localhost:5003/login`** (ou `/noc/login`), connecte-toi (par défaut souvent `admin` / `changeme` — voir `docker-compose` / `.env`).
6. Sur le **Dashboard** MS3, la section **Prédictions QoS récentes** doit montrer la nouvelle ligne (données lues depuis MySQL).
7. Ouvre **Operations** : `http://localhost:5003/ops` ou `**http://localhost/noc/ops`** (même page derrière Nginx). Voir ci-dessous ce que tu y vois par défaut.

#### Forcer une alerte **CRITICAL** (MS3) — procédure et limites du moteur

Le flux décrit dans le guide est **correct** : MS1 appelle MS3 en `**POST /api/sync/prediction`** après une écriture réussie en base ; MS3 crée une alerte **CRITICAL** seulement si `congestion_level` vaut exactement `**High`** (congestion sévère). Vérifie sur le conteneur **ms1** : variable `**MS3_URL`** pointant vers MS3 (ex. `http://ms3:5000`) et **pas** de `DISABLE_MS3_SYNC` activé.

**Piège fréquent (UI MS1) :** la pression est une combinaison pondérée de délai, PLR, jitter, stress débit, mobilité (`congestion_engine.py`). Avec **jitter = 0** et sans débit / mobilité, la contribution **délai + PLR seule** ne dépasse pas **~56** sur 100. Or les bandes **Medium → High** pour les profils **eMBB (1)** et **mMTC (2)** sont au-delà de **66** / **68** : tu restes donc souvent en **Medium** même avec délai et PLR « très mauvais ».

**Moyens simples pour obtenir `High` depuis le dashboard MS1 :**

1. **Profil URLLC** — Renseigne **Slice type = `3`**. Les seuils **Medium** s’arrêtent à **55** ; avec des métriques déjà sévères (ex. **Delay (ms)** `80`–`200`, **PLR** `0.001`–`0.01`), la pression peut dépasser **55** → **High** → alerte possible après sync.
2. **Profils 1 / 2** — Ajoute un **Jitter (ms)** suffisant (ex. `**10`** ou plus) en gardant délai et PLR élevés, pour que la pression dépasse `pressure_medium_max`.
3. **API** — Tu peux aussi envoyer `demand_mbps` / `capacity_mbps` (surcharge) via l’API JSON si tu automatises le test.

Contrôle le résultat sur MS1 : carte **Last result** → **Congestion (API)** doit afficher `**High`** (affichage opérateur **Critical**). Ensuite rafraîchis le **Dashboard** ou **Operations** MS3 : l’alerte apparaît dans `**alerts`**.

#### Page **Operations** (`/ops`) : tableaux vides — normal ou pas ?


| Section                        | Remplissage                                                                                                                                                                                                                                                                                                         |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Network slices (inventory)** | **Manuel uniquement** (formulaire *Add / update*). Rien n’insère ici automatiquement depuis MS1. Vide au départ = attendu.                                                                                                                                                                                          |
| **Congestion pressure bands**  | **Manuel** (sauvegardes opérateur dans `operator_thresholds`). Si vide, le message *« No overrides (defaults apply) »* est normal : MS1 utilise les seuils par défaut du moteur (et fusionne la table **seulement** si `CONGESTION_THRESHOLDS_FROM_DB=true`, ce qui est le cas dans `docker-compose` pour **ms1**). |
| **Alerts**                     | **Automatique** après sync MS1 lors d’un `**High`**, ou toute autre logique qui écrit dans `alerts`. Si vide : pas encore de **High**, sync désactivée, ou MS3 injoignable depuis MS1. Sur `/ops`, le bouton **Acknowledge** concerne les alertes **non** encore acquittées.                                        |


### 3.4 Scénario : anomalies visibles dans le NOC

MS2 n’a pas d’écran HTML dédié ; les anomalies apparaissent dans MS3 quand des lignes existent en base.

- **Option UI :** `http://localhost:5000/docs` → exécute **POST** `/api/anomaly/detect` avec un corps JSON aligné sur l’entraînement : `slice_id`, `packet_loss_rate` (0–1), `packet_delay` (ms), drapeaux service 0/1 (`lte_5g`, `gbr`, etc.). Les champs supplémentaires sont ignorés.
- Reviens sur `**http://localhost:5003/...` dashboard** → section **Anomalies récentes**.

Si l’appel échoue (modèles manquants), lance d’abord un entraînement (section **9**, commandes `docker compose` + `ci_train.csv`) pour générer les fichiers sous `ml/`.

### 3.5 Scénario : modèles MS5

1. Ouvre `**http://localhost:5005/ui`** pour voir la liste.
2. Après un **entraînement CI** (§9, `docker compose` + `ci_train.csv`) ou un entraînement complet, si l’enregistrement automatique vers MS5 est actif et MS5 joignable, de nouvelles entrées peuvent apparaître ; sinon tu peux toujours enregistrer un modèle test via **POST** `/models/register` dans `**http://localhost:5005/docs`** (section API ci-dessous).

### 3.6 Scénario : historique et export (MS1)

- `**http://localhost:5001/ui/history**` : liste des prédictions récentes.
- Lien **Export CSV** sur le dashboard MS1 : télécharge un export des prédictions (selon les droits / données présentes).

### 3.7 Scénario : supervision ELK (Elasticsearch + Kibana + Metricbeat)

La stack de supervision démarre **automatiquement** avec `docker compose up -d` (pas de profil dédié). Trois services entrent en jeu :


| Composant         | URL hôte                | Conteneur (réseau Docker)   | Rôle                                                                                                                                                                                         |
| ----------------- | ----------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Elasticsearch** | `http://localhost:9200` | `http://elasticsearch:9200` | Moteur de stockage / recherche. Reçoit les métriques de Metricbeat et les documents d’entraînement (`network-slicing-metrics`).                                                              |
| **Kibana**        | `http://localhost:5601` | `http://kibana:5601`        | UI : **Discover**, **Dashboard**, **Stack Management**. Branche sur `ELASTICSEARCH_HOSTS=http://elasticsearch:9200`.                                                                         |
| **Metricbeat**    | — *(pas de port hôte)*  | —                           | Agent qui collecte les métriques **système** (CPU, mémoire, réseau, disque, fs) et **Docker** (containers, CPU, mémoire, réseau, diskio) → ES toutes les 10 s (`metricbeat/metricbeat.yml`). |


#### Vérifications rapides côté navigateur

1. Ouvre `**http://localhost:5601`**. Si une page « Kibana server is not ready yet » s’affiche, patiente : Elasticsearch ou Metricbeat finit son démarrage.
2. Une fois Kibana prêt, va dans **☰ → Discover** :
  - Sélectionne le data view `**metricbeat-*`** (créé automatiquement par `setup.dashboards.enabled: true` côté Metricbeat).
  - Tu dois voir des documents avec `event.module = system` (hôte) et `event.module = docker` (conteneurs `network-slicing-*`).
3. **☰ → Dashboard** : ouvre par exemple `**[Metricbeat System] Host overview ECS`** ou `**[Metricbeat Docker] Overview ECS**` pour visualiser CPU, mémoire, réseau, disque.
4. Pour le **suivi des modèles ML** indexé par le pipeline CD :
  - Crée (si besoin) un data view sur le pattern `**network-slicing-metrics*`** (champ temps : `@timestamp`).
  - Filtre par `pipeline: train_models` → tu verras les `accuracies.rf / xgb / mlp` produits par `scripts/push_metadata_to_elasticsearch.py`.

#### Vérifications API (curl, sans Kibana)

```bash
curl -s "http://localhost:9200/_cluster/health?pretty"
curl -s "http://localhost:9200/_cat/indices?v"
curl -s "http://localhost:9200/metricbeat-*/_count?pretty"
curl -s "http://localhost:9200/network-slicing-metrics/_search?pretty&size=1"
```

**Attendus :**

- `_cluster/health` → `status: green` ou `yellow` (mono-nœud).
- `_cat/indices` → présence d’index `metricbeat-8.x-YYYY.MM.DD` et, après une CD, `network-slicing-metrics`.
- `_count` > 0 dès que Metricbeat a poussé sa première salve (~10–30 s).

#### Indexer manuellement les métadonnées du dernier entraînement

Le script `scripts/push_metadata_to_elasticsearch.py` lit `ml/metadata.json` et indexe accuracy + run MLflow dans `network-slicing-metrics`. Variables clés : `**ELASTICSEARCH_URL`** (défaut `http://localhost:9200`) et `**ELASTICSEARCH_INDEX**` (défaut `network-slicing-metrics`).

```bash
python scripts/push_metadata_to_elasticsearch.py
```

Depuis le conteneur `ci` (réseau Docker, ES atteignable via DNS interne) :

```bash
docker compose --profile ci run --rm --no-deps -e ELASTICSEARCH_URL=http://elasticsearch:9200 ci python scripts/push_metadata_to_elasticsearch.py
```

#### Désactiver la sortie Elasticsearch côté entraînement

Pour l’entraînement CI (§9), on passe `**DISABLE_ELASTICSEARCH_PUSH=1**` afin que `train_models.py` n’essaie pas d’atteindre ES depuis un environnement sans stack (cas GitHub Actions).

#### Pannes courantes (monitoring)

- **Kibana en boucle « not ready »** : attendre 60–90 s, ou `docker compose logs -f kibana` puis `docker compose logs -f elasticsearch` (souvent : ES pas encore `yellow`).
- **Aucun index `metricbeat-*`** : `docker compose logs -f metricbeat`. Sous Docker Desktop Windows/macOS, les statistiques host reflètent la VM Linux interne — c’est attendu.
- `**network-slicing-metrics` vide** : aucune CD n’a tourné, ou `ml/metadata.json` absent (lancer un entraînement §9 d’abord).

---

## 4. Cas d’usage A — Démarrer toute la stack et vérifier la santé

```bash
docker compose up -d --build
```

Attendre que MySQL et les healthchecks soient verts, puis :

```bash
curl -s http://localhost:5001/health
curl -s http://localhost:5000/health
curl -s http://localhost:5003/health
curl -s http://localhost:5005/health
curl -s http://localhost/health
```

**Résultat attendu :** JSON avec `"status": "healthy"` (ou équivalent) pour chaque service.

**Monitoring ELK (santé du cluster, voir aussi §3.7) :**

```bash
curl -s "http://localhost:9200/_cluster/health?pretty"
curl -s http://localhost:5601/api/status
```

Le cluster doit être `green` ou `yellow` (mode mono-nœud), et Kibana doit répondre `available`. Premier démarrage : compter ~60 s pour Elasticsearch et ~90 s supplémentaires pour Kibana.

**Arrêt :**

```bash
docker compose down
```

---

## 5. Cas d’usage B — Workflow opérateur : prédiction QoS (MS1) + persistance + sync MS3 *(API / optionnel)*

*(Équivalent du scénario UI §3.3 ; utile pour scripts ou Swagger.)*

1. **Prédiction 5G** (depuis l’hôte, MS1 exposé en `5001→5000`) :

```bash
curl -s -X POST http://localhost:5001/predict/qos/5g ^
  -H "Content-Type: application/json" ^
  -d "{\"slice_id\":\"demo_slice\",\"time\":14,\"plr\":0.001,\"delay\":100,\"lte5g_cat\":14}"
```

*(Sous PowerShell, tu peux utiliser `curl.exe` ou un fichier JSON ; sous bash, une seule ligne sans `^`.)*

1. **Vérifier les stats MS1** :

```bash
curl -s http://localhost:5001/predict/stats
```

1. **MS3 — données agrégées (API, sans cookie)** :

```bash
curl -s http://localhost:5003/api/dashboard-data
```

1. **UI NOC** : ouvrir dans le navigateur
  - `http://localhost:5003/login` ou `http://localhost/noc/login`  
  - identifiants par défaut (voir `docker-compose` / `.env.example`) : utilisateur / mot de passe dashboard.

**Cas limite utile pour les alertes :** refaire une prédiction avec des métriques très dégradées pour obtenir `congestion_level` égal à `**High`** ; MS1 notifie MS3 et une alerte **CRITICAL** peut apparaître dans la section Alertes du dashboard (si la sync n’est pas désactivée : `DISABLE_MS3_SYNC`).

---

## 6. Cas d’usage C — Détection d’anomalies (MS2) *(API / optionnel)*

```bash
curl -s -X POST http://localhost:5000/api/anomaly/detect ^
  -H "Content-Type: application/json" ^
  -d "{\"slice_id\":\"demo_slice\",\"packet_loss_rate\":0.001,\"packet_delay\":12.3,\"lte_5g\":1,\"gbr\":0,\"ar_vr_gaming\":0,\"healthcare\":0,\"industry_4_0\":0,\"iot_devices\":1,\"public_safety\":0,\"smart_city_home\":0,\"smart_transportation\":0,\"smartphone\":0}"
```

Puis :

```bash
curl -s "http://localhost:5000/api/anomaly/stats?days=7"
```

**Si erreur liée aux modèles :** exécuter le cas d’usage F (entraînement CI) pour générer les `.pkl` sous `ml/`.

---

## 7. Cas d’usage D — Gestion des modèles (MS5) *(API / optionnel)*

```bash
curl -s http://localhost:5005/models
```

Enregistrement test (exemple) :

```bash
curl -s -X POST http://localhost:5005/models/register ^
  -H "Content-Type: application/json" ^
  -d "{\"model_name\":\"manual_test\",\"model_version\":\"1.0.0\",\"accuracy\":0.9,\"precision\":0.89,\"recall\":0.91,\"f1_score\":0.9,\"roc_auc\":0.95,\"log_loss\":0.3,\"training_time\":1.0}"
```

**UI MS5 :** `http://localhost:5005/ui` (voir §3.5).

---

## 8. Cas d’usage E — Passerelle Nginx et carte du workflow

- **Racine API gateway :** `http://localhost/`
- **Workflow UI (diagramme / liens) :** `http://localhost/workflow/`
- **MS3 derrière Nginx :** préfixe `/noc/` (login dashboard)

Vérifie que `nginx` est bien `up` dans `docker compose ps`.

---

## 9. Cas d’usage F — Entraînement ML (local)

### Entraînement court (même logique que CI)

À la racine du dépôt (là où se trouve `docker-compose.yml`). Tu peux enchaîner les deux lignes telles quelles sous **bash** ; sous **PowerShell**, exécute-les l’une après l’autre (ou mets la deuxième sur une seule ligne).

```bash
docker compose up -d mlflow
docker compose --profile ci run --rm --no-deps -e MLFLOW_TRACKING_URI=http://mlflow:5000 -e DISABLE_ELASTICSEARCH_PUSH=1 -e TRAIN_DATA_PATH=tests/fixtures/ci_train.csv ci python scripts/train_models.py
```

Équivalent **Makefile** (si `make` est installé) : `make train-ci`.

Démarre **MLflow**, utilise `tests/fixtures/ci_train.csv`, envoie le run au tracking (`MLFLOW_TRACKING_URI=http://mlflow:5000`), et produit / met à jour les sorties sous `ml/`.

### Entraînement sur le jeu versionné (défaut du projet)

Chemin par défaut aligné sur `**scripts/train_models.py`** et `**.env.example**` : `**./data/train_dataset.csv**`. Le service `**ci**` monte le dépôt en `**/app**` (`working_dir: /app`), donc ce chemin relatif est le même à l’intérieur du conteneur.

**Prérequis :** `docker compose up -d mlflow`.

**PowerShell** (une seule ligne, sans échappement `^` de cmd.exe) :

```powershell
docker compose --profile ci run --rm --no-deps -e MLFLOW_TRACKING_URI=http://mlflow:5000 -e DISABLE_ELASTICSEARCH_PUSH=1 -e TRAIN_DATA_PATH=./data/train_dataset.csv ci python scripts/train_models.py
```

**PowerShell** (plusieurs lignes — continuation avec le **backtick** ``` en fin de ligne) :

```powershell
docker compose --profile ci run --rm --no-deps `
  -e MLFLOW_TRACKING_URI=http://mlflow:5000 `
  -e DISABLE_ELASTICSEARCH_PUSH=1 `
  -e TRAIN_DATA_PATH=./data/train_dataset.csv `
  ci python scripts/train_models.py
```

**bash** (équivalent une ligne) :

```bash
docker compose --profile ci run --rm --no-deps -e MLFLOW_TRACKING_URI=http://mlflow:5000 -e DISABLE_ELASTICSEARCH_PUSH=1 -e TRAIN_DATA_PATH=./data/train_dataset.csv ci python scripts/train_models.py
```

**Autre fichier dans le dépôt :** garde un chemin relatif à la racine du repo, par ex. `TRAIN_DATA_PATH=tests/fixtures/ci_train.csv`, ou absolu dans le conteneur : `TRAIN_DATA_PATH=/app/data/mon_autre.csv`. Un CSV **hors du dossier du projet** n’est pas visible dans `ci` tant qu’il n’est pas ajouté au volume Compose (copie dans `data/` ou montage dédié).

### MLflow (requis pour l’entraînement)

Le service `**mlflow`** fait partie de la stack : `docker compose up -d` le lance comme les autres services. Vérifie les variables `**MLFLOW_***` dans `.env` (voir `.env.example`). UI : `**http://localhost:5006**` (mapping hôte du `docker-compose.yml`).

---

## 10. Cas d’usage G — CI locale (qualité + tests unitaires, sans stack microservices)

Même image `ci` que les workflows ; exécuter depuis la racine du dépôt :

```bash
docker compose --profile ci run --rm --no-deps ci ruff check .
docker compose --profile ci run --rm --no-deps ci black --check .
docker compose --profile ci run --rm --no-deps ci sh -c "bandit -c bandit.yaml -r . -ll -q && pip-audit -r requirements.txt"
docker compose --profile ci run --rm --no-deps ci pytest tests/unit -v
```

Équivalent **Makefile** : `make ci`.

Enchaîne : **Ruff**, **Black --check**, **Bandit + pip-audit**, **pytest tests/unit**.

---

## 11. Cas d’usage H — Tests d’intégration (stack requise)

Avec la stack déjà démarrée (`docker compose up -d`) :

```bash
docker compose --profile ci run --rm --no-deps ci pytest test_api.py -v
```

Équivalent **Makefile** : `make ci-integration`.

**Couverture typique de `test_api.py` :** health MS1–MS5, prédiction QoS + erreur 400, stats MS1/MS2, agrégat MS3, liste / enregistrement MS5, endpoints Nginx `/` et `/health`.

---

## 12. Cas d’usage I — GitHub Actions (dépôt sur GitHub)

1. Pousser sur les branches configurées (`main`, `jihed` selon `.github/workflows/ci.yml`).
2. Onglet **Actions** :
  - **CI** : qualité + unitaires + job d’intégration (stack Docker sur le runner).
  - **ML pipeline** : entraînement planifié (cron hebdomadaire), manuel, ou sur push limité à certains chemins (`Makefile`, `scripts/train_models.py`, etc.) — **avec MLflow** (service démarré sur le runner).

---

## 13. Tableau récapitulatif des objectifs → UI / commandes / URLs


| Objectif                           | Action principale                                                                                                                       |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Données minimales dans le repo     | Déjà : `tests/fixtures/ci_train.csv`                                                                                                    |
| Gros dataset privé                 | `TRAIN_DATA_PATH` + fichier hors Git ou chemin local                                                                                    |
| Tout démarrer                      | `docker compose up -d --build`                                                                                                          |
| Parcours UI complet                | **§3** — workflow map, MS1 dashboard (**§3.2** champs formulaire), MS3 NOC, MS5 `/ui`, Swagger MS2                                      |
| Vérifier services (rapide)         | `curl .../health` (§4) ou liens `/docs` / pages UI                                                                                      |
| QoS + BDD + MS3                    | **UI :** §3.3 (`:5001/ui/dashboard` puis `:5003` dashboard) ; **API :** §5                                                              |
| Anomalies                          | **UI :** Swagger `5000/docs` + tableau MS3 ; **API :** §6                                                                               |
| MS5                                | **UI :** `http://localhost:5005/ui` ; **API :** §7                                                                                      |
| Qualité code locale                | §10 — quatre `docker compose --profile ci run ...` (Ruff, Black, Bandit/pip-audit, pytest unit)                                         |
| Tests API bout-en-bout             | §11 — `docker compose --profile ci run --rm --no-deps ci pytest test_api.py -v` (stack `up`)                                            |
| Entraînement comme en CI           | §9 — `docker compose up -d mlflow` puis `run ... ci python scripts/train_models.py` avec `TRAIN_DATA_PATH=tests/fixtures/ci_train.csv`  |
| Suivi des runs ML                  | UI `http://localhost:5006` après `docker compose up`                                                                                    |
| Supervision système / Docker (ELK) | **UI :** `http://localhost:5601` (Kibana → Discover `metricbeat-`* ou dashboards préchargés) ; **API :** `http://localhost:9200` (§3.7) |
| Suivi accuracy modèles (Kibana)    | Data view `network-slicing-metrics`* après `python scripts/push_metadata_to_elasticsearch.py` (§3.7)                                    |
| Automatisation distante            | GitHub Actions (`ci.yml`, `ml-pipeline.yml`)                                                                                            |


---

*Document généré pour accompagner les tests du projet Network Slicing : données, Docker Compose, Makefile (raccourcis optionnels) et cas d’usage API/UI.*