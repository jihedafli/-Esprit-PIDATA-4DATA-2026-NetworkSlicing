#!/usr/bin/env python3
"""
5G Network Slicing - QoS Prediction Service (MS1)
FastAPI — QoS + congestion (Low / Medium / High, seuils dépendants du slice)
"""

import csv
import io
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import mysql.connector
import requests
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from starlette.templating import Jinja2Templates

from congestion_engine import classify_congestion, congestion_display_label, qos_from_pressure

from slice_inference import predict_slice_models, slice_label_for_class

logger = logging.getLogger(__name__)

app = FastAPI(
    title="MS1 QoS Prediction",
    description="5G slice QoS and congestion severity (Low / Medium / High)",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


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


class QoSPredictRequest(BaseModel):
    """
    All inputs required to rebuild the same feature row as ``scripts/train_models.py``
    (log PLR, service 0/1 flags, then server-side Is_Critical / Is_IoT_Service / QoS_Score).
    The **length** of the vector passed to RF/XGB/MLP is exactly ``len(joblib.load('ml/features.pkl'))``
    (often around 14 after selection on a full training set).
    """

    model_config = ConfigDict(extra="ignore")

    slice_id: str = Field(
        ...,
        description=(
            "Opaque session or inventory id (e.g. slice_001). "
            "Not used for SLA/thresholds — use slice_type or RF output via congestion_slice_profile."
        ),
    )
    slice_type: Optional[int] = Field(
        None,
        ge=1,
        le=3,
        description=(
            "Notebook slice Type when known from provisioning: 1=eMBB, 2=mMTC, 3=URLLC. "
            "If set, selects SLA delay/PLR refs and congestion bands (overrides RF for profile)."
        ),
    )
    time: int = Field(0, description="Hour of day (0–23)")
    plr: float = Field(
        ..., description="Packet loss rate (fraction, e.g. 0.001) → Packet Loss Rate"
    )
    delay: float = Field(..., description="Packet delay (ms) → Packet delay")
    lte5g_cat: int = Field(
        0, description="Legacy LTE/5G category (optional; may imply lte_5g if set)"
    )
    jitter: float = Field(0.0, ge=0, description="Jitter (ms), optional")
    demand_mbps: Optional[float] = Field(
        None,
        ge=0,
        description="Requested / demanded throughput (Mbps), optional",
    )
    capacity_mbps: Optional[float] = Field(
        None,
        ge=0,
        description="Available slice capacity (Mbps), optional",
    )
    mobility_stress: float = Field(
        0.0,
        ge=0,
        le=1,
        description="Mobility / connectivity stress proxy (0–1), optional",
    )
    # Training-aligned inputs (IBM AADS / train_models.py) — build the vector in ml/features.pkl
    lte_5g: int = Field(0, ge=0, le=1, description="LTE/5G flag → LTE/5G")
    gbr: int = Field(0, ge=0, le=1)
    ar_vr_gaming: int = Field(0, ge=0, le=1, description="AR/VR/Gaming")
    healthcare: int = Field(0, ge=0, le=1)
    industry_4_0: int = Field(0, ge=0, le=1, description="Industry 4.0")
    iot_devices: int = Field(0, ge=0, le=1, description="IoT Devices")
    public_safety: int = Field(0, ge=0, le=1)
    smart_city_home: int = Field(0, ge=0, le=1, description="Smart City & Home")
    smart_transportation: int = Field(0, ge=0, le=1)
    smartphone: int = Field(0, ge=0, le=1)
    slice_type_hint: Optional[int] = Field(
        None,
        ge=1,
        le=3,
        description="Fallback slice type (1–3) when ML artifacts are missing and slice_type is not set",
    )


class QoSPredictResponse(BaseModel):
    slice_id: Optional[str]
    qos_score: float
    p_sla_met: float
    qos_risk_score: float
    risk_tier: str
    congestion_level: str
    congestion_display: str = Field(
        ...,
        description="Operator-facing label (Normal / Light / Critical); API keeps congestion_level as Low/Medium/High",
    )
    sla_respected: bool
    pipeline: str
    pressure_index: float = Field(..., description="Congestion pressure 0–100")
    congestion_detail: Dict[str, Any] = Field(default_factory=dict)
    predicted_slice_type: Optional[int] = Field(
        None, description="RF slice class 1|2|3 when ml/features.pkl + rf_model.pkl are loaded"
    )
    predicted_slice_label: Optional[str] = Field(
        None, description="eMBB | mMTC | URLLC when predicted_slice_type is set"
    )
    congestion_slice_profile: str = Field(
        ...,
        description="Slice-type key used for congestion thresholds (matches RF prediction when available)",
    )


def _notify_ms3_sync(payload: Dict[str, Any]) -> None:
    """Best-effort POST vers MS-3 pour notifier les opérateurs (réseau Docker)."""
    if os.getenv("DISABLE_MS3_SYNC", "").lower() in ("1", "true", "yes"):
        return
    base = os.getenv("MS3_URL", "").strip()
    if not base:
        return
    url = f"{base.rstrip('/')}/api/sync/prediction"
    try:
        requests.post(url, json=payload, timeout=4)
    except Exception as e:
        logger.warning("MS3 sync skipped: %s", e)


def _run_prediction(body: Dict[str, Any], pipeline_label: str) -> QoSPredictResponse:
    ml_detail, congestion_slice_key = predict_slice_models(body)

    congestion_level, pressure, detail = classify_congestion(
        float(body.get("delay", 0)),
        float(body.get("plr", 0)),
        congestion_slice_key,
        jitter_ms=float(body.get("jitter") or 0),
        demand_mbps=body.get("demand_mbps"),
        capacity_mbps=body.get("capacity_mbps"),
        mobility_stress=float(body.get("mobility_stress") or 0),
    )

    detail = dict(detail)
    detail["slice_ml"] = ml_detail
    detail["congestion_slice_profile"] = congestion_slice_key

    qos_score, p_sla_met, qos_risk_score, risk_tier = qos_from_pressure(
        pressure, float(body.get("plr", 0))
    )

    # SLA violée si congestion sévérité High (notebook-aligned labels)
    sla_respected = congestion_level != "High"

    prf = int(ml_detail["rf_class"]) if ml_detail.get("rf_class") is not None else None

    return QoSPredictResponse(
        slice_id=body.get("slice_id"),
        qos_score=qos_score,
        p_sla_met=p_sla_met,
        qos_risk_score=qos_risk_score,
        risk_tier=risk_tier,
        congestion_level=congestion_level,
        congestion_display=congestion_display_label(congestion_level),
        sla_respected=sla_respected,
        pipeline=pipeline_label,
        pressure_index=round(pressure, 4),
        congestion_detail=detail,
        predicted_slice_type=prf,
        predicted_slice_label=slice_label_for_class(prf),
        congestion_slice_profile=congestion_slice_key,
    )


def _persist_prediction(body: Dict[str, Any], result: QoSPredictResponse) -> None:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO qos_predictions
        (slice_id, time, plr, delay, lte5g_cat, qos_score, p_sla_met,
         qos_risk_score, risk_tier, congestion_level, sla_respected)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            body.get("slice_id"),
            body.get("time"),
            body.get("plr"),
            body.get("delay"),
            body.get("lte5g_cat"),
            result.qos_score,
            result.p_sla_met,
            result.qos_risk_score,
            result.risk_tier,
            result.congestion_level,
            result.sla_respected,
        ),
    )
    conn.commit()
    cursor.close()
    conn.close()


