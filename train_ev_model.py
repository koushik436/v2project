import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.tree import DecisionTreeClassifier

from mlops_runtime import (
    CANDIDATES_DIR,
    FEATURE_COLUMNS,
    LABELS,
    TARGET_COLUMN,
    build_baseline_stats,
    ensure_dirs,
    label_mapping,
    model_version_tag,
    promote_candidate,
    rollback_to_previous,
    sha256_file,
    utc_now_iso,
)

DATASET_PATH = Path("ev_battery_dataset.csv")
SEED = 42
MIN_ROWS = 50

REQUIRED_COLUMNS = ["temperature", "current", "voltage", "esp_status", "label"]


def validate_dataset(df: pd.DataFrame) -> None:
    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(f"Missing required columns: {missing_columns}")

    scoped = df[REQUIRED_COLUMNS]
    if scoped.isna().any().any():
        raise ValueError("Dataset has missing values in required columns")

    if len(scoped) < MIN_ROWS:
        raise ValueError(f"Dataset must have at least {MIN_ROWS} rows for reliable training")

    scoped["label"] = scoped["label"].astype(str).str.upper()
    invalid_labels = set(scoped[TARGET_COLUMN].unique()) - set(LABELS)
    if invalid_labels:
        raise ValueError(f"Dataset has invalid labels: {sorted(invalid_labels)}")


def build_pipeline(random_state: int, max_depth: int) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", "passthrough", ["temperature", "current", "voltage"]),
            ("cat", OneHotEncoder(handle_unknown="ignore"), ["esp_status"]),
        ]
    )

    model = DecisionTreeClassifier(random_state=random_state, max_depth=max_depth)
    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )


def evaluation_payload(y_true: pd.Series, y_pred: pd.Series) -> dict:
    accuracy = accuracy_score(y_true, y_pred)
    precision, recall, f1, support = precision_recall_fscore_support(y_true, y_pred, labels=list(LABELS), zero_division=0)

    per_class = {
        label: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1_score": float(f1[index]),
            "support": int(support[index]),
        }
        for index, label in enumerate(LABELS)
    }

    confusion = confusion_matrix(y_true, y_pred, labels=list(LABELS))
    macro_f1 = float(sum(f1) / len(LABELS))

    return {
        "accuracy": float(accuracy),
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": {
            "labels": list(LABELS),
            "matrix": confusion.tolist(),
        },
    }


def train_candidate(args: argparse.Namespace) -> dict:
    if not DATASET_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}")

    ensure_dirs()

    df = pd.read_csv(DATASET_PATH)
    df.columns = [str(column).strip().lower() for column in df.columns]
    df[TARGET_COLUMN] = df[TARGET_COLUMN].astype(str).str.upper()
    df["esp_status"] = df["esp_status"].astype(str).str.upper()

    validate_dataset(df)

    x = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]

    x_train, x_test, y_train, y_test = train_test_split(
        x,
        y,
        test_size=args.test_size,
        random_state=args.seed,
        stratify=y,
    )

    pipeline = build_pipeline(random_state=args.seed, max_depth=args.max_depth)
    pipeline.fit(x_train, y_train)

    predictions = pipeline.predict(x_test)
    metrics = evaluation_payload(y_test, predictions)

    version = model_version_tag(prefix="ev_model")
    candidate_dir = CANDIDATES_DIR / version
    candidate_dir.mkdir(parents=True, exist_ok=True)

    model_path = candidate_dir / "model.joblib"
    joblib.dump(pipeline, model_path)

    dataset_hash = sha256_file(DATASET_PATH)
    baseline_stats = build_baseline_stats(df)

    training_config = {
        "seed": args.seed,
        "test_size": args.test_size,
        "max_depth": args.max_depth,
        "dataset_path": str(DATASET_PATH),
        "dataset_hash": dataset_hash,
        "rows": int(len(df)),
        "label_distribution": {label: int((y == label).sum()) for label in LABELS},
    }

    manifest = {
        "model": {
            "version": version,
            "created_at": utc_now_iso(),
            "model_path": str(model_path),
            "framework": "scikit-learn",
            "algorithm": "DecisionTreeClassifier",
        },
        "dataset": {
            "path": str(DATASET_PATH),
            "hash_sha256": dataset_hash,
            "version_ref": f"sha256:{dataset_hash[:12]}",
            "rows": int(len(df)),
        },
        "schema": {
            "features": FEATURE_COLUMNS,
            "target": TARGET_COLUMN,
            "label_mapping": label_mapping(),
        },
        "metrics": {
            "accuracy": metrics["accuracy"],
            "macro_f1": metrics["macro_f1"],
            "per_class": metrics["per_class"],
        },
        "drift_baseline": baseline_stats,
        "training_config": training_config,
    }

    (candidate_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (candidate_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    (candidate_dir / "classification_report.txt").write_text(
        classification_report(y_test, predictions, labels=list(LABELS), digits=4, zero_division=0),
        encoding="utf-8",
    )
    (candidate_dir / "training_config.json").write_text(json.dumps(training_config, indent=2), encoding="utf-8")

    promotion = {"promoted": False, "reason": "Promotion skipped"}
    if args.promote:
        promotion = promote_candidate(candidate_dir, max_metric_drop=args.max_metric_drop)

    return {
        "candidate_dir": str(candidate_dir),
        "manifest": manifest,
        "metrics": metrics,
        "promotion": promotion,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Train and govern EV battery risk model artifacts")
    parser.add_argument("--action", choices=["train", "rollback"], default="train")
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--test-size", type=float, default=0.2)
    parser.add_argument("--max-depth", type=int, default=6)
    parser.add_argument("--promote", action="store_true", help="Run promotion gate after training")
    parser.add_argument("--max-metric-drop", type=float, default=0.01, help="Allowed drop from baseline metrics")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.action == "rollback":
        result = rollback_to_previous()
        print("Rollback: OK")
        print(json.dumps(result, indent=2))
        return

    result = train_candidate(args)

    print("Dataset check: OK")
    print(f"Candidate dir: {result['candidate_dir']}")
    print(f"Accuracy: {result['metrics']['accuracy']:.4f}")
    print(f"Macro F1: {result['metrics']['macro_f1']:.4f}")
    print("Per-class metrics:")
    for label in LABELS:
        row = result["metrics"]["per_class"][label]
        print(
            f"  {label}: precision={row['precision']:.4f}, recall={row['recall']:.4f}, "
            f"f1={row['f1_score']:.4f}, support={row['support']}"
        )

    if args.promote:
        print("Promotion result:")
        print(json.dumps(result["promotion"], indent=2))


if __name__ == "__main__":
    main()
