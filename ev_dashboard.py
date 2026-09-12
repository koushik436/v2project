import argparse
import logging
import os
import math
import random
import socket
import threading
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import load_dotenv

import pandas as pd
import serial
import json
from flask import Flask, jsonify, request, send_from_directory

# Load environment variables from .env file
load_dotenv()

from mlops_runtime import (
    append_prediction_log,
    append_signed_prediction_log,
    append_eval_event,
    canonical_input_hash,
    confidence_and_label,
    compute_priority_2_intelligence,
    compute_priority_3_intelligence,
    detect_drift_alerts,
    explainability_payload,
    get_feature_importance_map,
    load_model_bundle,
    promote_candidate,
    read_pointer,
    rollback_to_previous,
    compute_eval_summary,
    compute_bias_breakdown,
    utc_now_iso,
)

WEB_DIR = Path(__file__).resolve().parent / "web"
WEB_BUILD_DIR = WEB_DIR / "dist"

logger = logging.getLogger("ev_dashboard")


def get_web_root() -> Path:
    if (WEB_BUILD_DIR / "index.html").exists():
        return WEB_BUILD_DIR
    return WEB_DIR

STATUS_ALLOWED = {"CONNECTED", "DISCONNECTED"}
TEMPERATURE_RANGE = (-40.0, 125.0)
CURRENT_RANGE = (-5.0, 5.0)
VOLTAGE_RANGE = (0.0, 100.0)


def fnv1a32(text: str) -> int:
    hash_value = 2166136261
    for byte in text.encode("utf-8", errors="ignore"):
        hash_value ^= byte
        hash_value = (hash_value * 16777619) & 0xFFFFFFFF
    return hash_value


def validate_ranges(temperature: float, current: float, voltage: float, status: str) -> None:
    if not (TEMPERATURE_RANGE[0] <= temperature <= TEMPERATURE_RANGE[1]):
        raise ValueError(f"Temperature out of range: {temperature}")
    if not (CURRENT_RANGE[0] <= current <= CURRENT_RANGE[1]):
        raise ValueError(f"Current out of range: {current}")
    if not (VOLTAGE_RANGE[0] <= voltage <= VOLTAGE_RANGE[1]):
        raise ValueError(f"Voltage out of range: {voltage}")

    normalized_status = status.upper()
    if normalized_status not in STATUS_ALLOWED:
        raise ValueError(f"Unexpected status: {status}")


def parse_serial_line(line: str):
    if line.startswith("V2|"):
        return parse_v2_payload(line)

    if line.startswith("Temp:") or "Temp:" in line and "Voltage:" in line and "Current:" in line and "Status:" in line:
        return parse_pretty_payload(line)

    return parse_legacy_csv(line)


def parse_pretty_payload(line: str):
    parts = [segment.strip() for segment in line.split("|")]
    if len(parts) != 4:
        raise ValueError(f"Expected 4 fields for pretty payload, got {len(parts)}")

    def parse_field(text: str, prefix: str, suffix: Optional[str] = None) -> str:
        if not text.startswith(prefix):
            raise ValueError(f"Expected prefix '{prefix}' in '{text}'")
        value = text[len(prefix):].strip()
        if suffix:
            if not value.endswith(suffix):
                raise ValueError(f"Expected suffix '{suffix}' in '{text}'")
            value = value[: -len(suffix)].strip()
        return value

    temperature = float(parse_field(parts[0], "Temp:", "C"))
    voltage = float(parse_field(parts[1], "Voltage:", "V"))
    current = float(parse_field(parts[2], "Current:", "A"))
    status = parse_field(parts[3], "Status:").upper()

    validate_ranges(temperature, current, voltage, status)

    return {
        "temperature": temperature,
        "current": current,
        "voltage": voltage,
        "esp_status": status,
        "device_id": "legacy",
        "sequence_number": None,
        "relay_state": "-",
        "fail_safe": False,
    }


def parse_legacy_csv(line: str):
    parts = [segment.strip() for segment in line.split(",")]
    if len(parts) != 4:
        raise ValueError(f"Expected 4 fields, got {len(parts)}")

    temperature = float(parts[0])
    current = float(parts[1])
    voltage = float(parts[2])
    status = parts[3].upper()

    validate_ranges(temperature, current, voltage, status)

    return {
        "temperature": temperature,
        "current": current,
        "voltage": voltage,
        "esp_status": status,
        "device_id": "legacy",
        "sequence_number": None,
        "relay_state": "-",
        "fail_safe": False,
    }