@app.get("/health", tags=["health"])
def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "MS1-QoS-Prediction",
        "timestamp": datetime.now().isoformat(),
    }


@app.post(
    "/predict/qos/5g",
    response_model=QoSPredictResponse,
    tags=["prediction"],
    summary="Predict 5G QoS + congestion",
)
def predict_qos(data: QoSPredictRequest) -> QoSPredictResponse:
    body = data.model_dump()
    result = _run_prediction(body, pipeline_label="5G")

    try:
        _persist_prediction(body, result)
    except Exception as e:
        logger.error("Database error: %s", e)
    else:
        _notify_ms3_sync(
            {
                "slice_id": body.get("slice_id"),
                "congestion_level": result.congestion_level,
                "pressure_index": result.pressure_index,
                "qos_score": result.qos_score,
                "sla_respected": result.sla_respected,
                "pipeline": result.pipeline,
                "predicted_slice_type": result.predicted_slice_type,
                "congestion_slice_profile": result.congestion_slice_profile,
                "congestion_display": result.congestion_display,
                "timestamp": datetime.now().isoformat(),
            }
        )

    return result


@app.post(
    "/predict/congestion",
    response_model=QoSPredictResponse,
    tags=["prediction"],
    summary="Congestion-focused prediction (same engine as 5G QoS)",
)
def predict_congestion_route(data: QoSPredictRequest) -> QoSPredictResponse:
    """Même logique que /predict/qos/5g ; utile pour workflows orientés congestion."""
    body = data.model_dump()
    result = _run_prediction(body, pipeline_label="5G-congestion")

    try:
        _persist_prediction(body, result)
    except Exception as e:
        logger.error("Database error: %s", e)
    else:
        _notify_ms3_sync(
            {
                "slice_id": body.get("slice_id"),
                "congestion_level": result.congestion_level,
                "pressure_index": result.pressure_index,
                "qos_score": result.qos_score,
                "sla_respected": result.sla_respected,
                "pipeline": result.pipeline,
                "predicted_slice_type": result.predicted_slice_type,
                "congestion_slice_profile": result.congestion_slice_profile,
                "congestion_display": result.congestion_display,
                "timestamp": datetime.now().isoformat(),
            }
        )

    return result


