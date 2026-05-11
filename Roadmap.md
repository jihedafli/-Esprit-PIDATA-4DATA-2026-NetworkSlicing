# Système de prédiction QoS et de détection d’anomalies pour le découpage réseau 5G

> **Vue à jour en langage simple (services, fichiers, liens) :** `GUIDE_SIMPLE_PROJET.md`  
> Les API du dépôt utilisent **FastAPI** ; certaines phrases ci-dessous peuvent encore mentionner Flask à des fins historiques — se référer au code et à `requirements.txt`.

## Présentation du projet

**Pipeline d’apprentissage automatique de bout en bout** pour l’optimisation des réseaux 5G, avec prédiction QoS en temps réel, détection d’anomalies et supervision complète du système. Ce projet illustre les bonnes pratiques d’ingénierie ML, du développement des modèles jusqu’au déploiement en production.

**Auteur** : Jihed Afli  
**Établissement** : École d’ingénieurs Esprit — PIDATA 4DATA (2025-2026)  
**Thème** : Découpage réseau 5G et analytique prédictive  
**Déploiement** : Architecture microservices sous Docker

---

## 🎯 Objectifs du projet

- **Prédiction QoS** : estimer les probabilités de QoS du réseau à partir du taux de perte de paquets, du délai et de la catégorie LTE/5G
- **Détection d’anomalies** : repérer en temps réel des comportements réseau inhabituels
- **Conformité SLA** : surveiller les violations d’accords de niveau de service et alerter
- **Gestion des modèles** : suivre les versions, les métriques de performance et la détection de dérive
- **Supervision en temps réel** : tableau de bord avec alertes pour les événements critiques
- **Prêt pour la production** : déploiement complet avec Docker, supervision et journalisation

---

## 🏗️ Architecture du système
┌─────────────────────────────────────────────────────────────┐ │ Système de découpage réseau 5G │ ├─────────────────────────────────────────────────────────────┤ │ │ │ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ │ │ │ Pipeline ML │ │ Tableau de │ │ Supervision │ │ │ │ (MS1) │ │ bord (MS3) │ │ (MS5) │ │ │ │ Port : 5001 │ │ Port : 5003 │ │ Port : 5005 │ │ │ └──────────────┘ └──────────────┘ └──────────────┘ │ │ │ │ │ │ │ ┌──────────────────────────────────────────────────┐ │ │ │ Détection d’anomalies (MS2) │ │ │ │ Port : 5000 | Nginx : 80/443 │ │ │ └──────────────────────────────────────────────────┘ │ │ │ │ │ │ │ ┌──────────────────────────────────────────────────┐ │ │ │ Base MySQL 8.0 (persistante) │ │ │ │ Base : network_slicing_5g │ │ │ └──────────────────────────────────────────────────┘ │ │ │ │ ┌──────────────────────────────────────────────────┐ │ │ │ Système d’alertes (e-mail) │ │ │ │ Alertes SLA en temps réel │ │ │ └──────────────────────────────────────────────────┘ │ │ │ └─────────────────────────────────────────────────────────────┘


---

## 📦 Contenu du projet

### **1. Pipeline de modèles ML**
- ✅ Prétraitement des données et ingénierie des caractéristiques
- ✅ Classifieur calibré XGBoost pour la prédiction QoS 5G
- ✅ Score de risque SLA
- ✅ Versioning des modèles et détection de dérive
- ✅ Explicabilité des modèles via SHAP

### **2. Architecture microservices**
- ✅ **MS1** (5001) : service principal de prédiction QoS
- ✅ **MS2** (5000) : service de détection d’anomalies
- ✅ **MS3** (5003) : tableau de bord et gestion des alertes
- ✅ **MS5** (5005) : gestion des modèles et supervision

### **3. Supervision en temps réel**
- ✅ Health checks pour tous les services
- ✅ Métriques de performance (précision, rappel, F1-score)
- ✅ Détection de dérive des modèles
- ✅ Historique et statistiques des prédictions

### **4. Système d’alertes**
- ✅ Alertes e-mail (SMTP)
- ✅ Niveaux de gravité multiples (INFO, WARNING, CRITICAL)
- ✅ Détection des violations SLA par seuils

### **5. Conteneurisation Docker**
- ✅ Orchestration multi-conteneurs avec Docker Compose
- ✅ Health checks pour chaque service
- ✅ Persistance des bases via volumes
- ✅ Isolation réseau entre services