def parse_v2_payload(line: str):
    parts = [segment.strip() for segment in line.split("|")]
    if len(parts) != 12:
        raise ValueError(f"Expected 12 fields for v2 payload, got {len(parts)}")
    if parts[0] != "V2":
        raise ValueError(f"Invalid v2 prefix: {parts[0]}")

    body, crc_hex = line.rsplit("|", maxsplit=1)
    expected_crc = fnv1a32(body)
    try:
        received_crc = int(crc_hex, 16)
    except ValueError as exc:
        raise ValueError(f"Invalid CRC hex: {crc_hex}") from exc

    if expected_crc != received_crc:
        raise ValueError("CRC mismatch")

    temperature = float(parts[5])
    current = float(parts[6])
    voltage = float(parts[7])
    status = parts[8].upper()

    validate_ranges(temperature, current, voltage, status)

    return {
        "temperature": temperature,
        "current": current,
        "voltage": voltage,
        "esp_status": status,
        "device_id": parts[1],
        "sequence_number": int(parts[3]),
        "relay_state": parts[9].upper(),
        "fail_safe": parts[10] == "1",
    }


def build_feature_row(temperature: float, current: float, voltage: float, esp_status: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "temperature": temperature,
                "current": current,
                "voltage": voltage,
                "esp_status": esp_status,
            }
        ]
    )


def classify_rule_based(sample: dict) -> str:
    temp = float(sample.get("temperature", 0.0))
    current = float(sample.get("current", 0.0))
    voltage = float(sample.get("voltage", 0.0))
    status = str(sample.get("esp_status", "CONNECTED")).upper()

    if temp > 33.0 or current > 1.2 or voltage < 3.5:
        return "CRITICAL"
    if (29.0 <= temp <= 33.0) or current >= 1.0 or voltage <= 3.7 or status == "DISCONNECTED":
        return "WARNING"
    return "NORMAL"


def build_demo_sample(elapsed_seconds: float, sequence: int) -> Tuple[Optional[dict], str]:
    if elapsed_seconds < 30:
        # Phase 1: NORMAL, but close to the live range around 33-34.5°C
        return {
            "temperature": 33.5 + math.sin(elapsed_seconds / 6.5) * 0.45,
            "current": 0.12 + math.sin(elapsed_seconds / 3.8) * 0.06,
            "voltage": 0.65 + math.sin(elapsed_seconds / 5.0) * 0.22,
            "esp_status": "CONNECTED",
            "device_id": "demo",
            "sequence_number": sequence,
            "relay_state": "ON",
            "fail_safe": False,
        }, "NORMAL"

    if elapsed_seconds < 65:
        # Phase 2: WARNING and a deterministic malformed packet rehearsal at 40s.
        if 40 <= elapsed_seconds < 41:
            return None, "MALFORMED"
        return {
            "temperature": 33.8 + math.sin(elapsed_seconds / 4.2) * 0.35,
            "current": 0.14 + math.sin(elapsed_seconds / 3.2) * 0.04,
            "voltage": 0.55 + math.sin(elapsed_seconds / 3.5) * 0.28,
            "esp_status": "DISCONNECTED",
            "device_id": "demo",
            "sequence_number": sequence,
            "relay_state": "OFF",
            "fail_safe": False,
        }, "WARNING"

    if elapsed_seconds < 100:
        # Phase 3: CRITICAL with unplug/disconnect and spike rehearsals.
        if 76 <= elapsed_seconds < 80:
            return None, "DISCONNECT"
        if 88 <= elapsed_seconds < 90:
            return {
                "temperature": 34.8,
                "current": 0.18,
                "voltage": 0.30,
                "esp_status": "DISCONNECTED",
                "device_id": "demo",
                "sequence_number": sequence,
                "relay_state": "OFF",
                "fail_safe": True,
            }, "SPIKE"
        return {
            "temperature": 34.3 + math.sin(elapsed_seconds / 2.4) * 0.25,
            "current": 0.15 + math.sin(elapsed_seconds / 2.6) * 0.05,
            "voltage": 0.65 + math.sin(elapsed_seconds / 2.9) * 0.22,
            "esp_status": "DISCONNECTED",
            "device_id": "demo",
            "sequence_number": sequence,
            "relay_state": "OFF",
            "fail_safe": True,
        }, "CRITICAL"

    # Phase 4: RECOVERY
    return {
        "temperature": 33.4 + math.sin(elapsed_seconds / 5.5) * 0.35,
        "current": 0.10 + math.sin(elapsed_seconds / 4.6) * 0.05,
        "voltage": 0.72 + math.sin(elapsed_seconds / 5.8) * 0.20,
        "esp_status": "CONNECTED",
        "device_id": "demo",
        "sequence_number": sequence,
        "relay_state": "ON",
        "fail_safe": False,
    }, "RECOVERY"


