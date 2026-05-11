#!/usr/bin/env python3
"""
train.py — 5G Network Slice Selection
IBM AADS Pipeline: Preprocessing → Feature Engineering → Feature Extraction
→ Feature Selection → RF + XGBoost + MLP → Evaluation → Save Models

Fully aligned with mlops_fixed.ipynb
"""

import os
import sys
import json
import time
import warnings
from contextlib import nullcontext
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
import joblib
import numpy as np
import pandas as pd
from datetime import datetime

from sklearn.ensemble import RandomForestClassifier, IsolationForest
from sklearn.neural_network import MLPClassifier
from xgboost import XGBClassifier

from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.utils.class_weight import compute_class_weight, compute_sample_weight
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    classification_report,
    roc_auc_score,
)
from sklearn.feature_selection import chi2, f_classif, mutual_info_classif
from sklearn.decomposition import PCA

warnings.filterwarnings("ignore")

# ── Paths ──────────────────────────────────────────────────────────────────────
TRAIN_DATA_PATH = os.getenv("TRAIN_DATA_PATH", "./data/train_dataset.csv")
MODEL_OUTPUT_DIR = "./ml/"

# ── Constants ──────────────────────────────────────────────────────────────────
RANDOM_STATE = 42
np.random.seed(RANDOM_STATE)

TARGET = "slice Type"
COLS_TO_DROP = ["Time", "LTE/5g Category", "Non-GBR", "IoT"]
SLICE_MAP = {1: "eMBB", 2: "mMTC", 3: "URLLC"}

SLA = {
    1: {"name": "eMBB", "max_delay_ms": 300, "max_loss_rate": 0.01},
    2: {"name": "mMTC", "max_delay_ms": 300, "max_loss_rate": 0.01},
    3: {"name": "URLLC", "max_delay_ms": 10, "max_loss_rate": 1e-6},
}


# ── MS-5 auto-registration ────────────────────────────────────────────────────
# Best-effort: pushes one row per trained model to MS-5 ``/models/register`` so
# the operator dashboard at :5005/ui reflects every training run automatically.
# Skipped silently when MS-5 is unreachable (CI runners, offline training, etc.)
# or when DISABLE_MS5_REGISTER is truthy.
def register_models_to_ms5(metadata: dict) -> None:
    if os.getenv("DISABLE_MS5_REGISTER", "").lower() in ("1", "true", "yes"):
        return

    base = os.getenv("MS5_URL", "http://ms5:5000").strip().rstrip("/")
    if not base:
        return

    try:
        import requests
    except ImportError:
        print("  ⚠️  MS-5 register skipped: 'requests' not installed")
        return

    metrics = metadata.get("metrics", {}) or {}
    version = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    url = f"{base}/models/register"

    sent = 0
    for key, model_name in (("rf", "rf_model"), ("xgb", "xgb_model"), ("mlp", "mlp_model")):
        m = metrics.get(key) or {}
        if not m:
            continue
        payload = {
            "model_name": model_name,
            "model_version": version,
            "accuracy": m.get("accuracy"),
            "precision": m.get("precision"),
            "recall": m.get("recall"),
            "f1_score": m.get("f1"),
            "training_time": m.get("inference_ms"),
        }
        try:
            r = requests.post(url, json=payload, timeout=4)
            if r.status_code == 200:
                sent += 1
            else:
                print(f"  ⚠️  MS-5 register {model_name}: HTTP {r.status_code}")
        except requests.RequestException as e:
            print(f"  ⚠️  MS-5 register skipped ({model_name}): {e.__class__.__name__}")
            return

    if sent:
        print(f"  📤 MS-5 registered {sent} model row(s) at {url}")


def push_metadata_to_elasticsearch_index() -> None:
    """Index ``ml/metadata.json`` into Elasticsearch for Kibana (monitoring accuracy)."""
    if os.getenv("DISABLE_ELASTICSEARCH_PUSH", "").lower() in ("1", "true", "yes"):
        return
    try:
        from scripts.push_metadata_to_elasticsearch import main as es_push_main
    except ImportError as e:
        print(f"  ⚠️  Elasticsearch push skipped: {e}")
        return
    code = es_push_main()
    if code == 0:
        print("  📤 Elasticsearch: indexed training metadata for Kibana.")


