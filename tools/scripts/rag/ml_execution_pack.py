# Timestamp: 2026-05-18 16:52:00

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


NUMERIC_FEATURE_COLUMNS = [
    "evidence_count",
    "object_count",
    "relation_count",
    "action_count",
    "source_hit_count",
    "text_length",
    "question_length",
    "answer_length",
    "review_signal_count",
]

FEATURE_COLUMNS = [
    "question_id",
    "question",
    "answer",
    *NUMERIC_FEATURE_COLUMNS,
    "label_requires_review",
    "label_contract_pass",
]


@dataclass(frozen=True)
class MlExecutionPackResult:
    output_dir: Path
    feature_table_csv: Path
    feature_table_jsonl: Path
    model_registry_path: Path
    run_matrix_path: Path
    catboost_pool_schema_path: Path
    report_path: Path
    row_count: int


@dataclass(frozen=True)
class BaselineResult:
    output_dir: Path
    metrics_path: Path
    report_path: Path
    model_family: str
    status: str
    row_count: int
    target: str


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        raise FileNotFoundError(path)
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_no}")
        rows.append(value)
    return rows


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0


def _bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def _row_to_feature(row: dict[str, Any]) -> dict[str, Any]:
    question = str(row.get("question") or row.get("query") or "")
    answer = str(row.get("answer") or row.get("final_answer") or row.get("preview") or "")
    evidence_count = _list_count(row.get("evidence_documents")) or _list_count(row.get("source_hits"))
    action_count = _list_count(row.get("recommended_actions"))
    requires_review = _bool_int(row.get("requires_review"))
    review_signal_count = requires_review + action_count + (1 if evidence_count == 0 else 0)
    return {
        "question_id": str(row.get("id") or row.get("question_id") or f"row-{abs(hash(question))}"),
        "question": question,
        "answer": answer,
        "evidence_count": evidence_count,
        "object_count": _list_count(row.get("related_objects")),
        "relation_count": _list_count(row.get("related_relations")) or _list_count(row.get("relation_hits")),
        "action_count": action_count,
        "source_hit_count": _list_count(row.get("source_hits")) or evidence_count,
        "text_length": len(f"{question}\n{answer}"),
        "question_length": len(question),
        "answer_length": len(answer),
        "review_signal_count": review_signal_count,
        "label_requires_review": requires_review,
        "label_contract_pass": _bool_int(row.get("contract_pass")),
    }


def build_feature_rows(runtime_answers_path: Path) -> list[dict[str, Any]]:
    return [_row_to_feature(row) for row in _read_jsonl(runtime_answers_path)]


def build_model_registry() -> dict[str, Any]:
    return {
        "purpose": "OBYBK GraphRAG answer contract와 운영 추천 결과를 lightweight ML baseline으로 반복 평가하기 위한 모델 후보 registry",
        "models": [
            {
                "id": "catboost_classifier",
                "package": "catboost",
                "optional": True,
                "use_case": "tabular + categorical feature가 섞인 review-required / quality-risk 분류",
                "why": "작은 feature engineering으로도 범주형/수치형 tabular baseline을 빠르게 만들 수 있음",
            },
            {
                "id": "random_forest_classifier",
                "package": "scikit-learn",
                "optional": False,
                "use_case": "작은 데이터에서 non-linear feature interaction baseline",
                "why": "설치와 실행이 가볍고 feature importance 설명이 쉬움",
            },
            {
                "id": "logistic_regression",
                "package": "scikit-learn",
                "optional": False,
                "use_case": "review-required 여부를 설명 가능한 linear baseline으로 검증",
                "why": "계수 기반으로 어떤 feature가 영향을 주는지 설명 가능",
            },
            {
                "id": "hist_gradient_boosting_classifier",
                "package": "scikit-learn",
                "optional": False,
                "use_case": "CatBoost 설치 전 gradient boosting 계열 fallback",
                "why": "external heavy dependency 없이 boosting baseline을 시험 가능",
            },
            {
                "id": "isolation_forest",
                "package": "scikit-learn",
                "optional": False,
                "use_case": "근거 부족·관계 누락 같은 anomalous answer 탐지",
                "why": "라벨이 부족한 초기 단계에서 quality-risk 후보를 찾을 수 있음",
            },
        ],
    }


def build_run_matrix() -> dict[str, Any]:
    return {
        "execution_order": [
            "prepare_features",
            "train_sklearn_baseline",
            "train_catboost_optional",
            "export_predictions",
            "handoff_pgvector",
            "serve_fastapi",
        ],
        "jobs": [
            {"id": "prepare_features", "command": "python tools/scripts/rag/ml_execution_pack.py --runtime-answers <jsonl> --output-dir <dir>"},
            {"id": "train_sklearn_baseline", "command": "python tools/scripts/rag/ml_execution_pack.py --runtime-answers <jsonl> --output-dir <dir> --run-baseline"},
            {"id": "train_catboost_optional", "command": "python tools/scripts/rag/train_catboost_optional.py --features <ml_feature_table.csv>", "status": "planned_optional"},
            {"id": "export_predictions", "artifact": "ml_baseline_metrics.json"},
            {"id": "handoff_pgvector", "artifact": "pgvector_seed.jsonl"},
            {"id": "serve_fastapi", "artifact": "FastAPI endpoints read runtime answers, ML features, and pgvector seed"},
        ],
    }


def build_catboost_pool_schema() -> dict[str, Any]:
    return {
        "target_candidates": ["label_requires_review", "label_contract_pass"],
        "default_target": "label_requires_review",
        "id_column": "question_id",
        "text_features": ["question", "answer"],
        "numeric_features": NUMERIC_FEATURE_COLUMNS,
        "cat_features": [],
        "notes": [
            "CatBoost가 설치되어 있으면 Pool(text_features=...)로 바로 연결 가능하다.",
            "초기 MVP에서는 scikit-learn baseline을 기본 실행하고 CatBoost는 optional 고급 baseline으로 둔다.",
        ],
    }


