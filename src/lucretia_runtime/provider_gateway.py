from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

from .mock_provider import build_mock_provider_asset
from .provider_models import ProviderAssetRequest, ProviderJob, safe_relative_path, utc_now_iso
from .runway_adapter import (
    extract_runway_output_url,
    poll_runway_task,
    runway_config_from_env,
    runway_status_from_payload,
    submit_runway_text_to_video,
)


PROVIDER_JOBS_DIR = Path("data/generated/provider_jobs")
PROVIDER_ASSETS_DIR = Path("data/generated/provider_assets")
PROVIDER_ASSEMBLY_DIR = Path("data/generated/assembly_provider")


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def provider_jobs_dir(root: Path) -> Path:
    path = root / PROVIDER_JOBS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def provider_assets_dir(root: Path) -> Path:
    path = root / PROVIDER_ASSETS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def provider_assembly_dir(root: Path) -> Path:
    path = root / PROVIDER_ASSEMBLY_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _job_manifest_path(root: Path, job_id: str) -> Path:
    return provider_jobs_dir(root) / f"{job_id}.json"


def _job_id(request: ProviderAssetRequest) -> str:
    basis = ":".join([
        request.provider,
        request.assembly_plan_id,
        request.episode_id,
        request.segment_id,
        request.scene_id,
        request.prompt,
    ])
    return "PJOB_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12].upper()


def _caption_for_order(plan: Dict[str, Any], order: int, fallback: str) -> str:
    captions = plan.get("caption_slots", [])
    if order - 1 < len(captions):
        item = captions[order - 1]
        return str(item.get("text", "") or item.get("caption", "") or fallback)
    return fallback


def request_from_segment(plan: Dict[str, Any], segment: Dict[str, Any], provider: str = "mock", width: int = 720, height: int = 1280) -> ProviderAssetRequest:
    order = int(segment.get("order", 1))
    scene_id = str(segment.get("scene_id", "SCN_UNKNOWN"))
    prompt = str(segment.get("prompt") or segment.get("description") or _caption_for_order(plan, order, scene_id))
    start = float(segment.get("start_time", 0))
    end = float(segment.get("end_time", start + 2))
    duration = float(segment.get("duration_seconds", max(0.1, end - start)))
    return ProviderAssetRequest(
        provider=provider,
        assembly_plan_id=str(plan.get("assembly_plan_id", "ASP_UNKNOWN")),
        episode_id=str(plan.get("episode_id", segment.get("episode_id", "EP_UNKNOWN"))),
        segment_id=str(segment.get("segment_id", f"SEG_{order:03d}")),
        scene_id=scene_id,
        render_job_id=str(segment.get("render_job_id", "RND_UNKNOWN")),
        prompt=prompt,
        duration_seconds=duration,
        width=width,
        height=height,
        seed=str(segment.get("seed") or f"{plan.get('assembly_plan_id', 'ASP_UNKNOWN')}:{scene_id}"),
        metadata={
            "order": order,
            "transition_hint": segment.get("transition"),
            "source": "assembly_plan_segment",
        },
    )


