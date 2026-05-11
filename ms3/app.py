#!/usr/bin/env python3
"""
5G Network Slicing - Dashboard Service (MS3)
FastAPI — API agrégée + interface NOC (authentification session)
"""

import decimal
import os
import secrets
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Optional

import json

import mysql.connector
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _fmt4(v: Any) -> str:
    if v is None:
        return "—"
    try:
        return f"{float(v):.4f}"
    except (TypeError, ValueError):
        return "—"


templates.env.filters["fmt4"] = _fmt4


def _ui_root(request: Request) -> str:
    """
    Public path prefix when MS3 is behind a reverse proxy (e.g. Nginx /noc/).
    Prefer the X-Forwarded-Prefix header; fallback MS3_PUBLIC_PREFIX for local setups.
    """
    h = (request.headers.get("x-forwarded-prefix") or "").strip()
    if h:
        return h.rstrip("/")
    return os.getenv("MS3_PUBLIC_PREFIX", "").strip().rstrip("/")


def _abs_url(request: Request, path: str) -> str:
    """Browser path starting at site root, including proxy prefix when present."""
    if not path.startswith("/"):
        path = f"/{path}"
    root = _ui_root(request)
    return f"{root}{path}" if root else path


templates.env.globals["abs_url"] = _abs_url


app = FastAPI(
    title="MS3 Dashboard",
    description="Aggregated network slicing dashboard data",
    version="1.0.0",
)

SESSION_SECRET = os.getenv("SESSION_SECRET") or os.getenv(
    "SECRET_KEY", "dev-ms3-change-in-production"
)
if len(SESSION_SECRET) < 16:
    raise RuntimeError("SESSION_SECRET / SECRET_KEY must be at least 16 characters")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    max_age=86400,
    same_site="lax",
    https_only=False,
)
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
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


def ensure_operator_schema() -> None:
    """Table seuils opérateur (idempotent)."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS operator_thresholds (
            profile_key VARCHAR(32) PRIMARY KEY,
            pressure_low_max FLOAT NOT NULL,
            pressure_medium_max FLOAT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
        """)
    conn.commit()
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


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _json_safe_row(row: dict) -> dict:
    return {k: _json_safe_value(v) for k, v in dict(row).items()}


def verify_credentials(username: str, password: str) -> bool:
    """Comparaison constante-temps (variables d\'environnement)."""
    expected_user = os.getenv("DASHBOARD_USER", "admin")
    expected_pass = os.getenv("DASHBOARD_PASSWORD", "admin")
    u_ok = secrets.compare_digest(username.encode("utf-8"), expected_user.encode("utf-8"))
    p_ok = secrets.compare_digest(password.encode("utf-8"), expected_pass.encode("utf-8"))
    return u_ok and p_ok


def fetch_dashboard_payload() -> Dict[str, Any]:
    """Données agrégées (partagé API JSON + page HTML)."""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT * FROM qos_predictions
        WHERE `timestamp` >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        ORDER BY `timestamp` DESC
        LIMIT 100
        """)
    predictions = cursor.fetchall()

    cursor.execute("""
        SELECT * FROM anomaly_detections
        WHERE `timestamp` >= DATE_SUB(NOW(), INTERVAL 24 HOUR)
        ORDER BY `timestamp` DESC
        LIMIT 100
        """)
    anomalies = cursor.fetchall()

    cursor.execute("""
        SELECT * FROM alerts
        ORDER BY `timestamp` DESC
        LIMIT 50
        """)
    alerts = cursor.fetchall()

    cursor.close()
    conn.close()

    predictions = [_json_safe_row(p) for p in predictions]
    anomalies = [_json_safe_row(a) for a in anomalies]
    alerts = [_json_safe_row(a) for a in alerts]

    total_slices = (
        len({p.get("slice_id") for p in predictions if p.get("slice_id")}) if predictions else 0
    )
    qos_vals = [
        _x for _x in (_safe_float(p.get("qos_score")) for p in predictions) if _x is not None
    ]
    avg_qos = round(sum(qos_vals) / len(qos_vals), 4) if qos_vals else 0
    anomalies_count = sum(1 for a in anomalies if a.get("is_anomaly") in (True, 1, "1"))
    critical_alerts = sum(1 for a in alerts if str(a.get("severity") or "").upper() == "CRITICAL")

    return {
        "summary": {
            "total_slices_monitored": total_slices,
            "avg_qos_score": avg_qos,
            "anomalies_detected_24h": anomalies_count,
            "critical_alerts": critical_alerts,
        },
        "predictions": predictions[:20],
        "anomalies": anomalies[:20],
        "alerts": alerts[:20],
    }


# ——— Auth & UI ———


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Any:
    if request.session.get("user"):
        return RedirectResponse(url=_abs_url(request, "/dashboard"), status_code=302)
    return templates.TemplateResponse(request, "login.html", {"error": None})


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> Any:
    try:
        if verify_credentials(username, password):
            request.session["user"] = username
            return RedirectResponse(url=_abs_url(request, "/dashboard"), status_code=303)
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Identifiant ou mot de passe incorrect."},
            status_code=401,
        )
    except Exception as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": f"Erreur serveur ({exc.__class__.__name__}). Voir les logs MS3.",
            },
            status_code=500,
        )


@app.get("/logout")
def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url=_abs_url(request, "/login"), status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(request: Request) -> Any:
    if not request.session.get("user"):
        return RedirectResponse(url=_abs_url(request, "/login"), status_code=302)
    ensure_operator_schema()
    username = request.session.get("user", "")
    try:
        data = fetch_dashboard_payload()
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"username": username, "message": str(e)},
            status_code=500,
        )
    try:
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {"username": username, "data": data},
        )
    except Exception as e:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"username": username, "message": f"Template: {e}"},
            status_code=500,
        )


@app.get("/", tags=["meta"])
def root(request: Request) -> Any:
    """Redirige vers le tableau de bord (puis login si non connecté)."""
    return RedirectResponse(url=_abs_url(request, "/dashboard"), status_code=302)


# ——— API (sans auth — tests d’intégration & agrégation machines) ———


@app.get("/health", tags=["health"])
def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "MS3-Dashboard",
        "timestamp": datetime.now().isoformat(),
    }


class PredictionSyncPayload(BaseModel):
    """Charge utile envoyée par MS-1 après une prédiction enregistrée."""

    slice_id: str
    congestion_level: str
    congestion_display: Optional[str] = None
    pressure_index: float = 0.0
    qos_score: float = 0.0
    sla_respected: bool = True
    pipeline: str = "5G"
    timestamp: Optional[str] = None


@app.post("/api/sync/prediction", tags=["dashboard"])
def sync_prediction_from_ms1(payload: PredictionSyncPayload) -> Dict[str, Any]:
    """Réception best-effort des prédictions MS-1 (journal + alerte si critique)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        msg = json.dumps(payload.model_dump(), ensure_ascii=False)
        cursor.execute(
            "INSERT INTO system_logs (service, level, message) VALUES (%s, %s, %s)",
            ("MS1-sync", "INFO", msg),
        )
        if payload.congestion_level == "High":
            label = payload.congestion_display or payload.congestion_level
            cursor.execute(
                """
                INSERT INTO alerts (alert_type, severity, message, slice_id)
                VALUES (%s, %s, %s, %s)
                """,
                (
                    "congestion",
                    "CRITICAL",
                    f"Congestion sévère ({label}) — tranche {payload.slice_id} "
                    f"(pression {payload.pressure_index:.1f})",
                    payload.slice_id,
                ),
            )
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "accepted", "slice_id": payload.slice_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/dashboard-data", tags=["dashboard"])
def get_dashboard_data() -> Dict[str, Any]:
    try:
        return fetch_dashboard_payload()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/alerts", tags=["dashboard"])
