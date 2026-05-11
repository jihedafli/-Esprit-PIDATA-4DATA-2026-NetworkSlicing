.PHONY: help build up down logs clean test shell lint format-check security test-unit train-ci ci ci-integration workflow-url cd-pipeline

help:
	@echo "5G Network Slicing - Docker Commands"
	@echo "====================================="
	@echo ""
	@echo "Container Management:"
	@echo "  make build        - Build all Docker images"
	@echo "  make up           - Start all services in detached mode"
	@echo "  make down         - Stop all services"
	@echo "  make restart      - Restart all services"
	@echo "  make rebuild      - Rebuild and restart all services"
	@echo ""
	@echo "Logs & Monitoring:"
	@echo "  make logs         - View logs from all services"
	@echo "  make logs-ms1     - View MS1 logs"
	@echo "  make logs-ms2     - View MS2 logs"
	@echo "  make logs-ms3     - View MS3 logs"
	@echo "  make logs-ms5     - View MS5 logs"
	@echo "  make logs-nginx   - View Nginx logs"
	@echo "  make logs-mysql   - View MySQL logs"
	@echo ""
	@echo "Database:"
	@echo "  make db-shell     - Open MySQL shell"
	@echo "  make db-backup    - Backup MySQL database"
	@echo "  make db-restore   - Restore MySQL database"
	@echo ""
	@echo "Development (commandes dans l’image Docker ci — pas de pip sur l’hôte):"
	@echo "  make ci           - CI locale = lint + format-check + security + test-unit"
	@echo "  make ci-integration - pytest test_api (après docker compose up -d)"
	@echo "  make workflow-url - Affiche l’URL du tableau workflow (nginx)"
	@echo "  make cd-pipeline  - Rappel: CD manuelle via GitHub Actions (workflow CD manual)"
	@echo "  make test         - Tests API (docker compose up -d requis)"
	@echo "  make lint         - Ruff"
	@echo "  make format-check - Black"
	@echo "  make security     - Bandit + pip-audit"
	@echo "  make test-unit    - Pytest tests/unit"
	@echo "  make train-ci     - MLflow up + entraînement tests/fixtures/ci_train.csv (tracking actif)"
	@echo "  make shell-ms1    - Open shell in MS1 container"
	@echo "  make shell-ms2    - Open shell in MS2 container"
	@echo "  make shell-ms3    - Open shell in MS3 container"
	@echo "  make shell-ms5    - Open shell in MS5 container"
	@echo ""
	@echo "Cleaning:"
	@echo "  make clean        - Remove all containers, networks, and volumes"
	@echo "  make clean-data   - Remove all data volumes (WARNING: deletes data)"

build:
	@echo "Building Docker images..."
	docker-compose build --no-cache

up:
	@echo "Starting all services..."
	docker-compose up -d
	@echo "Services starting..."
	@echo "API Gateway: http://localhost"
	@echo "Workflow UI: http://localhost/workflow/"
	@echo "NOC Dashboard: http://localhost:5003/login (admin / changeme)"
	@echo "NOC via nginx: http://localhost/noc/login"
	@echo "MS1 (QoS): http://localhost:5001"
	@echo "MS2 (Anomaly): http://localhost:5000"
	@echo "MS3 (Dashboard): http://localhost:5003"
	@echo "MS5 (Model Mgmt): http://localhost:5005"
	@echo "Elasticsearch: http://localhost:9200 (image pulled on first up if missing)"
	@echo "Kibana: http://localhost:5601"
	@echo "MySQL: localhost:3306"

down:
	@echo "Stopping all services..."
	docker-compose down

restart:
	@echo "Restarting all services..."
	docker-compose restart

rebuild:
	@echo "Rebuilding all services..."
	docker-compose down
	docker-compose build --no-cache
	docker-compose up -d

logs:
	docker-compose logs -f

logs-ms1:
	docker-compose logs -f ms1

logs-ms2:
	docker-compose logs -f ms2

logs-ms3:
	docker-compose logs -f ms3

logs-ms5:
	docker-compose logs -f ms5

logs-nginx:
	docker-compose logs -f nginx

