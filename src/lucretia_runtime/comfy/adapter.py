from __future__ import annotations

import os
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from ..provider_models import utc_now_iso
from .client import ComfyClient, ComfyClientError
from .job_store import (
    append_job_event,
    comfy_inputs_dir,
    job_debug_dir,
    load_jobs,
    upsert_job,
    write_debug_json,
)
from .manager import ComfyManager
from .workflow_patch import (
    WorkflowValidationError,
    load_workflow,
    patch_ids_from_env,
    patch_workflow_with_report,
    strip_generated_audio,
    validate_workflow,
)


LOGICAL_BLOCKS = (
    ("engine", "ComfyUI engine"),
    ("workflow_load", "Workflow load"),
    ("workflow_validate", "Workflow validation"),
    ("source_stage", "Source image staging"),
    ("image_upload", "Image upload"),
    ("workflow_patch", "Workflow patch"),
    ("prompt_submit", "Prompt submit"),
    ("queue", "ComfyUI queue"),
    ("execute", "Workflow execution"),
    ("output_detect", "Output detection"),
    ("download", "Output download"),
    ("import", "Lucreția import"),
)

STAGE_TO_BLOCK = {
    "job_created": None,
    "engine_starting": "engine",
    "engine_ready": "engine",
    "workflow_loading": "workflow_load",
    "workflow_loaded": "workflow_load",
    "workflow_validating": "workflow_validate",
    "workflow_validation_failed": "workflow_validate",
    "workflow_validated": "workflow_validate",
    "source_staging": "source_stage",
    "source_staged": "source_stage",
    "image_uploading": "image_upload",
    "image_uploaded": "image_upload",
    "workflow_patching": "workflow_patch",
    "workflow_patched": "workflow_patch",
    "prompt_submitting": "prompt_submit",
    "prompt_submitted": "prompt_submit",
    "queued_in_comfy": "queue",
    "executing_in_comfy": "execute",
    "history_poll_started": "execute",
    "comfy_execution_failed": "execute",
    "output_missing": "output_detect",
    "output_detected": "output_detect",
    "download_started": "download",
    "download_finished": "download",
    "import_completed": "import",
    "job_failed": None,
    "relay_queued": "queue",
    "relay_claimed": "queue",
    "relay_running": "execute",
    "relay_failed": "execute",
}

TERMINAL_STAGES = {
    "engine_ready",
    "workflow_loaded",
    "workflow_validated",
    "source_staged",
    "image_uploaded",
    "workflow_patched",
    "prompt_submitted",
    "output_detected",
    "download_finished",
    "import_completed",
}

RUNNING_STAGES = {
    "engine_starting",
    "workflow_loading",
    "workflow_validating",
    "source_staging",
    "image_uploading",
    "workflow_patching",
    "prompt_submitting",
    "queued_in_comfy",
    "executing_in_comfy",
    "history_poll_started",
    "download_started",
    "relay_queued",
    "relay_claimed",
    "relay_running",
}


@dataclass(frozen=True)
class ComfyI2VRequest:
    image_path: str
    prompt: str
    negative_prompt: str = ""
    seed: int = 12345
    frames: int = 9
    width: int = 512
    height: int = 320
    workflow_path: str = "workflows/comfy/ltx23_i2v_api.json"
    generate_audio: bool = False
    metadata: dict | None = None

    def __post_init__(self) -> None:
        if self.generate_audio:
            raise ValueError(
                "AI-generated audio is disabled. Add child-friendly sound in the separate post-production stage."
            )


