#!/usr/bin/env python3
"""
Optional CD step: index ml/metadata.json into Elasticsearch so Kibana can
visualize model accuracy and pipeline metadata (compose services elasticsearch + kibana).
Uses only the standard library (no requests).
"""

from __future__ import annotations

import json
import os
import sys
from http.client import HTTPConnection, HTTPSConnection
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
META = ROOT / "ml" / "metadata.json"


def _post_json(
    url: str, body: bytes, headers: dict[str, str], timeout: float = 30
) -> tuple[int, bytes]:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Only http/https Elasticsearch URLs are allowed, got {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("Elasticsearch URL must include a hostname")
    if parsed.scheme == "https":
        port = parsed.port or 443
        conn: HTTPConnection = HTTPSConnection(parsed.hostname, port, timeout=timeout)
    else:
        port = parsed.port or 80
        conn = HTTPConnection(parsed.hostname, port, timeout=timeout)
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    try:
        conn.request("POST", path, body=body, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def main() -> int:
    url_base = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200").rstrip("/")
    index = os.getenv("ELASTICSEARCH_INDEX", "network-slicing-metrics")
    if not META.exists():
        print(
            f"Skip ES seed: {META} not found (run training first).",
            file=sys.stderr,
        )
        return 0
    with open(META, encoding="utf-8") as f:
        meta = json.load(f)
    metrics = meta.get("metrics") or {}
    doc = {
        "@timestamp": meta.get("timestamp"),
        "pipeline": "train_models",
        "source": "metadata.json",
        "mlflow_run_id": (meta.get("mlflow") or {}).get("run_id"),
        "accuracies": {
            "rf": (metrics.get("rf") or {}).get("accuracy"),
            "xgb": (metrics.get("xgb") or {}).get("accuracy"),
            "mlp": (metrics.get("mlp") or {}).get("accuracy"),
        },
        "tool": "cd-pipeline",
    }
    payload = json.dumps(doc).encode("utf-8")
    doc_url = f"{url_base}/{index}/_doc"
    hdrs = {"Content-Type": "application/json"}
    try:
        status, response_body = _post_json(doc_url, payload, hdrs, timeout=30)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Elasticsearch unreachable at {url_base}: {e}", file=sys.stderr)
        return 1
    text = response_body.decode()
    if status >= 400:
        print(text, file=sys.stderr)
        return 1
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