def update_connection_health(state: dict, stale_after: float) -> None:
    last_packet_monotonic = state.get("last_packet_monotonic")
    if last_packet_monotonic is None:
        state["last_packet_age_seconds"] = None
        return

    age = time.monotonic() - last_packet_monotonic
    state["last_packet_age_seconds"] = round(age, 2)
    if age >= stale_after and state.get("connection") == "connected":
        state["connection"] = "stale"
        state["data_status"] = "stale"
        state["message"] = f"No valid packets for {stale_after:.1f}s"


def apply_fault_injection(state: dict, sample: Optional[dict]) -> Tuple[Optional[dict], bool]:
    fault = state.get("fault_inject")
    if not fault:
        return sample, False

    fault_type = fault.get("type", "").lower()
    if fault_type == "disconnect":
        state["connection"] = "disconnected"
        state["data_status"] = "degraded"
        state["message"] = "Fault rehearsal: serial disconnect simulated"
        state["fault_inject"] = None
        return None, True

    if fault_type == "malformed":
        state["parse_errors"] = state.get("parse_errors", 0) + 1
        state["data_status"] = "degraded"
        state["message"] = "Fault rehearsal: malformed packet ignored"
        state["fault_inject"] = None
        return None, True

    if fault_type == "spike" and sample is not None:
        sample["temperature"] = 43.0
        sample["current"] = 2.0
        sample["voltage"] = 3.0
        sample["esp_status"] = "DISCONNECTED"
        sample["relay_state"] = "OFF"
        sample["fail_safe"] = True
        state["message"] = "Fault rehearsal: sudden sensor spike injected"
        state["fault_inject"] = None
        return sample, True

    return sample, False