@app.get("/predict/stats", tags=["prediction"])
def get_stats() -> Dict[str, Any]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT COUNT(*) as total FROM qos_predictions")
        total = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) as compliant
            FROM qos_predictions
            WHERE sla_respected = TRUE
            """)
        compliant = cursor.fetchone()["compliant"]

        cursor.close()
        conn.close()

        return {
            "total_predictions": total,
            "sla_compliance_rate": round(compliant / total, 4) if total > 0 else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


def _public_prefix(request: Optional[Request] = None) -> str:
    if request is not None:
        forwarded_prefix = request.headers.get("x-forwarded-prefix", "")
        if forwarded_prefix:
            return forwarded_prefix.rstrip("/")
    return os.getenv("MS1_PUBLIC_PREFIX", "").rstrip("/")


@app.get("/ui", tags=["ui"])
def ui_index_redirect(request: Request) -> RedirectResponse:
    p = _public_prefix(request)
    return RedirectResponse(url=(f"{p}/ui/dashboard" if p else "/ui/dashboard"), status_code=302)


@app.get("/ui/dashboard", response_class=HTMLResponse, tags=["ui"])
def ui_dashboard(request: Request) -> Any:
    """MS-1 prediction dashboard (metrics form + last run summary + chart)."""
    prefix = _public_prefix(request)
    chart_url = f"{prefix}/api/ui/chart-series" if prefix else "/api/ui/chart-series"
    return templates.TemplateResponse(
        request,
        "ms1/dashboard.html",
        {
            "public_prefix": prefix,
            "chart_url": chart_url,
            "error": None,
        },
    )


@app.post("/ui/predict", tags=["ui"])
def ui_predict(
    request: Request,
    prediction_mode: str = Form(...),
    slice_id: str = Form(...),
    time: int = Form(0),
    plr: float = Form(...),
    delay: float = Form(...),
    lte5g_cat: int = Form(0),
    jitter: float = Form(0),
    slice_type: Optional[int] = Form(None),
    lte_5g: int = Form(0),
    gbr: int = Form(0),
    ar_vr_gaming: int = Form(0),
    healthcare: int = Form(0),
    industry_4_0: int = Form(0),
    iot_devices: int = Form(0),
    public_safety: int = Form(0),
    smart_city_home: int = Form(0),
    smart_transportation: int = Form(0),
    smartphone: int = Form(0),
) -> Any:
    body: Dict[str, Any] = {
        "slice_id": slice_id,
        "time": time,
        "plr": plr,
        "delay": delay,
        "lte5g_cat": lte5g_cat,
        "jitter": jitter,
        "slice_type": slice_type,
        "lte_5g": lte_5g,
        "gbr": gbr,
        "ar_vr_gaming": ar_vr_gaming,
        "healthcare": healthcare,
        "industry_4_0": industry_4_0,
        "iot_devices": iot_devices,
        "public_safety": public_safety,
        "smart_city_home": smart_city_home,
        "smart_transportation": smart_transportation,
        "smartphone": smartphone,
        "slice_type_hint": None,
        "demand_mbps": None,
        "capacity_mbps": None,
        "mobility_stress": 0.0,
    }
    mode = (prediction_mode or "5g").lower().strip()
    if mode == "congestion":
        pipeline = "5G-congestion"
    else:
        pipeline = "5G"

    try:
        result = _run_prediction(body, pipeline_label=pipeline)
        try:
            _persist_prediction(body, result)
        except Exception as e:
            logger.error("Database error (UI): %s", e)
        else:
            _notify_ms3_sync(
                {
                    "slice_id": body.get("slice_id"),
                    "congestion_level": result.congestion_level,
                    "congestion_display": result.congestion_display,
                    "pressure_index": result.pressure_index,
                    "qos_score": result.qos_score,
                    "sla_respected": result.sla_respected,
                    "pipeline": result.pipeline,
                    "predicted_slice_type": result.predicted_slice_type,
                    "congestion_slice_profile": result.congestion_slice_profile,
                    "timestamp": datetime.now().isoformat(),
                }
            )
        prefix = _public_prefix(request)
        chart_url = f"{prefix}/api/ui/chart-series" if prefix else "/api/ui/chart-series"
        return templates.TemplateResponse(
            request,
            "ms1/dashboard.html",
            {
                "public_prefix": prefix,
                "chart_url": chart_url,
                "last_result": result.model_dump(),
                "submitted_mode": mode,
                "error": None,
            },
        )
    except Exception as e:
        logger.exception("UI predict failed")
        prefix = _public_prefix(request)
        chart_url = f"{prefix}/api/ui/chart-series" if prefix else "/api/ui/chart-series"
        return templates.TemplateResponse(
            request,
            "ms1/dashboard.html",
            {
                "public_prefix": prefix,
                "chart_url": chart_url,
                "error": str(e),
            },
            status_code=500,
        )


@app.get("/ui/history", response_class=HTMLResponse, tags=["ui"])
def ui_history(request: Request) -> Any:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT slice_id, timestamp, qos_score, congestion_level, risk_tier, sla_respected
        FROM qos_predictions
        ORDER BY timestamp DESC
        LIMIT 500
        """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    for r in rows:
        cl = (r.get("congestion_level") or "") or ""
        r["congestion_display"] = congestion_display_label(cl) if cl else "—"
    prefix = _public_prefix(request)
    return templates.TemplateResponse(
        request,
        "ms1/history.html",
        {"public_prefix": prefix, "rows": rows},
    )


