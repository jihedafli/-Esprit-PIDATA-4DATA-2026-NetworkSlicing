"""
5G slice congestion — operational labels: Low, Medium, High (aligned with notebook).

Pressure index (0–100) from latency, packet loss, jitter, capacity stress, mobility stress.
Delay/PLR normalization uses slice-specific SLA reference caps (same as train_models SLA dict).
Threshold bands for pressure → labels remain slice-aware via CONGESTION_THRESHOLDS_JSON.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Jitter normalization (global; optional per-profile extension via JSON later)
_JITTER_REF_MS = float(os.getenv("CONGESTION_JITTER_REF_MS", "5.0"))

# Notebook-aligned SLA caps (scripts/train_models.py SLICE_MAP + SLA) — used as reference
# denominators so URLLC at 80 ms scores as severe vs 10 ms cap, not vs a global 80 ms.
_DEFAULT_SLA_REFS_MS: Dict[str, Tuple[float, float]] = {
    "default": (300.0, 0.01),
    "1": (300.0, 0.01),  # eMBB
    "2": (300.0, 0.01),  # mMTC
    "3": (10.0, 1e-6),  # URLLC
    "eMBB": (300.0, 0.01),
    "mMTC": (300.0, 0.01),
    "URLLC": (10.0, 1e-6),
}

# Default slice-aware pressure bands: pressure ≤ low_max → congestion severity Low (healthy network load),
# ≤ medium_max → Medium, else High. Override per slice_id / slice type via CONGESTION_THRESHOLDS_JSON.
_DEFAULT_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "default": {"pressure_low_max": 33.0, "pressure_medium_max": 66.0},
    "1": {"pressure_low_max": 33.0, "pressure_medium_max": 66.0},
    "2": {"pressure_low_max": 35.0, "pressure_medium_max": 68.0},
    "3": {"pressure_low_max": 25.0, "pressure_medium_max": 55.0},
    "eMBB": {"pressure_low_max": 33.0, "pressure_medium_max": 66.0},
    "mMTC": {"pressure_low_max": 35.0, "pressure_medium_max": 68.0},
    "URLLC": {"pressure_low_max": 25.0, "pressure_medium_max": 55.0},
}


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def _load_threshold_map() -> Dict[str, Dict[str, float]]:
    """Merge notebook-style JSON env with defaults (same keys as CONGESTION_THRESHOLDS dict)."""
    merged = {k: dict(v) for k, v in _DEFAULT_THRESHOLDS.items()}
    raw = os.getenv("CONGESTION_THRESHOLDS_JSON", "").strip()
    if raw:
        try:
            user = json.loads(raw)
            if isinstance(user, dict):
                for key, val in user.items():
                    if (
                        isinstance(val, dict)
                        and "pressure_low_max" in val
                        and "pressure_medium_max" in val
                    ):
                        merged[str(key)] = {
                            "pressure_low_max": float(val["pressure_low_max"]),
                            "pressure_medium_max": float(val["pressure_medium_max"]),
                        }
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            logger.warning("CONGESTION_THRESHOLDS_JSON invalid, using defaults: %s", e)
    _merge_db_thresholds(merged)
    return merged


def _merge_db_thresholds(merged: Dict[str, Dict[str, float]]) -> None:
    """Optional merge from MySQL ``operator_thresholds`` (MS-3 CRUD)."""
    if os.getenv("CONGESTION_THRESHOLDS_FROM_DB", "").lower() not in ("1", "true", "yes"):
        return
    try:
        import mysql.connector

        conn = mysql.connector.connect(
            host=os.getenv("DB_HOST", "mysql"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=os.getenv("DB_PASSWORD", "rootpassword"),
            database=os.getenv("DB_NAME", "network_slicing_5g"),
        )
        cur = conn.cursor()
        cur.execute(
            "SELECT profile_key, pressure_low_max, pressure_medium_max FROM operator_thresholds"
        )
        for profile_key, low_m, med_m in cur.fetchall():
            merged[str(profile_key)] = {
                "pressure_low_max": float(low_m),
                "pressure_medium_max": float(med_m),
            }
        cur.close()
        conn.close()
    except Exception as e:
        logger.debug("operator_thresholds merge skipped: %s", e)


# API keeps Low/Medium/High; dashboards and operators often use Normal/Light/Critical.
_CONGESTION_LEVEL_TO_DISPLAY = {"Low": "Normal", "Medium": "Light", "High": "Critical"}
_DISPLAY_TO_LEVEL = {v: k for k, v in _CONGESTION_LEVEL_TO_DISPLAY.items()}


def congestion_display_label(level: str) -> str:
    """Map engine label → operator-facing label (Normal / Light / Critical)."""
    return _CONGESTION_LEVEL_TO_DISPLAY.get(level, level)


def congestion_engine_label(display_label: str) -> str:
    """Reverse map when accepting UI labels."""
    return _DISPLAY_TO_LEVEL.get(display_label, display_label)


def _thresholds_for_slice(slice_id: str) -> Tuple[Dict[str, float], str]:
    """
    Resolve pressure_low_max / pressure_medium_max for this slice.
    Returns (threshold_dict, profile_key_used).
    """
    m = _load_threshold_map()
    sid = (slice_id or "").strip() or "default"

    if sid in m:
        return m[sid], sid

    for k in m:
        if k.lower() == sid.lower():
            return m[k], k

    # Slice type integers / names embedded in id (notebook slice Type 1|2|3)
    for token, profile in (
        ("urllc", "URLLC"),
        ("emb", "eMBB"),
        ("mmtc", "mMTC"),
    ):
        if token in sid.lower():
            return m.get(profile, m["default"]), profile

    if sid in ("1", "2", "3") and sid in m:
        return m[sid], sid

    return m["default"], "default"


def _load_sla_ref_map() -> Dict[str, Tuple[float, float]]:
    """Merge defaults with CONGESTION_SLA_REFS_JSON overrides."""
    merged: Dict[str, Tuple[float, float]] = {k: v for k, v in _DEFAULT_SLA_REFS_MS.items()}
    raw = os.getenv("CONGESTION_SLA_REFS_JSON", "").strip()
    if not raw:
        return merged
    try:
        user = json.loads(raw)
        if not isinstance(user, dict):
            return merged
        for key, val in user.items():
            if not isinstance(val, dict):
                continue
            if "delay_ref_ms" in val and "plr_ref" in val:
                merged[str(key)] = (
                    float(val["delay_ref_ms"]),
                    float(val["plr_ref"]),
                )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("CONGESTION_SLA_REFS_JSON invalid, using defaults: %s", e)
    return merged


def _sla_refs_for_profile(profile_key: str) -> Tuple[float, float]:
    """Return (delay_ref_ms, plr_ref) for pressure normalization for this resolved profile."""
    m = _load_sla_ref_map()
    k = (profile_key or "").strip() or "default"
    if k in m:
        return m[k]
    for cand, refs in m.items():
        if cand.lower() == k.lower():
            return refs
    return m["default"]


def compute_pressure_index(
    *,
    slice_id: str,
    plr: float,
    delay_ms: float,
    jitter_ms: float = 0.0,
    demand_mbps: Optional[float] = None,
    capacity_mbps: Optional[float] = None,
    mobility_stress: float = 0.0,
) -> Tuple[float, Dict[str, Any]]:
    """
    Weighted pressure 0–100 from KPIs. PLR as fraction (e.g. 0.001).

    ``slice_id`` must be the **slice-type profile key** (``\"1\"|\"2\"|\"3\"``, or names like
    ``eMBB`` / ``URLLC``), same as used for threshold bands: it selects both
    CONGESTION_THRESHOLDS_JSON pressure bands and SLA reference caps for delay/PLR scoring.
    """
    mobility_stress = _clamp(float(mobility_stress), 0.0, 1.0)

    th, profile_key = _thresholds_for_slice(slice_id)
    delay_ref_ms, plr_ref = _sla_refs_for_profile(profile_key)

    delay_score = _clamp(100.0 * (delay_ms / max(delay_ref_ms, 1e-6)))
    plr_score = _clamp(100.0 * (plr / max(plr_ref, 1e-15)))
    jitter_score = _clamp(100.0 * (jitter_ms / max(_JITTER_REF_MS, 1e-6))) if jitter_ms > 0 else 0.0

    rate_score = 0.0
    if (
        demand_mbps is not None
        and capacity_mbps is not None
        and capacity_mbps > 0
        and demand_mbps > 0
    ):
        ratio = demand_mbps / capacity_mbps
        if ratio > 1.0:
            rate_score = _clamp(100.0 * (ratio - 1.0))

    mob_score = 100.0 * mobility_stress

    pressure = (
        0.28 * delay_score
        + 0.28 * plr_score
        + 0.14 * jitter_score
        + 0.22 * rate_score
        + 0.08 * mob_score
    )
    pressure = _clamp(pressure)

    breakdown = {
        "delay_score": round(delay_score, 2),
        "plr_score": round(plr_score, 2),
        "jitter_score": round(jitter_score, 2),
        "rate_stress_score": round(rate_score, 2),
        "mobility_score": round(mob_score, 2),
        "pressure_index": round(pressure, 2),
        "threshold_profile": profile_key,
        "pressure_low_max": th["pressure_low_max"],
        "pressure_medium_max": th["pressure_medium_max"],
        "sla_delay_ref_ms": round(delay_ref_ms, 6),
        "sla_plr_ref": plr_ref,
        "sla_note": "delay/plr scores vs notebook SLA caps for this slice profile",
    }
    return pressure, breakdown


def pressure_to_label(
    pressure: float,
    *,
    pressure_low_max: float,
    pressure_medium_max: float,
) -> str:
    """Map pressure to congestion severity labels (notebook: Low / Medium / High)."""
    if pressure <= pressure_low_max:
        return "Low"
    if pressure <= pressure_medium_max:
        return "Medium"
    return "High"


def classify_congestion(
    delay_ms: float,
    plr: float,
    slice_id: str,
    *,
    jitter_ms: float = 0.0,
    demand_mbps: Optional[float] = None,
    capacity_mbps: Optional[float] = None,
    mobility_stress: float = 0.0,
) -> Tuple[str, float, Dict[str, Any]]:
    """
    Operational alias: classify congestion from KPIs and slice-type profile key.

    ``slice_id`` must identify the **slice profile** for both SLA normalization (delay/PLR
    reference caps) and pressure→label bands — use ``\"1\"|\"2\"|\"3\"``, or names
    ``eMBB`` / ``mMTC`` / ``URLLC``, or an id that contains those tokens (see
    ``_thresholds_for_slice``). It is not the opaque session ``slice_id`` from the API body.
    """
    return predict_congestion(
        slice_id=slice_id,
        plr=plr,
        delay_ms=delay_ms,
        jitter_ms=jitter_ms,
        demand_mbps=demand_mbps,
        capacity_mbps=capacity_mbps,
        mobility_stress=mobility_stress,
    )


def predict_congestion(
    *,
    slice_id: str,
    plr: float,
    delay_ms: float,
    jitter_ms: float = 0.0,
    demand_mbps: Optional[float] = None,
    capacity_mbps: Optional[float] = None,
    mobility_stress: float = 0.0,
) -> Tuple[str, float, Dict[str, Any]]:
    """
    Returns (congestion_level, pressure_index, detail dict).
    congestion_level ∈ {Low, Medium, High}.
    """
    pressure, breakdown = compute_pressure_index(
        slice_id=slice_id,
        plr=plr,
        delay_ms=delay_ms,
        jitter_ms=jitter_ms,
        demand_mbps=demand_mbps,
        capacity_mbps=capacity_mbps,
        mobility_stress=mobility_stress,
    )

    label = pressure_to_label(
        pressure,
        pressure_low_max=float(breakdown["pressure_low_max"]),
        pressure_medium_max=float(breakdown["pressure_medium_max"]),
    )

    detail: Dict[str, Any] = {
        "breakdown": breakdown,
        "labels_source": "rules",
    }
    return label, pressure, detail


def qos_from_pressure(pressure: float, plr: float) -> Tuple[float, float, float, str]:
    """
    Derive qos_score (0–1), p_sla_met, qos_risk_score, risk_tier from pressure and PLR.
    """
    plr_component = min(plr * 80.0, 1.0)
    qos_score = _clamp(
        1.0 - (pressure / 100.0) * 0.88 - 0.12 * plr_component,
        0.05,
        1.0,
    )
    qos_risk_score = round(1.0 - qos_score, 4)
    p_sla_met = round(qos_score, 4)

    if qos_risk_score < 0.2:
        risk_tier = "Low"
    elif qos_risk_score < 0.5:
        risk_tier = "Medium"
    else:
        risk_tier = "High"

    return round(qos_score, 4), p_sla_met, qos_risk_score, risk_tier