def process_sample(
    sample: dict,
    state: dict,
    primary_bundle,
    shadow_bundle,
    feature_importances: dict,
    baseline_stats: dict,
    started_monotonic: float,
) -> None:
    feature_row = build_feature_row(
        sample["temperature"],
        sample["current"],
        sample["voltage"],
        sample["esp_status"],
    )

    state["inference_count"] = state.get("inference_count", 0) + 1

    model_failed = False
    confidence = 0.0
    latency_ms = 0.0
    model_prediction = "WARNING"

    try:
        model_prediction, confidence, latency_ms = confidence_and_label(primary_bundle.model, feature_row)
        state["model_status"] = "ok"
    except Exception as exc:
        model_failed = True
        state["inference_failures"] = state.get("inference_failures", 0) + 1
        state["model_status"] = "degraded"
        state["model_error_count"] = state.get("model_error_count", 0) + 1
        state["last_recovery_message"] = f"Model inference failed: {exc}. Auto-healed with fallback prediction."
        model_prediction = state.get("last_model_prediction") or state.get("last_prediction") or "WARNING"
        confidence = float(state.get("last_confidence") or 0.55)

    state["inference_latency_total_ms"] = state.get("inference_latency_total_ms", 0.0) + latency_ms

    inference_count = max(state.get("inference_count", 1), 1)
    inference_failures = state.get("inference_failures", 0)
    avg_latency_ms = state.get("inference_latency_total_ms", 0.0) / inference_count
    failure_rate = inference_failures / inference_count
    throughput = inference_count / max(time.monotonic() - started_monotonic, 1e-6)

    drift_alerts = detect_drift_alerts(sample, baseline_stats)
    explainability = explainability_payload(sample, feature_importances)
    recent_healthy_samples = state.get("recent_healthy_samples", [])
    priority_2 = compute_priority_2_intelligence(
        sample=sample,
        baseline_stats=baseline_stats,
        recent_healthy_samples=recent_healthy_samples,
        model_prediction=model_prediction,
        confidence=float(confidence),
        drift_alerts=drift_alerts,
    )

    prediction = priority_2["ensemble_prediction"]
    adaptive_thresholds = priority_2["adaptive_thresholds"]
    adaptive_prediction = priority_2["adaptive_prediction"]
    sensor_fault = priority_2["sensor_fault"]
    out_of_distribution = priority_2["out_of_distribution"]
    recovery_policy = priority_2["recovery_policy"]
    ensemble_score = priority_2["ensemble_score"]
    priority_3 = compute_priority_3_intelligence(
        sample=sample,
        baseline_stats=baseline_stats,
        recent_healthy_samples=recent_healthy_samples,
        drift_alerts=drift_alerts,
        confidence=float(confidence),
        priority_2=priority_2,
        ensemble_prediction=prediction,
    )

    shadow_prediction = "-"
    if shadow_bundle:
        try:
            shadow_prediction, _, _ = confidence_and_label(shadow_bundle.model, feature_row)
        except Exception:
            shadow_prediction = "ERROR"

    input_hash = canonical_input_hash(
        {
            "temperature": sample["temperature"],
            "current": sample["current"],
            "voltage": sample["voltage"],
            "esp_status": sample["esp_status"],
        }
    )

    append_prediction_log(
        {
            "timestamp": utc_now_iso(),
            "mode": state.get("runtime_mode"),
            "data_source": state.get("data_source"),
            "model_version": state.get("model_version", "legacy"),
            "input_hash": input_hash,
            "model_prediction": model_prediction,
            "prediction": prediction,
            "adaptive_prediction": adaptive_prediction,
            "ensemble_score": ensemble_score,
            "priority_3": priority_3,
            "priority_3_summary": priority_3["priority_3_summary"],
            "confidence": round(float(confidence), 6),
            "latency_ms": round(float(latency_ms), 3),
            "drift_alerts": drift_alerts,
            "explainability": explainability,
            "priority_2": priority_2,
            "device_id": sample["device_id"],
            "sequence_number": sample["sequence_number"],
            "shadow_prediction": shadow_prediction,
            "model_failed": model_failed,
        }
    )
    # Also write a tamper-evident signed log (best-effort)
    try:
        log_event = {
            "timestamp": utc_now_iso(),
            "mode": state.get("runtime_mode"),
            "data_source": state.get("data_source"),
            "model_version": state.get("model_version", "legacy"),
            "input_hash": input_hash,
            "model_prediction": model_prediction,
            "prediction": prediction,
            "adaptive_prediction": adaptive_prediction,
            "ensemble_score": ensemble_score,
            "priority_3": priority_3,
            "priority_3_summary": priority_3.get("priority_3_summary"),
            "confidence": round(float(confidence), 6),
            "latency_ms": round(float(latency_ms), 3),
            "device_id": sample.get("device_id"),
            "sequence_number": sample.get("sequence_number"),
            "model_failed": model_failed,
        }
        append_signed_prediction_log(log_event)
        try:
            eval_event = {
                "timestamp": log_event["timestamp"],
                "model_version": log_event.get("model_version"),
                "prediction": log_event.get("prediction"),
                "confidence": log_event.get("confidence"),
                "latency_ms": log_event.get("latency_ms", 0.0),
                "device_id": log_event.get("device_id"),
            }
            append_eval_event(eval_event)
        except Exception:
            pass
    except Exception:
        # Best-effort — do not break the inference loop on logging errors
        pass

    state.update(
        {
            "connection": "connected",
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "temperature": round(sample["temperature"], 2),
            "current": round(sample["current"], 3),
            "voltage": round(sample["voltage"], 3),
            "esp_status": sample["esp_status"],
            "prediction": prediction,
            "confidence": round(float(confidence), 4),
            "latency_ms": round(float(latency_ms), 2),
            "inference_throughput_rps": round(float(throughput), 3),
            "inference_avg_latency_ms": round(float(avg_latency_ms), 2),
            "inference_failure_rate": round(float(failure_rate), 4),
            "model_prediction": model_prediction,
            "ensemble_prediction": prediction,
            "ensemble_score": ensemble_score,
            "drift_alerts": drift_alerts,
            "drift_alert_count": len(drift_alerts),
            "explainability": explainability,
            "adaptive_thresholds": adaptive_thresholds,
            "adaptive_threshold_source": adaptive_thresholds.get("source", "training_baseline"),
            "adaptive_prediction": adaptive_prediction,
            "sensor_fault": sensor_fault,
            "sensor_fault_label": sensor_fault.get("label", "battery_issue"),
            "sensor_fault_reason": sensor_fault.get("reason", "-"),
            "out_of_distribution": out_of_distribution,
            "ood_score": out_of_distribution.get("score", 0),
            "ood_flagged": out_of_distribution.get("flagged", False),
            "recovery_policy": recovery_policy,
            "recovery_action": recovery_policy.get("action", "-"),
            "recovery_rationale": recovery_policy.get("rationale", "-"),
            "priority_2_summary": priority_2.get("priority_2_summary", "-"),
            "rul_forecast": priority_3["rul_forecast"],
            "what_if_scenarios": priority_3["what_if_scenarios"],
            "digital_twin": priority_3["digital_twin"],
            "drift_monitoring": priority_3["drift_monitoring"],
            "fleet_intelligence": priority_3["fleet_intelligence"],
            "rul_minutes": priority_3["rul_forecast"]["minutes"],
            "rul_cycles": priority_3["rul_forecast"]["cycles"],
            "health_index": priority_3["rul_forecast"]["health_index"],
            "drift_score": priority_3["drift_monitoring"]["drift_score"],
            "retrain_recommended": priority_3["drift_monitoring"]["retrain_recommended"],
            "fleet_mode": priority_3["fleet_intelligence"]["mode"],
            "shadow_prediction": shadow_prediction,
            "shadow_disagreement": bool(
                shadow_bundle and shadow_prediction not in {"-", "ERROR"} and shadow_prediction != prediction
            ),
            "message": "Live stream running",
            "device_id": sample["device_id"],
            "sequence_number": sample["sequence_number"],
            "relay_state": sample["relay_state"],
            "fail_safe": sample["fail_safe"],
            "packets_received": state.get("packets_received", 0) + 1,
            "last_packet_monotonic": time.monotonic(),
            "data_status": "ok",
            "last_prediction": prediction,
            "last_model_prediction": model_prediction,
            "last_confidence": round(float(confidence), 4),
            "last_recovery_message": state.get("last_recovery_message", ""),
        }
    )

    if prediction == "NORMAL" and confidence >= 0.6 and not out_of_distribution.get("flagged", False):
        healthy_samples = state.get("recent_healthy_samples", [])
        state["recent_healthy_samples"] = (healthy_samples + [sample])[-16:]


    reading_entry = {
        "timestamp": state.get("timestamp"),
        "temperature": round(sample["temperature"], 2),
        "current": round(sample["current"], 3),
        "voltage": round(sample["voltage"], 3),
        "prediction": prediction,
        "confidence": round(float(confidence), 4),
    }
    readings_history = state.get("readings_history", [])
    state["readings_history"] = (readings_history + [reading_entry])[-15:]