@app.get("/ui/export.csv", tags=["ui"])
def ui_export_csv() -> StreamingResponse:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT slice_id, timestamp, time, plr, delay, qos_score, congestion_level,
               risk_tier, sla_respected
        FROM qos_predictions
        ORDER BY timestamp DESC
        LIMIT 5000
        """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "slice_id",
            "timestamp",
            "time",
            "plr",
            "delay",
            "qos_score",
            "congestion_level",
            "risk_tier",
            "sla_respected",
        ]
    )
    for r in rows:
        w.writerow(
            [
                r.get("slice_id"),
                r.get("timestamp"),
                r.get("time"),
                r.get("plr"),
                r.get("delay"),
                r.get("qos_score"),
                r.get("congestion_level"),
                r.get("risk_tier"),
                r.get("sla_respected"),
            ]
        )

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="qos_predictions.csv"'},
    )


@app.get("/api/ui/chart-series", tags=["ui"])
def ui_chart_series() -> Dict[str, Any]:
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT timestamp, qos_score
        FROM qos_predictions
        ORDER BY timestamp ASC
        LIMIT 200
        """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    series = []
    for r in rows:
        ts = r.get("timestamp")
        if hasattr(ts, "isoformat"):
            ts_s = ts.isoformat()
        else:
            ts_s = str(ts)
        series.append(
            {"t": ts_s, "qos": float(r["qos_score"]) if r.get("qos_score") is not None else None}
        )
    return {"series": series}


@app.get("/", tags=["meta"])
def index() -> Dict[str, Any]:
    return {
        "service": "MS1-QoS-Prediction",
        "version": "1.2.0",
        "docs": "/docs",
        "dashboard_ui": "/ui/dashboard",
        "endpoints": [
            "/health",
            "/predict/qos/5g",
            "/predict/congestion",
            "/predict/stats",
            "/ui/dashboard",
            "/ui/history",
            "/ui/export.csv",
            "/api/ui/chart-series",
        ],
        "congestion_labels_api": ["Low", "Medium", "High"],
        "congestion_labels_display": ["Normal", "Light", "Critical"],
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
