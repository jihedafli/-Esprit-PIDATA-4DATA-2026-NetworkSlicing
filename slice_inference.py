"""
Slice-type inference (RF / XGB / MLP) aligned with scripts/train_models.py.

Builds one row in the same space as training (log PLR, engineered flags, QoS_Score),
then subsets columns to the list saved in ml/features.pkl and runs classifiers.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

EPSILON = 1e-9

SLICE_LABELS: Dict[int, str] = {1: "eMBB", 2: "mMTC", 3: "URLLC"}


def _model_dir() -> Path:
    return Path(os.getenv("ML_MODEL_DIR", "ml")).resolve()


def _paths() -> Dict[str, Path]:
    d = _model_dir()
    return {
        "rf": d / "rf_model.pkl",
        "xgb": d / "xgb_model.pkl",
        "mlp": d / "mlp_model.pkl",
        "scaler": d / "scaler.pkl",
        "features": d / "features.pkl",
    }


_artifacts_cache: Optional[Dict[str, Any]] = None


def load_ml_artifacts(*, force_reload: bool = False) -> Optional[Dict[str, Any]]:
    """Load RF/XGB/MLP + scaler + feature list from ML_MODEL_DIR (default ml/)."""
    global _artifacts_cache
    if _artifacts_cache is not None and not force_reload:
        return _artifacts_cache

    p = _paths()
    if not p["features"].is_file() or not p["rf"].is_file():
        logger.info(
            "Slice ML artifacts missing under %s (need features.pkl + rf_model.pkl)",
            _model_dir(),
        )
        _artifacts_cache = None
        return None

    try:
        features: List[str] = joblib.load(p["features"])
        rf = joblib.load(p["rf"])
        scaler = joblib.load(p["scaler"]) if p["scaler"].is_file() else None
        xgb = joblib.load(p["xgb"]) if p["xgb"].is_file() else None
        mlp = joblib.load(p["mlp"]) if p["mlp"].is_file() else None
    except Exception as e:
        logger.warning("Failed to load slice ML artifacts: %s", e)
        _artifacts_cache = None
        return None

    _artifacts_cache = {
        "features": features,
        "rf": rf,
        "scaler": scaler,
        "xgb": xgb,
        "mlp": mlp,
    }
    return _artifacts_cache


def _int01(body: Dict[str, Any], key: str, default: int = 0) -> int:
    if key not in body:
        return default
    try:
        return 1 if int(body[key]) != 0 else 0
    except (TypeError, ValueError):
        return default


def build_engineered_feature_row(body: Dict[str, Any]) -> Dict[str, float]:
    """
    Replicate preprocess (log PLR) + engineer_features from train_models.py.
    Outlier capping is skipped on single-row inference (training uses batch IQR).
    """
    raw_plr = float(body.get("plr", 0.0))
    delay = float(body.get("delay", 0.0))
    log_plr = float(np.log10(raw_plr + EPSILON))

    lte_5g = _int01(body, "lte_5g", 0)
    if lte_5g == 0 and body.get("lte5g_cat"):
        try:
            lte_5g = 1 if int(body["lte5g_cat"]) != 0 else 0
        except (TypeError, ValueError):
            pass

    healthcare = _int01(body, "healthcare", 0)
    public_safety = _int01(body, "public_safety", 0)
    smart_transportation = _int01(body, "smart_transportation", 0)
    iot_devices = _int01(body, "iot_devices", 0)
    smart_city_home = _int01(body, "smart_city_home", 0)
    industry_4_0 = _int01(body, "industry_4_0", 0)

    row: Dict[str, float] = {
        "Packet Loss Rate": log_plr,
        "Packet delay": delay,
        "LTE/5G": float(lte_5g),
        "GBR": float(_int01(body, "gbr", 0)),
        "AR/VR/Gaming": float(_int01(body, "ar_vr_gaming", 0)),
        "Healthcare": float(healthcare),
        "Industry 4.0": float(industry_4_0),
        "IoT Devices": float(iot_devices),
        "Public Safety": float(public_safety),
        "Smart City & Home": float(smart_city_home),
        "Smart Transportation": float(smart_transportation),
        "Smartphone": float(_int01(body, "smartphone", 0)),
    }

    row["Is_Critical"] = float(
        int(
            row["Healthcare"] == 1.0
            or row["Public Safety"] == 1.0
            or row["Smart Transportation"] == 1.0
        )
    )
    row["Is_IoT_Service"] = float(
        int(
            row["IoT Devices"] == 1.0
            or row["Smart City & Home"] == 1.0
            or row["Industry 4.0"] == 1.0
        )
    )
    row["QoS_Score"] = 1.0 / (delay + 1.0) + (1.0 - np.clip(row["Packet Loss Rate"], 0.0, 1.0))
    return row


def _fallback_congestion_slice_key(body: Dict[str, Any]) -> str:
    st = body.get("slice_type")
    if st is not None:
        try:
            h = int(st)
            if h in (1, 2, 3):
                return str(h)
        except (TypeError, ValueError):
            pass
    hint = body.get("slice_type_hint")
    if hint is not None:
        try:
            h = int(hint)
            if h in (1, 2, 3):
                return str(h)
        except (TypeError, ValueError):
            pass
    return "2"


def predict_slice_models(body: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """
    Run RF (and optionally XGB, MLP) on the request payload.

    Returns (detail_dict, congestion_slice_key) where congestion_slice_key is
    the slice type profile '1'|'2'|'3' for congestion + SLA refs.

    If the client sends an explicit ``slice_type`` (1--3), that **wins** for
    ``congestion_slice_key``; otherwise RF when available, else
    ``slice_type_hint`` / '2'.
    """
    explicit: Optional[str] = None
    st = body.get("slice_type")
    if st is not None:
        try:
            h = int(st)
            if h in (1, 2, 3):
                explicit = str(h)
        except (TypeError, ValueError):
            pass

    art = load_ml_artifacts()
    out: Dict[str, Any] = {
        "artifacts_loaded": bool(art),
        "features_used": [],
        "rf_class": None,
        "xgb_class": None,
        "mlp_class": None,
        "congestion_profile_source": "rf" if explicit is None else "slice_type",
    }

    if not art:
        out["note"] = "no_artifacts"
        out["congestion_profile_source"] = "slice_type" if explicit is not None else "hint"
        if explicit is not None:
            return out, explicit
        return out, _fallback_congestion_slice_key(body)

    features: List[str] = art["features"]
    out["features_used"] = list(features)

    full = build_engineered_feature_row(body)
    try:
        values = [float(full[c]) for c in features]
    except KeyError as e:
        logger.warning("Feature missing from engineered row: %s", e)
        out["error"] = f"missing_engineered_key:{e}"
        out["congestion_profile_source"] = "slice_type" if explicit is not None else "hint"
        if explicit is not None:
            return out, explicit
        return out, _fallback_congestion_slice_key(body)

    X = pd.DataFrame([values], columns=features)

    rf = art["rf"]
    try:
        rf_pred = int(np.asarray(rf.predict(X)).ravel()[0])
        if rf_pred not in (1, 2, 3):
            rf_pred = int(np.clip(rf_pred, 1, 3))
        out["rf_class"] = rf_pred
    except Exception as e:
        logger.warning("RF slice prediction failed: %s", e)
        out["rf_error"] = str(e)

    if art.get("xgb") is not None:
        try:
            xgb_raw = int(np.asarray(art["xgb"].predict(X)).ravel()[0]) + 1
            out["xgb_class"] = xgb_raw
        except Exception as e:
            logger.warning("XGB slice prediction failed: %s", e)
            out["xgb_error"] = str(e)

    if art.get("mlp") is not None and art.get("scaler") is not None:
        try:
            Xs = art["scaler"].transform(X)
            mlp_pred = int(np.asarray(art["mlp"].predict(Xs)).ravel()[0])
            out["mlp_class"] = mlp_pred
        except Exception as e:
            logger.warning("MLP slice prediction failed: %s", e)
            out["mlp_error"] = str(e)

    if explicit is not None:
        return out, explicit

    if out["rf_class"] is not None:
        out["congestion_profile_source"] = "rf"
        return out, str(int(out["rf_class"]))

    out["congestion_profile_source"] = "hint"
    return out, _fallback_congestion_slice_key(body)


def slice_label_for_class(cls: Optional[int]) -> Optional[str]:
    if cls is None:
        return None
    try:
        return SLICE_LABELS.get(int(cls))
    except (TypeError, ValueError):
        return None
