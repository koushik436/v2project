import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import List, Optional, Tuple


def check_dependencies() -> Tuple[bool, List[str]]:
    required_modules = [
        "flask",
        "pandas",
        "serial",
        "joblib",
        "sklearn",
    ]
    missing = []
    for module_name in required_modules:
        try:
            importlib.import_module(module_name)
        except Exception:
            missing.append(module_name)
    return len(missing) == 0, missing


def resolve_model_path(explicit_model_path: Optional[str]) -> Path:
    if explicit_model_path:
        requested = Path(explicit_model_path)
        if requested.exists():
            return requested

        candidate = Path("models") / "candidates" / requested.parent.name / "model.joblib"
        if candidate.exists():
            return candidate

    pointer_file = Path("models") / "pointers" / "stable.json"
    if pointer_file.exists():
        try:
            payload = json.loads(pointer_file.read_text(encoding="utf-8"))
            stable_path = payload.get("stable_model_path")
            if stable_path:
                pointer_path = Path(stable_path)
                if pointer_path.exists():
                    return pointer_path

                candidate = Path("models") / "candidates" / pointer_path.parent.name / "model.joblib"
                if candidate.exists():
                    return candidate
        except Exception:
            pass

    candidate_models = sorted(
        (Path("models") / "candidates").glob("*/model.joblib"),
        key=lambda model_file: model_file.stat().st_mtime,
        reverse=True,
    )
    if candidate_models:
        return candidate_models[0]

    return Path("ev_risk_model.joblib")


def check_model(explicit_model_path: Optional[str]) -> Tuple[bool, str]:
    model_path = resolve_model_path(explicit_model_path)
    if model_path.exists():
        return True, str(model_path)
    return False, str(model_path)


def check_serial(port: str) -> Tuple[bool, List[str]]:
    try:
        from serial.tools import list_ports

        available = [entry.device for entry in list_ports.comports()]
    except Exception:
        return False, []

    return port in available, available


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight checks for EV hackathon deployment")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--model-path", default=None)
    parser.add_argument("--demo-mode", action="store_true")
    parser.add_argument("--allow-no-hardware", action="store_true")
    args = parser.parse_args()

    dep_ok, missing = check_dependencies()
    model_ok, model_path = check_model(args.model_path)
    serial_ok, ports = check_serial(args.port)

    print("[Preflight] Dependency validation:", "OK" if dep_ok else f"MISSING: {missing}")
    print("[Preflight] Model availability:", "OK" if model_ok else f"NOT FOUND: {model_path}")
    print("[Preflight] Serial availability:", "OK" if serial_ok else f"PORT {args.port} NOT FOUND, available={ports}")

    if not dep_ok or not model_ok:
        return 2

    if args.demo_mode or args.allow_no_hardware:
        return 0

    if not serial_ok:
        return 3

    return 0


if __name__ == "__main__":
    if sys.version_info < (3, 9):
        raise RuntimeError("Python 3.9 or higher is required")
    raise SystemExit(main())
