# Timestamp: 2026-05-19 12:50:00

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any

try:  # pragma: no cover - import availability is environment-specific
    import psycopg
    from psycopg import sql
except Exception:  # pragma: no cover
    psycopg = None
    sql = None

try:
    from .pgvector_integration_pack import hash_text_to_vector, vector_literal
except ImportError:  # Allow direct script execution.
    from pgvector_integration_pack import hash_text_to_vector, vector_literal


@dataclass(frozen=True)
class PgVectorStoreStatus:
    ok: bool
    dsn_present: bool
    extension_installed: bool
    table_exists: bool
    row_count: int
    vector_dim: int
    table_name: str
    error: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "dsn_present": self.dsn_present,
            "extension_installed": self.extension_installed,
            "table_exists": self.table_exists,
            "row_count": self.row_count,
            "vector_dim": self.vector_dim,
            "table_name": self.table_name,
            "error": self.error,
        }


def _require_psycopg() -> None:
    if psycopg is None or sql is None:
        raise RuntimeError("psycopg is required for live PostgreSQL/pgvector integration")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object at {path}:{line_no}")
        rows.append(payload)
    return rows


def _embedding_dim_from_text(value: str) -> int:
    numbers = re.findall(r"-?\d+(?:\.\d+)?(?:e[+-]?\d+)?", value, flags=re.I)
    return len(numbers)


def _tokens(text: str) -> set[str]:
    return {token for token in re.split(r"[^0-9A-Za-z가-힣]+", text.lower()) if len(token) >= 2}


def _table_identifier(table_name: str):
    _require_psycopg()
    if "." in table_name:
        schema, table = table_name.split(".", 1)
        return sql.Identifier(schema, table)
    return sql.Identifier(table_name)


def init_pgvector_schema(dsn: str, *, table_name: str = "obybk_rag_documents", vector_dim: int = 16) -> dict[str, Any]:
    _require_psycopg()
    if not dsn:
        raise ValueError("PostgreSQL DSN is required")
    table = _table_identifier(table_name)
    with psycopg.connect(dsn) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(
            sql.SQL(
                """
                CREATE TABLE IF NOT EXISTS {table} (
                  id text PRIMARY KEY,
                  content text NOT NULL,
                  metadata jsonb NOT NULL DEFAULT '{{}}'::jsonb,
                  embedding vector({vector_dim}) NOT NULL,
                  created_at timestamptz NOT NULL DEFAULT now()
                )
                """
            ).format(table=table, vector_dim=sql.Literal(int(vector_dim)))
        )
        conn.execute(
            sql.SQL("CREATE INDEX IF NOT EXISTS {index_name} ON {table} USING hnsw (embedding vector_cosine_ops)").format(
                index_name=sql.Identifier(f"{table_name.replace('.', '_')}_embedding_hnsw_idx"),
                table=table,
            )
        )
        conn.commit()
    return {"dsn_present": True, "table_name": table_name, "vector_dim": vector_dim}


def load_pgvector_seed(
    dsn: str,
    seed_jsonl: Path | str,
    *,
    table_name: str = "obybk_rag_documents",
    vector_dim: int | None = None,
) -> dict[str, Any]:
    _require_psycopg()
    seed_path = Path(seed_jsonl)
    rows = _read_jsonl(seed_path)
    if not rows:
        return {"table_name": table_name, "seed_jsonl": str(seed_path), "loaded_count": 0, "vector_dim": vector_dim or 0}
    inferred_dim = len(rows[0].get("embedding") or []) or vector_dim or 16
    init_pgvector_schema(dsn, table_name=table_name, vector_dim=int(vector_dim or inferred_dim))
    table = _table_identifier(table_name)
    with psycopg.connect(dsn) as conn:
        for row in rows:
            embedding = [float(value) for value in (row.get("embedding") or [])]
            conn.execute(
                sql.SQL(
                    """
                    INSERT INTO {table} (id, content, metadata, embedding)
                    VALUES (%s, %s, %s::jsonb, %s::vector)
                    ON CONFLICT (id) DO UPDATE
                    SET content = EXCLUDED.content,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                    """
                ).format(table=table),
                (
                    str(row.get("id")),
                    str(row.get("content") or ""),
                    json.dumps(row.get("metadata") or {}, ensure_ascii=False),
                    vector_literal(embedding),
                ),
            )
        conn.commit()
    return {"table_name": table_name, "seed_jsonl": str(seed_path), "loaded_count": len(rows), "vector_dim": int(vector_dim or inferred_dim)}


def pgvector_status(dsn: str, *, table_name: str = "obybk_rag_documents") -> PgVectorStoreStatus:
    _require_psycopg()
    if not dsn:
        return PgVectorStoreStatus(False, False, False, False, 0, 0, table_name, "missing_dsn")
    table = _table_identifier(table_name)
    try:
        with psycopg.connect(dsn, connect_timeout=5) as conn:
            extension_row = conn.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')").fetchone()
            extension_installed = bool(extension_row[0]) if extension_row else False
            regclass_row = conn.execute("SELECT to_regclass(%s)", (table_name,)).fetchone()
            table_exists = bool(regclass_row and regclass_row[0])
            row_count = 0
            vector_dim = 0
            if table_exists:
                count_row = conn.execute(sql.SQL("SELECT COUNT(*) FROM {table}").format(table=table)).fetchone()
                row_count = int(count_row[0]) if count_row else 0
                dim_row = conn.execute(sql.SQL("SELECT embedding::text FROM {table} LIMIT 1").format(table=table)).fetchone()
                vector_dim = _embedding_dim_from_text(str(dim_row[0])) if dim_row else 0
            return PgVectorStoreStatus(True, True, extension_installed, table_exists, row_count, vector_dim, table_name)
    except Exception as exc:
        return PgVectorStoreStatus(False, True, False, False, 0, 0, table_name, f"{type(exc).__name__}: {exc}")


def search_pgvector(
    dsn: str,
    question: str,
    *,
    table_name: str = "obybk_rag_documents",
    top_k: int = 3,
    vector_dim: int | None = None,
) -> list[dict[str, Any]]:
    _require_psycopg()
    if not dsn:
        raise ValueError("PostgreSQL DSN is required")
    status = pgvector_status(dsn, table_name=table_name)
    dim = int(vector_dim or status.vector_dim or 16)
    query_vector = vector_literal(hash_text_to_vector(question, dim))
    table = _table_identifier(table_name)
    with psycopg.connect(dsn) as conn:
        rows = conn.execute(
            sql.SQL(
                """
                SELECT id,
                       content,
                       metadata,
                       1 - (embedding <=> %s::vector) AS vector_score
                FROM {table}
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """
            ).format(table=table),
            (query_vector, query_vector, max(10, min(int(top_k) * 10, 100))),
        ).fetchall()
    matches: list[dict[str, Any]] = []
    query_tokens = _tokens(question)
    for row in rows:
        metadata = row[2]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        vector_score = float(row[3] or 0.0)
        token_overlap = len(query_tokens & _tokens(str(row[1] or "")))
        score = token_overlap + vector_score
        matches.append(
            {
                "id": row[0],
                "content": row[1],
                "metadata": metadata or {},
                "score": round(score, 6),
                "token_overlap": token_overlap,
                "vector_score": round(vector_score, 6),
                "retriever": "pgvector",
            }
        )
    matches.sort(key=lambda item: item["score"], reverse=True)
    return matches[: max(1, min(int(top_k), 50))]
