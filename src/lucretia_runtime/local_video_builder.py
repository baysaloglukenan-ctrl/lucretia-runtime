from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List

import imageio.v2 as imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from .audio_layer_engine import create_silent_audio_wav
from .caption_renderer import draw_caption
from .timeline_builder import build_video_segments
from .video_models import LocalVideoBuild, VideoBuildSegment


def _read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _font(size: int):
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _color(seed: str) -> tuple[int, int, int]:
    h = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    return (40 + int(h[0:2], 16) % 120, 40 + int(h[2:4], 16) % 120, 70 + int(h[4:6], 16) % 130)


def _draw_centered(draw: ImageDraw.ImageDraw, img: Image.Image, text: str, y: int, font_size: int) -> None:
    font = _font(font_size)
    bbox = draw.textbbox((0, 0), text, font=font)
    x = (img.width - (bbox[2] - bbox[0])) // 2
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))


def _fit_cover(image: Image.Image, width: int, height: int) -> Image.Image:
    src = ImageOps.exif_transpose(image).convert("RGB")
    scale = max(width / src.width, height / src.height)
    new_size = (max(1, int(src.width * scale)), max(1, int(src.height * scale)))
    src = src.resize(new_size, Image.Resampling.LANCZOS)
    left = max(0, (src.width - width) // 2)
    top = max(0, (src.height - height) // 2)
    return src.crop((left, top, left + width, top + height))


def _placeholder_frame(segment: VideoBuildSegment, frame_index: int, frame_count: int, width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height), _color(segment.scene_id))
    draw = ImageDraw.Draw(img, "RGBA")
    progress = frame_index / max(1, frame_count - 1)
    cx = int(width * (0.18 + 0.64 * progress))
    cy = int(height * 0.48)
    draw.ellipse((cx - 54, cy - 54, cx + 54, cy + 54), fill=(255, 255, 255, 210))
    draw.ellipse((width - cx - 38, cy + 120 - 38, width - cx + 38, cy + 120 + 38), fill=(255, 215, 0, 220))
    _draw_centered(draw, img, "LUCREȚIA ENGINE", 80, 48)
    _draw_centered(draw, img, f"Episode {segment.episode_id}", 150, 28)
    _draw_centered(draw, img, f"Shot {segment.order} / Scene", 225, 34)
    _draw_centered(draw, img, segment.scene_id[-28:], 280, 24)
    _draw_centered(draw, img, f"Asset: {segment.asset.asset_type}", 350, 24)
    draw_caption(img, segment.caption or segment.scene_id)
    return img


def _image_asset_frame(segment: VideoBuildSegment, width: int, height: int) -> Image.Image | None:
    if segment.asset.asset_type != "image" or not segment.asset.source_path:
        return None
    try:
        img = _fit_cover(Image.open(segment.asset.source_path), width, height)
        draw = ImageDraw.Draw(img, "RGBA")
        label = f"{segment.order:02d} · {segment.scene_id[-32:]}"
        font = _font(max(13, min(18, width // 24)))
        bbox = draw.textbbox((0, 0), label, font=font)
        x0, y0 = 12, 12
        x1 = min(width - 12, x0 + (bbox[2] - bbox[0]) + 18)
        y1 = y0 + (bbox[3] - bbox[1]) + 14
        draw.rounded_rectangle((x0, y0, x1, y1), radius=10, fill=(0, 0, 0, 62))
        draw.text((x0 + 9, y0 + 6), label, font=font, fill=(255, 255, 255, 205))
        return img
    except Exception:
        return None


def _base_asset_frame(segment: VideoBuildSegment, width: int, height: int) -> Image.Image | None:
    if segment.asset.asset_type == "image":
        return _image_asset_frame(segment, width, height)
    return None


def _cleanup_raw_silent_video(raw_video: Path, final_video: Path) -> None:
    if raw_video == final_video:
        return
    try:
        raw_video.unlink(missing_ok=True)
    except Exception:
        pass


def build_local_video_from_plan(assembly_plan_path: Path, output_dir: Path, project_root: Path | None = None, fps: int = 12, width: int = 720, height: int = 1280) -> Path:
    project_root = project_root or assembly_plan_path.parents[3]
    output_dir.mkdir(parents=True, exist_ok=True)
    plan = _read_json(assembly_plan_path)
    segments = build_video_segments(plan, project_root)
    video_build_id = f"VB_{hashlib.sha1(plan['assembly_plan_id'].encode('utf-8')).hexdigest()[:8].upper()}"
    raw_video = output_dir / f"{video_build_id}_{plan['episode_id']}_silent.mp4"
    final_video = output_dir / f"{video_build_id}_{plan['episode_id']}.mp4"
    audio_path = output_dir / f"{video_build_id}_{plan['episode_id']}.wav"

    resolved_asset_count = sum(1 for segment in segments if segment.asset.resolved)
    image_asset_count = sum(1 for segment in segments if segment.asset.asset_type == "image" and segment.asset.resolved)
    provider_image_count = sum(1 for segment in segments if segment.asset.asset_type == "image" and segment.asset.resolved and segment.asset.source_path and "provider_assets" in segment.asset.source_path)

    with imageio.get_writer(str(raw_video), fps=fps, codec="libx264", quality=7, macro_block_size=16) as writer:
        for segment in segments:
            frames = max(1, int(segment.duration_seconds * fps))
            asset_frame = _base_asset_frame(segment, width, height)
            for idx in range(frames):
                frame = asset_frame.copy() if asset_frame else _placeholder_frame(segment, idx, frames, width, height)
                writer.append_data(np.asarray(frame))

    total_duration = sum(s.duration_seconds for s in segments)
    create_silent_audio_wav(audio_path, total_duration)
    try:
        subprocess.run(["ffmpeg", "-y", "-i", str(raw_video), "-i", str(audio_path), "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_video)], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        _cleanup_raw_silent_video(raw_video, final_video)
    except Exception:
        final_video = raw_video

    build = LocalVideoBuild(video_build_id, plan["assembly_plan_id"], plan["episode_id"], str(final_video), width, height, fps, round(total_duration, 2), segments, "built")
    (output_dir / f"{video_build_id}_{plan['episode_id']}_manifest.json").write_text(json.dumps(build.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    summary = {
        "engine": "local_video_builder",
        "video_build_id": video_build_id,
        "assembly_plan_id": plan["assembly_plan_id"],
        "episode_id": plan["episode_id"],
        "output_file": str(final_video),
        "segment_count": len(segments),
        "resolved_asset_count": resolved_asset_count,
        "image_asset_count": image_asset_count,
        "provider_image_count": provider_image_count,
        "caption_policy": "provider_assets_keep_native_text_no_extra_caption_overlay",
        "duration_seconds": round(total_duration, 2),
        "status": "built",
        "note": "Provider-backed image assets are treated as final visual frames; no duplicate caption overlay is drawn on top of them.",
    }
    (output_dir / "local_video_builder_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return final_video


def build_local_videos_from_dir(assembly_dir: Path, output_dir: Path, project_root: Path | None = None, fps: int = 12, width: int = 720, height: int = 1280) -> List[Path]:
    return [build_local_video_from_plan(p, output_dir, project_root=project_root, fps=fps, width=width, height=height) for p in sorted(assembly_dir.glob("ASP_*.json"))]
