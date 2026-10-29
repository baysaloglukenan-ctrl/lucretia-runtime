from __future__ import annotations

import hashlib
import time
from pathlib import Path

from .production import (
    compile_scene_prompt,
    create_production,
    get_production,
    mark_scene_submitted,
    review_scene,
    save_production,
    scene_for_submission,
)
from .story_compiler import compile_original_story, compile_single_shot
from .keyframe_renderer import render_story_keyframe
from .video_validation import validate_scene_video
from .final_reel_composer import publish_single_shot


def create_original_reel(root: Path) -> dict:
    seed = time.time_ns()
    story = compile_original_story(seed)
    single_shot = compile_single_shot(story)
    key = hashlib.sha256(str(seed).encode()).hexdigest()[:10].upper()
    characters = [
        {"name": name, "description": description, "visual_rules": rules}
        for name, description, rules, _shape in story["characters"]
    ]
    scenes = [{
        "title": "Reel complet de 10 secunde",
        "prompt": single_shot["prompt"],
        "required_end_state": single_shot["required_end_state"],
        "duration_seconds": single_shot["duration_seconds"],
        "start_asset": render_story_keyframe(root, key, 0, story),
        "required_characters": [character[0] for character in story["characters"]],
        "negative_prompt": single_shot["negative_prompt"],
        "caption": "",
    }]
    return create_production(
        root,
        title=story["title"],
        universe_id=story["universe_id"],
        universe_rules=story["rules"],
        plot=story["plot"],
        characters=characters,
        scenes=scenes,
        forbidden=["human", "human hand", "existing copyrighted character"],
        automation={
            "mode": "autonomous_single_shot",
            "seed": seed,
            "auto_approve": True,
            "duration_seconds": 10,
            "caption_cues": single_shot["captions"],
        },
    )


def _enqueue_scene(root: Path, production: dict, scene: dict) -> dict:
    from .comfy import ComfyI2VRequest, enqueue_relay_job

    prompt, negative = compile_scene_prompt(production, scene)
    seed = int(hashlib.sha256(f"{production['production_id']}:{scene['scene_id']}:{scene.get('attempts', 0)}".encode()).hexdigest()[:8], 16)
    request = ComfyI2VRequest(
        image_path=scene["start_asset"], prompt=prompt, negative_prompt=negative, seed=seed,
        frames=int(scene["frames"]), width=512, height=896,
        workflow_path="workflows/comfy/ltx23_i2v_api.json", generate_audio=False,
        metadata={"source": "autonomous_production", "production_id": production["production_id"], "scene_id": scene["scene_id"]},
    )
    job = enqueue_relay_job(root, request)
    mark_scene_submitted(root, production["production_id"], scene["scene_id"], job["job_id"])
    return job


def start_original_reel(root: Path, production_id: str) -> dict:
    production = get_production(root, production_id)
    if production.get("automation", {}).get("mode") != "autonomous_single_shot":
        raise RuntimeError("This production is not autonomous.")
    production["automation"]["running"] = True
    production["automation"]["error"] = ""
    save_production(root, production)
    scene = next((item for item in production["scenes"] if item.get("status") in {"ready", "retry"}), None)
    if not scene:
        raise RuntimeError("No scene is waiting for generation.")
    production, scene = scene_for_submission(root, production_id, scene["scene_id"])
    return _enqueue_scene(root, production, scene)


def advance_original_reel(root: Path, production_id: str, scene_id: str) -> None:
    production = get_production(root, production_id)
    automation = production.get("automation", {})
    if automation.get("mode") != "autonomous_single_shot" or not automation.get("running"):
        return
    scene = next(item for item in production["scenes"] if item["scene_id"] == scene_id)
    output_path = root / str(scene.get("output_path", ""))
    source_path = root / str(scene.get("start_asset", ""))
    validation = validate_scene_video(
        output_path,
        float(scene.get("duration_seconds", 0) or 0),
        source_path=source_path,
    )
    scene["technical_validation"] = validation
    save_production(root, production)
    if not validation["valid"]:
        note = "Technical validation failed: " + "; ".join(validation["errors"])
        production = review_scene(root, production_id, scene_id, approved=False, note=note)
        production["automation"]["running"] = False
        production["automation"]["error"] = note
        save_production(root, production)
        return
    review_scene(
        root,
        production_id,
        scene_id,
        approved=True,
        note=f"Technical validation passed ({validation['duration_seconds']:.2f}s, {validation['size_bytes']} bytes).",
    )
    production = get_production(root, production_id)
    try:
        output, subtitle = publish_single_shot(
            root,
            production_id,
            output_path,
            automation.get("caption_cues", []),
        )
    except Exception as exc:
        production = get_production(root, production_id)
        production["status"] = "publishing_failed"
        production["automation"]["running"] = False
        production["automation"]["error"] = str(exc)
        save_production(root, production)
        return
    production = get_production(root, production_id)
    production["automation"]["running"] = False
    production["automation"]["completed"] = True
    production["status"] = "published"
    production["final_output"] = str(output.relative_to(root)).replace("\\", "/")
    production["subtitle_output"] = str(subtitle.relative_to(root)).replace("\\", "/")
    production["raw_output"] = str(output_path.relative_to(root)).replace("\\", "/")
    save_production(root, production)