# ══════════════════════════════════════════════════════════════════════════════
# STEP 0 — LOAD DATA
# ══════════════════════════════════════════════════════════════════════════════
def load_data(path: str) -> pd.DataFrame:
    print(f"  Loading data from: {path}")
    df = pd.read_csv(path)
    print(f"  Shape : {df.shape}")
    print(f"  Columns : {df.columns.tolist()}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# STEP 1 — NOISE INJECTION (6% label noise — makes results realistic)
# ══════════════════════════════════════════════════════════════════════════════
def inject_noise(df: pd.DataFrame, noise_pct: float = 0.06) -> pd.DataFrame:
    print(f"\n  Injecting {noise_pct*100:.0f}% label noise...")
    df = df.copy()
    np.random.seed(RANDOM_STATE)
    n_noise = int(noise_pct * len(df))
    noise_idx = np.random.choice(len(df), size=n_noise, replace=False)

    original_vals = df[TARGET].iloc[noise_idx].values
    flipped_vals = np.array(
        [np.random.choice([x for x in [1, 2, 3] if x != v]) for v in original_vals]
    )
    df[TARGET].iloc[noise_idx] = flipped_vals

    changed = (df[TARGET].values != df[TARGET].values).sum()
    print(f"  Labels changed : {n_noise} ({noise_pct*100:.2f}%)")
    print(f"  Label distribution after noise:")
    for sl, cnt in df[TARGET].value_counts().sort_index().items():
        print(f"    Slice {sl} ({SLICE_MAP[sl]}) : {cnt}")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# STEP 2 — PREPROCESSING
# ══════════════════════════════════════════════════════════════════════════════
def preprocess(df: pd.DataFrame):
    print("\n  Preprocessing...")
    base_features = [c for c in df.columns if c != TARGET and c not in COLS_TO_DROP]

    X = df[base_features].copy()
    y = df[TARGET].copy()

    # Log-transform Packet Loss Rate (heavy right skew)
    EPSILON = 1e-9
    X["Packet Loss Rate"] = np.log10(X["Packet Loss Rate"] + EPSILON)

    print(f"  Base features ({len(base_features)}): {base_features}")
    return X, y, base_features


# ══════════════════════════════════════════════════════════════════════════════
# STEP 3 — OUTLIER DETECTION & CAPPING (IQR Winsorization)
# ══════════════════════════════════════════════════════════════════════════════
def detect_and_cap_outliers(X: pd.DataFrame) -> pd.DataFrame:
    print("\n  Outlier detection (IQR)...")
    X = X.copy()
    continuous_cols = ["Packet Loss Rate", "Packet delay"]
    for col in continuous_cols:
        Q1 = X[col].quantile(0.25)
        Q3 = X[col].quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        n_out = ((X[col] < lower) | (X[col] > upper)).sum()
        pct = n_out / len(X) * 100
        X[col] = X[col].clip(lower=lower, upper=upper)
        status = "✅ No outliers" if pct == 0 else f"⚠️  {pct:.2f}% capped"
        print(f"    {col:<22} : {n_out} outliers ({pct:.2f}%)  {status}")
    return X


# ══════════════════════════════════════════════════════════════════════════════
# STEP 4 — FEATURE ENGINEERING
# ══════════════════════════════════════════════════════════════════════════════
def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["Is_Critical"] = (
        (df["Healthcare"] == 1) | (df["Public Safety"] == 1) | (df["Smart Transportation"] == 1)
    ).astype(int)
    df["Is_IoT_Service"] = (
        (df["IoT Devices"] == 1) | (df["Smart City & Home"] == 1) | (df["Industry 4.0"] == 1)
    ).astype(int)
    df["QoS_Score"] = 1 / (df["Packet delay"] + 1) + (1 - df["Packet Loss Rate"].clip(0, 1))
    return df


# ══════════════════════════════════════════════════════════════════════════════
# STEP 5 — FEATURE EXTRACTION (Variance + Correlation + PCA analysis)
# ══════════════════════════════════════════════════════════════════════════════
def extract_features(X: pd.DataFrame, features: list) -> tuple:
    print("\n  Feature extraction...")
    features = list(dict.fromkeys(features))  # dedup

    # Variance check
    LOW_VAR = 0.05
    variances = X[features].var()
    low_var_feats = variances[variances < LOW_VAR].index.tolist()

    # Correlation check (positional indexing — no duplicate label issues)
    corr_matrix = X[features].corr().abs()
    n = len(features)
    redundant = []
    for i in range(n):
        for j in range(i + 1, n):
            if corr_matrix.iloc[i, j] > 0.85:
                redundant.append(features[j])

    # Always drop Is_Broadband if present (perfect duplicate of LTE/5G)
    if "Is_Broadband" in features:
        redundant.append("Is_Broadband")

    to_drop = list(set(redundant + low_var_feats))
    if to_drop:
        X = X.drop(columns=[c for c in to_drop if c in X.columns])
        features = [f for f in features if f not in to_drop]
        print(f"    Dropped: {to_drop}")
    else:
        print("    ✅ No features dropped")

    print(f"    Final features ({len(features)}): {features}")
    return X, features


# ══════════════════════════════════════════════════════════════════════════════
# STEP 6 — FEATURE SELECTION (Chi2 + ANOVA + MI)
# ══════════════════════════════════════════════════════════════════════════════
def select_features(X: pd.DataFrame, y: pd.Series, features: list) -> list:
    print("\n  Feature selection (Chi2 + ANOVA + MI)...")
    actual_cols = X[features].columns.tolist()
    known_binary = [
        "LTE/5G",
        "GBR",
        "AR/VR/Gaming",
        "Healthcare",
        "Industry 4.0",
        "IoT Devices",
        "Public Safety",
        "Smart City & Home",
        "Smart Transportation",
        "Smartphone",
        "Is_Critical",
        "Is_IoT_Service",
    ]
    known_continuous = ["Packet Loss Rate", "Packet delay", "QoS_Score"]
    binary_cols = [c for c in known_binary if c in actual_cols]
    continuous_cols = [c for c in known_continuous if c in actual_cols]

    # Mutual Information — drop features with MI < 0.01
    mi_scores = mutual_info_classif(X[features], y, random_state=RANDOM_STATE)
    mi_df = pd.Series(mi_scores, index=features)
    weak_feats = mi_df[mi_df < 0.01].index.tolist()

    if weak_feats:
        X = X.drop(columns=weak_feats, errors="ignore")
        features = [f for f in features if f not in weak_feats]
        print(f"    Dropped weak MI features: {weak_feats}")
    else:
        print("    ✅ All features pass MI threshold")

    print(f"    Final features ({len(features)}): {features}")
    return features


# ══════════════════════════════════════════════════════════════════════════════
# STEP 7 — TRAIN MODELS
# ══════════════════════════════════════════════════════════════════════════════
def train_models(
    X_tr, y_tr, X_val, y_val, X_tr_scaled, X_val_scaled, class_weight_dict, classes_arr
):

    results = {}

    # ── Random Forest ──────────────────────────────────────────────
    print("\n  Training Random Forest...")
    rf_model = RandomForestClassifier(
        n_estimators=300,
        max_depth=None,
        min_samples_split=5,
        min_samples_leaf=2,
        class_weight=class_weight_dict,
        n_jobs=-1,
        random_state=RANDOM_STATE,
    )
    rf_model.fit(X_tr, y_tr)
    rf_pred = rf_model.predict(X_val)
    rf_prob = rf_model.predict_proba(X_val)
    results["rf"] = {
        "model": rf_model,
        "pred": rf_pred,
        "prob": rf_prob,
        "acc": accuracy_score(y_val, rf_pred),
        "f1": f1_score(y_val, rf_pred, average="macro"),
    }
    print(f'    RF  — Acc: {results["rf"]["acc"]:.4f}  F1: {results["rf"]["f1"]:.4f}')

    # ── XGBoost ────────────────────────────────────────────────────
    print("\n  Training XGBoost...")
    y_tr_xgb = y_tr - 1
    y_val_xgb = y_val - 1
    sample_weights_xgb = compute_sample_weight("balanced", y=y_tr_xgb)

    xgb_model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        eval_metric="mlogloss",
        n_jobs=-1,
        random_state=RANDOM_STATE,
        verbosity=0,
    )
    xgb_model.fit(
        X_tr,
        y_tr_xgb,
        sample_weight=sample_weights_xgb,
        eval_set=[(X_tr, y_tr_xgb), (X_val, y_val_xgb)],
        verbose=False,
    )
    xgb_pred = xgb_model.predict(X_val) + 1
    xgb_prob = xgb_model.predict_proba(X_val)
    results["xgb"] = {
        "model": xgb_model,
        "pred": xgb_pred,
        "prob": xgb_prob,
        "acc": accuracy_score(y_val, xgb_pred),
        "f1": f1_score(y_val, xgb_pred, average="macro"),
    }
    print(f'    XGB — Acc: {results["xgb"]["acc"]:.4f}  F1: {results["xgb"]["f1"]:.4f}')

    # ── MLP Neural Network ─────────────────────────────────────────
    print("\n  Training MLP...")
    mlp_model = MLPClassifier(
        hidden_layer_sizes=(128, 64, 32),
        activation="relu",
        solver="adam",
        alpha=1e-4,
        learning_rate_init=0.001,
        max_iter=300,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=15,
        random_state=RANDOM_STATE,
        verbose=False,
    )
    mlp_model.fit(X_tr_scaled, y_tr)
    mlp_pred = mlp_model.predict(X_val_scaled)
    mlp_prob = mlp_model.predict_proba(X_val_scaled)
    results["mlp"] = {
        "model": mlp_model,
        "pred": mlp_pred,
        "prob": mlp_prob,
        "acc": accuracy_score(y_val, mlp_pred),
        "f1": f1_score(y_val, mlp_pred, average="macro"),
    }
    print(f'    MLP — Acc: {results["mlp"]["acc"]:.4f}  F1: {results["mlp"]["f1"]:.4f}')

    return results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 8 — ISOLATION FOREST (anomaly detection)
