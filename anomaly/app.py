#!/usr/bin/env python3
"""
5G Network Slicing - Anomaly Detection Service (MS2)
FastAPI — Autoencoder / heuristic anomaly detection
"""

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict

import mysql.connector
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

_here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _here)
sys.path.insert(0, os.path.abspath(os.path.join(_here, "..")))
from ml.inference import detect_anomaly, training_aligned_feature_dict

logger = logging.getLogger(__name__)

app = FastAPI(
    title="MS2 Anomaly Detection",
    description="Real-time slice anomaly scoring",
    version="1.0.0",
)

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


class AnomalyDetectRequest(BaseModel):
    """Raw slice metrics + service flags; aligned with scripts/train_models preprocessing."""

    model_config = ConfigDict(extra="ignore")

    slice_id: str
    packet_loss_rate: float = Field(
        ..., ge=0.0, le=1.0, description="Linear packet loss rate (0–1)"
    )
    packet_delay: float = Field(..., ge=0.0, description="Packet delay (ms)")
    lte_5g: int = Field(..., ge=0, le=1)
    gbr: int = Field(..., ge=0, le=1)
    ar_vr_gaming: int = Field(..., ge=0, le=1)
    healthcare: int = Field(..., ge=0, le=1)
    industry_4_0: int = Field(..., ge=0, le=1)
    iot_devices: int = Field(..., ge=0, le=1)
    public_safety: int = Field(..., ge=0, le=1)
    smart_city_home: int = Field(..., ge=0, le=1)
    smart_transportation: int = Field(..., ge=0, le=1)
    smartphone: int = Field(..., ge=0, le=1)


@app.get("/health", tags=["health"])
def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "MS2-Anomaly-Detection",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/anomaly/detect", tags=["anomaly"])
def detect_anomaly_endpoint(payload: AnomalyDetectRequest) -> Dict[str, Any]:
    slice_id = payload.slice_id
    features = training_aligned_feature_dict(
        packet_loss_rate=payload.packet_loss_rate,
        packet_delay=payload.packet_delay,
        lte_5g=payload.lte_5g,
        gbr=payload.gbr,
        ar_vr_gaming=payload.ar_vr_gaming,
        healthcare=payload.healthcare,
        industry_4_0=payload.industry_4_0,
        iot_devices=payload.iot_devices,
        public_safety=payload.public_safety,
        smart_city_home=payload.smart_city_home,
        smart_transportation=payload.smart_transportation,
        smartphone=payload.smartphone,
    )

    result = detect_anomaly(features, slice_id=slice_id)
    is_anomaly = result["is_anomaly"]
    anomaly_score = result["score"]
    confidence = result["confidence"]
    method = result["method"]

    output: Dict[str, Any] = {
        "status": "success",
        "data": {
            "slice_id": slice_id,
            "is_anomaly": is_anomaly,
            "score": round(anomaly_score, 4),
            "confidence": round(confidence, 4),
            "method": method,
        },
    }
    if result.get("detail"):
        output["data"]["consensus_detail"] = result["detail"]

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO anomaly_detections
            (slice_id, is_anomaly, score, confidence, method, features)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                slice_id,
                is_anomaly,
                anomaly_score,
                confidence,
                method,
                json.dumps(payload.model_dump()),
            ),
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        logger.error("Database error: %s", e)

    return output


@app.get("/api/anomaly/stats", tags=["anomaly"])
def get_anomaly_stats(days: int = Query(7, ge=1, le=365)) -> Dict[str, Any]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute(
            """
            SELECT
                COUNT(*) as total_checks,
                SUM(CASE WHEN is_anomaly = TRUE THEN 1 ELSE 0 END) as anomalies_detected,
                AVG(score) as avg_score,
                AVG(confidence) as avg_confidence
            FROM anomaly_detections
            WHERE `timestamp` >= DATE_SUB(NOW(), INTERVAL %s DAY)
            """,
            (days,),
        )

        stats = cursor.fetchone()
        cursor.close()
        conn.close()

        return dict(stats) if stats else {}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/", tags=["meta"])
def index() -> Dict[str, Any]:
    return {
        "service": "MS2-Anomaly-Detection",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": ["/health", "/api/anomaly/detect", "/api/anomaly/stats"],
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
