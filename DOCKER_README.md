# 5G Network Slicing - Network Infrastructure

**Simple full map (French):** `GUIDE_SIMPLE_PROJET.md`

A comprehensive microservices-based system for predicting 5G network QoS, detecting anomalies, and monitoring network slices in real-time.

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   5G Network Slicing System                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      │
│  │   MS1        │  │   MS3        │  │   MS5        │      │
│  │  QoS         │  │ Dashboard    │  │ Model        │      │
│  │ Predict      │  │ & Alerts     │  │ Management   │      │
│  │ Port: 5001   │  │ Port: 5003   │  │ Port: 5005   │      │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      │
│         │                 │                 │               │
│         └─────────────────┼─────────────────┘               │
│                           │                                 │
│  ┌────────────────────────▼────────────────────────┐        │
│  │        Anomaly Detection (MS2)                  │        │
│  │        Port: 5000 | Nginx: 80/443              │        │
│  └─────────────────────────────────────────────────┘        │
│                           │                                 │
│  ┌──────────────────────────────────────────────────┘        │
│  │   MySQL 8.0 Database (Persistent)                       │
│  │   Database: network_slicing_5g                          │
│  └──────────────────────────────────────────────────────────┘│
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │        Alert System (Email)                          │  │
│  │        Real-time SLA Violation Alerts                │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Git

### Deployment

```bash
# 1. Clone repository
git clone <repository-url>
cd -Esprit-PIDATA-4DATA-2026-NetworkSlicing

# 2. Configure environment (optional)
cp .env.example .env
# Edit .env with your settings

# 3. Start all services
docker-compose up -d

# 4. Check service status
docker-compose ps

# 5. View logs
docker-compose logs -f
```

### Access Points

| Service | URL | Description |
|---------|-----|-------------|
| **API Gateway** | http://localhost | Nginx reverse proxy |
| **MS1 (QoS)** | http://localhost:5001 | QoS Prediction API |
| **MS2 (Anomaly)** | http://localhost:5000 | Anomaly Detection API |
| **MS3 (Dashboard)** | http://localhost:5003 | Dashboard & Monitoring |
| **MS5 (Model Mgmt)** | http://localhost:5005 | Model Registry & Metrics |
| **MySQL Database** | localhost:3306 | Database (user: network_user) |

## Docker Services

### 1. MySQL Database
- **Image:** `mysql:8.0`
- **Port:** 3306
- **Database:** `network_slicing_5g`
- **User:** `network_user` / `network_pass`
- **Volumes:** `mysql_data` (persistent storage)
- **Health Check:** `mysqladmin ping`

### 2. MS1 - QoS Prediction Service
- **Port:** 5001 (external) → 5000 (internal)
- **Purpose:** Predict QoS scores and SLA compliance
- **Health Endpoint:** `/health`
- **Main API:** `/predict/qos/5g`
- **Docker Context:** Root directory

### 3. MS2 - Anomaly Detection Service
- **Port:** 5000 (external) → 5000 (internal)
- **Purpose:** Real-time anomaly detection on network metrics
- **Health Endpoint:** `/health`
- **Main API:** `/api/anomaly/detect`
- **Docker Context:** `./anomaly/`

### 4. MS3 - Dashboard Service
- **Port:** 5003 (external) → 5000 (internal)
- **Purpose:** Aggregate dashboard data and statistics
- **Health Endpoint:** `/health`
- **Main API:** `/api/dashboard-data`
- **Docker Context:** `./ms3/`

### 5. MS5 - Model Management Service
- **Port:** 5005 (external) → 5000 (internal)
- **Purpose:** Model versioning, metrics tracking, drift detection
- **Health Endpoint:** `/health`
- **Main API:** `/models`
- **Docker Context:** `./ms5_model_management/`
- **Volume:** `ms5_models` (persistent model storage)

### 6. Nginx Reverse Proxy
- **Image:** `nginx:alpine`
- **Ports:** 80 (HTTP), 443 (HTTPS)
- **Routes:**
  - `/api/ms1/*` → MS1
  - `/api/ms2/*` → MS2
  - `/api/ms3/*` → MS3
  - `/api/ms5/*` → MS5

## API Endpoints

### MS1 - QoS Prediction
```bash
# Single prediction
POST /api/ms1/predict/qos/5g
{
  "slice_id": "slice_001",
  "time": 14,
  "plr": 0.001,
  "delay": 100,
  "lte5g_cat": 14
}

# Get statistics
GET /api/ms1/predict/stats
```

### MS2 - Anomaly Detection
```bash
# Detect anomaly
POST /api/ms2/api/anomaly/detect
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

# Get statistics
GET /api/ms2/api/anomaly/stats?days=7
```

### MS3 - Dashboard
```bash
# Get dashboard data
GET /api/ms3/api/dashboard-data
```

