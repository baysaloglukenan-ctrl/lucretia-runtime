from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from ..provider_models import utc_now_iso
from .adapter import (
    ComfyI2VRequest,
    _new_job,
    _output_dir,
    _transition,
)
from .job_store import load_jobs, upsert_job
from .workflow_patch import load_workflow, validate_workflow


_CLAIM_LOCK = threading.Lock()


def _worker_status_path(root: Path) -> Path:
    path = root / "data" / "generated" / "comfy" / "relay_worker.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _record_worker_heartbeat(root: Path, worker_id: str) -> None:
    path = _worker_status_path(root)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps({"worker_id": worker_id, "last_seen": utc_now_iso()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(path)


def relay_worker_status(root: Path, *, max_age_seconds: int = 35, public: bool = False) -> dict:
    path = _worker_status_path(root)
    payload: dict = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            payload = loaded if isinstance(loaded, dict) else {}
        except Exception:
            payload = {}
    last_seen = str(payload.get("last_seen", ""))
    age_seconds: float | None = None
    if last_seen:
        try:
            then = datetime.fromisoformat(last_seen)
            if then.tzinfo is None:
                then = then.replace(tzinfo=timezone.utc)
            age_seconds = max(0.0, (datetime.now(timezone.utc) - then).total_seconds())
        except ValueError:
            age_seconds = None
    status = {
        "connected": age_seconds is not None and age_seconds <= max_age_seconds,
        "last_seen": last_seen,
        "seconds_since_seen": round(age_seconds, 1) if age_seconds is not None else None,
    }
    if not public:
        status["worker_id"] = str(payload.get("worker_id", ""))
    return status


def enqueue_relay_job(root: Path, request: ComfyI2VRequest) -> dict:
    source = root / request.image_path if not Path(request.image_path).is_absolute() else Path(request.image_path)
    if not source.exists():
        raise FileNotFoundError(f"I2V source image not found: {source}")
    workflow = root / request.workflow_path if not Path(request.workflow_path).is_absolute() else Path(request.workflow_path)
    report = validate_workflow(load_workflow(workflow), require_i2v=True)
    if not report.get("valid"):
        raise RuntimeError(f"Workflow validation failed: {report.get('errors', [])}")
    job = _new_job(root, request)
    job["workflow_validation"] = report
    job["relay"] = {"worker_id": "", "claimed_at": "", "heartbeat_at": ""}
    return _transition(root, job, "relay_queued", status="relay_queued", details={"mode": "relay"})


def claim_relay_job(root: Path, worker_id: str) -> dict | None:
    with _CLAIM_LOCK:
        _record_worker_heartbeat(root, worker_id)
        for job in load_jobs(root):
            if job.get("status") != "relay_queued":
                continue
            now = utc_now_iso()
            job["relay"] = {"worker_id": worker_id, "claimed_at": now, "heartbeat_at": now}
            _transition(root, job, "relay_claimed", status="relay_claimed", details={"worker_id": worker_id})
            return {
                "job_id": job["job_id"],
                "image_url": f"/worker/jobs/{job['job_id']}/source",
                "request": {
                    "prompt": job.get("prompt", ""),
                    "negative_prompt": job.get("negative_prompt", ""),
                    "seed": job.get("seed", 12345),
                    "frames": job.get("frames", 9),
                    "width": job.get("width", 512),
                    "height": job.get("height", 320),
                    "workflow_path": job.get("workflow_path", "workflows/comfy/ltx23_i2v_api.json"),
                    "generate_audio": bool(job.get("generate_audio", False)),
                },
            }
    return None


def relay_source_path(root: Path, job_id: str) -> Path | None:
    job = next((item for item in load_jobs(root) if item.get("job_id") == job_id), None)
    if not job:
        return None
    source = root / str(job.get("source_image", ""))
    return source if source.exists() and source.is_file() else None


def update_relay_job(root: Path, job_id: str, payload: dict) -> dict:
    job = next((item for item in load_jobs(root) if item.get("job_id") == job_id), None)
    if not job:
        raise KeyError(job_id)
    relay = job.setdefault("relay", {})
    relay["heartbeat_at"] = utc_now_iso()
    for key in ("local_job_id", "prompt_id"):
        if payload.get(key):
            job[key] = str(payload[key]) if key == "prompt_id" else payload[key]
    status = str(payload.get("status", "relay_running"))
    error = str(payload.get("error", ""))
    stage = "relay_failed" if status == "failed" else "relay_running"
    updated = _transition(root, job, stage, status=status, details=payload, error=error)
    if status == "failed":
        metadata = job.get("metadata", {}) if isinstance(job.get("metadata"), dict) else {}
        if metadata.get("production_id") and metadata.get("scene_id"):
            from ..production import mark_scene_failed

            mark_scene_failed(root, str(metadata["production_id"]), str(metadata["scene_id"]), error)
    return updated


def complete_relay_job(root: Path, job_id: str, filename: str, data: bytes, prompt_id: str = "") -> dict:
    job = next((item for item in load_jobs(root) if item.get("job_id") == job_id), None)
    if not job:
        raise KeyError(job_id)
    safe_name = Path(filename or f"{job_id}.mp4").name
    if Path(safe_name).suffix.lower() not in {".mp4", ".webm", ".mov"}:
        safe_name += ".mp4"
    output = _output_dir(root) / f"{job_id}_{safe_name}"
    output.write_bytes(data)
    job["output_path"] = str(output.relative_to(root)).replace("\\", "/")
    job["built_at"] = utc_now_iso()
    if prompt_id:
        job["prompt_id"] = prompt_id
    upsert_job(root, job)
    completed = _transition(
        root,
        job,
        "import_completed",
        status="built",
        details={"output_path": job["output_path"], "source": "render_relay_worker"},
    )
    metadata = job.get("metadata", {}) if isinstance(job.get("metadata"), dict) else {}
    if metadata.get("production_id") and metadata.get("scene_id"):
        from ..production import record_scene_output

        record_scene_output(root, str(metadata["production_id"]), str(metadata["scene_id"]), job["output_path"])
        if metadata.get("source") == "autonomous_production":
            from ..autonomous_production import advance_original_reel

            advance_original_reel(root, str(metadata["production_id"]), str(metadata["scene_id"]))
    return completed
