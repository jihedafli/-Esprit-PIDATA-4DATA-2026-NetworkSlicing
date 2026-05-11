#!/usr/bin/env python3
"""
5G Network Slicing - Model Management Service (MS5)
FastAPI
"""

import decimal
import json
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pathlib import Path as FsPath

import mysql.connector
from fastapi import FastAPI, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from starlette.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

app = FastAPI(
    title="MS5 Model Management",
    description="Model registry and performance metrics",
    version="1.1.0",
)

BASE_DIR = FsPath(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(status_code=400, content={"detail": exc.errors()})


DB_CONFIG = {
    "host": os.getenv("DB_HOST", "mysql"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "rootpassword"),
    "database": os.getenv("DB_NAME", "network_slicing_5g"),
}


def get_db_connection():
    return mysql.connector.connect(**DB_CONFIG)


def ensure_model_metrics_schema():
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema = DATABASE() AND table_name = 'model_metrics'"
        )
        if cur.fetchone()[0] == 0:
            cur.execute("""
                CREATE TABLE model_metrics (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    model_name VARCHAR(100) NOT NULL,
                    model_version VARCHAR(50),
                    accuracy FLOAT,
                    `precision` FLOAT,
                    recall FLOAT,
                    f1_score FLOAT,
                    roc_auc FLOAT,
                    log_loss FLOAT,
                    training_time FLOAT,
                    training_date DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """)
            conn.commit()
            return
        cur.execute("SHOW COLUMNS FROM model_metrics")
        cols = {row[0] for row in cur.fetchall()}
        if "precision" not in cols:
            cur.execute("ALTER TABLE model_metrics ADD COLUMN `precision` FLOAT NULL")
            conn.commit()
    finally:
        cur.close()
        conn.close()


def _json_safe_value(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, date):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).decode("utf-8", errors="replace")
    if isinstance(v, dict):
        return {k: _json_safe_value(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe_value(x) for x in v]
    return v


def _json_safe_row(row: dict) -> dict:
    return {k: _json_safe_value(v) for k, v in dict(row).items()}


def _discover_ml_artifacts() -> Dict[str, Any]:
    """
    Liste les fichiers modèle sur disque (répertoire projet ml/ monté dans le conteneur).

    Complète la table MySQL model_metrics : celle-ci ne se remplit que si
    scripts/train_models.py a pu joindre MS5 (POST /models/register) ou si tu enregistres à la main.
    """
    raw = os.getenv("ML_ARTIFACTS_PATH", "").strip()
    if not raw:
        return {"artifacts": [], "metadata_bundle": None}

    artifacts: List[Dict[str, Any]] = []
    metadata_bundle: Optional[Dict[str, Any]] = None

    for root_str in raw.split(","):
        root_str = root_str.strip()
        if not root_str:
            continue
        base = FsPath(root_str)
        if not base.is_dir():
            continue

        meta_path = base / "metadata.json"
        if meta_path.is_file():
            try:
                with meta_path.open(encoding="utf-8") as f:
                    meta = json.load(f)
                metadata_bundle = {
                    "timestamp": meta.get("timestamp"),
                    "models_saved": meta.get("models_saved"),
                    "n_features": meta.get("n_features"),
                    "source_dir": root_str,
                }
            except (json.JSONDecodeError, OSError):
                metadata_bundle = {"source_dir": root_str, "error": "metadata.json unreadable"}

        for pattern in ("*.pkl", "*.h5"):
            for fpath in sorted(base.glob(pattern)):
                if not fpath.is_file():
                    continue
                try:
                    st = fpath.stat()
                except OSError:
                    continue
                artifacts.append(
                    {
                        "filename": fpath.name,
                        "size_bytes": st.st_size,
                        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(
                            timespec="seconds"
                        ),
                    }
                )

    artifacts.sort(key=lambda x: x["filename"])
    return {"artifacts": artifacts, "metadata_bundle": metadata_bundle}


class ModelRegisterBody(BaseModel):
    model_name: str
    model_version: Optional[str] = "v1.0"
    accuracy: Optional[float] = None
    precision: Optional[float] = Field(
        None, description="Precision metric (maps to SQL column `precision`)"
    )
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    roc_auc: Optional[float] = None
    log_loss: Optional[float] = None
    training_time: Optional[float] = None


@app.get("/health", tags=["health"])
def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "MS5-Model-Management",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/models", tags=["models"])
def list_models() -> Dict[str, Any]:
    """
    - **models** : lignes en base (`model_metrics`), alimentées par POST `/models/register`
      ou par `scripts/train_models.py` si MS5 est joignable à la fin de l’entraînement.
    - **artifacts** : fichiers présents dans `ML_ARTIFACTS_PATH` (ex. `ml/*.pkl` montés dans le conteneur).
    """
    try:
        ensure_model_metrics_schema()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM model_metrics
            ORDER BY id DESC
            """)
        models = [_json_safe_row(m) for m in cursor.fetchall()]

        cursor.close()
        conn.close()

        disk = _discover_ml_artifacts()
        return {
            "models": models,
            "artifacts": disk["artifacts"],
            "metadata_bundle": disk["metadata_bundle"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/models/register", tags=["models"])
def register_model(body: ModelRegisterBody) -> Dict[str, Any]:
    try:
        ensure_model_metrics_schema()
        data = body.model_dump()

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO model_metrics
            (model_name, model_version, accuracy, `precision`, recall, f1_score, roc_auc, log_loss, training_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                data.get("model_name"),
                data.get("model_version", "v1.0"),
                data.get("accuracy"),
                data.get("precision"),
                data.get("recall"),
                data.get("f1_score"),
                data.get("roc_auc"),
                data.get("log_loss"),
                data.get("training_time"),
            ),
        )

        conn.commit()
        model_id = cursor.lastrowid

        cursor.close()
        conn.close()

        return {
            "status": "success",
            "model_id": model_id,
            "message": "Model registered successfully",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@app.get("/models/{model_id}/metrics", tags=["models"])
def get_model_metrics(
    model_id: int = Path(..., description="Model row id"),
) -> Dict[str, Any]:
    try:
        ensure_model_metrics_schema()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM model_metrics WHERE id = %s", (model_id,))
        model = cursor.fetchone()

        cursor.close()
        conn.close()

        if model:
            return _json_safe_row(model)
        raise HTTPException(status_code=404, detail="Model not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/ui", response_class=HTMLResponse, tags=["ui"])
def ui_dashboard(request: Request) -> Any:
    try:
        ensure_model_metrics_schema()
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM model_metrics ORDER BY id DESC LIMIT 100")
        models = [_json_safe_row(m) for m in cursor.fetchall()]
        cursor.close()
        conn.close()
        disk = _discover_ml_artifacts()
    except Exception as e:
        models = []
        err = str(e)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {
                "models": [],
                "artifacts": [],
                "metadata_bundle": None,
                "error": err,
            },
            status_code=500,
        )
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "models": models,
            "artifacts": disk["artifacts"],
            "metadata_bundle": disk["metadata_bundle"],
            "error": None,
        },
    )


@app.get("/", tags=["meta"])
def index() -> Dict[str, Any]:
    return {
        "service": "MS5-Model-Management",
        "version": "1.1.0",
        "docs": "/docs",
        "dashboard_ui": "/ui",
        "endpoints": [
            "/health",
            "/models",
            "/models/register",
            "/models/{id}/metrics",
            "/ui",
        ],
        "note": "GET /models returns DB rows (models) plus on-disk artifacts under ML_ARTIFACTS_PATH",
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