### MS5 - Model Management
```bash
# List models
GET /api/ms5/models

# Register new model
POST /api/ms5/models/register
{
  "model_name": "xgboost_5g_v1",
  "model_version": "1.0.0",
  "accuracy": 0.912,
  "precision": 0.89,
  "recall": 0.94,
  "f1_score": 0.91,
  "roc_auc": 0.9542
}
```

## File Structure

```
5G-NetworkSlicing/
├── docker-compose.yml           # Main orchestration
├── Dockerfile                   # Production-ready container
├── .dockerignore               # Docker build exclusions
├── requirements.txt             # Python dependencies
├── init.sql                     # Database initialization
├── nginx.conf                   # Reverse proxy config
├── config.py                    # Configuration settings
├── models.py                    # Database ORM models
├── app.py                       # MS1 main application
├── alert_service.py             # Alert handling service
├── Makefile                     # Convenient commands
├── .env.example                 # Environment template
│
├── anomaly/                      # MS2 - Anomaly Detection
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
│
├── ms3/                          # MS3 - Dashboard
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
│
├── ms5_model_management/         # MS5 - Model Management
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app.py
│
├── ml/                           # ML models directory
│   ├── model_5G.joblib          # Trained model
│   ├── scaler_5G.joblib         # Feature scaler
│   └── encoder_congestion.joblib # Label encoder
│
├── data/                         # Data storage
│   ├── raw/                      # Raw data files
│   └── processed/                # Processed datasets
│
├── logs/                         # Application logs
└── ssl/                          # SSL certificates (optional)
```

## Environment Variables

All configuration is done via environment variables. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_HOST` | mysql | MySQL host |
| `DB_PORT` | 3306 | MySQL port |
| `DB_USER` | network_user | Database user |
| `DB_PASSWORD` | network_pass | Database password |
| `SECRET_KEY` | — | Application secret (see `.env.example`) |
| `ALERT_EMAIL` | — | Email destination for SMTP alerts |

See `.env.example` for full configuration.

## Health Checks

All services provide health check endpoints:

```bash
curl http://localhost/health                    # Via Nginx
curl http://localhost:5001/health               # MS1
curl http://localhost:5000/health               # MS2
curl http://localhost:5003/health               # MS3
curl http://localhost:5005/health               # MS5
```

## Common Commands (using Makefile)

```bash
make help          # Show all commands
make up            # Start services
make down          # Stop services
make logs          # View logs
make status        # Service status
make rebuild       # Rebuild and restart
make clean         # Clean up resources
make db-shell      # Open MySQL shell
make db-backup     # Backup database
```

All commands work cross-platform (PowerShell/Bash).

## Production Considerations

1. **Change default passwords** in `docker-compose.yml` and `init.sql`
2. **Configure SSL** certificates in `/ssl` directory and uncomment HTTPS block in `nginx.conf`
3. **Set proper SECRET_KEY** in environment variables
4. **Enable authentication** on all API endpoints
5. **Configure external database** if needed (update `DB_HOST`)
6. **Set up monitoring** (Prometheus, Grafana) - see MONITORING.md
7. **Enable log aggregation** (ELK stack or similar)
8. **Configure backup** strategy for database and models
9. **Set resource limits** in docker-compose.yml
10. **Use secrets management** (Docker secrets, HashiCorp Vault)

## Development

### Local Development (without Docker)
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Initialize database
# (requires running MySQL instance)
python -c "from models import BaseModel; BaseModel.execute_query('CREATE DATABASE IF NOT EXISTS network_slicing_5g')"

# Run service
python app.py
```

### Adding New Microservices

1. Create service directory (e.g., `ms6/`)
2. Add `Dockerfile`, `requirements.txt`, `app.py`
3. Add service definition to `docker-compose.yml`
4. Update Nginx configuration if needed
5. Add health check endpoint
6. Update this documentation

## Testing

```bash
# Run unit tests
pytest tests/

# Run API tests
pytest tests/test_api_endpoints.py

# Test with curl
curl -X POST http://localhost:5001/predict/qos/5g \
  -H "Content-Type: application/json" \
  -d '{"slice_id":"test","time":12,"plr":0.01,"delay":50,"lte5g_cat":14}'
```

## Troubleshooting

### Services not starting
```bash
# Check logs
docker-compose logs -f

# Check service status
docker-compose ps

# Restart specific service
docker-compose restart ms1
```

### Database connection issues
```bash
# Verify MySQL is running
docker-compose ps mysql

# Check MySQL logs
docker-compose logs mysql

# Connect directly
docker-compose exec mysql mysql -u network_user -pnetwork_pass network_slicing_5g
```

### Port conflicts
If ports 80, 443, 5000-5005 are in use:
1. Edit `docker-compose.yml` to use different ports
2. Update any client configurations

### Volume permissions (Linux/Mac)
```bash
# Fix permissions
sudo chown -R 1000:1000 mysql_data ms5_models
```

## License

Academic project - Esprit School of Engineering (PIDATA 4DATA 2025-2026)

## Support

For issues and questions, refer to the project documentation or contact the development team.