logs-mysql:
	docker-compose logs -f mysql

db-shell:
	docker-compose exec mysql mysql -u network_user -pnetwork_pass network_slicing_5g

db-backup:
	@echo "Backing up database..."
	mkdir -p backups
	docker-compose exec -T mysql mysqldump -u network_user -pnetwork_pass network_slicing_5g > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "Backup completed: backups/backup_$(date +%Y%m%d_%H%M%S).sql"

db-restore:
	@echo "Usage: make db-restore FILE=backup.sql"

db-shell:
	docker-compose exec mysql mysql -u network_user -pnetwork_pass network_slicing_5g

test:
	docker compose --profile ci run --rm --no-deps ci pytest test_api.py -v

lint:
	docker compose --profile ci run --rm --no-deps ci ruff check .

format-check:
	docker compose --profile ci run --rm --no-deps ci black --check .

security:
	docker compose --profile ci run --rm --no-deps ci sh -c "bandit -c bandit.yaml -r . -ll -q && pip-audit -r requirements.txt"

test-unit:
	docker compose --profile ci run --rm --no-deps ci pytest tests/unit -v

train-ci:
	docker compose up -d mlflow
	docker compose --profile ci run --rm --no-deps -e MLFLOW_TRACKING_URI=http://mlflow:5000 -e DISABLE_ELASTICSEARCH_PUSH=1 -e TRAIN_DATA_PATH=tests/fixtures/ci_train.csv ci python scripts/train_models.py

# Équivalent local des jobs CI quality + unit (sans stack Docker des microservices)
ci: lint format-check security test-unit
	@echo ""
	@echo "CI locale terminée (équivalent jobs quality + unit). Intégration: make ci-integration"

ci-integration:
	@echo "Requiert la stack: docker compose up -d"
	docker compose --profile ci run --rm --no-deps ci pytest test_api.py -v

workflow-url:
	@echo "Workflow UI (nginx): http://localhost/workflow/"

# CD manuelle = dépôt GitHub → Actions → workflow « CD manual » (pas de script local)
cd-pipeline:
	@echo "CD manuelle: ouvrir GitHub → Actions → « CD manual » → Run workflow"
	@echo "Configurer les secrets DOCKERHUB_USERNAME et DOCKERHUB_TOKEN pour le push Docker Hub."

shell-ms1:
	docker-compose exec ms1 /bin/bash

shell-ms2:
	docker-compose exec ms2 /bin/bash

shell-ms3:
	docker-compose exec ms3 /bin/bash

shell-ms5:
	docker-compose exec ms5 /bin/bash

clean:
	@echo "Cleaning up..."
	docker-compose down -v --remove-orphans
	docker system prune -f

clean-data:
	@echo "WARNING: This will delete all persistent data!"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		docker-compose down -v; \
		docker volume rm network-slicing_mysql_data network-slicing_ms5_models 2>/dev/null || true; \
		echo "Data volumes removed"; \
	fi

status:
	@echo "Service Status:"
	@echo "==============="
	docker-compose ps

# Initialize database with sample data
init-db:
	@echo "Initializing database with sample data..."
	# Placeholder for initialization script

# Show all API endpoints
endpoints:
	@echo "API Endpoints:"
	@echo "=============="
	@echo "Workflow UI (nginx):"
	@echo "  GET  http://localhost/workflow/"
	@echo "NOC Dashboard (MS3, auth):"
	@echo "  GET  http://localhost:5003/login"
	@echo "  GET  http://localhost/noc/login"
	@echo ""
	@echo "QoS Prediction (MS1):"
	@echo "  POST http://localhost:5001/predict/qos/5g"
	@echo "  POST http://localhost:5001/predict/congestion"
	@echo ""
	@echo "Anomaly Detection (MS2):"
	@echo "  POST http://localhost:5000/api/anomaly/detect"
	@echo ""
	@echo "Dashboard (MS3):"
	@echo "  GET  http://localhost:5003/api/dashboard-data"
	@echo ""
	@echo "Model Management (MS5):"
	@echo "  GET  http://localhost:5005/models"
	@echo "  POST http://localhost:5005/models/register"
