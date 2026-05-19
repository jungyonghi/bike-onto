# Timestamp: 2026-05-18 16:52:00

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class PgVectorIntegrationPackResult:
    output_dir: Path
    schema_sql_path: Path
    seed_jsonl_path: Path
    upsert_sql_path: Path
    query_examples_sql_path: Path
    report_path: Path
    seed_count: int
    vector_dim: int


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_no}")
        rows.append(payload)
    return rows


def hash_text_to_vector(text: str, dim: int = 16) -> list[float]:
    values: list[float] = []
    seed = text.encode("utf-8") or b"empty"
    counter = 0
    while len(values) < dim:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        counter += 1
        for byte in digest:
            values.append((byte / 127.5) - 1.0)
            if len(values) == dim:
                break
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [round(value / norm, 6) for value in values]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{value:.6f}" for value in vector) + "]"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _content_for_row(row: dict[str, Any]) -> str:
    return "\n".join(
        part
        for part in [
            str(row.get("question") or ""),
            str(row.get("answer") or row.get("final_answer") or row.get("preview") or ""),
        ]
        if part
    )


def _metadata_for_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "requires_review": bool(row.get("requires_review")),
        "contract_pass": bool(row.get("contract_pass")),
        "evidence_documents": row.get("evidence_documents") or row.get("source_hits") or [],
        "related_objects_count": len(row.get("related_objects") or []),
        "related_relations_count": len(row.get("related_relations") or row.get("relation_hits") or []),
        "recommended_actions_count": len(row.get("recommended_actions") or []),
    }


def build_pgvector_schema_sql(table_name: str, vector_dim: int) -> str:
    return f"""-- Timestamp: 2026-05-18 16:52:00
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS {table_name} (
  id text PRIMARY KEY,
  content text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
  embedding vector({vector_dim}) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS {table_name}_embedding_hnsw_idx
ON {table_name}
USING hnsw (embedding vector_cosine_ops);
"""


def build_pgvector_integration_pack(
    runtime_answers_path: Path | str,
    output_dir: Path | str,
    *,
    vector_dim: int = 16,
    table_name: str = "obybk_rag_documents",
) -> PgVectorIntegrationPackResult:
    runtime_answers_path = Path(runtime_answers_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(runtime_answers_path)
    seed_rows: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        item_id = str(row.get("id") or row.get("question_id") or f"answer-{index:04d}")
        content = _content_for_row(row)
        seed_rows.append(
            {
                "id": item_id,
                "content": content,
                "metadata": _metadata_for_row(row),
                "embedding": hash_text_to_vector(content, vector_dim),
            }
        )

    schema_path = output_dir / "pgvector_schema.sql"
    seed_path = output_dir / "pgvector_seed.jsonl"
    upsert_path = output_dir / "pgvector_upsert.sql"
    query_path = output_dir / "pgvector_query_examples.sql"
    report_path = output_dir / "pgvector_integration_report.md"

    schema_path.write_text(build_pgvector_schema_sql(table_name, vector_dim), encoding="utf-8")
    seed_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in seed_rows), encoding="utf-8")

    upsert_lines = ["-- Timestamp: 2026-05-18 16:52:00", "BEGIN;"]
    for row in seed_rows:
        metadata_json = json.dumps(row["metadata"], ensure_ascii=False)
        upsert_lines.append(
            " ".join(
                [
                    f"INSERT INTO {table_name} (id, content, metadata, embedding)",
                    f"VALUES ({_sql_literal(row['id'])}, {_sql_literal(row['content'])}, {_sql_literal(metadata_json)}::jsonb, '{vector_literal(row['embedding'])}'::vector)",
                    "ON CONFLICT (id) DO UPDATE SET content = EXCLUDED.content, metadata = EXCLUDED.metadata, embedding = EXCLUDED.embedding;",
                ]
            )
        )
    upsert_lines.append("COMMIT;")
    upsert_path.write_text("\n".join(upsert_lines) + "\n", encoding="utf-8")

    example_vector = vector_literal(hash_text_to_vector("오전 부족 위험 재배치 검토", vector_dim))
    query_path.write_text(
        f"""-- Timestamp: 2026-05-18 16:52:00
-- Example semantic search query. Replace the vector with an embedding generated by the production embedder.
SELECT id, content, metadata, 1 - (embedding <=> '{example_vector}'::vector) AS cosine_similarity
FROM {table_name}
ORDER BY embedding <=> '{example_vector}'::vector
LIMIT 5;

-- Review-required queue check.
SELECT id, metadata->>'requires_review' AS requires_review, metadata->>'contract_pass' AS contract_pass
FROM {table_name}
WHERE metadata->>'requires_review' = 'true';
""",
        encoding="utf-8",
    )

    report_path.write_text(
        "\n".join(
            [
                "# Timestamp: 2026-05-18 16:52:00",
                "",
                "# pgvector Integration Pack Report",
                "",
                f"- runtime answers: `{runtime_answers_path}`",
                f"- table: `{table_name}`",
                f"- vector_dim: {vector_dim}",
                f"- seed rows: {len(seed_rows)}",
                "- execution mode: artifact-first SQL pack; run schema/upsert SQL against PostgreSQL with pgvector enabled",
                "",
            ]
        ),
        encoding="utf-8",
    )

    return PgVectorIntegrationPackResult(
        output_dir=output_dir,
        schema_sql_path=schema_path,
        seed_jsonl_path=seed_path,
        upsert_sql_path=upsert_path,
        query_examples_sql_path=query_path,
        report_path=report_path,
        seed_count=len(seed_rows),
        vector_dim=vector_dim,
    )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Build pgvector SQL/seed artifacts from GraphRAG runtime answers.")
    parser.add_argument("--runtime-answers", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--vector-dim", type=int, default=16)
    parser.add_argument("--table-name", default="obybk_rag_documents")
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = build_pgvector_integration_pack(
        args.runtime_answers,
        args.output_dir,
        vector_dim=args.vector_dim,
        table_name=args.table_name,
    )
    print(
        json.dumps(
            {
                "seed_count": result.seed_count,
                "vector_dim": result.vector_dim,
                "schema_sql": str(result.schema_sql_path),
                "seed_jsonl": str(result.seed_jsonl_path),
                "upsert_sql": str(result.upsert_sql_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
