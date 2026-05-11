#!/usr/bin/env python3
"""
ML Inference for MS-2: Keras autoencoder (.h5) + Isolation Forest (iso_forest.pkl).

When both detectors are available, consensus is strict AND (both must flag anomaly).
IF is trained on unscaled features in scripts/train_models.py; AE uses the same raw feature
vector + StandardScaler from scaler.pkl. Artifacts live under ml/ (joblib for IF/scaler/features).
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

PLR_EPSILON = 1e-9
_DEFAULT_AUTOENCODER_THRESHOLD = 1e-3


def _ml_dir() -> Path:
    return Path(__file__).resolve().parent


def _engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Mirror scripts/train_models.engineer_features (keep in sync)."""
    df = df.copy()
    df["Is_Critical"] = (
        (df["Healthcare"] == 1) | (df["Public Safety"] == 1) | (df["Smart Transportation"] == 1)
    ).astype(int)
    df["Is_IoT_Service"] = (
        (df["IoT Devices"] == 1) | (df["Smart City & Home"] == 1) | (df["Industry 4.0"] == 1)
    ).astype(int)
    df["QoS_Score"] = 1 / (df["Packet delay"] + 1) + (1 - df["Packet Loss Rate"].clip(0, 1))
    return df


def training_aligned_feature_dict(
    packet_loss_rate: float,
    packet_delay: float,
    lte_5g: int,
    gbr: int,
    ar_vr_gaming: int,
    healthcare: int,
    industry_4_0: int,
    iot_devices: int,
    public_safety: int,
    smart_city_home: int,
    smart_transportation: int,
    smartphone: int,
) -> Dict[str, Any]:
    """log10(PLR) → engineer_features (as in train_models) → columns in features.pkl."""
    row = {
        "Packet Loss Rate": float(np.log10(float(packet_loss_rate) + PLR_EPSILON)),
        "Packet delay": float(packet_delay),
        "LTE/5G": int(lte_5g),
        "GBR": int(gbr),
        "AR/VR/Gaming": int(ar_vr_gaming),
        "Healthcare": int(healthcare),
        "Industry 4.0": int(industry_4_0),
        "IoT Devices": int(iot_devices),
        "Public Safety": int(public_safety),
        "Smart City & Home": int(smart_city_home),
        "Smart Transportation": int(smart_transportation),
        "Smartphone": int(smartphone),
    }
    df = pd.DataFrame([row])
    df = _engineer_features(df)

    mm = get_model_manager()
    cols = mm.feature_columns
    if cols:
        df = df.reindex(columns=list(cols), fill_value=0)

    return {str(k): float(df.iloc[0][k]) for k in df.columns}


def _read_threshold_from_json(path: Path) -> Optional[float]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        val = data.get("threshold")
        if val is not None:
            return float(val)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def get_autoencoder_threshold() -> float:
    """MSE threshold for Keras autoencoder (env overrides JSON)."""
    env_ae = os.getenv("AUTOENCODER_THRESHOLD", "").strip()
    if env_ae:
        return float(env_ae)
    env_legacy = os.getenv("ANOMALY_THRESHOLD", "").strip()
    if env_legacy:
        return float(env_legacy)
    for p in (_ml_dir() / "autoencoder_threshold.json", _ml_dir() / "anomaly_threshold.json"):
        v = _read_threshold_from_json(p)
        if v is not None:
            return v
    return _DEFAULT_AUTOENCODER_THRESHOLD


def parse_slice_type(slice_id: Optional[str]) -> Optional[int]:
    """Map slice_id (e.g. '2', 'slice-urllc-3') to 1|2|3 for per-slice .h5 files."""
    if slice_id is None:
        return None
    s = str(slice_id).strip()
    if s in ("1", "2", "3"):
        return int(s)
    m = re.fullmatch(r"\d+", s)
    if m:
        v = int(m.group(0))
        if v in (1, 2, 3):
            return v
    m = re.search(r"[123]", s)
    if m:
        v = int(m.group(0))
        if v in (1, 2, 3):
            return v
    return None


