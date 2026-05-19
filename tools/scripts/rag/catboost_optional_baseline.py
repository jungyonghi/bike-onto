# Timestamp: 2026-05-18 16:58:00

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

try:
    from .ml_execution_pack import NUMERIC_FEATURE_COLUMNS
except ImportError:  # Allow direct script execution.
    from ml_execution_pack import NUMERIC_FEATURE_COLUMNS


@dataclass(frozen=True)
class CatBoostOptionalResult:
    output_dir: Path
    report_path: Path
    status: str
    row_count: int
    target: str


def _load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_report(output_dir: Path, payload: dict[str, Any]) -> CatBoostOptionalResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "catboost_optional_report.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CatBoostOptionalResult(
        output_dir=output_dir,
        report_path=report_path,
        status=str(payload["status"]),
        row_count=int(payload["row_count"]),
        target=str(payload["target"]),
    )


def run_catboost_optional_baseline(
    *,
    feature_table_csv: Path | str,
    output_dir: Path | str,
    target: str = "label_requires_review",
) -> CatBoostOptionalResult:
    feature_table_csv = Path(feature_table_csv)
    output_dir = Path(output_dir)
    rows = _load_rows(feature_table_csv)
    base_payload: dict[str, Any] = {
        "model_id": "catboost_classifier",
        "target": target,
        "row_count": len(rows),
        "feature_table_csv": str(feature_table_csv),
        "numeric_features": NUMERIC_FEATURE_COLUMNS,
        "text_features": ["question", "answer"],
    }

    if not rows:
        return _write_report(output_dir, {**base_payload, "status": "no_rows"})

    labels = [int(row.get(target, "0") or 0) for row in rows]
    if len(set(labels)) < 2:
        return _write_report(output_dir, {**base_payload, "status": "single_class", "class_values": sorted(set(labels))})

    try:
        from catboost import CatBoostClassifier, Pool
    except Exception as error:
        return _write_report(
            output_dir,
            {
                **base_payload,
                "status": "dependency_missing",
                "install_hint": "pip install catboost",
                "error": str(error),
                "note": "CatBoost는 optional heavy dependency다. 현재 smoke baseline은 scikit-learn으로 실행한다.",
            },
        )

    feature_names = ["question", "answer", *NUMERIC_FEATURE_COLUMNS]
    data = []
    for row in rows:
        data.append([row.get("question", ""), row.get("answer", ""), *[float(row.get(column, "0") or 0) for column in NUMERIC_FEATURE_COLUMNS]])
    pool = Pool(data=data, label=labels, feature_names=feature_names, text_features=[0, 1])
    model = CatBoostClassifier(iterations=32, learning_rate=0.1, depth=4, loss_function="Logloss", verbose=False, random_seed=42)
    model.fit(pool)
    predictions = [int(value) for value in model.predict(pool)]
    accuracy = sum(1 for pred, label in zip(predictions, labels) if pred == label) / len(labels)
    model_path = output_dir / "catboost_model.cbm"
    output_dir.mkdir(parents=True, exist_ok=True)
    model.save_model(str(model_path))
    return _write_report(
        output_dir,
        {
            **base_payload,
            "status": "trained",
            "training_accuracy": accuracy,
            "model_path": str(model_path),
            "note": "Small smoke fit on all rows; add holdout split when row_count grows.",
        },
    )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run optional CatBoost baseline if catboost is installed.")
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--target", default="label_requires_review")
    args = parser.parse_args(list(argv) if argv is not None else None)
    result = run_catboost_optional_baseline(feature_table_csv=args.features, output_dir=args.output_dir, target=args.target)
    print(json.dumps({"status": result.status, "report_path": str(result.report_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
