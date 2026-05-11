"""Unit tests for config (no network, no Docker)."""

import importlib

import pytest


@pytest.fixture(autouse=True)
def reload_config_after_each():
    yield
    import config

    importlib.reload(config)


def test_db_config_has_required_keys():
    import config

    for key in ("host", "port", "user", "password", "database"):
        assert key in config.DB_CONFIG


def test_db_config_reads_env(monkeypatch):
    monkeypatch.setenv("DB_HOST", "test-db")
    monkeypatch.setenv("DB_PORT", "3307")
    import config

    importlib.reload(config)
    assert config.DB_CONFIG["host"] == "test-db"
    assert config.DB_CONFIG["port"] == 3307
