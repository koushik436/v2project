import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd
import serial
from serial import SerialException

from mlops_runtime import (
    append_prediction_log,
    canonical_input_hash,
    confidence_and_label,
    compute_priority_2_intelligence,
    compute_priority_3_intelligence,
    detect_drift_alerts,
    explainability_payload,
    get_feature_importance_map,
    load_model_bundle,
    utc_now_iso,
)

STATUS_ALLOWED = {"CONNECTED", "DISCONNECTED"}
TEMPERATURE_RANGE = (-40.0, 125.0)
CURRENT_RANGE = (0.0, 5.0)
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
    """Parse legacy CSV or v2 packet payload formats."""
    if line.startswith("V2|"):
        return parse_v2_payload(line)

    return parse_legacy_csv(line)


def parse_legacy_csv(line: str):
    """Parse expected line format: temperature,current,voltage,status"""
    parts = [segment.strip() for segment in line.split(",")]
    if len(parts) != 4:
        raise ValueError(f"Expected 4 fields, got {len(parts)}")

    temperature = float(parts[0])
    current = float(parts[1])
    voltage = float(parts[2])
    status = parts[3]

    if not status:
        raise ValueError("Status is empty")

    status = status.upper()
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

    prefix = parts[0]
    if prefix != "V2":
        raise ValueError(f"Invalid v2 prefix: {prefix}")

    body, crc_hex = line.rsplit("|", maxsplit=1)
    expected_crc = fnv1a32(body)
    try:
        received_crc = int(crc_hex, 16)
    except ValueError as exc:
        raise ValueError(f"Invalid CRC hex: {crc_hex}") from exc

    if expected_crc != received_crc:
        raise ValueError("CRC mismatch")

    device_id = parts[1]
    _packet_version = parts[2]
    sequence_number = int(parts[3])
    _timestamp_ms = int(parts[4])
    temperature = float(parts[5])
    current = float(parts[6])
    voltage = float(parts[7])
    status = parts[8].upper()
    relay_state = parts[9].upper()
    fail_safe = parts[10] == "1"

    validate_ranges(temperature, current, voltage, status)

    return {
        "temperature": temperature,
        "current": current,
        "voltage": voltage,
        "esp_status": status,
        "device_id": device_id,
        "sequence_number": sequence_number,
        "relay_state": relay_state,
        "fail_safe": fail_safe,
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


def write_csv_row(csv_writer, timestamp, sample, prediction_record):
    csv_writer.writerow(
        {
            "timestamp": timestamp,
            "temperature_c": sample["temperature"],
            "current_a": sample["current"],
            "voltage_v": sample["voltage"],
            "esp_status": sample["esp_status"],
            "ai_prediction": prediction_record["prediction"],
            "device_id": sample["device_id"],
            "sequence_number": sample["sequence_number"],
            "relay_state": sample["relay_state"],
            "fail_safe": sample["fail_safe"],
            "model_version": prediction_record["model_version"],
            "model_prediction": prediction_record["model_prediction"],
            "confidence": round(prediction_record["confidence"], 4),
            "latency_ms": round(prediction_record["latency_ms"], 3),
            "drift_alerts": "|".join(prediction_record["drift_alerts"]),
            "shadow_prediction": prediction_record["shadow_prediction"],
            "ensemble_prediction": prediction_record["ensemble_prediction"],
            "ensemble_score": prediction_record["ensemble_score"],
            "adaptive_prediction": prediction_record["adaptive_prediction"],
            "sensor_fault_label": prediction_record["sensor_fault_label"],
            "ood_score": prediction_record["ood_score"],
            "recovery_action": prediction_record["recovery_action"],
            "rul_minutes": prediction_record["rul_minutes"],
            "rul_cycles": prediction_record["rul_cycles"],
            "health_index": prediction_record["health_index"],
            "drift_score": prediction_record["drift_score"],
            "retrain_recommended": prediction_record["retrain_recommended"],
            "priority_2_summary": prediction_record["priority_2_summary"],
            "priority_3_summary": prediction_record["priority_3_summary"],
        }
    )


def monitor_battery(
    port: str,
    baudrate: int,
    timeout: float,
    enable_csv: bool,
    csv_path: str,
    model_path: str,
    shadow_model_path: Optional[str],
    reconnect_backoff_max: float,
    stale_after: float,
):
    primary_bundle = load_model_bundle(model_path)
    shadow_bundle = load_model_bundle(shadow_model_path) if shadow_model_path else None

    feature_importances = get_feature_importance_map(primary_bundle.model)
    baseline_stats = primary_bundle.manifest.get("drift_baseline", {}) if primary_bundle.manifest else {}
    recent_healthy_samples = []

    csv_file = None
    csv_writer = None

    if enable_csv:
        csv_file = open(csv_path, mode="a", newline="", encoding="utf-8")
        fieldnames = [
            "timestamp",
            "temperature_c",
            "current_a",
            "voltage_v",
            "esp_status",
            "ai_prediction",
            "device_id",
            "sequence_number",
            "relay_state",
            "fail_safe",
            "model_version",
            "model_prediction",
            "confidence",
            "latency_ms",
            "drift_alerts",
            "shadow_prediction",
            "ensemble_prediction",
            "ensemble_score",
            "adaptive_prediction",
            "sensor_fault_label",
            "ood_score",
            "recovery_action",
            "rul_minutes",
            "rul_cycles",
            "health_index",
            "drift_score",
            "retrain_recommended",
            "priority_2_summary",
            "priority_3_summary",
        ]
        csv_writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        if csv_file.tell() == 0:
            csv_writer.writeheader()

    malformed_count = 0
    reconnect_attempt = 0
    last_valid_sample_monotonic = None
    stale_reported = False
    started_monotonic = time.monotonic()
    inference_count = 0
    inference_failures = 0
    latency_total_ms = 0.0

    try:
        print(f"Loaded model: {primary_bundle.model_path} (version={primary_bundle.version})")
        if shadow_bundle:
            print(f"Loaded shadow model: {shadow_bundle.model_path} (version={shadow_bundle.version})")
        print("Listening... Press Ctrl+C to stop")

        while True:
            try:
                with serial.Serial(port=port, baudrate=baudrate, timeout=timeout) as ser:
                    reconnect_attempt = 0
                    stale_reported = False
                    print(f"Connected to {port} at {baudrate} baud")

                    while True:
                        raw_bytes = ser.readline()

                        if not raw_bytes:
                            if (
                                last_valid_sample_monotonic is not None
                                and not stale_reported
                                and (time.monotonic() - last_valid_sample_monotonic) >= stale_after
                            ):
                                stale_reported = True
                                print(f"Stream stale: no valid packets for {stale_after:.1f}s")
                            continue

                        raw_line = raw_bytes.decode("utf-8", errors="ignore").strip()
                        if not raw_line:
                            continue

                        try:
                            sample = parse_serial_line(raw_line)
                        except ValueError as exc:
                            malformed_count += 1
                            print(f"Skipping invalid line [{malformed_count}]: '{raw_line}' ({exc})")
                            continue

                        if stale_reported:
                            print("Stream recovered")
                        stale_reported = False
                        last_valid_sample_monotonic = time.monotonic()

                        feature_row = build_feature_row(
                            sample["temperature"],
                            sample["current"],
                            sample["voltage"],
                            sample["esp_status"],
                        )

                        inference_count += 1
                        model_prediction = prediction = "WARNING"
                        try:
                            model_prediction, confidence, latency_ms = confidence_and_label(primary_bundle.model, feature_row)
                        except Exception:
                            inference_failures += 1
                            model_prediction = classify_rule_based(sample)
                            confidence = 0.55
                            latency_ms = 0.0

                        latency_total_ms += latency_ms
                        drift_alerts = detect_drift_alerts(sample, baseline_stats)
                        explainability = explainability_payload(sample, feature_importances)
                        priority_2 = compute_priority_2_intelligence(
                            sample=sample,
                            baseline_stats=baseline_stats,
                            recent_healthy_samples=recent_healthy_samples,
                            model_prediction=model_prediction,
                            confidence=confidence,
                            drift_alerts=drift_alerts,
                        )
                        priority_3 = compute_priority_3_intelligence(
                            sample=sample,
                            baseline_stats=baseline_stats,
                            recent_healthy_samples=recent_healthy_samples,
                            drift_alerts=drift_alerts,
                            confidence=confidence,
                            priority_2=priority_2,
                            ensemble_prediction=priority_2["ensemble_prediction"],
                        )

                        prediction = priority_2["ensemble_prediction"].upper()
                        adaptive_prediction = priority_2["adaptive_prediction"]
                        sensor_fault = priority_2["sensor_fault"]
                        out_of_distribution = priority_2["out_of_distribution"]
                        recovery_policy = priority_2["recovery_policy"]

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
                                "model_version": primary_bundle.version,
                                "input_hash": input_hash,
                                "model_prediction": model_prediction,
                                "prediction": prediction,
                                "confidence": round(confidence, 6),
                                "latency_ms": round(latency_ms, 3),
                                "drift_alerts": drift_alerts,
                                "explainability": explainability,
                                "priority_2": priority_2,
                                "device_id": sample["device_id"],
                                "sequence_number": sample["sequence_number"],
                                "shadow_prediction": shadow_prediction,
                            }
                        )

                        elapsed = max(time.monotonic() - started_monotonic, 1e-6)
                        throughput = inference_count / elapsed
                        failure_rate = inference_failures / inference_count
                        avg_latency_ms = latency_total_ms / inference_count

                        prediction_record = {
                            "model_prediction": model_prediction,
                            "prediction": prediction,
                            "ensemble_prediction": prediction,
                            "ensemble_score": priority_2["ensemble_score"],
                            "adaptive_prediction": adaptive_prediction,
                            "model_version": primary_bundle.version,
                            "confidence": confidence,
                            "latency_ms": latency_ms,
                            "drift_alerts": drift_alerts,
                            "sensor_fault_label": sensor_fault["label"],
                            "ood_score": out_of_distribution["score"],
                            "recovery_action": recovery_policy["action"],
                            "priority_2_summary": priority_2["priority_2_summary"],
                            "rul_minutes": priority_3["rul_forecast"]["minutes"],
                            "rul_cycles": priority_3["rul_forecast"]["cycles"],
                            "health_index": priority_3["rul_forecast"]["health_index"],
                            "drift_score": priority_3["drift_monitoring"]["drift_score"],
                            "retrain_recommended": priority_3["drift_monitoring"]["retrain_recommended"],
                            "priority_3_summary": priority_3["priority_3_summary"],
                            "shadow_prediction": shadow_prediction,
                        }

                        print("-" * 52)
                        print(f"Temperature (C):  {sample['temperature']:.2f}")
                        print(f"Current (A):      {sample['current']:.3f}")
                        print(f"Voltage (V):      {sample['voltage']:.3f}")
                        print(f"ESP Status:       {sample['esp_status']}")
                        print(f"Device ID:        {sample['device_id']}")
                        print(f"Sequence Number:  {sample['sequence_number']}")
                        print(f"Relay State:      {sample['relay_state']}")
                        print(f"Fail Safe:        {sample['fail_safe']}")
                        print(f"AI Prediction:    {prediction}")
                        print(f"Model Vote:       {model_prediction}")
                        print(f"Model Version:    {primary_bundle.version}")
                        print(f"Confidence:       {confidence:.3f}")
                        print(f"Latency (ms):     {latency_ms:.2f}")
                        print(f"Throughput (r/s): {throughput:.2f}")
                        print(f"Failure Rate:     {failure_rate:.3%}")
                        if drift_alerts:
                            print(f"Drift Alerts:     {', '.join(drift_alerts)}")
                        else:
                            print("Drift Alerts:     none")
                        print(f"Sensor Fault:     {sensor_fault['label']} - {sensor_fault['reason']}")
                        print(f"OOD Score:        {out_of_distribution['score']}")
                        print(f"Recovery Action:  {recovery_policy['action']} - {recovery_policy['rationale']}")
                        print(f"RUL Forecast:     {priority_3['rul_forecast']['minutes']} min / {priority_3['rul_forecast']['cycles']} cycles")
                        print(f"Health Index:     {priority_3['rul_forecast']['health_index']}/100")
                        print(f"Twin Alignment:   {priority_3['digital_twin']['alignment']}%")
                        print(f"Retrain Signal:   {priority_3['drift_monitoring']['drift_score']}/100 -> {priority_3['drift_monitoring']['retrain_recommended']}")
                        print(f"Fleet Top Risk:   {priority_3['fleet_intelligence']['top_asset']}")
                        if shadow_bundle:
                            print(f"Shadow Prediction:{shadow_prediction}")
                        print(
                            "Top Feature:      "
                            f"{explainability['top_feature']} ({explainability['top_feature_score']:.3f})"
                        )

                        if prediction == "CRITICAL":
                            print("ALERT: HIGH RISK DETECTED")
                        elif prediction == "WARNING":
                            print("ALERT: WARNING STAGE")
                        else:
                            print("ALERT: SYSTEM NORMAL")

                        if prediction == "NORMAL" and confidence >= 0.6 and not out_of_distribution["flagged"]:
                            recent_healthy_samples = (recent_healthy_samples + [sample])[-16:]

                        if csv_writer is not None:
                            timestamp = datetime.now().isoformat(timespec="seconds")
                            write_csv_row(csv_writer, timestamp, sample, prediction_record)
                            if csv_file is not None:
                                csv_file.flush()

            except (SerialException, OSError) as exc:
                reconnect_attempt += 1
                backoff = min(reconnect_backoff_max, 2 ** min(reconnect_attempt, 3))
                print(f"Serial error: {exc}")
                print(f"Reconnect attempt {reconnect_attempt} in {backoff:.1f}s")
                time.sleep(backoff)

    except KeyboardInterrupt:
        print("\nMonitoring stopped")
    finally:
        if csv_file is not None:
            csv_file.close()


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="EV battery monitor with model-based live prediction from serial data."
    )
    parser.add_argument("--port", required=True, help="COM port, for example COM3")
    parser.add_argument("--baudrate", type=int, default=9600, help="Serial baud rate")
    parser.add_argument("--timeout", type=float, default=1.0, help="Serial read timeout in seconds")
    parser.add_argument("--log-csv", action="store_true", help="Enable CSV logging")
    parser.add_argument("--csv-path", default="battery_log.csv", help="CSV output path")
    parser.add_argument("--model-path", default=None, help="Path to trained model file (defaults to stable pointer)")
    parser.add_argument("--shadow-model-path", default=None, help="Optional model path for shadow evaluation")
    parser.add_argument("--reconnect-backoff-max", type=float, default=8.0, help="Maximum reconnect backoff in seconds")
    parser.add_argument("--stale-after", type=float, default=5.0, help="Mark stream stale after N seconds without valid packets")
    return parser


def main():
    parser = build_arg_parser()
    args = parser.parse_args()

    monitor_battery(
        port=args.port,
        baudrate=args.baudrate,
        timeout=args.timeout,
        enable_csv=args.log_csv,
        csv_path=args.csv_path,
        model_path=args.model_path,
        shadow_model_path=args.shadow_model_path,
        reconnect_backoff_max=args.reconnect_backoff_max,
        stale_after=args.stale_after,
    )


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        raise RuntimeError("Python 3.9 or higher is required")
    main()