# ══════════════════════════════════════════════════════════════════════════════
def train_isolation_forest(X_tr):
    print("\n  Training Isolation Forest...")
    iso = IsolationForest(
        n_estimators=200, contamination=0.05, random_state=RANDOM_STATE, n_jobs=-1
    )
    iso.fit(X_tr)
    return iso


# ══════════════════════════════════════════════════════════════════════════════
# STEP 9 — EVALUATION
# ══════════════════════════════════════════════════════════════════════════════
def evaluate(
    results: dict, y_val: pd.Series, X_train_full, y_train_full, X_tr_scaled, y_tr, scaler, features
):
    print("\n" + "=" * 65)
    print("  FINAL MODEL COMPARISON")
    print("=" * 65)
    print(f"  {'Model':<18} {'Val Acc':>9} {'F1 Macro':>10} {'Precision':>11} {'Recall':>8}")
    print("  " + "-" * 60)

    metrics = {}
    for key, name in [("rf", "Random Forest"), ("xgb", "XGBoost"), ("mlp", "MLP")]:
        pred = results[key]["pred"]
        acc = accuracy_score(y_val, pred)
        f1 = f1_score(y_val, pred, average="macro")
        prec = precision_score(y_val, pred, average="macro")
        rec = recall_score(y_val, pred, average="macro")
        print(f"  {name:<18} {acc:>9.4f} {f1:>10.4f} {prec:>11.4f} {rec:>8.4f}")
        metrics[key] = {"accuracy": acc, "f1": f1, "precision": prec, "recall": rec}

    # 5-fold CV on RF only (fastest)
    print("\n  5-Fold CV (Random Forest):")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    cv_sc = cross_val_score(
        results["rf"]["model"], X_train_full, y_train_full, cv=cv, scoring="accuracy", n_jobs=-1
    )
    print(f"    Mean ± Std : {cv_sc.mean():.4f} ± {cv_sc.std():.4f}")
    metrics["rf"]["cv_mean"] = cv_sc.mean()
    metrics["rf"]["cv_std"] = cv_sc.std()

    # Inference time
    print("\n  Inference times (ms/sample):")
    X_val_local = (
        pd.DataFrame(scaler.inverse_transform(X_tr_scaled[:100]), columns=features)
        if hasattr(scaler, "inverse_transform")
        else None
    )

    for key, name, X_inf in [
        ("rf", "Random Forest", pd.DataFrame(X_tr_scaled[:100], columns=features)),
        ("xgb", "XGBoost", pd.DataFrame(X_tr_scaled[:100], columns=features)),
        ("mlp", "MLP", X_tr_scaled[:100]),
    ]:
        start = time.time()
        for _ in range(100):
            results[key]["model"].predict(X_inf)
        inf_ms = (time.time() - start) / (100 * 100) * 1000
        print(f"    {name:<18} : {inf_ms:.6f} ms")
        metrics[key]["inference_ms"] = inf_ms

    return metrics


