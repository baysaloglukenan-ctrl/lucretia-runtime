from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from .asset_resolver import resolve_segment_asset
from .video_models import VideoBuildSegment


def build_video_segments(assembly_plan: Dict[str, Any], project_root: Path) -> List[VideoBuildSegment]:
    segments: List[VideoBuildSegment] = []
    timeline = sorted(assembly_plan.get("timeline", []), key=lambda s: s.get("order", 0))
    captions = assembly_plan.get("caption_slots", [])
    audio = assembly_plan.get("audio_slots", [])
    transitions = assembly_plan.get("transitions", [])

    for seg in timeline:
        order = int(seg.get("order", len(segments) + 1))
        caption = ""
        if order - 1 < len(captions):
            caption = captions[order - 1].get("text", "") or captions[order - 1].get("caption", "")
        if not caption:
            caption = seg.get("scene_id", "Scene")

        audio_cue = "soft_slapstick_pulse"
        if order - 1 < len(audio):
            audio_cue = audio[order - 1].get("cue", audio_cue)

        transition = "cut"
        if order - 1 < len(transitions):
            transition = transitions[order - 1].get("type", transition)

        start = float(seg.get("start_time", 0))
        end = float(seg.get("end_time", start + 2))
        duration = float(seg.get("duration_seconds", max(0.1, end - start)))
        segments.append(VideoBuildSegment(
            segment_id=seg.get("segment_id", f"SEG_{order:03d}"),
            episode_id=assembly_plan.get("episode_id", seg.get("episode_id", "EP_UNKNOWN")),
            scene_id=seg.get("scene_id", "SCN_UNKNOWN"),
            order=order,
            start_time=start,
            end_time=end,
            duration_seconds=duration,
            asset=resolve_segment_asset(seg, project_root),
            caption=caption,
            audio_cue=audio_cue,
            transition_in=transition,
            transition_out=transition,
        ))
    return segments
