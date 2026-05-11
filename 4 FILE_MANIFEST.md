# Infrastructure Docker — inventaire des fichiers

> **Vue simple (langage clair, tous les services) :** `GUIDE_SIMPLE_PROJET.md`

## Résumé

Infrastructure microservices complète basée sur Docker : services métier (**MySQL, MS1–MS5, Nginx**), outils **MLflow**, stack **Elasticsearch / Kibana / Metricbeat**, et service **`ci`** (profil Docker) pour la qualité et les tests.

## Liste complète des fichiers

### Fichiers de configuration à la racine

- `docker-compose.yml` — Orchestration : MySQL, MS1, MS2, MS3, MS5, Nginx, MLflow, Elasticsearch, Kibana, Metricbeat, service `ci` (profil `ci`)
- `Dockerfile` — Conteneur de production pour MS1 (uvicorn / FastAPI, health checks, Python 3.10-slim)
- `nginx.conf` — Reverse proxy avec limitation de débit, en-têtes de sécurité, routage
- `init.sql` — Schéma de base avec les tables : qos_predictions, anomaly_detections, model_metrics, alerts, system_logs
- `requirements.txt` — Dépendances principales (fastapi, uvicorn, scikit-learn, xgboost, mysql-connector, shap, optuna, joblib, mlflow, …)
- `.dockerignore` — Exclusions de build (node_modules, __pycache__, data, models, logs, .git)
- `config.py` — Configuration centrale avec chargement des variables d’environnement
- `models.py` — ORM de la base avec BaseModel et modèles spécialisés
- `alert_service.py` — Envoi des alertes par e-mail (SMTP)
- `app.py` — Application **FastAPI** MS1 (prédiction QoS, UI, `/docs`)
- `test_api.py` — Tests d’intégration Pytest pour tous les services
- `init_db.py` — Script d’initialisation de la base pour le développement local
- `Makefile` — Commandes CLI pour toutes les opérations Docker
- `.env.example` — Modèle de variables d’environnement
- `INFRASTRUCTURE.md` — Documentation complète de l’infrastructure
- `DOCKER_README.md` — Guide de déploiement convivial
- `deploy.sh` — Script de déploiement Bash

### Arborescence des répertoires

```
5G-NetworkSlicing/
│
├── Fichiers racine principaux (voir ci-dessus)
│
├── anomaly/                    # MS2 — Service de détection d’anomalies
│   ├── Dockerfile              # Python 3.10-slim, TensorFlow CPU pour .h5
│   ├── requirements.txt        # FastAPI, scikit-learn, tensorflow-cpu, …
│   └── app.py                  # API FastAPI — détection d’anomalies
│
├── ms3/                        # MS3 — NOC / tableau de bord
│   ├── Dockerfile              # Python 3.10-slim, app.py comme point d’entrée
│   ├── requirements.txt        # FastAPI, Jinja2, pandas, mysql-connector, …
│   ├── templates/              # login, dashboard, ops, …
│   └── app.py                  # UI + API agrégées + alertes
│
├── ms5_model_management/       # MS5 — Service de gestion des modèles
│   ├── Dockerfile              # Python 3.10-slim, app.py comme point d’entrée
│   ├── requirements.txt        # FastAPI, pandas, mysql-connector, …
│   ├── templates/              # UI inventaire modèles
│   └── app.py                  # API du registre de modèles et des métriques
│
├── metricbeat/                 # Config Beat → Elasticsearch
│   └── metricbeat.yml
│
├── workflow_ui/                # Fichiers statiques Nginx (/workflow/)
│
├── ml/                         # Répertoire des modèles ML (monté en volume)
│   └── .gitkeep
│
├── data/                       # Stockage des données (monté en volume)
│   ├── train_dataset.csv      # CSV d’entraînement par défaut (TRAIN_DATA_PATH)
│   ├── raw/.gitkeep           # Données brutes de trafic réseau
│   ├── processed/.gitkeep     # Données d’entraînement traitées
│   └── test/.gitkeep          # Jeux de données de test
│
├── logs/                       # Journaux d’application (monté en volume)
│   └── .gitkeep
│
└── ssl/                        # Certificats SSL pour HTTPS
    └── README.md              # Instructions pour ajouter les certificats
```

## Détails de l’infrastructure

### Configuration des services

| Service | Image | Build | Ports | Volumes | Réseau |
|---------|-------|-------|-------|---------|---------|
| MySQL | `mysql:8.0` | - | 3306:3306 | `mysql_data` | `network-slicing-network` |
| MS1 | Personnalisée | `Dockerfile` | 5001:5000 | - | `network-slicing-network` |
| MS2 | Personnalisée | `anomaly/Dockerfile` | 5000:5000 | - | `network-slicing-network` |
| MS3 | Personnalisée | `ms3/Dockerfile` | 5003:5000 | - | `network-slicing-network` |
| MS5 | Personnalisée | `ms5_model_management/Dockerfile` | 5005:5000 | `ms5_models` | `network-slicing-network` |
| Nginx | `nginx:alpine` | - | 80:80, 443:443 | `./nginx.conf`, `workflow_ui`, `ssl` | `network-slicing-network` |
| MLflow | Personnalisée | `Dockerfile.mlflow` | 5006:5000 | `./ml` | `network-slicing-network` |
| Elasticsearch | `docker.elastic.co/.../elasticsearch:8.11.4` | - | 9200:9200 | `es_data` | `network-slicing-network` |
| Kibana | `docker.elastic.co/.../kibana:8.11.4` | - | 5601:5601 | - | `network-slicing-network` |
| Metricbeat | `docker.elastic.co/.../metricbeat:8.11.4` | - | - | `metricbeat/metricbeat.yml`, sockets host | `network-slicing-network` |

