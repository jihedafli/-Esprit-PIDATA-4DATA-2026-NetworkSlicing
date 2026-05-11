#!/usr/bin/env python3
"""
model_registry.py — 5G Network Slice Selection
Model versioning, registration, and deployment tracking.

Tracks all 4 models produced by train.py:
  - rf_model.pkl       (Random Forest)
  - xgb_model.pkl      (XGBoost)
  - mlp_model.pkl      (MLP Neural Network)
  - iso_forest.pkl     (Isolation Forest — anomaly detection)

Registry file: ./ml/registry.json
"""

import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Paths ──────────────────────────────────────────────────────────────────────
MODEL_OUTPUT_DIR = "./ml/"
REGISTRY_PATH = "./ml/registry.json"
METADATA_PATH = "./ml/metadata.json"

# ── Model definitions — must match train.py output ────────────────────────────
MODEL_FILES = {
    "random_forest": "rf_model.pkl",
    "xgboost": "xgb_model.pkl",
    "mlp": "mlp_model.pkl",
    "isolation_forest": "iso_forest.pkl",
}

SLICE_MAP = {1: "eMBB", 2: "mMTC", 3: "URLLC"}


# ══════════════════════════════════════════════════════════════════════════════
# MODEL REGISTRY
# ══════════════════════════════════════════════════════════════════════════════
class ModelRegistry:
    """
    Tracks model versions, metrics, and active deployments.

    Registry structure:
    {
      "models": {
        "random_forest": [
          {
            "version": "v20260510_142300",
            "timestamp": "...",
            "path": "./ml/rf_model.pkl",
            "metrics": {"accuracy": 0.94, "f1": 0.93, ...},
            "features": [...],
            "n_features": 14,
            "noise_pct": 0.06
          },
          ...
        ],
        ...
      },
      "active_version": {
        "random_forest": "v20260510_142300",
        ...
      }
    }
    """

    def __init__(self, registry_path: str = REGISTRY_PATH):
        self.registry_path = registry_path
        self.registry = self._load()

    def _load(self) -> Dict[str, Any]:
        if os.path.exists(self.registry_path):
            with open(self.registry_path, "r") as f:
                return json.load(f)
        return {"models": {}, "active_version": {}}

    def _save(self):
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, "w") as f:
            json.dump(self.registry, f, indent=2)

    # ── Register ───────────────────────────────────────────────────
    def register(
        self,
        name: str,
        version: str,
        metrics: Dict[str, Any],
        path: str,
        features: list = None,
        n_features: int = None,
        noise_pct: float = 0.06,
    ) -> str:
        """Register a new model version and set it as active."""
        if name not in self.registry["models"]:
            self.registry["models"][name] = []

        entry = {
            "version": version,
            "timestamp": datetime.now().isoformat(),
            "path": path,
            "metrics": metrics,
            "features": features or [],
            "n_features": n_features or len(features or []),
            "noise_pct": noise_pct,
        }

        self.registry["models"][name].append(entry)
        self.registry["active_version"][name] = version
        self._save()
        return version

    # ── Query ──────────────────────────────────────────────────────
    def get_latest(self, name: str) -> Optional[Dict[str, Any]]:
        """Return the most recently registered version of a model."""
        versions = self.registry["models"].get(name)
        return versions[-1] if versions else None

    def get_active(self, name: str) -> Optional[Dict[str, Any]]:
        """Return the currently active version of a model."""
        active_ver = self.registry["active_version"].get(name)
        if not active_ver:
            return None
        return self.get_by_version(name, active_ver)

    def get_by_version(self, name: str, version: str) -> Optional[Dict[str, Any]]:
        """Return a specific version of a model."""
        for entry in self.registry["models"].get(name, []):
            if entry["version"] == version:
                return entry
        return None

    def list_versions(self, name: str) -> list:
        """List all registered versions of a model."""
        return [e["version"] for e in self.registry["models"].get(name, [])]

    def list_models(self) -> list:
        """List all registered model names."""
        return list(self.registry["models"].keys())

    # ── Promote ────────────────────────────────────────────────────
    def set_active(self, name: str, version: str) -> bool:
        """Promote a specific version to active (e.g. after A/B testing)."""
        if self.get_by_version(name, version):
            self.registry["active_version"][name] = version
            self._save()
            print(f"  ✅ {name} → active version set to {version}")
            return True
        print(f"  ❌ Version {version} not found for model {name}")
        return False

    # ── Rollback ───────────────────────────────────────────────────
    def rollback(self, name: str) -> bool:
        """Roll back to the previous version of a model."""
        versions = self.list_versions(name)
        if len(versions) < 2:
            print(f"  ❌ No previous version to roll back to for {name}")
            return False
        prev_version = versions[-2]
        return self.set_active(name, prev_version)

    # ── Summary ────────────────────────────────────────────────────
    def summary(self):
        """Print a summary of all registered models."""
        print("=" * 70)
        print("  MODEL REGISTRY SUMMARY")
        print("=" * 70)
        if not self.registry["models"]:
            print("  No models registered yet. Run train.py first.")
            return

        for name in self.list_models():
            active_ver = self.registry["active_version"].get(name, "none")
            versions = self.list_versions(name)
            active = self.get_active(name)
            print(f"\n  📦 {name}")
            print(f"     Versions registered : {len(versions)}")
            print(f"     Active version      : {active_ver}")
            if active:
                print(f'     Timestamp           : {active["timestamp"]}')
                print(f'     Path                : {active["path"]}')
                print(f'     Features            : {active["n_features"]}')
                print(f'     Noise injected      : {active["noise_pct"]*100:.0f}%')
                if active["metrics"]:
                    print(f"     Metrics:")
                    for k, v in active["metrics"].items():
                        if isinstance(v, float):
                            print(f"       {k:<18} : {v:.4f}")
                        else:
                            print(f"       {k:<18} : {v}")
        print()
        print("=" * 70)