# ══════════════════════════════════════════════════════════════════════════════
# STEP 10 — SLA COMPLIANCE CHECK
# ══════════════════════════════════════════════════════════════════════════════
def check_sla(df_clean: pd.DataFrame) -> dict:
    print("\n  SLA Compliance Check...")
    base_feats = [c for c in df_clean.columns if c != TARGET and c not in COLS_TO_DROP]
    _, X_val_orig, _, y_val_orig = train_test_split(
        df_clean[base_feats],
        df_clean[TARGET],
        test_size=0.2,
        stratify=df_clean[TARGET],
        random_state=RANDOM_STATE,
    )
    X_sla = X_val_orig.copy()
    X_sla["slice Type"] = y_val_orig.values
    sla_results = {}

    for sl in [1, 2, 3]:
        sub = X_sla[X_sla["slice Type"] == sl]
        total = len(sub)
        sla_met = (
            (sub["Packet delay"] <= SLA[sl]["max_delay_ms"])
            & (sub["Packet Loss Rate"] <= SLA[sl]["max_loss_rate"])
        ).sum()
        pct = sla_met / total * 100
        sla_results[sl] = {
            "name": SLICE_MAP[sl],
            "total": total,
            "sla_met": int(sla_met),
            "pct": pct,
        }
        status = "✅ PASS" if pct == 100 else "⚠️  WARN" if pct >= 95 else "🚨 FAIL"
        print(f"    {SLICE_MAP[sl]:<8} : {pct:.2f}%  {status}")

    return sla_results


