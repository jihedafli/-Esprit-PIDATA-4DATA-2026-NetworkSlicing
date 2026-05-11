# Infrastructure Docker — configuration complète

> **Vue d’ensemble simple (liste des services et fichiers) :** `GUIDE_SIMPLE_PROJET.md`

## Vue d’ensemble

Infrastructure Docker complète pour le projet de découpage réseau 5G : microservices **MS1–MS5**, **MySQL**, **Nginx**, **MLflow**, stack **Elasticsearch / Kibana / Metricbeat**, et service **`ci`** (profil Docker) pour tests et qualité.

## Fichiers créés

### Niveau racine

| Fichier | Rôle |
|------|---------|
| `docker-compose.yml` | Fichier d’orchestration principal pour tous les services |
| `Dockerfile` | Conteneur de production pour MS1 (Python 3.10-slim) |
| `.dockerignore` | Exclusions de build pour le contexte Docker |
| `requirements.txt` | Dépendances Python principales pour tous les services |
| `nginx.conf` | Configuration du reverse proxy |
| `init.sql` | Initialisation du schéma de base de données |
| `config.py` | Paramètres de configuration centralisés |
| `models.py` | Modèles ORM de la base de données |
| `alert_service.py` | Gestion des alertes e-mail (SMTP) |
| `app.py` | Application principale MS1 (prédiction QoS) |
| `Makefile` | Commandes CLI pratiques |
| `.env.example` | Modèle de variables d’environnement |
| `test_api.py` | Suite de tests d’intégration |
| `init_db.py` | Script d’initialisation de la base de données |
| `DOCKER_README.md` | Documentation complète |

### Par service

**MS2 (détection d’anomalies) :**
- `anomaly/Dockerfile`
- `anomaly/requirements.txt`
- `anomaly/app.py` — service **FastAPI** pour la détection d’anomalies

**MS3 (tableau de bord) :**
- `ms3/Dockerfile`
- `ms3/requirements.txt`
- `ms3/app.py` — service de tableau de bord et d’agrégation d’alertes

**MS5 (gestion des modèles) :**
- `ms5_model_management/Dockerfile`
- `ms5_model_management/requirements.txt`
- `ms5_model_management/app.py` — registre de modèles et service de métriques

### Arborescence avec emplacements réservés

```
├── ml/.gitkeep                  # Pour les modèles entraînés
├── data/raw/.gitkeep            # Pour les données brutes
├── data/processed/.gitkeep      # Pour les données traitées
├── data/test/.gitkeep           # Pour les données de test
├── logs/.gitkeep                # Pour les journaux d’application
└── ssl/README.md               # Pour les certificats SSL
```

## Architecture des services

### Vue d’ensemble des services

| Service | Nom | Port | Rôle | Contexte Docker |
|---------|------|------|---------|----------------|
| MySQL | Base de données | 3306 | Stockage persistant des données | Image officielle |
| MS1 | Prédiction QoS | 5001 | Prédire les scores QoS | Répertoire racine |
| MS2 | Détection d’anomalies | 5000 | Détection d’anomalies en temps réel | `./anomaly/` |
| MS3 | Tableau de bord | 5003 | Tableaux de bord de supervision | `./ms3/` |
| MS5 | Gestion des modèles | 5005 | Registre de modèles et métriques | `./ms5_model_management/` |
| Nginx | Passerelle API | 80/443 | Reverse proxy et routage | Image officielle |
| MLflow | Suivi ML | 5006 | Expériences et artefacts (**requis** pour l’entraînement) | `Dockerfile.mlflow` |
| Elasticsearch | Données / métriques | 9200 | Moteur de recherche pour Metricbeat et index ML | Image Elastic |
| Kibana | Visualisation | 5601 | Tableaux de bord sur Elasticsearch | Image Elastic |
| Metricbeat | Collecte | — | Métriques système et Docker → ES | `metricbeat/metricbeat.yml` |

### Configuration réseau

- **Réseau :** `network-slicing-network` (réseau bridge)
- **Isolation :** services isolés dans le réseau Docker
- **Communication :** résolution DNS interne (nom du service comme nom d’hôte)