def save_job(root: Path, job: ProviderJob) -> Path:
    path = _job_manifest_path(root, job.job_id)
    path.write_text(json.dumps(job.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def read_job(root: Path, job_id: str) -> ProviderJob | None:
    path = _job_manifest_path(root, job_id)
    if not path.exists():
        return None
    return ProviderJob.from_dict(_read_json(path))


def list_jobs(root: Path) -> List[ProviderJob]:
    jobs: List[ProviderJob] = []
    for path in sorted(provider_jobs_dir(root).glob("PJOB_*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            jobs.append(ProviderJob.from_dict(_read_json(path)))
        except Exception:
            continue
    return jobs


def _submit_mock_provider_request(root: Path, job: ProviderJob) -> ProviderJob:
    try:
        running = job.with_status("running")
        save_job(root, running)
        output_path = build_mock_provider_asset(job.request, provider_assets_dir(root), running.job_id)
        built = running.with_status(
            "built",
            output_path=safe_relative_path(output_path, root),
            output_type="image/png",
            provider_response={
                "adapter": "mock_provider",
                "note": "Local deterministic mock asset. No external provider was called.",
            },
        )
        save_job(root, built)
        return built
    except Exception as exc:  # pragma: no cover
        failed = job.with_status("failed", error=str(exc))
        save_job(root, failed)
        return failed


def _submit_runway_provider_request(root: Path, job: ProviderJob) -> ProviderJob:
    try:
        submitting = job.with_status("submitting")
        save_job(root, submitting)
        response = submit_runway_text_to_video(submitting.request)
        submitted = submitting.with_status(
            "submitted",
            provider_response={
                "adapter": "runway_adapter",
                "task_id": response.get("task_id"),
                "runway_status": response.get("status"),
                "api_version": response.get("api_version"),
                "dry_run": response.get("dry_run", False),
                "raw": response.get("response", response),
            },
        )
        save_job(root, submitted)
        return submitted
    except Exception as exc:
        failed = job.with_status(
            "failed",
            error=str(exc),
            provider_response={"adapter": "runway_adapter", "configured": runway_config_from_env().configured},
        )
        save_job(root, failed)
        return failed


def submit_provider_request(root: Path, request: ProviderAssetRequest) -> ProviderJob:
    created = utc_now_iso()
    job = ProviderJob(
        job_id=_job_id(request),
        provider=request.provider,
        status="queued",
        request=request,
        created_at=created,
        updated_at=created,
    )
    save_job(root, job)

    if request.provider == "mock":
        return _submit_mock_provider_request(root, job)
    if request.provider == "runway":
        return _submit_runway_provider_request(root, job)

    failed = job.with_status("failed", error=f"Provider '{request.provider}' is not implemented.")
    save_job(root, failed)
    return failed


def submit_mock_jobs_for_plan(root: Path, assembly_plan_path: Path, width: int = 720, height: int = 1280) -> List[ProviderJob]:
    plan = _read_json(assembly_plan_path)
    jobs: List[ProviderJob] = []
    for segment in sorted(plan.get("timeline", []), key=lambda item: item.get("order", 0)):
        request = request_from_segment(plan, segment, provider="mock", width=width, height=height)
        jobs.append(submit_provider_request(root, request))
    summary = {
        "sprint": 11,
        "assembly_plan_id": plan.get("assembly_plan_id"),
        "episode_id": plan.get("episode_id"),
        "provider": "mock",
        "job_count": len(jobs),
        "built_jobs": sum(1 for job in jobs if job.status == "built"),
        "jobs": [job.to_dict() for job in jobs],
    }
    (provider_jobs_dir(root) / "provider_gateway_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return jobs


def submit_runway_jobs_for_plan(root: Path, assembly_plan_path: Path, width: int = 720, height: int = 1280, max_segments: int = 1) -> List[ProviderJob]:
    plan = _read_json(assembly_plan_path)
    jobs: List[ProviderJob] = []
    segments = sorted(plan.get("timeline", []), key=lambda item: item.get("order", 0))[:max_segments]
    for segment in segments:
        request = request_from_segment(plan, segment, provider="runway", width=width, height=height)
        jobs.append(submit_provider_request(root, request))
    summary = {
        "sprint": 11,
        "assembly_plan_id": plan.get("assembly_plan_id"),
        "episode_id": plan.get("episode_id"),
        "provider": "runway",
        "job_count": len(jobs),
        "submitted_jobs": sum(1 for job in jobs if job.status == "submitted"),
        "built_jobs": sum(1 for job in jobs if job.status == "built"),
        "failed_jobs": sum(1 for job in jobs if job.status == "failed"),
        "jobs": [job.to_dict() for job in jobs],
    }
    (provider_jobs_dir(root) / "runway_gateway_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return jobs


def poll_runway_jobs(root: Path) -> List[ProviderJob]:
    updated_jobs: List[ProviderJob] = []
    for job in list_jobs(root):
        if job.provider != "runway" or job.status not in {"submitted", "running", "submitting"}:
            continue
        task_id = str(job.provider_response.get("task_id") or job.provider_response.get("raw", {}).get("task_id") or "")
        if not task_id:
            failed = job.with_status("failed", error="Runway job has no task_id.")
            save_job(root, failed)
            updated_jobs.append(failed)
            continue
        try:
            payload = poll_runway_task(task_id)
            status = runway_status_from_payload(payload)
            output_url = extract_runway_output_url(payload)
            next_job = job.with_status(
                status,
                output_path=output_url or job.output_path,
                output_type="video/mp4" if output_url else job.output_type,
                provider_response={
                    **job.provider_response,
                    "poll_payload": payload,
                    "last_polled_at": utc_now_iso(),
                    "output_url": output_url,
                },
            )
            save_job(root, next_job)
            updated_jobs.append(next_job)
        except Exception as exc:
            failed = job.with_status("failed", error=str(exc))
            save_job(root, failed)
            updated_jobs.append(failed)
    return updated_jobs


def _latest_built_jobs_by_segment(root: Path) -> Dict[str, ProviderJob]:
    mapped: Dict[str, ProviderJob] = {}
    for job in list_jobs(root):
        if job.status != "built" or not job.output_path:
            continue
        segment_id = job.request.segment_id
        if segment_id not in mapped:
            mapped[segment_id] = job
    return mapped


def materialize_provider_assets_into_plan(root: Path, assembly_plan_path: Path, output_dir: Path | None = None) -> Path:
    source_plan = _read_json(assembly_plan_path)
    plan = deepcopy(source_plan)
    original_plan_id = str(source_plan.get("assembly_plan_id", assembly_plan_path.stem))
    provider_plan_id = original_plan_id if original_plan_id.endswith("_PROVIDER") else f"{original_plan_id}_PROVIDER"
    plan["assembly_plan_id"] = provider_plan_id

    jobs_by_segment = _latest_built_jobs_by_segment(root)
    materialized = 0
    next_timeline: list[dict[str, Any]] = []
    for segment in plan.get("timeline", []):
        updated = dict(segment)
        segment_id = str(updated.get("segment_id", ""))
        job = jobs_by_segment.get(segment_id)
        if job and job.output_path:
            updated["output_path"] = job.output_path
            updated["provider_job_id"] = job.job_id
            updated["provider"] = job.provider
            updated["asset_source"] = "provider_gateway"
            materialized += 1
        next_timeline.append(updated)
    plan["timeline"] = next_timeline
    plan["provider_materialization"] = {
        "source_assembly_plan_id": original_plan_id,
        "provider_assembly_plan_id": provider_plan_id,
        "materialized_segments": materialized,
        "total_segments": len(next_timeline),
        "created_at": utc_now_iso(),
    }

    target_dir = output_dir or provider_assembly_dir(root)
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / f"{provider_plan_id}.json"
    out_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def provider_summary(root: Path) -> Dict[str, Any]:
    jobs = list_jobs(root)
    runway_config = runway_config_from_env()
    return {
        "service": "lucretia-provider-gateway",
        "sprint": 11,
        "mode": "mock-plus-runway-adapter",
        "runway_configured": runway_config.configured,
        "runway_dry_run": runway_config.dry_run,
        "runway_model": runway_config.model,
        "runway_api_version": runway_config.api_version,
        "job_count": len(jobs),
        "built_jobs": sum(1 for job in jobs if job.status == "built"),
        "submitted_jobs": sum(1 for job in jobs if job.status == "submitted"),
        "failed_jobs": sum(1 for job in jobs if job.status == "failed"),
        "runway_jobs": sum(1 for job in jobs if job.provider == "runway"),
        "mock_jobs": sum(1 for job in jobs if job.provider == "mock"),
        "jobs": [job.to_dict() for job in jobs[:20]],
    }
