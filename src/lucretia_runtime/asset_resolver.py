from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from .video_models import ResolvedSegmentAsset


def resolve_segment_asset(segment: Dict[str, Any], project_root: Path) -> ResolvedSegmentAsset:
    output_path = segment.get("output_path")
    resolved_path: Optional[Path] = None
    if output_path:
        p = Path(output_path)
        candidates = [p]
        if not p.is_absolute():
            candidates.append(project_root / p)
        for candidate in candidates:
            if candidate.exists():
                resolved_path = candidate
                break

    asset_type = "placeholder"
    if resolved_path and resolved_path.suffix.lower() in {".mp4", ".mov", ".webm"}:
        asset_type = "video"
    elif resolved_path and resolved_path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
        asset_type = "image"
    elif resolved_path:
        asset_type = "mock_text_asset"

    return ResolvedSegmentAsset(
        segment_id=segment.get("segment_id", "SEG_UNKNOWN"),
        scene_id=segment.get("scene_id", "SCN_UNKNOWN"),
        render_job_id=segment.get("render_job_id", "RND_UNKNOWN"),
        source_path=str(resolved_path) if resolved_path else None,
        asset_type=asset_type,
        resolved=resolved_path is not None,
        placeholder_reason=None if resolved_path else "missing_real_render_asset_using_generated_placeholder",
    )
