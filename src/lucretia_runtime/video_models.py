from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional


@dataclass
class ResolvedSegmentAsset:
    segment_id: str
    scene_id: str
    render_job_id: str
    source_path: Optional[str]
    asset_type: str
    resolved: bool
    placeholder_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VideoBuildSegment:
    segment_id: str
    episode_id: str
    scene_id: str
    order: int
    start_time: float
    end_time: float
    duration_seconds: float
    asset: ResolvedSegmentAsset
    caption: str
    audio_cue: str
    transition_in: str
    transition_out: str

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["asset"] = self.asset.to_dict()
        return data


@dataclass
class LocalVideoBuild:
    video_build_id: str
    assembly_plan_id: str
    episode_id: str
    output_file: str
    width: int
    height: int
    fps: int
    duration_seconds: float
    segments: List[VideoBuildSegment] = field(default_factory=list)
    status: str = "built"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["segments"] = [s.to_dict() for s in self.segments]
        return data
