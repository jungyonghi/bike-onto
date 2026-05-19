# Timestamp: 2026-04-20 18:24:07
# Timestamp: 2026-04-20 20:55:00
# Timestamp: 2026-04-20 21:10:00

from __future__ import annotations

import csv
import json
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .schemas import CandidateRecord, RawCandidateRecord


def to_serializable(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [to_serializable(item) for item in value]
    if isinstance(value, dict):
        return {key: to_serializable(item) for key, item in value.items()}
    return value


def create_run_output_dir(base_output_dir: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = base_output_dir / f"run_{timestamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def persist_phase_outputs(output_dir: Path, phase_outputs: dict[str, Any]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    persisted: dict[str, str] = {}
    for filename, payload in phase_outputs.items():
        path = output_dir / filename
        path.write_text(
            json.dumps(to_serializable(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        persisted[filename] = str(path)
    return persisted


def persist_candidate_records_csv(
    output_dir: Path,
    filename: str,
    records: list[CandidateRecord],
) -> str:
    return _persist_dataclass_csv(output_dir, filename, records, list(CandidateRecord.__dataclass_fields__.keys()))


def persist_raw_candidate_records_csv(
    output_dir: Path,
    filename: str,
    records: list[RawCandidateRecord],
) -> str:
    return _persist_dataclass_csv(output_dir, filename, records, list(RawCandidateRecord.__dataclass_fields__.keys()))


def _persist_dataclass_csv(
    output_dir: Path,
    filename: str,
    records: list[Any],
    fieldnames: list[str],
) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / filename
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(f"# Timestamp: {timestamp}\n")
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            row = record.to_dict() if hasattr(record, "to_dict") else dict(record)
            if "antonyms" in row and isinstance(row["antonyms"], list):
                row["antonyms"] = ", ".join(row["antonyms"])
            writer.writerow(row)

    return str(path)