def resolve_autoencoder_path(slice_id: Optional[str]) -> Optional[Path]:
    """
    Pick first existing file: AUTOENCODER_PATH (if set), autoencoder_slice_{n}.h5, autoencoder.h5.
    All relative paths are resolved under ml/.
    """
    ml_dir = _ml_dir()
    candidates: List[Path] = []

    raw = os.getenv("AUTOENCODER_PATH", "").strip()
    if raw:
        p = Path(raw)
        candidates.append(p if p.is_absolute() else ml_dir / p)

    st = parse_slice_type(slice_id)
    if st is not None:
        candidates.append(ml_dir / f"autoencoder_slice_{st}.h5")

    candidates.append(ml_dir / "autoencoder.h5")

    seen: set[str] = set()
    for p in candidates:
        try:
            key = str(p.resolve())
        except OSError:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if p.is_file():
            return p
    return None


_ae_model_cache: Dict[str, Any] = {}


def _load_keras_autoencoder(path: Path):
    import tensorflow as tf

    key = str(path.resolve())
    if key not in _ae_model_cache:
        _ae_model_cache[key] = tf.keras.models.load_model(path, compile=False)
    return _ae_model_cache[key]


class ModelManager:
    """Keras AE (.h5) + scaler + feature list; IsolationForest on unscaled X (training-aligned)."""

    def __init__(
        self,
        scaler_path: Optional[str] = None,
        features_path: Optional[str] = None,
        iso_forest_path: Optional[str] = None,
    ):
        ml = _ml_dir()
        self.scaler_path = scaler_path or os.getenv("SCALER_PATH", str(ml / "scaler.pkl"))
        self.features_path = features_path or os.getenv("ENCODER_PATH", str(ml / "features.pkl"))
        self.iso_forest_path = iso_forest_path or os.getenv(
            "ISO_FOREST_PATH", str(ml / "iso_forest.pkl")
        )

        self.scaler = None
        self.feature_columns: Optional[list] = None
        self.iso_forest = None
        self._loaded = False

    def load(self) -> bool:
        try:
            if os.path.exists(self.scaler_path):
                self.scaler = joblib.load(self.scaler_path)
            if os.path.exists(self.features_path):
                self.feature_columns = joblib.load(self.features_path)
            if os.path.exists(self.iso_forest_path):
                self.iso_forest = joblib.load(self.iso_forest_path)
            self._loaded = True
            return True
        except Exception as e:
            print(f"Error loading MS2 artifacts: {e}")
            return False

    def has_isolation_forest(self) -> bool:
        return self.iso_forest is not None

    def can_run_autoencoder(self, slice_id: Optional[str]) -> bool:
        return (
            self.scaler is not None
            and self.feature_columns
            and resolve_autoencoder_path(slice_id) is not None
        )

    def _prepare_features(self, features: Dict[str, Any]) -> np.ndarray:
        if self.feature_columns:
            values = [features.get(col, 0) for col in self.feature_columns]
        else:
            values = list(features.values())
        return np.array(values, dtype=np.float32)

    def predict_autoencoder(
        self, features: Dict[str, Any], slice_id: Optional[str]
    ) -> Tuple[bool, float, float]:
        path = resolve_autoencoder_path(slice_id)
        if path is None or self.scaler is None:
            raise RuntimeError("Autoencoder or scaler not available.")
        feature_array = self._prepare_features(features)
        X = feature_array.reshape(1, -1)
        Xs = self.scaler.transform(X)
        model = _load_keras_autoencoder(path)
        reconstructed = np.asarray(model.predict(Xs, verbose=0), dtype=np.float64)
        mse = float(np.mean(np.square(Xs - reconstructed)))
        thr = get_autoencoder_threshold()
        denom = max(thr, 1e-12)
        is_anomaly = mse > thr
        confidence = min(0.95, 0.5 + (mse / denom) * 0.45)
        return is_anomaly, mse, confidence