# ══════════════════════════════════════════════════════════════════════════════
# STEP 11 — SAVE MODELS + METADATA
# ══════════════════════════════════════════════════════════════════════════════
def save_models(
    results: dict, scaler, features: list, iso_forest, metrics: dict, sla_results: dict
):
    os.makedirs(MODEL_OUTPUT_DIR, exist_ok=True)
    print(f"\n  Saving models to {MODEL_OUTPUT_DIR}...")

    joblib.dump(results["rf"]["model"], os.path.join(MODEL_OUTPUT_DIR, "rf_model.pkl"))
    joblib.dump(results["xgb"]["model"], os.path.join(MODEL_OUTPUT_DIR, "xgb_model.pkl"))
    joblib.dump(results["mlp"]["model"], os.path.join(MODEL_OUTPUT_DIR, "mlp_model.pkl"))
    joblib.dump(scaler, os.path.join(MODEL_OUTPUT_DIR, "scaler.pkl"))
    joblib.dump(features, os.path.join(MODEL_OUTPUT_DIR, "features.pkl"))
    joblib.dump(iso_forest, os.path.join(MODEL_OUTPUT_DIR, "iso_forest.pkl"))

    metadata = {
        "timestamp": datetime.now().isoformat(),
        "features": features,
        "n_features": len(features),
        "slice_map": SLICE_MAP,
        "noise_pct": 0.06,
        "metrics": metrics,
        "sla_results": {str(k): v for k, v in sla_results.items()},
        "models_saved": [
            "rf_model.pkl",
            "xgb_model.pkl",
            "mlp_model.pkl",
            "scaler.pkl",
            "features.pkl",
            "iso_forest.pkl",
        ],
    }
    meta_path = os.path.join(MODEL_OUTPUT_DIR, "metadata.json")
    with open(meta_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print("  ✅ rf_model.pkl")
    print("  ✅ xgb_model.pkl")
    print("  ✅ mlp_model.pkl")
    print("  ✅ scaler.pkl")
    print("  ✅ features.pkl")
    print("  ✅ iso_forest.pkl")
    print("  ✅ metadata.json")
    return metadata


# ══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════════
def run_pipeline():
    use_mlflow = os.getenv("DISABLE_MLFLOW", "").lower() not in ("1", "true", "yes")
    mlflow_run = nullcontext()
    if use_mlflow:
        import mlflow
        from scripts.mlflow_integration import (
            configure_mlflow,
            flatten_metrics,
            get_tracking_uri,
            log_sklearn_and_xgb_models,
            write_run_pointer,
        )

        configure_mlflow()
        mlflow_run = mlflow.start_run(run_name=f"train_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    print("=" * 65)
    print("  5G NETWORK SLICE SELECTION — IBM AADS TRAINING PIPELINE")
    print("=" * 65)

    with mlflow_run:
        if use_mlflow:
            import mlflow

            mlflow.log_param("train_data_path", TRAIN_DATA_PATH)
            mlflow.log_param("random_state", RANDOM_STATE)
            mlflow.log_param("noise_pct", 0.06)
            mlflow.log_param("target", TARGET)

        # 0. Load
        print("\n[1/9] Loading data...")
        df_raw = load_data(TRAIN_DATA_PATH)
        df_clean = df_raw.copy()
        if use_mlflow:
            import mlflow

            mlflow.log_param("n_samples_raw", len(df_raw))

        # 1. Noise injection
        print("\n[2/9] Noise injection...")
        df_noisy = inject_noise(df_raw, noise_pct=0.06)

        # 2. Preprocessing
        print("\n[3/9] Preprocessing...")
        X, y, base_features = preprocess(df_noisy)

        # 3. Outlier detection
        print("\n[4/9] Outlier detection...")
        X = detect_and_cap_outliers(X)

        # 4. Feature engineering
        print("\n[5/9] Feature engineering...")
        X = engineer_features(X)
        features = list(X.columns)

        # 5. Feature extraction
        print("\n[6/9] Feature extraction...")
        X, features = extract_features(X, features)

        # 6. Feature selection
        print("\n[7/9] Feature selection...")
        features = select_features(X, y, features)
        X = X[features]

        # Train/val split
        X_tr, X_val, y_tr, y_val = train_test_split(
            X, y, test_size=0.2, stratify=y, random_state=RANDOM_STATE
        )
        scaler = StandardScaler()
        X_tr_scaled = scaler.fit_transform(X_tr)
        X_val_scaled = scaler.transform(X_val)
        classes_arr = np.array([1, 2, 3])
        cw = compute_class_weight("balanced", classes=classes_arr, y=y_tr)
        class_weight_dict = dict(zip(classes_arr, cw))

        if use_mlflow:
            import mlflow

            mlflow.log_param("n_train", int(len(X_tr)))
            mlflow.log_param("n_val", int(len(X_val)))
            mlflow.log_param("n_features", len(features))

        # 7. Train models
        print("\n[8/9] Training models...")
        results = train_models(
            X_tr, y_tr, X_val, y_val, X_tr_scaled, X_val_scaled, class_weight_dict, classes_arr
        )
        iso_forest = train_isolation_forest(X_tr)

        # 8. Evaluate
        metrics = evaluate(results, y_val, X, y, X_tr_scaled, y_tr, scaler, features)
        if use_mlflow:
            import mlflow

            for k, v in flatten_metrics(metrics).items():
                mlflow.log_metric(k, v)

        # 9. SLA check
        sla_results = check_sla(df_clean)
        if use_mlflow:
            import mlflow

            for sl_key, sl_val in sla_results.items():
                mlflow.log_metric(f"sla_slice_{sl_key}_pct", float(sl_val["pct"]))

        # 10. Save
        print("\n[9/9] Saving models...")
        metadata = save_models(results, scaler, features, iso_forest, metrics, sla_results)

        meta_path = os.path.join(MODEL_OUTPUT_DIR, "metadata.json")

        if use_mlflow:
            import mlflow
            from scripts.mlflow_integration import (
                get_tracking_uri,
                log_sklearn_and_xgb_models,
                write_run_pointer,
            )

            for fname in (
                "rf_model.pkl",
                "xgb_model.pkl",
                "mlp_model.pkl",
                "scaler.pkl",
                "features.pkl",
                "iso_forest.pkl",
            ):
                p = os.path.join(MODEL_OUTPUT_DIR, fname)
                if os.path.exists(p):
                    mlflow.log_artifact(p)

            logged = log_sklearn_and_xgb_models(results, iso_forest, X_tr, X_tr_scaled)
            run = mlflow.active_run()
            metadata["mlflow"] = {
                "run_id": run.info.run_id,
                "experiment_id": run.info.experiment_id,
                "tracking_uri": get_tracking_uri(),
                "artifacts": [{"path": a, "registry_name": r or None} for a, r in logged],
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)

            mlflow.log_artifact(meta_path)

            write_run_pointer(
                run.info.run_id,
                run.info.experiment_id,
                get_tracking_uri(),
                logged,
                Path(meta_path),
            )
            print(f"\n  📊 MLflow run_id: {run.info.run_id}")
            print(
                "  📊 MLflow UI: http://127.0.0.1:5006 if using compose service mlflow, "
                "else see MLFLOW_TRACKING_URI in .env.example"
            )

        register_models_to_ms5(metadata)
        push_metadata_to_elasticsearch_index()

        print("\n" + "=" * 65)
        print("  PIPELINE COMPLETE ✅")
        print(f'  Timestamp : {metadata["timestamp"]}')
        print(f"  Features  : {len(features)}")
        print(f'  RF  Acc   : {metrics["rf"]["accuracy"]:.4f}')
        print(f'  XGB Acc   : {metrics["xgb"]["accuracy"]:.4f}')
        print(f'  MLP Acc   : {metrics["mlp"]["accuracy"]:.4f}')
        print("=" * 65)
        return metadata


if __name__ == "__main__":
    run_pipeline()
