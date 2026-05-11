"""Unit tests for MLflow helper functions (no MLflow server)."""

from scripts.mlflow_integration import (
    flatten_metrics,
    get_tracking_uri,
    project_root,
    _normalize_sqlite_tracking_uri,
)


def test_project_root_has_config():
    assert (project_root() / "config.py").is_file()


def test_flatten_metrics_simple():
    out = flatten_metrics({"a": {"b": 1.0}, "c": 2})
    assert out["a_b"] == 1.0
    assert out["c"] == 2.0


def test_get_tracking_uri_default_uses_sqlite(monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    uri = get_tracking_uri()
    assert uri.startswith("sqlite:///")


def test_normalize_sqlite_uri_relative_is_project_anchored():
    raw = "sqlite:///ml/mlflow.db"
    norm = _normalize_sqlite_tracking_uri(raw)
    assert norm.startswith("sqlite:///")
    assert norm.endswith("/ml/mlflow.db")
    assert ".." not in norm


def test_get_tracking_uri_env_relative_sqlite_resolves_to_project(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:///ml/mlflow.db")
    uri = get_tracking_uri()
    expected = (project_root() / "ml" / "mlflow.db").resolve()
    assert uri == f"sqlite:///{expected.as_posix()}"
