"""
MLflow integration for training & registry (Grille Validation MLOps).
Covers: MLflow Tracking + Model Registry versioning.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Registry names (Model Registry) — override via env if needed
DEFAULT_REGISTRY_NAMES = {
    "rf_model": "5g-network-slicing-rf",
    "xgb_model": "5g-network-slicing-xgb",
    "mlp_model": "5g-network-slicing-mlp",
    "iso_forest_model": "5g-network-slicing-isolation-forest",
}


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _normalize_sqlite_tracking_uri(uri: str) -> str:
    """
    Anchor relative sqlite paths to the project root.

    Relative URIs like sqlite:///./ml/mlflow.db depend on the process cwd and no
    longer match the DB file used by Docker (./ml mounted at /app/ml). Absolute
    paths and http(s) URIs are left unchanged.
    """
    if not uri.lower().startswith("sqlite:"):
        return uri
    prefix = "sqlite:///"
    if not uri.startswith(prefix):
        return uri
    path_part = uri[len(prefix) :]
    p = Path(path_part)
    if p.is_absolute():
        return uri
    resolved = (project_root() / path_part).resolve()
    return f"sqlite:///{resolved.as_posix()}"


def get_tracking_uri() -> str:
    uri = os.getenv("MLFLOW_TRACKING_URI", "").strip()
    if uri:
        return _normalize_sqlite_tracking_uri(uri)
    db_path = project_root() / "ml" / "mlflow.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{db_path.as_posix()}"


def configure_mlflow() -> None:
    import mlflow
    from mlflow.tracking import MlflowClient

    uri = get_tracking_uri()
    mlflow.set_tracking_uri(uri)
    experiment = os.getenv("MLFLOW_EXPERIMENT_NAME", "5g-network-slice-selection")

    if uri.lower().startswith("http"):
        mlflow.set_experiment(experiment)
        return

    # File/SQLite backend: store artifacts under ml/mlartifacts so the same paths
    # work on the host and inside the MLflow container (compose bind-mounts ./ml).
    override = os.getenv("MLFLOW_ARTIFACT_ROOT", "").strip()
    if override:
        artifact_uri = override
    else:
        art_dir = (project_root() / "ml" / "mlartifacts").resolve()
        art_dir.mkdir(parents=True, exist_ok=True)
        artifact_uri = art_dir.as_uri()

    client = MlflowClient()
    if client.get_experiment_by_name(experiment) is None:
        mlflow.create_experiment(experiment, artifact_location=artifact_uri)
    mlflow.set_experiment(experiment)


def flatten_metrics(obj: Any, prefix: str = "") -> Dict[str, float]:
    """Flatten nested metric dicts for MLflow log_metric (numeric leaves only)."""
    out: Dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}_{k}" if prefix else str(k)
            out.update(flatten_metrics(v, key))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        out[prefix or "value"] = float(obj)
    return out


def registry_name_for_artifact(artifact_key: str) -> Optional[str]:
    if os.getenv("MLFLOW_REGISTER_MODELS", "true").lower() not in ("1", "true", "yes"):
        return None
    env_key = f"MLFLOW_REGISTRY_{artifact_key.upper()}"
    if os.getenv(env_key):
        return os.getenv(env_key)
    return DEFAULT_REGISTRY_NAMES.get(artifact_key)


def log_sklearn_and_xgb_models(
    results: dict,
    iso_forest,
    X_tr,
    X_tr_scaled,
) -> List[Tuple[str, str]]:
    """
    Log trained estimators as MLflow models with signatures.
    Returns list of (artifact_path, registry_name or '') for bookkeeping.
    """
    import mlflow
    import mlflow.sklearn
    import mlflow.xgboost
    from mlflow.models import infer_signature

    logged: List[Tuple[str, str]] = []

    sig_rf = infer_signature(
        X_tr.iloc[:1],
        results["rf"]["model"].predict(X_tr.iloc[:1]),
    )
    reg = registry_name_for_artifact("rf_model")
    mlflow.sklearn.log_model(
        results["rf"]["model"],
        artifact_path="rf_model",
        signature=sig_rf,
        registered_model_name=reg,
    )
    logged.append(("rf_model", reg or ""))

    sig_xgb = infer_signature(
        X_tr.iloc[:1],
        results["xgb"]["model"].predict(X_tr.iloc[:1]),
    )
    reg = registry_name_for_artifact("xgb_model")
    mlflow.xgboost.log_model(
        results["xgb"]["model"],
        artifact_path="xgb_model",
        signature=sig_xgb,
        registered_model_name=reg,
    )
    logged.append(("xgb_model", reg or ""))

    sig_mlp = infer_signature(
        X_tr_scaled[:1],
        results["mlp"]["model"].predict(X_tr_scaled[:1]),
    )
    reg = registry_name_for_artifact("mlp_model")
    mlflow.sklearn.log_model(
        results["mlp"]["model"],
        artifact_path="mlp_model",
        signature=sig_mlp,
        registered_model_name=reg,
    )
    logged.append(("mlp_model", reg or ""))

    sig_iso = infer_signature(
        X_tr.iloc[:1],
        iso_forest.predict(X_tr.iloc[:1]),
    )
    reg = registry_name_for_artifact("iso_forest_model")
    mlflow.sklearn.log_model(
        iso_forest,
        artifact_path="iso_forest_model",
        signature=sig_iso,
        registered_model_name=reg,
    )
    logged.append(("iso_forest_model", reg or ""))

    return logged


def write_run_pointer(
    run_id: str,
    experiment_id: str,
    tracking_uri: str,
    logged_models: List[Tuple[str, str]],
    metadata_path: Path,
) -> Path:
    """Persist last MLflow run info for scripts/version_models.py and ops."""
    out = {
        "run_id": run_id,
        "experiment_id": experiment_id,
        "tracking_uri": tracking_uri,
        "artifacts": [{"path": a, "registry": r} for a, r in logged_models],
        "metadata_json": str(metadata_path.as_posix()),
    }
    ptr = project_root() / "ml" / "mlflow_last_run.json"
    ptr.parent.mkdir(parents=True, exist_ok=True)
    with open(ptr, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
    return ptr


def mlflow_client():
    import mlflow
    from mlflow.tracking import MlflowClient

    mlflow.set_tracking_uri(get_tracking_uri())
    return MlflowClient()


def summarize_registered_models() -> None:
    """Print Model Registry versions (validation: versioning)."""
    client = mlflow_client()
    print("=" * 70)
    print("  MLFLOW MODEL REGISTRY")
    print("=" * 70)
    print(f"  Tracking URI: {get_tracking_uri()}")
    try:
        registered = client.search_registered_models()
    except Exception as e:
        print(f"  ⚠️  Could not list registry: {e}")
        registered = []
    if not registered:
        print("  No registered models found.")
        print("  Use MLFLOW_TRACKING_URI=http://127.0.0.1:5006 when the MLflow")
        print("  container is running, or a project-anchored sqlite URI (see .env.example).")
    else:
        for rm in sorted(registered, key=lambda m: m.name):
            vers = rm.latest_versions or []
            if not vers:
                print(f"\n  📌 {rm.name} (no versions)")
                continue
            latest = max(vers, key=lambda v: int(v.version))
            print(f"\n  📌 {rm.name}")
            print(f"     Latest version : {latest.version}")
            print(f"     Run ID         : {latest.run_id}")
            print(f"     Stage          : {latest.current_stage}")
            print(f"     Source         : {latest.source}")
    print()
    print("=" * 70)


def summarize_last_run() -> None:
    """Show tracking store info from ml/mlflow_last_run.json."""
    ptr = project_root() / "ml" / "mlflow_last_run.json"
    if not ptr.exists():
        print(f"  ❌ {ptr} not found. Run scripts/train_models.py first.")
        return
    with open(ptr, encoding="utf-8") as f:
        data = json.load(f)
    print("=" * 70)
    print("  MLFLOW LAST TRAINING RUN")
    print("=" * 70)
    for k, v in data.items():
        print(f"  {k}: {v}")
    print("=" * 70)
