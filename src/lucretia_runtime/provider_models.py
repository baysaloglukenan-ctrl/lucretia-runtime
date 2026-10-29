from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class ProviderAssetRequest:
    provider: str
    assembly_plan_id: str
    episode_id: str
    segment_id: str
    scene_id: str
    render_job_id: str
    prompt: str
    duration_seconds: float
    width: int = 720
    height: int = 1280
    seed: str | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "assembly_plan_id": self.assembly_plan_id,
            "episode_id": self.episode_id,
            "segment_id": self.segment_id,
            "scene_id": self.scene_id,
            "render_job_id": self.render_job_id,
            "prompt": self.prompt,
            "duration_seconds": self.duration_seconds,
            "width": self.width,
            "height": self.height,
            "seed": self.seed,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ProviderAssetRequest":
        return cls(
            provider=str(payload.get("provider", "mock")),
            assembly_plan_id=str(payload.get("assembly_plan_id", "ASP_UNKNOWN")),
            episode_id=str(payload.get("episode_id", "EP_UNKNOWN")),
            segment_id=str(payload.get("segment_id", "SEG_UNKNOWN")),
            scene_id=str(payload.get("scene_id", "SCN_UNKNOWN")),
            render_job_id=str(payload.get("render_job_id", "RND_UNKNOWN")),
            prompt=str(payload.get("prompt", "")),
            duration_seconds=float(payload.get("duration_seconds", 2.0)),
            width=int(payload.get("width", 720)),
            height=int(payload.get("height", 1280)),
            seed=payload.get("seed"),
            metadata=dict(payload.get("metadata", {})),
        )


@dataclass(frozen=True)
class ProviderJob:
    job_id: str
    provider: str
    status: str
    request: ProviderAssetRequest
    created_at: str
    updated_at: str
    output_path: str | None = None
    output_type: str | None = None
    error: str | None = None
    provider_response: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "provider": self.provider,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "request": self.request.to_dict(),
            "output_path": self.output_path,
            "output_type": self.output_type,
            "error": self.error,
            "provider_response": self.provider_response,
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "ProviderJob":
        return cls(
            job_id=str(payload.get("job_id", "PJOB_UNKNOWN")),
            provider=str(payload.get("provider", "mock")),
            status=str(payload.get("status", "unknown")),
            created_at=str(payload.get("created_at", utc_now_iso())),
            updated_at=str(payload.get("updated_at", utc_now_iso())),
            request=ProviderAssetRequest.from_dict(dict(payload.get("request", {}))),
            output_path=payload.get("output_path"),
            output_type=payload.get("output_type"),
            error=payload.get("error"),
            provider_response=dict(payload.get("provider_response", {})),
        )

    def with_status(self, status: str, **changes: Any) -> "ProviderJob":
        data = self.to_dict()
        data.update(changes)
        data["status"] = status
        data["updated_at"] = utc_now_iso()
        return ProviderJob.from_dict(data)


def safe_relative_path(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except Exception:
        return str(path)