*(Le service **`ci`** utilise le profil `ci` : pas de port public ; voir `GUIDE_CI_MLOPS_ETUDIANT.md`.)*

### Implémentation des health checks

```python
# Chaque service expose /health et renvoie :
{
  "status": "healthy",
  "service": "<Service-Name>",
  "timestamp": "2026-05-09T18:34:32.123456"
}
```

### Schéma de base de données (init.sql)

**Tables :**
1. `qos_predictions` — Historique des prédictions QoS
2. `anomaly_detections` — Enregistrements de détection d’anomalies
3. `model_metrics` — Suivi des performances des modèles
4. `alerts` — Journal des alertes système
5. `system_logs` — Journaux généraux de l’application

### Routage Nginx

**Serveurs upstream définis :**
- `ms1_backend` → `ms1:5000`
- `ms2_backend` → `ms2:5000`
- `ms3_backend` → `ms3:5000`
- `ms5_backend` → `ms5:5000`

**Routes :**
- `/api/ms1/*` → MS1 (limitation de débit)
- `/api/ms2/*` → MS2 (limitation de débit)
- `/api/ms3/*` → MS3 (limitation de débit)
- `/api/ms5/*` → MS5 (limitation de débit)
- `/health` → Relais du health check
- `/` → État de la passerelle API

**Sécurité :**
- X-Frame-Options: SAMEORIGIN
- X-Content-Type-Options: nosniff
- X-XSS-Protection: 1; mode=block
- Limitation de débit : 10 req/s avec rafale de 20

## Dépendances par service

### MS1 (prédiction QoS)

Voir `requirements.txt` à la racine : **FastAPI**, **uvicorn**, scikit-learn, xgboost, mysql-connector, shap, optuna, joblib, mlflow, jinja2, etc.

### MS2 (détection d’anomalies)

Voir `anomaly/requirements.txt` : FastAPI, uvicorn, scikit-learn, **tensorflow-cpu** (autoencodeur `.h5`), joblib, etc.

### MS3 (tableau de bord)

Voir `ms3/requirements.txt` : FastAPI, uvicorn, Jinja2, mysql-connector, pandas, etc.

### MS5 (gestion des modèles)

Voir `ms5_model_management/requirements.txt` et le `requirements.txt` racine selon l’image construite : FastAPI, uvicorn, pandas, mysql-connector, etc.

## États de déploiement

### Construction initiale
```bash
# Télécharger les images de base
docker pull python:3.10-slim
docker pull mysql:8.0
docker pull nginx:alpine

# Construire les images personnalisées (4 services)
docker-compose build

# Durée de build attendue : 5 à 10 minutes
```

### État d’exécution
- Tous les services démarrent avec `restart: unless-stopped`
- MySQL initialise la base à partir de `init.sql` au premier lancement
- Les services attendent la santé de MySQL avant de démarrer (chaîne de dépendances)
- Nginx démarre immédiatement mais attend les backends

### Topologie réseau

```
[Hôte]
  │
  ├── 80/443 (Nginx) ───┐
  │                      │
  ├── 5001 (MS1) ───────┘
  ├── 5000 (MS2) ───────┐
  ├── 5003 (MS3) ───────┘
  ├── 5005 (MS5) ───────┐
  │                      │
  └── 3306 (MySQL) ←────┘
        │
        └── network-slicing-network (bridge)
              ├── mysql
              ├── ms1
              ├── ms2
              ├── ms3
              ├── ms5
              └── nginx
```

## Commandes de nettoyage

```bash
# Arrêter tous les services, conserver les données
docker-compose down

# Arrêter et supprimer toutes les données
docker-compose down -v

# Supprimer les images
docker-compose down --rmi all

# Nettoyage complet (conteneurs, réseaux, volumes, images)
docker system prune -a --volumes

# Supprimer des volumes spécifiques
docker volume rm network-slicing_mysql_data
docker volume rm network-slicing_ms5_models
docker volume rm network-slicing_es_data
```

## Préparation à la production

### État actuel : prêt pour le développement

**Améliorations nécessaires pour la production :**
1. Remplacer les mots de passe par défaut
2. Activer SSL/TLS dans Nginx
3. Ajouter un middleware d’authentification
4. Configurer des limites de ressources
5. Mettre en place une base de données externe
6. Implémenter une agrégation de journaux adaptée
7. Ajouter la supervision (métriques Prometheus)
8. Définir des stratégies de sauvegarde
9. Mettre en place un pipeline CI/CD
10. Lancer des analyses de sécurité

**Liste de contrôle du déploiement en production :** voir `DOCKER_README.md`

---

**Créé le :** 2026-05-09  
**État :** Infrastructure complète ✓  
**Prêt pour :** développement et tests
