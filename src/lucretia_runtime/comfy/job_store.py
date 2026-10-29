from __future__ import annotations

import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_JOB_LOCK = threading.RLock()


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def comfy_generated_dir(root: Path) -> Path:
    path = root / "data" / "generated" / "comfy"
    path.mkdir(parents=True, exist_ok=True)
    return path


def comfy_inputs_dir(root: Path) -> Path:
    path = comfy_generated_dir(root) / "inputs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def comfy_debug_dir(root: Path) -> Path:
    path = comfy_generated_dir(root) / "debug"
    path.mkdir(parents=True, exist_ok=True)
    return path


def job_debug_dir(root: Path, job_id: str) -> Path:
    safe_job_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(job_id)).strip("._") or "unknown_job"
    path = comfy_debug_dir(root) / safe_job_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def jobs_path(root: Path) -> Path:
    return comfy_generated_dir(root) / "i2v_jobs.json"


def load_jobs(root: Path) -> list[dict]:
    with _JOB_LOCK:
        path = jobs_path(root)
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, list) else []
        except Exception:
            return []


def save_jobs(root: Path, jobs: list[dict]) -> None:
    with _JOB_LOCK:
        path = jobs_path(root)
        tmp_path = path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(jobs, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, path)


def upsert_job(root: Path, job: dict) -> None:
    with _JOB_LOCK:
        jobs = load_jobs(root)
        job_id = job.get("job_id")
        updated = False
        for idx, existing in enumerate(jobs):
            if existing.get("job_id") == job_id:
                jobs[idx] = job
                updated = True
                break
        if not updated:
            jobs.insert(0, job)
        save_jobs(root, jobs[:100])


def write_debug_json(root: Path, job_id: str, filename: str, payload: Any) -> Path:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(filename).name)
    if not safe_name.endswith(".json"):
        safe_name += ".json"
    path = job_debug_dir(root, job_id) / safe_name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return path


def append_job_event(root: Path, job_id: str, stage: str, *, status: str, details: dict | None = None) -> dict:
    event = {
        "at": _utc_now_iso(),
        "stage": stage,
        "status": status,
        "details": details or {},
    }
    path = job_debug_dir(root, job_id) / "events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return event