def _output_dir(root: Path) -> Path:
    path = root / "data" / "generated" / "videos"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _relative(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _safe_copy_source(root: Path, image_path: str) -> Path:
    source = root / image_path if not Path(image_path).is_absolute() else Path(image_path)
    if not source.exists():
        raise FileNotFoundError(f"I2V source image not found: {source}")
    dest = comfy_inputs_dir(root) / f"I2V_SRC_{int(time.time())}_{source.name}"
    shutil.copyfile(source, dest)
    return dest


def _find_first_output(history_payload: dict, prompt_id: str) -> dict | None:
    job = history_payload.get(prompt_id) or {}
    outputs = job.get("outputs", {}) if isinstance(job, dict) else {}
    for node_id, node_data in outputs.items():
        if not isinstance(node_data, dict):
            continue
        for key in ("gifs", "videos", "images"):
            items = node_data.get(key) or []
            if items:
                item = dict(items[0])
                item["kind"] = key
                item["node_id"] = str(node_id)
                return item
    return None


def _history_job(history_payload: dict, prompt_id: str) -> dict:
    value = history_payload.get(prompt_id)
    return value if isinstance(value, dict) else {}


def _history_execution_error(history_payload: dict, prompt_id: str) -> dict | None:
    history_job = _history_job(history_payload, prompt_id)
    status = history_job.get("status", {}) if isinstance(history_job, dict) else {}
    messages = status.get("messages", []) if isinstance(status, dict) else []
    for message in messages:
        if not isinstance(message, list) or len(message) < 2:
            continue
        kind = str(message[0])
        details = message[1] if isinstance(message[1], dict) else {"message": message[1]}
        if kind in {"execution_error", "execution_interrupted", "execution_cached_error"}:
            return {"kind": kind, **details}
    return None


def _history_completed(history_payload: dict, prompt_id: str) -> bool:
    history_job = _history_job(history_payload, prompt_id)
    status = history_job.get("status", {}) if isinstance(history_job, dict) else {}
    return bool(status.get("completed")) if isinstance(status, dict) else False


def _queue_state(queue_payload: dict, prompt_id: str) -> str:
    for key, state in (("queue_running", "executing"), ("queue_pending", "queued")):
        items = queue_payload.get(key, []) if isinstance(queue_payload, dict) else []
        for item in items:
            if isinstance(item, (list, tuple)) and any(str(value) == prompt_id for value in item[:3]):
                return state
            if isinstance(item, dict) and str(item.get("prompt_id", "")) == prompt_id:
                return state
    return "unknown"


def _new_job(root: Path, request: ComfyI2VRequest) -> dict:
    job_id = f"CI2V_{uuid.uuid4().hex[:12].upper()}"
    debug_dir = job_debug_dir(root, job_id)
    now = utc_now_iso()
    job = {
        "job_id": job_id,
        "prompt_id": "",
        "status": "preparing",
        "lifecycle_status": "preparing",
        "current_stage": "job_created",
        "current_block": "",
        "provider": "comfyui",
        "source_image": request.image_path,
        "uploaded_image": "",
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "seed": request.seed,
        "frames": request.frames,
        "width": request.width,
        "height": request.height,
        "workflow_path": request.workflow_path,
        "generate_audio": request.generate_audio,
        "workflow_validation": {},
        "workflow_patch": {},
        "logical_blocks": [
            {"id": block_id, "label": label, "status": "pending", "stage": "", "updated_at": "", "error": ""}
            for block_id, label in LOGICAL_BLOCKS
        ],
        "events": [],
        "artifacts": {},
        "debug_dir": _relative(root, debug_dir),
        "metadata": request.metadata or {},
        "created_at": now,
        "stage_updated_at": now,
        "submitted_at": "",
        "output_path": "",
        "provider_output": {},
        "error": "",
    }
    upsert_job(root, job)
    write_debug_json(
        root,
        job_id,
        "request.json",
        {
            "job_id": job_id,
            "image_path": request.image_path,
            "prompt": request.prompt,
            "negative_prompt": request.negative_prompt,
            "seed": request.seed,
            "frames": request.frames,
            "width": request.width,
            "height": request.height,
            "workflow_path": request.workflow_path,
            "generate_audio": request.generate_audio,
            "metadata": request.metadata or {},
        },
    )
    _transition(root, job, "job_created", status="preparing", details={"debug_dir": job["debug_dir"]})
    return job


def _block_status_for_stage(stage: str, failed: bool) -> str:
    if failed:
        return "failed"
    if stage in TERMINAL_STAGES:
        return "completed"
    if stage in RUNNING_STAGES:
        return "running"
    return "pending"


def _transition(
    root: Path,
    job: dict,
    stage: str,
    *,
    status: str | None = None,
    details: dict | None = None,
    error: str = "",
) -> dict:
    failed = bool(error) or stage.endswith("_failed") or stage in {"output_missing", "job_failed"}
    lifecycle_status = status or job.get("lifecycle_status") or job.get("status", "unknown")
    event = append_job_event(root, job["job_id"], stage, status=lifecycle_status, details=details)
    job["current_stage"] = stage
    job["stage_updated_at"] = event["at"]
    if status:
        job["lifecycle_status"] = status
        job["status"] = status if status in {"built", "failed"} else stage
    if error:
        job["error"] = error
    block_id = STAGE_TO_BLOCK.get(stage)
    if block_id:
        job["current_block"] = block_id
        for block in job.get("logical_blocks", []):
            if block.get("id") == block_id:
                block["status"] = _block_status_for_stage(stage, failed)
                block["stage"] = stage
                block["updated_at"] = event["at"]
                block["error"] = error
                break
    job.setdefault("events", []).append(event)
    job["events"] = job["events"][-60:]
    upsert_job(root, job)
    write_debug_json(root, job["job_id"], "job_manifest.json", job)
    return job


def _record_artifact(root: Path, job: dict, key: str, path: Path) -> None:
    job.setdefault("artifacts", {})[key] = _relative(root, path)
    upsert_job(root, job)


def _fail(root: Path, job: dict, stage: str, exc: Exception, *, details: dict | None = None) -> dict:
    payload = dict(details or {})
    if isinstance(exc, ComfyClientError):
        payload["http_status"] = exc.status_code
        payload["comfy_payload"] = exc.payload
        if exc.payload is not None:
            path = write_debug_json(root, job["job_id"], "comfy_error_response.json", exc.payload)
            _record_artifact(root, job, "comfy_error_response", path)
    if isinstance(exc, WorkflowValidationError):
        payload["validation"] = exc.report
    return _transition(root, job, stage, status="failed", details=payload, error=str(exc))


def comfy_status(root: Path) -> dict:
    manager = ComfyManager()
    status = manager.status()
    jobs = load_jobs(root)
    status["jobs"] = len(jobs)
    status["active_jobs"] = len([job for job in jobs if job.get("status") not in {"built", "failed"}])
    status["failed_jobs"] = len([job for job in jobs if job.get("status") == "failed"])
    return status


def list_i2v_jobs(root: Path) -> list[dict]:
    return load_jobs(root)


def submit_i2v_job(
    root: Path,
    request: ComfyI2VRequest,
    auto_start: bool = True,
    *,
    raise_on_error: bool = True,
) -> dict:
    job = _new_job(root, request)
    try:
        manager = ComfyManager()
        _transition(root, job, "engine_starting", status="preparing", details={"url": manager.url, "auto_start": auto_start})
        if auto_start:
            manager.start(wait_seconds=int(os.environ.get("LUCRETIA_COMFY_START_TIMEOUT", "30")))
        elif not manager.health():
            raise RuntimeError("ComfyUI is not running and auto_start is false.")
        _transition(root, job, "engine_ready", status="preparing", details={"url": manager.url})
        client = ComfyClient(manager.url)

        workflow_file = root / request.workflow_path if not Path(request.workflow_path).is_absolute() else Path(request.workflow_path)
        job["workflow_path"] = _relative(root, workflow_file)
        _transition(root, job, "workflow_loading", status="preparing", details={"path": job["workflow_path"]})
        workflow = load_workflow(workflow_file)
        workflow, audio_report = strip_generated_audio(workflow)
        job["audio_profile"] = audio_report
        original_path = write_debug_json(root, job["job_id"], "workflow_original.json", workflow)
        _record_artifact(root, job, "workflow_original", original_path)
        _transition(root, job, "workflow_loaded", status="preparing", details={"node_count": len(workflow)})

        _transition(root, job, "workflow_validating", status="preparing")
        validation = validate_workflow(workflow, require_i2v=True)
        job["workflow_validation"] = validation
        validation_path = write_debug_json(root, job["job_id"], "workflow_validation.json", validation)
        _record_artifact(root, job, "workflow_validation", validation_path)
        if not validation.get("valid"):
            raise WorkflowValidationError(validation)
        _transition(
            root,
            job,
            "workflow_validated",
            status="preparing",
            details={"workflow_type": validation.get("workflow_type"), "roles": validation.get("roles")},
        )

        _transition(root, job, "source_staging", status="preparing", details={"source": request.image_path})
        local_source = _safe_copy_source(root, request.image_path)
        job["staged_source"] = _relative(root, local_source)
        _transition(root, job, "source_staged", status="preparing", details={"staged_source": job["staged_source"]})

        _transition(root, job, "image_uploading", status="preparing", details={"filename": local_source.name})
        upload = client.upload_image(local_source)
        upload_path = write_debug_json(root, job["job_id"], "image_upload_response.json", upload)
        _record_artifact(root, job, "image_upload_response", upload_path)
        comfy_image_name = upload.get("name") or local_source.name
        if upload.get("subfolder"):
            comfy_image_name = f"{upload['subfolder']}/{comfy_image_name}"
        job["uploaded_image"] = comfy_image_name
        _transition(root, job, "image_uploaded", status="preparing", details={"uploaded_image": comfy_image_name})

        _transition(root, job, "workflow_patching", status="preparing")
        patched, patch_report = patch_workflow_with_report(
            workflow,
            image_name=comfy_image_name,
            prompt=request.prompt,
            negative_prompt=request.negative_prompt,
            seed=request.seed,
            frames=request.frames,
            width=request.width,
            height=request.height,
            strict=True,
            **patch_ids_from_env(),
        )
        job["workflow_patch"] = patch_report
        patch_path = write_debug_json(root, job["job_id"], "workflow_patch_report.json", patch_report)
        patched_path = write_debug_json(root, job["job_id"], "workflow_patched.json", patched)
        _record_artifact(root, job, "workflow_patch_report", patch_path)
        _record_artifact(root, job, "workflow_patched", patched_path)
        _transition(
            root,
            job,
            "workflow_patched",
            status="preparing",
            details={"patched_fields": patch_report.get("patched_fields"), "resolved_nodes": patch_report.get("resolved_nodes")},
        )

        _transition(root, job, "prompt_submitting", status="submitting")
        submitted = client.submit_prompt(patched)
        submit_path = write_debug_json(root, job["job_id"], "comfy_submit_response.json", submitted)
        _record_artifact(root, job, "comfy_submit_response", submit_path)
        prompt_id = submitted.get("prompt_id")
        if not prompt_id:
            raise RuntimeError(f"ComfyUI did not return prompt_id: {submitted}")
        job["prompt_id"] = str(prompt_id)
        job["submitted_at"] = utc_now_iso()
        _transition(root, job, "prompt_submitted", status="submitted", details={"prompt_id": prompt_id})
        _transition(root, job, "queued_in_comfy", status="queued", details={"prompt_id": prompt_id})
        return job
    except WorkflowValidationError as exc:
        _fail(root, job, "workflow_validation_failed", exc)
    except Exception as exc:
        _fail(root, job, "job_failed", exc)
    if raise_on_error:
        raise RuntimeError(job.get("error") or "ComfyUI I2V job failed")
    return job


def poll_i2v_jobs(root: Path, import_outputs: bool = True) -> list[dict]:
    manager = ComfyManager()
    if not manager.health():
        raise RuntimeError(f"ComfyUI is not running at {manager.url}.")
    client = ComfyClient(manager.url)
    jobs = load_jobs(root)
    changed = []
    for job in jobs:
        if job.get("status") in {"built", "failed"}:
            changed.append(job)
            continue
        prompt_id = str(job.get("prompt_id", ""))
        if not prompt_id:
            _fail(root, job, "job_failed", RuntimeError("Missing prompt_id"))
            changed.append(job)
            continue
        try:
            _transition(root, job, "history_poll_started", status="running", details={"prompt_id": prompt_id})
            queue_payload = client.queue()
            queue_path = write_debug_json(root, job["job_id"], "comfy_queue_response.json", queue_payload)
            _record_artifact(root, job, "comfy_queue_response", queue_path)
            queue_state = _queue_state(queue_payload, prompt_id)
            if queue_state == "queued":
                _transition(root, job, "queued_in_comfy", status="queued", details={"prompt_id": prompt_id})
            elif queue_state == "executing":
                _transition(root, job, "executing_in_comfy", status="running", details={"prompt_id": prompt_id})

            history = client.history(prompt_id)
            history_path = write_debug_json(root, job["job_id"], "comfy_history_response.json", history)
            _record_artifact(root, job, "comfy_history_response", history_path)
            execution_error = _history_execution_error(history, prompt_id)
            if execution_error:
                error = RuntimeError(
                    f"ComfyUI execution failed at node {execution_error.get('node_id', '?')}: "
                    f"{execution_error.get('exception_message') or execution_error.get('message') or execution_error}"
                )
                _fail(root, job, "comfy_execution_failed", error, details=execution_error)
                changed.append(job)
                continue

            output = _find_first_output(history, prompt_id)
            if not output:
                if _history_completed(history, prompt_id):
                    _fail(
                        root,
                        job,
                        "output_missing",
                        RuntimeError("ComfyUI marked the workflow complete but produced no video/image output."),
                    )
                else:
                    stage = "executing_in_comfy" if queue_state == "executing" else "queued_in_comfy"
                    status = "running" if queue_state == "executing" else "queued"
                    _transition(root, job, stage, status=status, details={"queue_state": queue_state})
                changed.append(job)
                continue

            job["provider_output"] = output
            _transition(root, job, "output_detected", status="running", details=output)
            filename = output.get("filename", "")
            subfolder = output.get("subfolder", "")
            file_type = output.get("type", "output")
            suffix = Path(filename).suffix or (".mp4" if output.get("kind") in {"gifs", "videos"} else ".png")
            local_name = f"I2V_{prompt_id[:8]}_{Path(filename).stem}{suffix}"
            local_path = _output_dir(root) / local_name
            if import_outputs:
                _transition(root, job, "download_started", status="running", details={"filename": filename})
                client.download_view(filename, local_path, subfolder=subfolder, file_type=file_type)
                _transition(root, job, "download_finished", status="running", details={"local_path": _relative(root, local_path)})
            job["output_path"] = _relative(root, local_path)
            job["built_at"] = utc_now_iso()
            _transition(root, job, "import_completed", status="built", details={"output_path": job["output_path"]})
            changed.append(job)
        except Exception as exc:
            _fail(root, job, "job_failed", exc)
            changed.append(job)
    return changed