### Vérifications de santé

Tous les services exposent un point de contrôle de santé répondant sur `/health` :
- Intervalle : 30 secondes
- Délai d’attente : 10 secondes
- Nouvelles tentatives : 3 essais
- Période de démarrage : 40 secondes

## Configuration

### Variables d’environnement

Le système utilise des variables d’environnement pour toute la configuration :

```bash
# Base de données
DB_HOST=mysql
DB_PORT=3306
DB_USER=network_user
DB_PASSWORD=network_pass
DB_NAME=network_slicing_5g

# Application (ex. sessions MS3 — noms de variables peuvent varier selon le service)
FLASK_ENV=production
FLASK_DEBUG=false
SECRET_KEY=<change-this>

# Alertes
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=<your-email>
SENDER_PASSWORD=<app-password>
ALERT_EMAIL=<admin-email>
```

### Volumes

Volumes de données persistants :
- `mysql_data` — fichiers de la base MySQL
- `ms5_models` — artefacts de modèles et points de contrôle

## Routes du reverse proxy Nginx

```
/api/ms1/*  →  http://ms1:5000
/api/ms2/*  →  http://ms2:5000
/api/ms3/*  →  http://ms3:5000
/api/ms5/*  →  http://ms5:5000

/health     →  http://ms1:5000/health
/           →  JSON d’état de l’API
```

**Fonctionnalités :**
- Limitation de débit (10 req/s avec rafale de 20)
- En-têtes de sécurité (X-Frame-Options, X-Content-Type-Options)
- Compression Gzip
- Connexions persistantes (keep-alive)
- Prise en charge HTTPS (certificats SSL dans `/ssl`)

## Dépendances

### Dépendances principales (voir `requirements.txt`)
- **FastAPI** — API HTTP (tous les services exposés)
- **Uvicorn** — serveur ASGI de production
- **MySQL Connector** — connexion à la base de données
- **Scikit-learn** — algorithmes ML
- **XGBoost** — gradient boosting
- **Pandas** / **NumPy** — données et calcul
- **Optuna** — optimisation d’hyperparamètres
- **Joblib** — persistance des modèles
- **SHAP** — explicabilité des modèles
- **MLflow** — suivi d’expériences (**obligatoire** pour `scripts/train_models.py` hors désactivation explicite)
- **Python-dotenv** — variables d’environnement

## Commandes de démarrage rapide

```bash
# Démarrer tous les services (inclut MLflow sur le port 5006 — requis pour l’entraînement nominal)
docker-compose up -d

# Voir tous les journaux
docker-compose logs -f

# Vérifier l’état des services
docker-compose ps

# Arrêter tous les services
docker-compose down

# Reconstruire toutes les images
docker-compose build --no-cache

# Ouvrir un shell MySQL
docker-compose exec mysql mysql -u network_user -pnetwork_pass network_slicing_5g

# Ouvrir un shell dans un service (exemple MS1)
docker-compose exec ms1 /bin/bash

# Journaux d’un service précis
docker-compose logs -f ms1

# Sauvegarder la base de données
docker-compose exec -T mysql mysqldump -u network_user -pnetwork_pass network_slicing_5g > backup.sql

# Arrêter et supprimer toutes les données (ATTENTION)
docker-compose down -v
docker volume rm network-slicing_mysql_data network-slicing_ms5_models network-slicing_es_data
```

### Avec le Makefile

```bash
make help        # Afficher toutes les commandes
make up          # Démarrer les services
make down        # Arrêter les services
make logs        # Voir les journaux
make status      # État des services
make rebuild     # Reconstruire et redémarrer
make clean       # Nettoyer les conteneurs
make clean-data  # Supprimer toutes les données persistantes (ATTENTION)
make db-shell    # Shell MySQL
make db-backup   # Sauvegarder la base
make endpoints   # Afficher les points de terminaison API
```

## Tests de l’API

Tester l’installation complète :