def synthetic_fallback_loop(state: dict, primary_bundle, shadow_bundle, stale_after: float) -> None:
    started_monotonic = time.monotonic()
    feature_importances = get_feature_importance_map(primary_bundle.model)
    baseline_stats = primary_bundle.manifest.get("drift_baseline", {}) if primary_bundle.manifest else {}

    state["runtime_mode"] = "synthetic_fallback"
    state["data_source"] = "mock"
    state["connection"] = "connected"
    state["message"] = "Serial unavailable. Auto-healed to synthetic fallback stream"

    sequence = 0
    while True:
        sequence += 1
        elapsed = time.monotonic() - started_monotonic
        sample, _ = build_demo_sample(elapsed, sequence)
        if sample is not None:
            process_sample(
                sample=sample,
                state=state,
                primary_bundle=primary_bundle,
                shadow_bundle=shadow_bundle,
                feature_importances=feature_importances,
                baseline_stats=baseline_stats,
                started_monotonic=started_monotonic,
            )
            if state.get("message") == "Live stream running":
                state["message"] = "Synthetic fallback stream active"

        update_connection_health(state, stale_after)
        time.sleep(1.0)


def demo_mode_loop(state: dict, primary_bundle, shadow_bundle, stale_after: float) -> None:
    started_monotonic = time.monotonic()
    feature_importances = get_feature_importance_map(primary_bundle.model)
    baseline_stats = primary_bundle.manifest.get("drift_baseline", {}) if primary_bundle.manifest else {}

    state["runtime_mode"] = "demo"
    state["data_source"] = "demo_simulator"
    state["connection"] = "connected"
    state["message"] = "Deterministic demo mode active"

    sequence = 0
    while True:
        sequence += 1
        elapsed = time.monotonic() - started_monotonic
        sample, stage = build_demo_sample(elapsed, sequence)

        if stage == "MALFORMED":
            state["parse_errors"] = state.get("parse_errors", 0) + 1
            state["message"] = "Fault rehearsal: malformed packet ignored safely"
            state["data_status"] = "degraded"
            time.sleep(1.0)
            continue

        if stage == "DISCONNECT":
            state["connection"] = "disconnected"
            state["data_status"] = "degraded"
            state["message"] = "Fault rehearsal: serial disconnect simulated, auto-healing"
            time.sleep(1.0)
            continue

        if stage == "SPIKE":
            state["message"] = "Fault rehearsal: sudden sensor spike handled"

        if sample is None:
            state["data_status"] = "degraded"
            state["prediction"] = state.get("last_prediction") or "WARNING"
            time.sleep(1.0)
            continue

        process_sample(
            sample=sample,
            state=state,
            primary_bundle=primary_bundle,
            shadow_bundle=shadow_bundle,
            feature_importances=feature_importances,
            baseline_stats=baseline_stats,
            started_monotonic=started_monotonic,
        )

        if stage == "RECOVERY":
            state["message"] = "Auto-healing complete: recovery state achieved"

        update_connection_health(state, stale_after)
        time.sleep(1.0)


