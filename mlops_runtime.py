from __future__ import annotations

import hashlib
import json
import shutil
import time
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import os

LABELS = ("NORMAL", "WARNING", "CRITICAL")
FEATURE_COLUMNS = ["temperature", "current", "voltage", "esp_status"]
TARGET_COLUMN = "label"

MODELS_ROOT = Path("models")
CANDIDATES_DIR = MODELS_ROOT / "candidates"
POINTERS_DIR = MODELS_ROOT / "pointers"
POINTER_FILE = POINTERS_DIR / "stable.json"
PREDICTION_LOG_PATH = Path("logs") / "prediction_events.jsonl"


@dataclass
class ModelBundle:
    model: Any
    version: str
    manifest: dict[str, Any]
    model_path: Path
    manifest_path: Path | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ensure_dirs() -> None:
    CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)
    POINTERS_DIR.mkdir(parents=True, exist_ok=True)
    PREDICTION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()
    with file_path.open("rb") as source:
        for chunk in iter(lambda: source.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_input_hash(sample: dict[str, Any]) -> str:
    canonical = json.dumps(sample, sort_keys=True, separators=(",", ":"), default=str)
    return sha256_text(canonical)


def model_version_tag(prefix: str = "ev_model") -> str:
    return f"{prefix}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"


def label_mapping() -> dict[str, int]:
    return {label: index for index, label in enumerate(LABELS)}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def build_baseline_stats(df: pd.DataFrame) -> dict[str, Any]:
    numeric_stats: dict[str, Any] = {}
    for column in ["temperature", "current", "voltage"]:
        series = pd.to_numeric(df[column], errors="coerce").dropna()
        numeric_stats[column] = {
            "mean": float(series.mean()),
            "std": float(series.std(ddof=0) or 1e-6),
            "min": float(series.min()),
            "max": float(series.max()),
        }

    status_distribution = (
        df["esp_status"].astype(str).str.upper().value_counts(normalize=True).to_dict()
    )

    return {
        "numeric": numeric_stats,
        "categorical": {
            "esp_status": {key: float(value) for key, value in status_distribution.items()}
        },
    }


def detect_drift_alerts(sample: dict[str, Any], baseline_stats: dict[str, Any], z_threshold: float = 3.0) -> list[str]:
    alerts: list[str] = []
    numeric_baseline = baseline_stats.get("numeric", {})

    for feature in ["temperature", "current", "voltage"]:
        stats = numeric_baseline.get(feature)
        if not stats:
            continue
        value = _safe_float(sample.get(feature))
        mean = _safe_float(stats.get("mean"))
        std = max(_safe_float(stats.get("std")), 1e-6)
        z_score = abs((value - mean) / std)
        if z_score >= z_threshold:
            alerts.append(f"{feature}_zscore_{z_score:.2f}")

    status = str(sample.get("esp_status", "")).upper()
    status_distribution = baseline_stats.get("categorical", {}).get("esp_status", {})
    if status and status not in status_distribution:
        alerts.append("esp_status_unseen")

    return alerts


def explainability_payload(sample: dict[str, Any], feature_importances: dict[str, float]) -> dict[str, Any]:
    temperature = _safe_float(sample.get("temperature"))
    current = _safe_float(sample.get("current"))
    voltage = _safe_float(sample.get("voltage"))
    disconnected = str(sample.get("esp_status", "")).upper() == "DISCONNECTED"

    signal_scores = {
        "temperature": 1.0 if temperature > 33 else (0.65 if temperature >= 29 else max(temperature / 29.0, 0.0)),
        "current": 1.0 if current > 1.2 else (0.65 if current >= 1.0 else max(current / 1.0, 0.0)),
        "voltage": 1.0 if voltage < 3.5 else (0.66 if voltage <= 3.7 else max((3.95 - voltage) / 0.25, 0.0)),
        "esp_status": 0.85 if disconnected else 0.14,
    }

    weighted: dict[str, float] = {}
    for feature in FEATURE_COLUMNS:
        importance = _safe_float(feature_importances.get(feature, 0.25))
        weighted[feature] = signal_scores.get(feature, 0.0) * max(importance, 1e-4)

    total = sum(weighted.values()) or 1.0
    normalized = {feature: value / total for feature, value in weighted.items()}
    ranked = sorted(normalized.items(), key=lambda item: item[1], reverse=True)

    lead_feature, lead_value = ranked[0]
    return {
        "feature_contributions": {feature: round(value, 4) for feature, value in normalized.items()},
        "top_feature": lead_feature,
        "top_feature_score": round(lead_value, 4),
        "reason": f"{lead_feature} has strongest risk contribution",
    }


def _cap(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _reference_stats(
    feature: str,
    baseline_stats: dict[str, Any],
    recent_healthy_samples: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    recent_healthy_samples = recent_healthy_samples or []
    recent_values = [
        _safe_float(sample.get(feature))
        for sample in recent_healthy_samples
        if sample.get(feature) is not None
    ]

    if len(recent_values) >= 3:
        mean = float(statistics.fmean(recent_values))
        std = float(statistics.pstdev(recent_values)) if len(recent_values) > 1 else 1e-6
        return {
            "mean": mean,
            "std": max(std, 1e-6),
            "source": "recent_healthy_window",
        }

    numeric = baseline_stats.get("numeric", {}).get(feature, {})
    return {
        "mean": _safe_float(numeric.get("mean", 0.0)),
        "std": max(_safe_float(numeric.get("std", 1.0)), 1e-6),
        "source": "training_baseline",
    }


def build_adaptive_thresholds(
    sample: dict[str, Any],
    baseline_stats: dict[str, Any],
    recent_healthy_samples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    thresholds: dict[str, Any] = {}
    for feature in ["temperature", "current", "voltage"]:
        reference = _reference_stats(feature, baseline_stats, recent_healthy_samples)
        mean = float(reference["mean"])
        std = float(reference["std"])

        if feature == "temperature":
            warning = mean + max(std * 1.9, 1.4)
            critical = mean + max(std * 3.0, 2.6)
        elif feature == "current":
            warning = mean + max(std * 1.8, 0.08)
            critical = mean + max(std * 2.8, 0.16)
        else:
            warning = mean - max(std * 1.7, 0.08)
            critical = mean - max(std * 2.7, 0.16)

        thresholds[feature] = {
            **reference,
            "warning": round(float(warning), 4),
            "critical": round(float(critical), 4),
            "value": round(_safe_float(sample.get(feature)), 4),
        }

    status_distribution = baseline_stats.get("categorical", {}).get("esp_status", {})
    thresholds["esp_status"] = {
        "value": str(sample.get("esp_status", "")).upper(),
        "allowed": sorted(status_distribution.keys()),
        "warning": "DISCONNECTED",
        "critical": "DISCONNECTED",
        "source": "training_baseline",
    }
    thresholds["source"] = next(iter(thresholds.values())).get("source", "training_baseline")
    return thresholds


def classify_with_thresholds(sample: dict[str, Any], thresholds: dict[str, Any]) -> str:
    temperature = _safe_float(sample.get("temperature"))
    current = _safe_float(sample.get("current"))
    voltage = _safe_float(sample.get("voltage"))
    status = str(sample.get("esp_status", "")).upper()

    if (
        temperature >= _safe_float(thresholds.get("temperature", {}).get("critical"))
        or current >= _safe_float(thresholds.get("current", {}).get("critical"))
        or voltage <= _safe_float(thresholds.get("voltage", {}).get("critical"))
        or status == "DISCONNECTED"
    ):
        return "CRITICAL"

    if (
        temperature >= _safe_float(thresholds.get("temperature", {}).get("warning"))
        or current >= _safe_float(thresholds.get("current", {}).get("warning"))
        or voltage <= _safe_float(thresholds.get("voltage", {}).get("warning"))
    ):
        return "WARNING"

    return "NORMAL"


def detect_out_of_distribution(
    sample: dict[str, Any],
    thresholds: dict[str, Any],
    drift_alerts: list[str] | None = None,
) -> dict[str, Any]:
    drift_alerts = drift_alerts or []
    components: dict[str, float] = {}

    for feature in ["temperature", "current", "voltage"]:
        reference = thresholds.get(feature, {})
        mean = _safe_float(reference.get("mean"))
        std = max(_safe_float(reference.get("std", 1.0)), 1e-6)
        value = _safe_float(sample.get(feature))
        components[feature] = abs((value - mean) / std)

    status = str(sample.get("esp_status", "")).upper()
    unseen_status = status not in set(thresholds.get("esp_status", {}).get("allowed", []))

    max_z = max(components.values()) if components else 0.0
    score = _cap(round(max_z * 21.0 + len(drift_alerts) * 10.0 + (18.0 if unseen_status else 0.0)), 0, 100)
    flagged = score >= 55 or unseen_status

    return {
        "score": int(score),
        "flagged": flagged,
        "max_zscore": round(float(max_z), 3),
        "components": {key: round(value, 3) for key, value in components.items()},
        "reason": "OOD profile differs from training baseline" if flagged else "Within expected operating envelope",
        "status_unseen": unseen_status,
    }


def diagnose_sensor_fault(
    sample: dict[str, Any],
    drift_alerts: list[str],
    out_of_distribution: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    status = str(sample.get("esp_status", "")).upper()
    temperature_alerts = [item for item in drift_alerts if item.startswith("temperature_")]
    current_alerts = [item for item in drift_alerts if item.startswith("current_")]
    voltage_alerts = [item for item in drift_alerts if item.startswith("voltage_")]

    if status != "CONNECTED" or out_of_distribution.get("status_unseen"):
        label = "communication_corruption"
        reason = "Telemetry stream looks corrupted or disconnected"
    elif len(temperature_alerts) + len(current_alerts) + len(voltage_alerts) >= 2 and out_of_distribution.get("score", 0) >= 60:
        label = "battery_issue"
        reason = "Multiple sensors drift together, which points to pack-level stress"
    elif len(temperature_alerts) + len(current_alerts) + len(voltage_alerts) == 1 and confidence < 0.78:
        label = "sensor_noise"
        reason = "Only one signal is unstable, which is consistent with noisy telemetry"
    elif out_of_distribution.get("score", 0) >= 70:
        label = "battery_issue"
        reason = "Incoming pattern is unlike the training distribution"
    else:
        label = "battery_issue"
        reason = "Trend is consistent with pack stress rather than isolated sensor noise"

    return {
        "label": label,
        "reason": reason,
        "confidence": round(float(confidence), 4),
    }


def choose_recovery_action(
    sensor_fault: dict[str, Any],
    out_of_distribution: dict[str, Any],
    ensemble_prediction: str,
) -> dict[str, Any]:
    diagnosis = sensor_fault.get("label", "battery_issue")
    ood_score = int(out_of_distribution.get("score", 0))

    if diagnosis == "communication_corruption":
        action = "reconnect"
        rationale = "Restore the telemetry link before trusting the stream"
    elif diagnosis == "sensor_noise":
        action = "smooth"
        rationale = "Apply smoothing and ignore the isolated noisy channel"
    elif ensemble_prediction == "CRITICAL" or ood_score >= 75:
        action = "fallback_model"
        rationale = "Switch to the robust fallback model while the pack is unstable"
    else:
        action = "isolate_sensor"
        rationale = "Quarantine the questionable sensor and continue monitoring the remaining signals"

    return {
        "action": action,
        "rationale": rationale,
    }


def compute_priority_2_intelligence(
    sample: dict[str, Any],
    baseline_stats: dict[str, Any],
    recent_healthy_samples: list[dict[str, Any]] | None,
    model_prediction: str,
    confidence: float,
    drift_alerts: list[str],
) -> dict[str, Any]:
    thresholds = build_adaptive_thresholds(sample, baseline_stats, recent_healthy_samples)
    adaptive_prediction = classify_with_thresholds(sample, thresholds)
    out_of_distribution = detect_out_of_distribution(sample, thresholds, drift_alerts)
    sensor_fault = diagnose_sensor_fault(sample, drift_alerts, out_of_distribution, confidence)

    model_score = {"NORMAL": 18.0, "WARNING": 58.0, "CRITICAL": 88.0}.get(model_prediction, 50.0)
    rule_score = {"NORMAL": 16.0, "WARNING": 54.0, "CRITICAL": 92.0}.get(adaptive_prediction, 50.0)
    anomaly_score = _cap(18.0 + len(drift_alerts) * 14.0 + out_of_distribution["score"] * 0.45, 0, 100)
    confidence_penalty = _cap((1.0 - _cap(confidence, 0.0, 1.0)) * 22.0, 0, 22)

    ensemble_score = _cap(
        round(model_score * 0.38 + rule_score * 0.34 + anomaly_score * 0.28 + confidence_penalty),
        0,
        100,
    )
    if ensemble_score >= 70:
        ensemble_prediction = "CRITICAL"
    elif ensemble_score >= 40:
        ensemble_prediction = "WARNING"
    else:
        ensemble_prediction = "NORMAL"

    recovery = choose_recovery_action(sensor_fault, out_of_distribution, ensemble_prediction)
    summary = (
        f"Adaptive baseline source: {thresholds['source']}. "
        f"Fault diagnosis: {sensor_fault['label']}. "
        f"Recovery action: {recovery['action']}."
    )

    return {
        "adaptive_thresholds": thresholds,
        "adaptive_prediction": adaptive_prediction,
        "sensor_fault": sensor_fault,
        "out_of_distribution": out_of_distribution,
        "ensemble_prediction": ensemble_prediction,
        "ensemble_score": int(ensemble_score),
        "recovery_policy": recovery,
        "priority_2_summary": summary,
    }


def _trend_from_samples(samples: list[dict[str, Any]] | None, feature: str) -> float:
    values = [
        _safe_float(sample.get(feature))
        for sample in (samples or [])
        if sample.get(feature) is not None
    ]
    if len(values) < 2:
        return 0.0
    recent = values[-6:]
    return (recent[-1] - recent[0]) / max(1, len(recent) - 1)


def _score_profile(
    temperature: float,
    current: float,
    voltage: float,
    status: str,
    temperature_trend: float = 0.0,
    current_trend: float = 0.0,
    voltage_trend: float = 0.0,
) -> tuple[int, dict[str, float]]:
    thermal = _cap((temperature - 25.0) * 4.0 + max(0.0, temperature_trend) * 18.0, 0, 100)
    electrical = _cap((current - 0.7) * 60.0 + max(0.0, current_trend) * 140.0, 0, 100)
    voltage_risk = _cap((3.95 - voltage) * 130.0 + max(0.0, -voltage_trend) * 170.0, 0, 100)
    status_penalty = 18.0 if str(status).upper() != "CONNECTED" else 0.0
    score = _cap(round(thermal * 0.38 + electrical * 0.34 + voltage_risk * 0.28 + status_penalty), 0, 100)
    components = {
        "thermal": round(float(thermal), 3),
        "electrical": round(float(electrical), 3),
        "voltage": round(float(voltage_risk), 3),
    }
    return int(score), components


def _project_scenario(
    sample: dict[str, Any],
    thresholds: dict[str, Any],
    name: str,
    temperature_delta: float = 0.0,
    current_delta: float = 0.0,
    voltage_delta: float = 0.0,
    status_override: str | None = None,
) -> dict[str, Any]:
    projected = dict(sample)
    projected["temperature"] = _safe_float(sample.get("temperature")) + temperature_delta
    projected["current"] = _safe_float(sample.get("current")) + current_delta
    projected["voltage"] = _safe_float(sample.get("voltage")) + voltage_delta
    if status_override is not None:
        projected["esp_status"] = status_override

    prediction = classify_with_thresholds(projected, thresholds)
    score, components = _score_profile(
        projected["temperature"],
        projected["current"],
        projected["voltage"],
        projected.get("esp_status", sample.get("esp_status", "CONNECTED")),
    )

    return {
        "name": name,
        "temperature": round(float(projected["temperature"]), 2),
        "current": round(float(projected["current"]), 3),
        "voltage": round(float(projected["voltage"]), 3),
        "prediction": prediction,
        "risk_score": score,
        "components": components,
    }


def _reference_vector(
    sample: dict[str, Any],
    baseline_stats: dict[str, Any],
    recent_healthy_samples: list[dict[str, Any]] | None,
) -> dict[str, float]:
    recent_healthy_samples = recent_healthy_samples or []

    def reference_value(feature: str) -> float:
        values = [
            _safe_float(item.get(feature))
            for item in recent_healthy_samples
            if item.get(feature) is not None
        ]
        if len(values) >= 3:
            return float(statistics.fmean(values))
        return _safe_float(baseline_stats.get("numeric", {}).get(feature, {}).get("mean", sample.get(feature, 0.0)))

    return {
        "temperature": reference_value("temperature"),
        "current": reference_value("current"),
        "voltage": reference_value("voltage"),
    }


def compute_priority_3_intelligence(
    sample: dict[str, Any],
    baseline_stats: dict[str, Any],
    recent_healthy_samples: list[dict[str, Any]] | None,
    drift_alerts: list[str],
    confidence: float,
    priority_2: dict[str, Any],
    ensemble_prediction: str,
) -> dict[str, Any]:
    thresholds = priority_2.get("adaptive_thresholds", {})
    out_of_distribution = priority_2.get("out_of_distribution", {})
    adaptive_prediction = priority_2.get("adaptive_prediction", "WARNING")

    temp_trend = _trend_from_samples(recent_healthy_samples, "temperature")
    current_trend = _trend_from_samples(recent_healthy_samples, "current")
    voltage_trend = _trend_from_samples(recent_healthy_samples, "voltage")

    base_score, components = _score_profile(
        _safe_float(sample.get("temperature")),
        _safe_float(sample.get("current")),
        _safe_float(sample.get("voltage")),
        sample.get("esp_status", "CONNECTED"),
        temp_trend,
        current_trend,
        voltage_trend,
    )

    confidence_factor = _cap(float(confidence), 0.0, 1.0)
    health_index = int(_cap(round(100 - base_score * 0.72 + confidence_factor * 10), 0, 100))
    rul_minutes = int(
        _cap(
            round(
                12.0
                + (100 - base_score) * 0.55
                - max(0.0, temp_trend) * 24.0
                - max(0.0, current_trend) * 30.0
                - max(0.0, -voltage_trend) * 36.0
                + confidence_factor * 8.0
            ),
            4,
            240,
        )
    )
    rul_cycles = int(_cap(round(rul_minutes * 1.8), 8, 520))

    reference = _reference_vector(sample, baseline_stats, recent_healthy_samples)
    observed_gap = _cap(
        abs(_safe_float(sample.get("temperature")) - reference["temperature"]) * 2.2
        + abs(_safe_float(sample.get("current")) - reference["current"]) * 28.0
        + abs(_safe_float(sample.get("voltage")) - reference["voltage"]) * 34.0,
        0,
        100,
    )
    digital_twin_alignment = int(_cap(round(100 - observed_gap), 0, 100))

    scenarios = [
        _project_scenario(sample, thresholds, "+8 C thermal burst", temperature_delta=8.0),
        _project_scenario(sample, thresholds, "high current burst", current_delta=0.45, voltage_delta=-0.06),
        _project_scenario(sample, thresholds, "voltage sag", voltage_delta=-0.22),
        _project_scenario(sample, thresholds, "combined stress", temperature_delta=4.0, current_delta=0.28, voltage_delta=-0.12),
    ]

    fleet_profiles = [
        {"name": "Vehicle 01 - current pack", "temperature_delta": 0.0, "current_delta": 0.0, "voltage_delta": 0.0},
        {"name": "Vehicle 02 - thermal hot spot", "temperature_delta": 4.5, "current_delta": 0.12, "voltage_delta": -0.05},
        {"name": "Vehicle 03 - load burst", "temperature_delta": 1.2, "current_delta": 0.52, "voltage_delta": -0.14},
        {"name": "Vehicle 04 - communication risk", "temperature_delta": 0.7, "current_delta": 0.04, "voltage_delta": -0.02, "status_override": "DISCONNECTED"},
    ]
    fleet_rankings = [
        _project_scenario(
            sample,
            thresholds,
            profile["name"],
            temperature_delta=profile.get("temperature_delta", 0.0),
            current_delta=profile.get("current_delta", 0.0),
            voltage_delta=profile.get("voltage_delta", 0.0),
            status_override=profile.get("status_override"),
        )
        for profile in fleet_profiles
    ]
    fleet_rankings.sort(key=lambda item: item["risk_score"], reverse=True)

    drift_inputs = len(drift_alerts) * 13 + (22 if out_of_distribution.get("flagged") else 0) + max(0, 100 - digital_twin_alignment) * 0.35
    retrain_score = int(_cap(round(drift_inputs), 0, 100))
    retrain_recommended = retrain_score >= 60 or adaptive_prediction == "CRITICAL"
    retrain_reason = (
        f"Drift score {retrain_score}/100 with alignment {digital_twin_alignment}% and OOD score {out_of_distribution.get('score', 0)}"
    )

    return {
        "rul_forecast": {
            "minutes": rul_minutes,
            "cycles": rul_cycles,
            "health_index": health_index,
            "confidence": round(confidence_factor, 4),
        },
        "what_if_scenarios": scenarios,
        "digital_twin": {
            "expected": reference,
            "observed": {
                "temperature": round(_safe_float(sample.get("temperature")), 2),
                "current": round(_safe_float(sample.get("current")), 3),
                "voltage": round(_safe_float(sample.get("voltage")), 3),
            },
            "alignment": digital_twin_alignment,
            "drift_gap": round(float(observed_gap), 2),
            "narrative": (
                f"Twin alignment is {digital_twin_alignment}% against the expected healthy baseline."
            ),
        },
        "drift_monitoring": {
            "drift_score": retrain_score,
            "retrain_recommended": retrain_recommended,
            "reason": retrain_reason,
            "adaptive_prediction": adaptive_prediction,
            "ensemble_prediction": ensemble_prediction,
            "adaptive_threshold_source": priority_2.get("adaptive_thresholds", {}).get("source", "training_baseline"),
        },
        "fleet_intelligence": {
            "mode": "synthetic_demo",
            "rankings": fleet_rankings,
            "top_asset": fleet_rankings[0]["name"] if fleet_rankings else "-",
        },
        "priority_3_summary": (
            f"RUL {rul_minutes} min / {rul_cycles} cycles; twin alignment {digital_twin_alignment}%; "
            f"drift score {retrain_score}/100; fleet top risk {fleet_rankings[0]['name'] if fleet_rankings else '-'}"
        ),
    }


def pointer_payload(stable_model_path: str, previous_model_path: str | None) -> dict[str, Any]:
    return {
        "stable_model_path": stable_model_path,
        "previous_model_path": previous_model_path,
        "updated_at": utc_now_iso(),
    }


def read_pointer() -> dict[str, Any] | None:
    if not POINTER_FILE.exists():
        return None
    return json.loads(POINTER_FILE.read_text(encoding="utf-8"))


def write_pointer(payload: dict[str, Any]) -> None:
    ensure_dirs()
    POINTER_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_manifest_for_model(model_path: Path) -> tuple[dict[str, Any] | None, Path | None]:
    manifest_path = model_path.parent / "manifest.json"
    if manifest_path.exists():
        return json.loads(manifest_path.read_text(encoding="utf-8")), manifest_path
    return None, None


def resolve_model_path(requested_model_path: str | None) -> Path:
    if requested_model_path:
        requested = Path(requested_model_path)
        if requested.exists():
            return requested

        candidate = Path("models") / "candidates" / requested.parent.name / "model.joblib"
        if candidate.exists():
            return candidate

    pointer = read_pointer()
    if pointer and pointer.get("stable_model_path"):
        pointer_path = Path(pointer["stable_model_path"])
        if pointer_path.exists():
            return pointer_path

        candidate = Path("models") / "candidates" / pointer_path.parent.name / "model.joblib"
        if candidate.exists():
            return candidate

    candidate_models = sorted(
        (Path("models") / "candidates").glob("*/model.joblib"),
        key=lambda model_file: model_file.stat().st_mtime,
        reverse=True,
    )
    if candidate_models:
        return candidate_models[0]

    return Path("ev_risk_model.joblib")


def load_model_bundle(requested_model_path: str | None = None) -> ModelBundle:
    model_path = resolve_model_path(requested_model_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")

    model = joblib.load(model_path)
    manifest, manifest_path = read_manifest_for_model(model_path)

    version = "legacy"
    if manifest and manifest.get("model", {}).get("version"):
        version = str(manifest["model"]["version"])

    return ModelBundle(
        model=model,
        version=version,
        manifest=manifest or {},
        model_path=model_path,
        manifest_path=manifest_path,
    )


def get_feature_importance_map(model: Any, feature_columns: list[str] | None = None) -> dict[str, float]:
    feature_columns = feature_columns or FEATURE_COLUMNS
    estimator = model
    if hasattr(model, "named_steps") and "model" in model.named_steps:
        estimator = model.named_steps["model"]

    if hasattr(estimator, "feature_importances_"):
        importances = estimator.feature_importances_
        if len(importances) >= len(feature_columns):
            sliced = importances[: len(feature_columns)]
            total = float(sum(sliced)) or 1.0
            return {
                feature: float(value / total)
                for feature, value in zip(feature_columns, sliced, strict=False)
            }

    uniform = 1.0 / max(len(feature_columns), 1)
    return {feature: uniform for feature in feature_columns}


def confidence_and_label(model: Any, feature_row: pd.DataFrame) -> tuple[str, float, float]:
    start = time.perf_counter()
    prediction = str(model.predict(feature_row)[0]).upper()

    confidence = 0.5
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(feature_row)
        if len(proba) > 0:
            confidence = float(max(proba[0]))

    latency_ms = (time.perf_counter() - start) * 1000.0
    return prediction, confidence, latency_ms


def append_prediction_log(event: dict[str, Any], log_path: Path | None = None) -> None:
    target = log_path or PREDICTION_LOG_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(event, default=str) + "\n")


def append_signed_prediction_log(event: dict[str, Any], log_path: Path | None = None, secret: str | None = None) -> None:
    """Append a tamper-evident signed prediction event using a chained hash.

    The signature is computed as sha256(json_canonical + previous_signature + secret).
    Stores events in a dedicated signed log file to avoid interfering with the existing
    plain prediction log.
    """
    target = Path(log_path) if log_path else Path("logs") / "signed_prediction_events.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)

    # Load previous signature if available
    prev_sig = ""
    try:
        if target.exists():
            with target.open("rb") as f:
                try:
                    # Seek from end and read last line
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    if size == 0:
                        prev_sig = ""
                    else:
                        offset = min(size, 4096)
                        f.seek(-offset, os.SEEK_END)
                        tail = f.read().decode("utf-8", errors="ignore")
                        last_line = tail.strip().splitlines()[-1]
                        try:
                            last_obj = json.loads(last_line)
                            prev_sig = str(last_obj.get("signature", ""))
                        except Exception:
                            prev_sig = ""
                except OSError:
                    prev_sig = ""
    except Exception:
        prev_sig = ""

    canonical = json.dumps(event, sort_keys=True, separators=(",", ":"), default=str)
    secret_val = secret or os.environ.get("PREDICTION_LOG_SECRET", "dev-secret")
    signature = sha256_text(canonical + prev_sig + secret_val)

    signed = dict(event)
    signed["signature"] = signature
    signed["prev_signature"] = prev_sig

    with target.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(signed, default=str) + "\n")


def append_eval_event(event: dict[str, Any], log_path: Path | None = None) -> None:
    """Append a lightweight evaluation event used for online metrics and bias checks."""
    target = Path(log_path) if log_path else Path("logs") / "eval_events.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as sink:
        sink.write(json.dumps(event, default=str) + "\n")


def compute_eval_summary(log_path: Path | None = None, last_n: int | None = 1000) -> dict[str, Any]:
    target = Path(log_path) if log_path else Path("logs") / "eval_events.jsonl"
    if not target.exists():
        return {"count": 0, "models": {}, "latency_ms_avg": 0.0}

    events = []
    with target.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue

    if last_n:
        events = events[-last_n:]

    summary: dict[str, Any] = {"count": len(events), "models": {}, "latency_ms_avg": 0.0}
    total_latency = 0.0
    for ev in events:
        mv = str(ev.get("model_version", "legacy"))
        m = summary["models"].setdefault(mv, {"count": 0, "latency_total_ms": 0.0})
        m["count"] += 1
        latency = float(ev.get("latency_ms", 0.0) or 0.0)
        m["latency_total_ms"] += latency
        total_latency += latency

    for mv, m in summary["models"].items():
        m["latency_avg_ms"] = m["latency_total_ms"] / max(1, m["count"])
        del m["latency_total_ms"]

    summary["latency_ms_avg"] = total_latency / max(1, len(events)) if events else 0.0
    return summary


def compute_bias_breakdown(log_path: Path | None = None, segment_key: str = "fleet_id") -> dict[str, Any]:
    """Compute per-segment counts and simple statistics from eval events.

    If `segment_key` is missing in events, falls back to grouping by `device_id`.
    """
    target = Path(log_path) if log_path else Path("logs") / "eval_events.jsonl"
    if not target.exists():
        return {"segments": {}, "message": "No eval events found"}

    events = []
    with target.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                events.append(json.loads(line))
            except Exception:
                continue

    segments: dict[str, dict[str, Any]] = {}
    for ev in events:
        seg = ev.get(segment_key) or ev.get("device_id") or "unknown"
        segs = segments.setdefault(str(seg), {"count": 0, "latency_total_ms": 0.0})
        segs["count"] += 1
        segs["latency_total_ms"] += float(ev.get("latency_ms", 0.0) or 0.0)

    for k, v in segments.items():
        v["latency_avg_ms"] = v["latency_total_ms"] / max(1, v["count"])
        del v["latency_total_ms"]

    return {"segments": segments}


def evaluate_threshold(metric_name: str, candidate_value: float, baseline_value: float, max_drop: float) -> tuple[bool, str]:
    allowed_floor = baseline_value - max_drop
    passed = candidate_value >= allowed_floor
    reason = (
        f"{metric_name}: candidate={candidate_value:.4f}, baseline={baseline_value:.4f}, "
        f"allowed_floor={allowed_floor:.4f}"
    )
    return passed, reason


def promote_candidate(candidate_dir: Path, max_metric_drop: float = 0.01) -> dict[str, Any]:
    ensure_dirs()

    manifest_path = candidate_dir / "manifest.json"
    model_path = candidate_dir / "model.joblib"
    if not manifest_path.exists() or not model_path.exists():
        raise FileNotFoundError(f"Candidate artifacts missing in {candidate_dir}")

    candidate_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_metrics = candidate_manifest.get("metrics", {})
    candidate_accuracy = float(candidate_metrics.get("accuracy", 0.0))
    candidate_macro_f1 = float(candidate_metrics.get("macro_f1", 0.0))

    pointer = read_pointer() or {}
    previous_stable_path = pointer.get("stable_model_path")

    checks: list[dict[str, Any]] = []
    can_promote = True

    if previous_stable_path:
        stable_manifest, _ = read_manifest_for_model(Path(previous_stable_path))
        if stable_manifest:
            stable_metrics = stable_manifest.get("metrics", {})
            stable_accuracy = float(stable_metrics.get("accuracy", 0.0))
            stable_macro_f1 = float(stable_metrics.get("macro_f1", 0.0))

            accuracy_pass, accuracy_reason = evaluate_threshold(
                "accuracy", candidate_accuracy, stable_accuracy, max_metric_drop
            )
            macro_pass, macro_reason = evaluate_threshold(
                "macro_f1", candidate_macro_f1, stable_macro_f1, max_metric_drop
            )
            checks.extend(
                [
                    {"metric": "accuracy", "passed": accuracy_pass, "reason": accuracy_reason},
                    {"metric": "macro_f1", "passed": macro_pass, "reason": macro_reason},
                ]
            )
            can_promote = accuracy_pass and macro_pass

    if can_promote:
        new_payload = pointer_payload(
            stable_model_path=str(model_path.resolve()),
            previous_model_path=previous_stable_path,
        )
        write_pointer(new_payload)

        # Keep root model file updated for backward compatibility.
        shutil.copy2(model_path, Path("ev_risk_model.joblib"))

    return {
        "promoted": can_promote,
        "candidate_dir": str(candidate_dir),
        "checks": checks,
        "pointer": read_pointer(),
    }


def rollback_to_previous() -> dict[str, Any]:
    pointer = read_pointer()
    if not pointer:
        raise RuntimeError("No pointer state found for rollback")

    previous_path = pointer.get("previous_model_path")
    if not previous_path:
        raise RuntimeError("No previous stable model available for rollback")

    current_stable = pointer.get("stable_model_path")
    rollback_payload = pointer_payload(
        stable_model_path=previous_path,
        previous_model_path=current_stable,
    )
    write_pointer(rollback_payload)

    previous_model = Path(previous_path)
    if previous_model.exists():
        shutil.copy2(previous_model, Path("ev_risk_model.joblib"))

    return {"rolled_back": True, "pointer": read_pointer()}