```bash
# Test de santé
curl http://localhost/health

# Test MS1
curl -X POST http://localhost:5001/predict/qos/5g \
  -H "Content-Type: application/json" \
  -d '{"slice_id":"test","time":14,"plr":0.001,"delay":100,"lte5g_cat":14}'

# Test MS2
curl -X POST http://localhost:5000/api/anomaly/detect \
  -H "Content-Type: application/json" \
  -d '{"slice_id":"test","packet_loss_rate":0.001,"packet_delay":12.3,"lte_5g":1,"gbr":0,"ar_vr_gaming":0,"healthcare":0,"industry_4_0":0,"iot_devices":1,"public_safety":0,"smart_city_home":0,"smart_transportation":0,"smartphone":0}'

# Test MS3
curl http://localhost:5003/api/dashboard-data

# Test MS5
curl http://localhost:5005/models

# Lancer les tests automatisés (nécessite pytest)
pytest test_api.py -v
```

## Notes de sécurité

⚠️ **Liste de contrôle pour un déploiement en production :**

1. Changer les mots de passe par défaut de la base dans `docker-compose.yml` et `init.sql`
2. Générer une `SECRET_KEY` forte dans `.env`
3. Activer HTTPS avec des certificats SSL valides (décommenter le bloc HTTPS dans `nginx.conf`)
4. Configurer le pare-feu pour n’exposer que les ports nécessaires
5. Utiliser Docker secrets pour les données sensibles
6. Mettre en place l’authentification / autorisation des API
7. Activer la journalisation d’audit
8. Définir des limites de ressources dans `docker-compose.yml`
9. Sauvegarder régulièrement la base de données
10. Superviser la santé des services et les journaux

## Évolutivité

L’architecture permet une montée en charge horizontale :

- Les **services sans état** (MS1, MS2, MS3, MS5) peuvent être répliqués
- **Répartition de charge** via Nginx (déjà configuré avec des serveurs upstream)
- La **base de données** peut être externe ou en cluster en production
- Les **volumes partagés** pour le stockage des modèles (MS5) peuvent être remplacés par S3 ou équivalent
- Des **files d’attente** peuvent être ajoutées pour une communication asynchrone

Exemple de mise à l’échelle :
```yaml
ms1:
  deploy:
    replicas: 3
  # ... reste de la configuration
```

## Dépannage

### Les services ne démarrent pas
```bash
docker-compose logs <nom-du-service>
docker-compose ps
docker-compose ps -a  # Voir les conteneurs arrêtés
```

### Erreurs de connexion à la base
```bash
# Vérifier que MySQL tourne
docker-compose ps mysql

# Consulter les journaux
docker-compose logs mysql

# Vérifier les identifiants
docker-compose exec mysql mysql -u network_user -pnetwork_pass -e "SHOW DATABASES;"
```

### Port déjà utilisé
Modifier `docker-compose.yml` pour changer le mappage des ports, ou arrêter le service en conflit.

### Erreurs de permissions sur les volumes (Linux / Mac)
```bash
sudo chown -R 1000:1000 mysql_data/ ms5_models/
```

## Prochaines étapes

Après l’installation :

1. Renforcer la sécurité (mots de passe, secrets, HTTPS) avant toute mise en production
2. Ajuster la logique métier dans MS1 si de nouveaux modèles ou seuils sont requis
3. Ajouter les modèles entraînés dans le répertoire `ml/`
4. Configurer les alertes e-mail dans `.env`
5. Installer les certificats SSL dans le répertoire `ssl/`
6. Ajouter un middleware d’authentification
7. Enrichir le NOC (MS3) et la détection de dérive (MS5) selon les besoins
8. Durcir et documenter la CI/CD (voir `.github/workflows/` et `GUIDE_CI_MLOPS_ETUDIANT.md`)
9. Configurer une base de données et une supervision de production

## Références

- Feuille de route du projet : `Roadmap.md`
- Guide simple : `GUIDE_SIMPLE_PROJET.md`
- CI / MLOps : `GUIDE_CI_MLOPS_ETUDIANT.md`
- Parcours UI : `WORKFLOW_TEST_GUIDE.md`

---

**État de l’infrastructure :** ✓ Complète et prête pour le développement