def serial_loop(
    port: str,
    baudrate: int,
    timeout: float,
    primary_bundle,
    shadow_bundle,
    state: dict,
    reconnect_backoff_max: float,
    stale_after: float,
) -> None:
    reconnect_attempt = 0
    started_monotonic = time.monotonic()
    feature_importances = get_feature_importance_map(primary_bundle.model)
    baseline_stats = primary_bundle.manifest.get("drift_baseline", {}) if primary_bundle.manifest else {}

    state["runtime_mode"] = "live"
    state["data_source"] = "serial"

    while True:
        try:
            with serial.Serial(port=port, baudrate=baudrate, timeout=timeout) as ser:
                reconnect_attempt = 0
                state["connection"] = "connected"
                state["message"] = f"Listening on {port}"

                while True:
                    raw = ser.readline()

                    if not raw:
                        update_connection_health(state, stale_after)
                        continue

                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line:
                        continue

                    try:
                        sample = parse_serial_line(line)
                    except ValueError:
                        state["parse_errors"] = state.get("parse_errors", 0) + 1
                        state["message"] = "Corrupted packet ignored safely"
                        state["data_status"] = "degraded"
                        continue

                    sample, _ = apply_fault_injection(state, sample)
                    if sample is None:
                        time.sleep(0.5)
                        continue

                    process_sample(
                        sample=sample,
                        state=state,
                        primary_bundle=primary_bundle,
                        shadow_bundle=shadow_bundle,
                        feature_importances=feature_importances,
                        baseline_stats=baseline_stats,
                        started_monotonic=started_monotonic,
                    )

        except Exception as exc:
            reconnect_attempt += 1
            backoff = min(reconnect_backoff_max, 2 ** min(reconnect_attempt, 3))
            state["connection"] = "reconnecting"
            state["data_status"] = "degraded"
            state["message"] = f"{exc} (retry in {backoff:.1f}s)"
            state["auto_heal_count"] = state.get("auto_heal_count", 0) + 1
            state["last_recovery_message"] = "Auto-healing: ingestion reconnect in progress"

            time.sleep(backoff)


