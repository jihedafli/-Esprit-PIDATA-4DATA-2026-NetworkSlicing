# Esprit PIDATA 4DATA — Network Slicing 5G

Academic project (2025–2026, **Esprit School of Engineering**, DATA track): microservices for **5G slice** QoS prediction, **anomaly detection**, **NOC-style dashboard**, and **model registry**, with Docker, MySQL, **MLflow** (required for training), and an optional Elastic stack for observability.

## Documentation

| Doc | Language | Purpose |
|-----|----------|---------|
| **`GUIDE_SIMPLE_PROJET.md`** | French | **Start here:** simple map of every service and main files. |
| `IDEE_GENERALE_PROJET.md` | French | Context, SLA & NOC glossaries, high-level architecture. |
| `EXPLICATION_CODE_PROJET.md` | French | Deeper walkthrough of code and routes. |
| `WORKFLOW_TEST_GUIDE.md` | French | Browser URLs, datasets, end-to-end checks. |
| `GUIDE_CI_MLOPS_ETUDIANT.md` | French | CI, `ci` Docker profile, Makefile. |
| `INFRASTRUCTURE.md` / `FILE_MANIFEST.md` | French | Docker topology and file inventory. |
| `DOCKER_README.md` | English | Deployment-oriented overview. |
| `Roadmap.md` | French | Objectives, API examples, repo layout. |

## Quick start

Prerequisites: **Docker** and **Docker Compose**.

```bash
git clone <repository-url>
cd -Esprit-PIDATA-4DATA-2026-NetworkSlicing
docker compose up -d --build
```

Then open MS1 docs at `http://localhost:5001/docs` or follow `WORKFLOW_TEST_GUIDE.md`.

## Tech stack

Python **3.10**, **FastAPI**, **Uvicorn**, **MySQL 8**, **scikit-learn** / **XGBoost**, optional **TensorFlow** (MS2), **MLflow** (training tracking), optional **Elasticsearch** / **Kibana** / **Metricbeat**, **Nginx**.