_model_manager: Optional[ModelManager] = None


def get_model_manager() -> ModelManager:
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelManager()
        _model_manager.load()
    return _model_manager


def detect_anomaly(features: Dict[str, Any], slice_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Run Isolation Forest and Keras autoencoder when possible.
    If both produce a result, is_anomaly = if_anomaly AND ae_anomaly (strict consensus).
    """
    mm = get_model_manager()
    X_raw = mm._prepare_features(features).reshape(1, -1)

    ae_part: Optional[Dict[str, Any]] = None
    iso_part: Optional[Dict[str, Any]] = None

    if mm.can_run_autoencoder(slice_id):
        try:
            ae_anomaly, ae_score, ae_conf = mm.predict_autoencoder(features, slice_id)
            ae_path = resolve_autoencoder_path(slice_id)
            ae_part = {
                "is_anomaly": ae_anomaly,
                "reconstruction_mse": ae_score,
                "confidence": ae_conf,
                "model_path": str(ae_path) if ae_path else None,
            }
        except Exception as e:
            print(f"Autoencoder prediction error: {e}")

    if mm.has_isolation_forest():
        try:
            pred = int(mm.iso_forest.predict(X_raw)[0])
            iso_part = {
                "is_anomaly": pred == -1,
                "sklearn_label": pred,
            }
        except Exception as e:
            print(f"IsolationForest prediction error: {e}")

    if ae_part is None and iso_part is None:
        return _heuristic_detection(features)

    if ae_part is None and iso_part is not None:
        ia = bool(iso_part["is_anomaly"])
        return {
            "is_anomaly": ia,
            "score": 1.0 if ia else 0.0,
            "confidence": 0.88 if ia else 0.28,
            "method": "IsolationForest",
            "detail": {"isolation_forest": iso_part},
        }

    if iso_part is None and ae_part is not None:
        return {
            "is_anomaly": ae_part["is_anomaly"],
            "score": ae_part["reconstruction_mse"],
            "confidence": ae_part["confidence"],
            "method": "KerasAutoencoder",
            "detail": {"autoencoder": ae_part},
        }

    assert ae_part is not None and iso_part is not None
    iso_flag = bool(iso_part["is_anomaly"])
    ae_flag = bool(ae_part["is_anomaly"])
    consensus = iso_flag and ae_flag
    score = float(ae_part["reconstruction_mse"])
    confidence = 0.92 if consensus else 0.38

    return {
        "is_anomaly": consensus,
        "score": score,
        "confidence": confidence,
        "method": "Consensus(IF∧AE)",
        "detail": {"isolation_forest": iso_part, "autoencoder": ae_part},
    }


def _heuristic_detection(features: Dict[str, Any]) -> Dict[str, Any]:
    """Fallback when models are missing; works on training-aligned feature dicts."""
    score = 0.0
    delay = float(features.get("Packet delay", 0))
    plr_log = float(features.get("Packet Loss Rate", -9))
    if delay > 150:
        score += 0.35
    if plr_log > -2.5:
        score += 0.35
    score += 0.1 * sum(1 for k in ("Is_Critical", "Healthcare", "Public Safety") if features.get(k))

    is_anomaly = score > 0.5
    confidence = min(0.95, 0.5 + score)

    return {
        "is_anomaly": is_anomaly,
        "score": score,
        "confidence": confidence,
        "method": "Heuristic",
    }


if __name__ == "__main__":
    test_features = training_aligned_feature_dict(
        packet_loss_rate=0.00016,
        packet_delay=22.0,
        lte_5g=1,
        gbr=0,
        ar_vr_gaming=0,
        healthcare=0,
        industry_4_0=0,
        iot_devices=1,
        public_safety=0,
        smart_city_home=0,
        smart_transportation=0,
        smartphone=0,
    )
    print(detect_anomaly(test_features, slice_id="1"))
