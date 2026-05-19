# Timestamp: 2026-05-18 16:55:00

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Iterable

try:
    from .pgvector_integration_pack import hash_text_to_vector
except ImportError:  # Allow direct script execution.
    from pgvector_integration_pack import hash_text_to_vector


@dataclass(frozen=True)
class ServiceArtifactPaths:
    runtime_answers_path: Path
    ml_feature_table_path: Path
    pgvector_seed_path: Path


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^0-9A-Za-z가-힣]+", text.lower()) if len(token) >= 2}


def _cosine(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def _search_seed(seed_rows: list[dict[str, Any]], question: str, top_k: int) -> list[dict[str, Any]]:
    if not seed_rows:
        return []
    query_tokens = _tokens(question)
    vector_dim = len(seed_rows[0].get("embedding") or []) or 16
    query_vector = hash_text_to_vector(question, vector_dim)
    scored: list[dict[str, Any]] = []
    for row in seed_rows:
        content = str(row.get("content") or "")
        overlap = len(query_tokens & _tokens(content))
        embedding = row.get("embedding") if isinstance(row.get("embedding"), list) else []
        vector_score = _cosine(query_vector, [float(value) for value in embedding])
        score = overlap + vector_score
        scored.append({**row, "score": round(float(score), 6), "token_overlap": overlap, "vector_score": round(float(vector_score), 6)})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[: max(1, min(top_k, 20))]


def create_app(
    *,
    runtime_answers_path: Path | str,
    ml_feature_table_path: Path | str,
    pgvector_seed_path: Path | str,
):
    try:
        from fastapi import FastAPI
        from pydantic import BaseModel, Field
    except Exception as error:  # pragma: no cover - dependency guard
        raise RuntimeError("FastAPI is required. Install with: pip install fastapi uvicorn") from error

    paths = ServiceArtifactPaths(
        runtime_answers_path=Path(runtime_answers_path),
        ml_feature_table_path=Path(ml_feature_table_path),
        pgvector_seed_path=Path(pgvector_seed_path),
    )

    class QueryRequest(BaseModel):
        question: str = Field(min_length=1)
        top_k: int = Field(default=3, ge=1, le=20)

    app = FastAPI(
        title="OBYBK Ontology-RAG Execution API",
        version="0.1.0",
        description="GraphRAG runtime answers, lightweight ML features, and pgvector handoff artifacts served through a FastAPI interface.",
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "runtime_answers_exists": paths.runtime_answers_path.exists(),
            "ml_features_exists": paths.ml_feature_table_path.exists(),
            "pgvector_seed_exists": paths.pgvector_seed_path.exists(),
        }

    @app.get("/answers")
    def answers(limit: int = 20) -> dict[str, Any]:
        rows = _read_jsonl(paths.runtime_answers_path)
        return {"count": len(rows), "items": rows[: max(1, min(limit, 100))]}

    @app.get("/ml/features")
    def ml_features(limit: int = 20) -> dict[str, Any]:
        rows = _read_jsonl(paths.ml_feature_table_path)
        return {"count": len(rows), "items": rows[: max(1, min(limit, 100))]}

    @app.get("/pgvector/status")
    def pgvector_status() -> dict[str, Any]:
        rows = _read_jsonl(paths.pgvector_seed_path)
        vector_dim = len(rows[0].get("embedding") or []) if rows else 0
        return {"seed_count": len(rows), "vector_dim": vector_dim, "seed_path": str(paths.pgvector_seed_path)}

    @app.post("/query")
    def query(request: QueryRequest) -> dict[str, Any]:
        seed_rows = _read_jsonl(paths.pgvector_seed_path)
        runtime_rows = {str(row.get("id") or row.get("question_id")): row for row in _read_jsonl(paths.runtime_answers_path)}
        matches = []
        for match in _search_seed(seed_rows, request.question, request.top_k):
            answer_row = runtime_rows.get(str(match.get("id")), {})
            matches.append(
                {
                    "id": match.get("id"),
                    "score": match.get("score"),
                    "token_overlap": match.get("token_overlap"),
                    "vector_score": match.get("vector_score"),
                    "content": match.get("content"),
                    "metadata": match.get("metadata"),
                    "answer": answer_row.get("answer") or answer_row.get("final_answer"),
                    "requires_review": bool((match.get("metadata") or {}).get("requires_review")),
                }
            )
        return {"question": request.question, "answer_count": len(matches), "matches": matches}

    return app


def write_smoke_contract(
    *,
    runtime_answers_path: Path,
    ml_feature_table_path: Path,
    pgvector_seed_path: Path,
    output_path: Path,
) -> Path:
    app = create_app(
        runtime_answers_path=runtime_answers_path,
        ml_feature_table_path=ml_feature_table_path,
        pgvector_seed_path=pgvector_seed_path,
    )
    payload = {
        "timestamp": "2026-05-18 16:52:00",
        "title": app.title,
        "routes": sorted(route.path for route in app.routes if hasattr(route, "path")),
        "runtime_answers_path": str(runtime_answers_path),
        "ml_feature_table_path": str(ml_feature_table_path),
        "pgvector_seed_path": str(pgvector_seed_path),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output_path


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Serve or smoke-test OBYBK Ontology-RAG FastAPI app.")
    parser.add_argument("--runtime-answers", required=True, type=Path)
    parser.add_argument("--ml-features", required=True, type=Path)
    parser.add_argument("--pgvector-seed", required=True, type=Path)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--smoke-output", type=Path, default=Path("fastapi_service_smoke_report.json"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8088)
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.smoke:
        path = write_smoke_contract(
            runtime_answers_path=args.runtime_answers,
            ml_feature_table_path=args.ml_features,
            pgvector_seed_path=args.pgvector_seed,
            output_path=args.smoke_output,
        )
        print(json.dumps({"ok": True, "smoke_report": str(path)}, ensure_ascii=False, indent=2))
        return

    import uvicorn

    app = create_app(
        runtime_answers_path=args.runtime_answers,
        ml_feature_table_path=args.ml_features,
        pgvector_seed_path=args.pgvector_seed,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