def list_alerts(limit: int = 50) -> Dict[str, Any]:
    """Liste brute des alertes (placeholder mentionné dans les métadonnées)."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT * FROM alerts
            ORDER BY `timestamp` DESC
            LIMIT %s
            """,
            (min(limit, 200),),
        )
        rows = [_json_safe_row(r) for r in cursor.fetchall()]
        cursor.close()
        conn.close()
        return {"alerts": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.post("/api/alerts/{alert_id}/acknowledge", tags=["dashboard"])
def acknowledge_alert(alert_id: int) -> Dict[str, Any]:
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE alerts SET acknowledged = TRUE WHERE id = %s",
            (alert_id,),
        )
        conn.commit()
        n = cursor.rowcount
        cursor.close()
        conn.close()
        if not n:
            raise HTTPException(status_code=404, detail="Alert not found")
        return {"status": "ok", "alert_id": alert_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/ops/", include_in_schema=False)
def ops_trailing_slash(request: Request) -> RedirectResponse:
    """Avoid /noc/ops/ + relative form actions resolving to /noc/ops/ops/... (404)."""
    return RedirectResponse(url=_abs_url(request, "/ops"), status_code=308)


@app.get("/ops", response_class=HTMLResponse, tags=["ui"])
def ops_page(request: Request) -> Any:
    if not request.session.get("user"):
        return RedirectResponse(url=_abs_url(request, "/login"), status_code=302)
    ensure_operator_schema()
    username = request.session.get("user", "")
    conn = get_db_connection()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT * FROM operator_thresholds ORDER BY profile_key")
    thresholds = [_json_safe_row(r) for r in cur.fetchall()]
    cur.execute("SELECT * FROM alerts ORDER BY `timestamp` DESC LIMIT 80")
    alerts = [_json_safe_row(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return templates.TemplateResponse(
        request,
        "ops.html",
        {"username": username, "thresholds": thresholds, "alerts": alerts},
    )


@app.post("/ops/thresholds/save")
def ops_save_threshold(
    request: Request,
    profile_key: str = Form(...),
    pressure_low_max: float = Form(...),
    pressure_medium_max: float = Form(...),
) -> Any:
    if not request.session.get("user"):
        return RedirectResponse(url=_abs_url(request, "/login"), status_code=302)
    ensure_operator_schema()
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO operator_thresholds (profile_key, pressure_low_max, pressure_medium_max)
        VALUES (%s, %s, %s)
        ON DUPLICATE KEY UPDATE pressure_low_max=VALUES(pressure_low_max), pressure_medium_max=VALUES(pressure_medium_max)
        """,
        (profile_key.strip(), pressure_low_max, pressure_medium_max),
    )
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url=_abs_url(request, "/ops"), status_code=303)


@app.post("/ops/alerts/ack")
def ops_ack_alert(request: Request, alert_id: int = Form(...)) -> Any:
    if not request.session.get("user"):
        return RedirectResponse(url=_abs_url(request, "/login"), status_code=302)
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE alerts SET acknowledged = TRUE WHERE id = %s", (alert_id,))
    conn.commit()
    cur.close()
    conn.close()
    return RedirectResponse(url=_abs_url(request, "/ops"), status_code=303)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