### **6. Tests**
- ✅ Tests unitaires pour les fonctions clés
- ✅ Tests d’intégration pour les points de terminaison API
- ✅ Génération de données de test
- ✅ Exécution automatisée de la suite de tests

---

## 🚀 Démarrage rapide

### Prérequis
- Python 3.10+
- Docker et Docker Compose
- Git

### Installation en développement local

```bash
# 1. Cloner et aller sur la branche jihed
git clone https://github.com/emna-guefrech/-Esprit-PIDATA-4DATA-2026-NetworkSlicing.git
cd -Esprit-PIDATA-4DATA-2026-NetworkSlicing
git checkout jihed

# 2. Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Sous Windows : venv\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Initialiser la base de données
python init_db.py

# 5. Lancer le service principal
python app.py
```

```bash
# Démarrer tous les services (recommandé)
docker-compose up -d

# Voir les journaux
docker-compose logs -f

# Arrêter tous les services
docker-compose down
```

### Prédiction QoS

```text
POST /predict/qos/5g
Content-Type: application/json

{
  "slice_id": "slice_001",
  "time": 14,                  # Heure du jour
  "plr": 0.001,                # Taux de perte de paquets
  "delay": 100,                # Délai en ms
  "lte5g_cat": 14              # Catégorie LTE/5G
}

Réponse :
{
  "slice_id": "slice_001",
  "qos_score": 0.8523,
  "p_sla_met": 0.8523,
  "qos_risk_score": 0.1477,
  "risk_tier": "Low",
  "congestion_level": "Normal",
  "sla_respected": true,
  "pipeline": "5G"
}
```

### Prédictions par lot

```text
POST /predict/batch
Content-Type: application/json

{
  "slices": [
    {"slice_id": "slice_001", "time": 14, "plr": 0.001, ...},
    {"slice_id": "slice_002", "time": 15, "plr": 0.002, ...}
  ]
}
```

### Détection d’anomalies

```text
POST /api/anomaly/detect
Content-Type: application/json

{
  "slice_id": "slice_001",
  "packet_loss_rate": 0.001,
  "packet_delay": 12.3,
  "lte_5g": 1,
  "gbr": 0,
  "ar_vr_gaming": 0,
  "healthcare": 0,
  "industry_4_0": 0,
  "iot_devices": 1,
  "public_safety": 0,
  "smart_city_home": 0,
  "smart_transportation": 0,
  "smartphone": 0
}

Réponse :
{
  "status": "success",
  "data": {
    "slice_id": "slice_001",
    "is_anomaly": false,
    "score": 0.12,
    "confidence": 0.95,
    "method": "IsolationForest"
  }
}
```

### Obtenir des statistiques

```text
GET /predict/stats
GET /api/anomaly/stats?days=7
GET /api/dashboard-data
```

## 📁 Structure du projet

