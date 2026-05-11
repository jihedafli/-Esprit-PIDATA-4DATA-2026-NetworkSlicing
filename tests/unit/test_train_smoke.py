"""Smoke test: full training pipeline on a small CSV (no MLflow, no Docker)."""

import importlib
from pathlib import Path


def test_train_pipeline_writes_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("DISABLE_MLFLOW", "1")
    monkeypatch.setenv("DISABLE_ELASTICSEARCH_PUSH", "1")
    repo = Path(__file__).resolve().parents[2]
    csv = repo / "tests" / "fixtures" / "ci_train.csv"
    assert csv.is_file(), "commit tests/fixtures/ci_train.csv for CI"
    monkeypatch.setenv("TRAIN_DATA_PATH", str(csv))
    monkeypatch.chdir(tmp_path)

    import scripts.train_models as tm

    importlib.reload(tm)
    tm.run_pipeline()

    assert (tmp_path / "ml" / "metadata.json").is_file()
    assert (tmp_path / "ml" / "rf_model.pkl").is_file()
