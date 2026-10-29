from __future__ import annotations

import json
from pathlib import Path

from .compositor import render_scene
from .presets import magnet_pull_scene
from .scene_models import MotionSceneSpec
from ..provider_models import utc_now_iso


def render_motion_scene(root: Path, scene: MotionSceneSpec, output_dir: Path | None = None, filename_prefix: str = "MOTION_CORE") -> Path:
    output_dir = output_dir or (root / "data" / "generated" / "videos")
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = utc_now_iso().replace(":", "-").replace("+", "Z")
    output = output_dir / f"{filename_prefix}_{scene.scene_id}_{stamp}.mp4"
    render_scene(root, scene, output)
    summary = {
        "sprint": "16A",
        "builder": "motion_core_object_animation",
        "status": "built",
        "output_file": str(output),
        "scene_id": scene.scene_id,
        "duration_seconds": scene.duration_seconds,
        "fps": scene.fps,
        "width": scene.width,
        "height": scene.height,
        "sprites": [sprite.object_id for sprite in scene.sprites],
        "animations": [animation.object_id for animation in scene.animations],
        "effects": scene.effects,
        "credits_spent": 0,
        "built_at": utc_now_iso(),
    }
    (output_dir / "motion_core_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return output


def render_magnet_pull_demo(root: Path, output_dir: Path | None = None, width: int = 720, height: int = 1280, duration: float = 5.0, fps: int = 24) -> Path:
    scene = magnet_pull_scene(root, width=width, height=height, duration=duration, fps=fps)
    return render_motion_scene(root, scene, output_dir=output_dir, filename_prefix="MOTION_CORE")