def build_app(state: dict, stale_after: float):
    web_root = get_web_root()
    app = Flask(__name__, static_folder=str(web_root), static_url_path="")

    @app.route("/")
    def index():
        return send_from_directory(str(web_root), "index.html")

    @app.route("/api/chat", methods=["POST"])
    def chat():
        message = request.json.get("message", "")
        
        api_key = os.environ.get("GEMINI_API_KEY", "").strip()
        if not api_key:
            return jsonify({"error": "GEMINI_API_KEY is not set"}), 500

        telemetry_context = {
            "prediction": state.get("prediction"),
            "confidence": state.get("confidence"),
            "voltage": state.get("voltage"),
            "current": state.get("current"),
            "temperature": state.get("temperature"),
            "message": state.get("message"),
            "recovery_action": state.get("recovery_action"),
            "rul_minutes": state.get("rul_minutes"),
        }
        
        system_prompt = (
            "You are an expert AI diagnostics assistant for an EV Battery project.\n"
            "You analyze live telemetry data and answer questions accurately in simple terms.\n"
            "Current live telemetry JSON:\n"
            f"{json.dumps(telemetry_context)}\n"
        )

        model_name = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        body = {
            "systemInstruction": {
                "parts": [{"text": system_prompt}]
            },
            "contents": [
                {"role": "user", "parts": [{"text": message}]}
            ],
            "generationConfig": {
                "temperature": 0.7,
                "topP": 0.9,
                "maxOutputTokens": 500,
            },
        }

        try:
            req = urllib_request.Request(
                url=url,
                data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=15) as rf:
                payload = json.loads(rf.read().decode("utf-8"))
            
            text_parts = []
            for candidate in payload.get("candidates", []) or []:
                content = candidate.get("content", {})
                for part in content.get("parts", []) or []:
                    text_val = part.get("text")
                    if text_val:
                        text_parts.append(text_val.strip())
            
            answer = "\n".join([segment for segment in text_parts if segment]).strip()
            if not answer:
                answer = "Gemini returned an empty response"
            return jsonify({"response": answer})
            
        except Exception as e:
            error_details = str(e)
            if hasattr(e, "read"):
                try:
                    error_details += " - " + e.read().decode("utf-8")
                except:
                    pass
            logger.error("Gemini chat error: %s", error_details, exc_info=True)
            return jsonify({"error": error_details}), 500

    @app.route("/api/latest")
    def latest():
        update_connection_health(state, stale_after)
        state["uptime_seconds"] = round(max(0.0, time.monotonic() - state.get("started_monotonic", time.monotonic())), 1)
        return jsonify(state)

    @app.route("/api/health")
    def health():
        update_connection_health(state, stale_after)
        return jsonify(
            {
                "connection": state.get("connection", "unknown"),
                "data_status": state.get("data_status", "unknown"),
                "message": state.get("message", "-"),
                "runtime_mode": state.get("runtime_mode", "unknown"),
                "data_source": state.get("data_source", "unknown"),
                "packets_received": state.get("packets_received", 0),
                "parse_errors": state.get("parse_errors", 0),
                "model_version": state.get("model_version", "legacy"),
                "model_status": state.get("model_status", "unknown"),
                "inference_count": state.get("inference_count", 0),
                "inference_failure_rate": state.get("inference_failure_rate", 0.0),
                "inference_avg_latency_ms": state.get("inference_avg_latency_ms", 0.0),
                "uptime_seconds": state.get("uptime_seconds", 0.0),
                "auto_heal_count": state.get("auto_heal_count", 0),
                "model_prediction": state.get("model_prediction", state.get("prediction", "unknown")),
                "ensemble_prediction": state.get("ensemble_prediction", state.get("prediction", "unknown")),
                "ensemble_score": state.get("ensemble_score", 0),
                "sensor_fault_label": state.get("sensor_fault_label", "unknown"),
                "ood_score": state.get("ood_score", 0),
                "recovery_action": state.get("recovery_action", "-"),
                "rul_minutes": state.get("rul_minutes", 0),
                "rul_cycles": state.get("rul_cycles", 0),
                "health_index": state.get("health_index", 0),
                "drift_score": state.get("drift_score", 0),
                "retrain_recommended": state.get("retrain_recommended", False),
            }
        )

    @app.route("/api/fault/inject", methods=["POST"])
    def fault_inject():
        payload = request.get_json(silent=True) or {}
        fault_type = str(payload.get("type", "")).lower()
        if fault_type not in {"disconnect", "malformed", "spike"}:
            return jsonify({"ok": False, "message": "Unsupported fault type"}), 400

        state["fault_inject"] = {"type": fault_type, "created_at": utc_now_iso()}
        state["message"] = f"Fault rehearsal queued: {fault_type}"
        return jsonify({"ok": True, "fault": state["fault_inject"]})
    return app


