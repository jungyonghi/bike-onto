-- Timestamp: 2026-05-19 11:52:00
-- OBYBK RAG store PostgreSQL schema handoff
CREATE TABLE IF NOT EXISTS rag_runs (
  run_id TEXT PRIMARY KEY,
  created_at TIMESTAMPTZ NOT NULL,
  domain_dir TEXT,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS rag_artifacts (
  artifact_id BIGSERIAL PRIMARY KEY,
  run_id TEXT REFERENCES rag_runs(run_id),
  kind TEXT NOT NULL,
  path TEXT NOT NULL,
  meta_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS rag_evaluation_questions (
  question_id TEXT NOT NULL,
  run_id TEXT NOT NULL REFERENCES rag_runs(run_id),
  category TEXT,
  question TEXT,
  status TEXT,
  contract_pass BOOLEAN NOT NULL DEFAULT FALSE,
  requires_review BOOLEAN NOT NULL DEFAULT FALSE,
  llm_mode TEXT,
  data_gap_count INTEGER NOT NULL DEFAULT 0,
  payload_json JSONB NOT NULL,
  PRIMARY KEY(question_id, run_id)
);
CREATE TABLE IF NOT EXISTS review_queue (
  review_id BIGSERIAL PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES rag_runs(run_id),
  question_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  payload_json JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_snippets (
  key TEXT PRIMARY KEY,
  title TEXT,
  content TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '',
  hit_count INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_rag_eval_run ON rag_evaluation_questions(run_id);
CREATE INDEX IF NOT EXISTS idx_rag_eval_category ON rag_evaluation_questions(category);
CREATE INDEX IF NOT EXISTS idx_review_queue_run ON review_queue(run_id, status);
CREATE INDEX IF NOT EXISTS idx_agent_snippets_tags ON agent_snippets(tags);