# ══════════════════════════════════════════════════════════════════════════════
# REGISTER — reads metadata.json produced by train.py and registers all models
# ══════════════════════════════════════════════════════════════════════════════
def register_from_metadata(metadata_path: str = METADATA_PATH):
    """
    Read metadata.json written by train.py and register all 4 models
    into the registry with their metrics and features.
    """
    if not os.path.exists(metadata_path):
        print(f"  ❌ {metadata_path} not found. Run train.py first.")
        return None

    with open(metadata_path, "r") as f:
        metadata = json.load(f)

    registry = ModelRegistry()
    version = f"v{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    features = metadata.get("features", [])
    noise = metadata.get("noise_pct", 0.06)
    metrics = metadata.get("metrics", {})

    print("=" * 65)
    print("  REGISTERING MODELS")
    print("=" * 65)
    print(f"  Version   : {version}")
    print(f'  Timestamp : {metadata.get("timestamp", "unknown")}')
    print(f"  Features  : {len(features)}")
    print(f"  Noise     : {noise*100:.0f}%")
    print()

    # Map model keys from metadata to registry names
    model_map = {
        "random_forest": ("rf", "rf_model.pkl"),
        "xgboost": ("xgb", "xgb_model.pkl"),
        "mlp": ("mlp", "mlp_model.pkl"),
        "isolation_forest": (None, "iso_forest.pkl"),
    }

    for reg_name, (meta_key, filename) in model_map.items():
        path = os.path.join(MODEL_OUTPUT_DIR, filename)
        model_metrics = metrics.get(meta_key, {}) if meta_key else {}

        if not os.path.exists(path):
            print(f"  ⚠️  {filename} not found — skipping {reg_name}")
            continue

        registry.register(
            name=reg_name,
            version=version,
            metrics=model_metrics,
            path=path,
            features=features,
            n_features=len(features),
            noise_pct=noise,
        )
        acc_str = f'  Acc={model_metrics.get("accuracy", 0):.4f}' if model_metrics else ""
        print(f"  ✅ {reg_name:<20} → {version}{acc_str}")

    mlflow_info = metadata.get("mlflow")
    if mlflow_info:
        print()
        print(f'  📊 MLflow run_id      : {mlflow_info.get("run_id", "—")}')
        print(f'  📊 MLflow experiment  : {mlflow_info.get("experiment_id", "—")}')
        print(f'  📊 MLflow tracking URI: {mlflow_info.get("tracking_uri", "—")}')

    print()
    registry.summary()
    return registry


# ══════════════════════════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════════════════════════
def main():
    import sys

    args = sys.argv[1:]

    registry = ModelRegistry()

    if not args or args[0] == "register":
        # Default: register models from latest train.py run
        register_from_metadata()

    elif args[0] == "summary":
        registry.summary()

    elif args[0] == "list" and len(args) >= 2:
        # python model_registry.py list random_forest
        name = args[1]
        versions = registry.list_versions(name)
        print(f"  Versions for {name}: {versions}")

    elif args[0] == "activate" and len(args) >= 3:
        # python model_registry.py activate random_forest v20260510_142300
        name, version = args[1], args[2]
        registry.set_active(name, version)

    elif args[0] == "rollback" and len(args) >= 2:
        # python model_registry.py rollback random_forest
        registry.rollback(args[1])

    elif args[0] == "mlflow-registry":
        from scripts.mlflow_integration import summarize_registered_models

        summarize_registered_models()

    elif args[0] == "mlflow-last-run":
        from scripts.mlflow_integration import summarize_last_run

        summarize_last_run()

    else:
        print("Usage:")
        print("  python scripts/version_models.py register          # register from metadata.json")
        print("  python scripts/version_models.py summary           # show all models")
        print("  python scripts/version_models.py list <model>      # list versions")
        print("  python scripts/version_models.py activate <model> <version>")
        print("  python scripts/version_models.py rollback <model>")
        print("  python scripts/version_models.py mlflow-registry   # MLflow Model Registry")
        print("  python scripts/version_models.py mlflow-last-run   # last MLflow training pointer")


if __name__ == "__main__":
    main()