def main():
    parser = argparse.ArgumentParser(description="EV battery live web dashboard")
    parser.add_argument("--port", default="COM6", help="COM port, for example COM6")
    parser.add_argument("--baudrate", type=int, default=9600)
    parser.add_argument("--timeout", type=float, default=1.0)
    parser.add_argument("--model-path", default=None, help="Primary model path (defaults to stable pointer)")
    parser.add_argument("--shadow-model-path", default=None, help="Optional shadow model path")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--web-port", type=int, default=5000)
    parser.add_argument("--reconnect-backoff-max", type=float, default=8.0)
    parser.add_argument("--stale-after", type=float, default=5.0)
    parser.add_argument("--demo-mode", action="store_true", help="Run deterministic no-hardware demo sequence")
    args = parser.parse_args()

    primary_bundle = load_model_bundle(args.model_path)
    shadow_bundle = load_model_bundle(args.shadow_model_path) if args.shadow_model_path else None

    state = {
        "connection": "starting",
        "data_status": "starting",
        "runtime_mode": "starting",
        "data_source": "starting",
        "timestamp": "-",
        "temperature": None,
        "current": None,
        "voltage": None,
        "esp_status": "-",
        "prediction": "WARNING",
        "last_prediction": "WARNING",
        "last_model_prediction": "WARNING",
        "model_version": primary_bundle.version,
        "model_status": "ok",
        "model_error_count": 0,
        "confidence": 0.0,
        "last_confidence": 0.0,
        "latency_ms": 0.0,
        "inference_count": 0,
        "inference_failures": 0,
        "inference_latency_total_ms": 0.0,
        "inference_avg_latency_ms": 0.0,
        "inference_failure_rate": 0.0,
        "inference_throughput_rps": 0.0,
        "drift_alerts": [],
        "drift_alert_count": 0,
        "adaptive_thresholds": {},
        "adaptive_threshold_source": "training_baseline",
        "adaptive_prediction": "WARNING",
        "ensemble_prediction": "WARNING",
        "ensemble_score": 50,
        "sensor_fault": {"label": "battery_issue", "reason": "-", "confidence": 0.0},
        "sensor_fault_label": "battery_issue",
        "sensor_fault_reason": "-",
        "out_of_distribution": {
            "score": 0,
            "flagged": False,
            "max_zscore": 0.0,
            "components": {},
            "reason": "-",
            "status_unseen": False,
        },
        "ood_score": 0,
        "ood_flagged": False,
        "recovery_policy": {"action": "isolate_sensor", "rationale": "-"},
        "recovery_action": "isolate_sensor",
        "recovery_rationale": "-",
        "priority_2_summary": "-",
        "priority_3": {
            "rul_forecast": {"minutes": 0, "cycles": 0, "health_index": 0, "confidence": 0.0},
            "what_if_scenarios": [],
            "digital_twin": {"expected": {}, "observed": {}, "alignment": 0, "drift_gap": 0.0, "narrative": "-"},
            "drift_monitoring": {
                "drift_score": 0,
                "retrain_recommended": False,
                "reason": "-",
                "adaptive_prediction": "WARNING",
                "ensemble_prediction": "WARNING",
                "adaptive_threshold_source": "training_baseline",
            },
            "fleet_intelligence": {"mode": "synthetic_demo", "rankings": [], "top_asset": "-"},
            "priority_3_summary": "-",
        },
        "priority_3_summary": "-",
        "rul_minutes": 0,
        "rul_cycles": 0,
        "health_index": 0,
        "drift_score": 0,
        "retrain_recommended": False,
        "explainability": {
            "feature_contributions": {},
            "top_feature": "-",
            "top_feature_score": 0.0,
            "reason": "-",
        },
        "shadow_prediction": "-",
        "shadow_disagreement": False,
        "recent_healthy_samples": [],
        "readings_history": [],
        "device_id": "-",
        "sequence_number": None,
        "relay_state": "-",
        "fail_safe": False,
        "packets_received": 0,
        "parse_errors": 0,
        "last_packet_age_seconds": None,
        "last_packet_monotonic": None,
        "message": "Initializing ingestion",
        "last_recovery_message": "",
        "auto_heal_count": 0,
        "fault_inject": None,
        "started_monotonic": time.monotonic(),
        "uptime_seconds": 0.0,
    }

    if args.demo_mode:
        target = demo_mode_loop
        worker_args = (state, primary_bundle, shadow_bundle, args.stale_after)
    else:
        target = serial_loop
        worker_args = (
            args.port,
            args.baudrate,
            args.timeout,
            primary_bundle,
            shadow_bundle,
            state,
            args.reconnect_backoff_max,
            args.stale_after,
        )

    worker = threading.Thread(target=target, args=worker_args, daemon=True)
    worker.start()

    app = build_app(state, args.stale_after)
    app.run(host=args.host, port=args.web_port, debug=False)


if __name__ == "__main__":
    main()