```text
jihed-branch/
│
├── README.md                           # Documentation du projet
├── requirements.txt                    # Dépendances Python
├── docker-compose.yml                  # Orchestration des services
├── Dockerfile                          # Conteneur de l’app principale
├── .dockerignore                       # Exclusions du build Docker
├── .gitignore                          # Règles d’ignorance Git
│
├── Application principale
├── app.py                              # Application Flask principale (MS1)
├── config.py                           # Configuration et alertes
├── models.py                           # Modèles de base de données
├── alert_service.py                    # Alertes e-mail (SMTP)
│
├── Modèles ML et données
├── ml/
│   ├── model_5G.joblib                 # Modèle XGBoost entraîné
│   ├── scaler_5G.joblib                # Scaler des caractéristiques
│   └── encoder_congestion.joblib       # Encodeur d’étiquettes
├── data/
│   ├── train_dataset.csv               # Jeu d’entraînement par défaut (TRAIN_DATA_PATH)
│   ├── raw/
│   │   └── network_traces.csv          # Données réseau brutes
│   ├── processed/
│   │   └── training_data.csv           # Jeu d’entraînement traité (optionnel)
│   └── test/
│       └── test_cases.json             # Données de test
│
├── Détection d’anomalies (MS2)
├── anomaly/
│   ├── app.py                          # App Flask (MS2)
│   ├── run.py                          # Lanceur du service
│   ├── config.py                       # Configuration
│   ├── docker-compose.yml              # Orchestration MS2
│   ├── Dockerfile                      # Conteneur MS2
│   ├── requirements.txt                # Dépendances MS2
│   ├── test_api.py                     # Tests d’intégration
│   ├── init_db.py                      # Init base de données
│   ├── nginx.conf                      # Config reverse proxy
│   └── app/
│       ├── __init__.py                 # Factory d’application
│       ├── routes/                     # Routes API
│       ├── services/                   # Logique métier
│       ├── models/                     # Modèles BD
│       └── templates/                  # Modèles HTML
│
├── Tableau de bord et alertes (MS3)
├── ms3/
│   ├── app.py                          # Service tableau de bord
│   ├── models.py                       # Modèles du tableau de bord
│   ├── service.py                      # Logique du tableau de bord
│   ├── run.py                          # Lanceur MS3
│   ├── requirements.txt                # Dépendances MS3
│   ├── docker-compose.yml              # Orchestration MS3
│   └── templates/                      # Modèles d’interface
│
├── Gestion des modèles (MS5)
├── ms5_model_management/
│   ├── app.py                          # Service registre de modèles
│   ├── models.py                       # Modèles BD MS5
│   ├── requirements.txt                # Dépendances MS5
│   ├── docker-compose.yml              # Orchestration MS5
│   ├── Dockerfile                      # Conteneur MS5
│   └── templates/                      # Modèles d’interface
│
├── Tests et validation
├── tests/
│   ├── test_ml_models.py               # Validation des modèles
│   ├── test_api_endpoints.py           # Tests API
│   ├── test_anomaly_detection.py       # Tests d’anomalies
│   ├── test_alerts.py                  # Tests du système d’alertes
│   └── conftest.py                     # Configuration des tests
│
├── Documentation
├── docs/
│   ├── ARCHITECTURE.md                 # Conception du système
│   ├── API_DOCUMENTATION.md            # Référence API
│   ├── DEPLOYMENT.md                   # Guide de déploiement
│   ├── MONITORING.md                   # Configuration de la supervision
│   ├── TROUBLESHOOTING.md              # Problèmes courants
│   └── DEVELOPMENT.md                  # Guide de développement
│
└── Utilitaires et scripts
    ├── scripts/
    │   ├── setup.sh                    # Configuration initiale
    │   ├── train_models.py             # Entraînement des modèles
    │   ├── generate_test_data.py       # Génération de données de test
    │   └── backup_database.sh          # Sauvegarde de la base
    └── logs/                           # Journaux d’application
```

## 🔧 Configuration

### Variables d’environnement

```bash
# Base de données
DB_USER=root
DB_PASS=root
DB_HOST=mysql
DB_NAME=network_slicing_5g

# Flask
FLASK_ENV=production
FLASK_DEBUG=false
SECRET_KEY=your-secret-key-here

# Alertes e-mail
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=your-email@gmail.com
SENDER_PASSWORD=your-app-password

# URL des services
MS1_URL=http://localhost:5001
MS2_URL=http://localhost:5000
MS3_URL=http://localhost:5003
MS5_URL=http://localhost:5005

```
Prédicteur QoS 5G XGBoost
Métriques (jeu de validation) :
├── Exactitude : 91,2 %
├── Précision : 0,89
├── Rappel : 0,94
├── F1-score : 0,91
├── ROC-AUC : 0,9542
├── Log loss : 0,2847
└── Temps d’entraînement : 2,3 s

Caractéristiques :
├── Heure (encodage sin/cos)
├── Taux de perte de paquets (échelle log)
├── Délai (échelle log)
├── Catégorie LTE/5G
├── Indicateur d’heure de pointe
└── Composites de risque construits

## 🔔 Système d’alertes

### Détection des violations SLA
Critique (🚨) :
├── Score de risque > 50 %
├── Probabilité QoS < 40 %
└── Action immédiate requise

Avertissement (⚠️) :
├── Score de risque 20–50 %
├── Probabilité QoS 40–70 %
└── Surveiller de près

Info (ℹ️) :
├── Fonctionnement normal
└── Purement informatif

Canaux d’alerte
E-mail : directement vers l’administrateur réseau
Tableau de bord : centre d’alertes en temps réel
Journaux : piste d’audit persistante