def build_ml_execution_pack(runtime_answers_path: Path | str, output_dir: Path | str) -> MlExecutionPackResult:
    runtime_answers_path = Path(runtime_answers_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = build_feature_rows(runtime_answers_path)
    feature_csv = output_dir / "ml_feature_table.csv"
    feature_jsonl = output_dir / "ml_feature_table.jsonl"
    registry_path = output_dir / "model_registry.json"
    run_matrix_path = output_dir / "ml_run_matrix.json"
    catboost_schema_path = output_dir / "catboost_pool_schema.json"
    report_path = output_dir / "ml_execution_pack_report.md"

    with feature_csv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    feature_jsonl.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    _write_json(registry_path, build_model_registry())
    _write_json(run_matrix_path, build_run_matrix())
    _write_json(catboost_schema_path, build_catboost_pool_schema())

    report_path.write_text(
        "\n".join(
            [
                "# Timestamp: 2026-05-18 16:52:00",
                "",
                "# ML Execution Pack Report",
                "",
                f"- runtime answers: `{runtime_answers_path}`",
                f"- feature rows: {len(rows)}",
                "- default baseline: scikit-learn RandomForestClassifier if available",
                "- optional model: CatBoostClassifier for richer tabular/text baseline",
                "- handoff: `ml_feature_table.jsonl` can be served by FastAPI and linked with pgvector seed metadata",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return MlExecutionPackResult(
        output_dir=output_dir,
        feature_table_csv=feature_csv,
        feature_table_jsonl=feature_jsonl,
        model_registry_path=registry_path,
        run_matrix_path=run_matrix_path,
        catboost_pool_schema_path=catboost_schema_path,
        report_path=report_path,
        row_count=len(rows),
    )


def _load_feature_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _write_baseline_metrics(output_dir: Path, payload: dict[str, Any]) -> BaselineResult:
    metrics_path = output_dir / "ml_baseline_metrics.json"
    report_path = output_dir / "ml_baseline_report.md"
    _write_json(metrics_path, payload)
    report_path.write_text(
        "\n".join(
            [
                "# Timestamp: 2026-05-18 16:52:00",
                "",
                "# ML Baseline Report",
                "",
                f"- model_family: {payload['model_family']}",
                f"- status: {payload['status']}",
                f"- target: {payload['target']}",
                f"- row_count: {payload['row_count']}",
                f"- training_accuracy: {payload.get('training_accuracy', 'n/a')}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return BaselineResult(
        output_dir=output_dir,
        metrics_path=metrics_path,
        report_path=report_path,
        model_family=str(payload["model_family"]),
        status=str(payload["status"]),
        row_count=int(payload["row_count"]),
        target=str(payload["target"]),
    )


def run_lightweight_baseline(feature_table_csv: Path | str, output_dir: Path | str, target: str = "label_requires_review") -> BaselineResult:
    feature_table_csv = Path(feature_table_csv)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = _load_feature_csv(feature_table_csv)

    if not rows:
        return _write_baseline_metrics(output_dir, {"model_family": "diagnostic", "status": "no_rows", "target": target, "row_count": 0})
    labels = [int(row.get(target, "0") or 0) for row in rows]
    if len(set(labels)) < 2:
        return _write_baseline_metrics(
            output_dir,
            {"model_family": "diagnostic", "status": "single_class", "target": target, "row_count": len(rows), "class_values": sorted(set(labels))},
        )

    x_values = [[float(row[column] or 0) for column in NUMERIC_FEATURE_COLUMNS] for row in rows]

    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score

        clf = RandomForestClassifier(n_estimators=32, random_state=42, min_samples_leaf=1)
        clf.fit(x_values, labels)
        predictions = clf.predict(x_values)
        accuracy = float(accuracy_score(labels, predictions))
        importances = {column: float(value) for column, value in zip(NUMERIC_FEATURE_COLUMNS, clf.feature_importances_)}
        payload = {
            "model_family": "sklearn",
            "model_id": "random_forest_classifier",
            "status": "trained_on_all_rows_smoke",
            "target": target,
            "row_count": len(rows),
            "training_accuracy": accuracy,
            "feature_importance": importances,
            "note": "Small smoke baseline; use holdout/cross-validation when row_count grows.",
        }
        return _write_baseline_metrics(output_dir, payload)
    except Exception as error:  # pragma: no cover - fallback for minimal envs
        predictions = [1 if (float(row["review_signal_count"]) > 0) else 0 for row in rows]
        accuracy = sum(int(pred == label) for pred, label in zip(predictions, labels)) / len(labels)
        return _write_baseline_metrics(
            output_dir,
            {
                "model_family": "rule_fallback",
                "status": "sklearn_unavailable",
                "target": target,
                "row_count": len(rows),
                "training_accuracy": accuracy,
                "error": str(error),
            },
        )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build OBYBK ML execution pack from GraphRAG runtime answers.")
    parser.add_argument("--runtime-answers", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-baseline", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    pack = build_ml_execution_pack(args.runtime_answers, args.output_dir)
    result: dict[str, Any] = {
        "feature_rows": pack.row_count,
        "feature_table_csv": str(pack.feature_table_csv),
        "model_registry": str(pack.model_registry_path),
    }
    if args.run_baseline:
        baseline = run_lightweight_baseline(pack.feature_table_csv, args.output_dir)
        result["baseline_metrics"] = str(baseline.metrics_path)
        result["baseline_status"] = baseline.status
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
