from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from lucretia_runtime.comfy.adapter import ComfyI2VRequest, list_i2v_jobs, poll_i2v_jobs, submit_i2v_job
from lucretia_runtime.final_reel_composer import publish_single_shot
from lucretia_runtime.production import (
    compile_scene_prompt,
    create_production,
    get_production,
    mark_scene_submitted,
    record_scene_output,
    review_scene,
)
from lucretia_runtime.video_validation import validate_scene_video


TEST_NAME = "single_reel_plane_spool_fan_conflict"
SOURCE = "data/generated/productions/single_reel_plane_spool_fan_conflict/plane_spool_fan_conflict_start.png"


def manifest_path(root: Path) -> Path:
    return root / "data" / "generated" / "productions" / TEST_NAME / "test.json"


def initialise(root: Path) -> dict:
    path = manifest_path(root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if not (root / SOURCE).exists():
        raise FileNotFoundError(root / SOURCE)
    captions = [
        {"start": 0, "end": 4, "text": "Vântul îl împinge spre margine!"},
        {"start": 4, "end": 9, "text": "Mosorel trage cu toată puterea."},
        {"start": 9, "end": 10, "text": "Salvat!"},
    ]
    production = create_production(
        root,
        title="Pli și firul de salvare",
        universe_id="orasul_mesei_de_croit",
        universe_rules="Craft objects are alive. Wind moves paper, while thread can restrain it. No humans exist.",
        plot="A fan blows a paper airplane toward the edge, but its spool friend catches it with red thread and pulls it back.",
        characters=[
            {"name": "Pli", "description": "the paper airplane already visible in the opening frame", "visual_rules": "do not alter its paper folds, face, eyes, color or proportions"},
            {"name": "Mosorel", "description": "the turquoise thread spool already visible in the opening frame", "visual_rules": "do not alter its body, face, red thread, feet, color or proportions"},
            {"name": "Ventilatorul", "description": "the green desk fan already visible in the opening frame", "visual_rules": "do not alter its cage, blades, face, stand, color or proportions"},
        ],
        scenes=[{
            "title": "Reel complet de 10 secunde",
            "duration_seconds": 10,
            "start_asset": SOURCE,
            "required_characters": ["Pli", "Mosorel", "Ventilatorul"],
            "prompt": (
                "Continue the immediate danger already visible in the opening frame as one continuous ten-second shot. "
                "The large angry fan keeps spinning at full speed. Its visible wind violently pushes the frightened paper airplane farther left and downward toward the open table edge. "
                "The existing red rescue thread is already attached to the airplane and stretches completely taut. "
                "The turquoise spool is pulled forward, braces both feet against the tabletop, leans backward and strains against the wind. "
                "After a clear struggle, the spool rotates its body to wind the red thread around itself and steadily pulls the airplane away from the edge. "
                "The airplane travels visibly rightward along the taut thread and lands safely beside the spool. "
                "Only after the airplane is safe, the fan blades slow down and stop; the fan looks defeated. "
                "End on the rescued airplane touching the spool, with the red thread still visibly connecting them. Keep the camera completely fixed."
            ),
            "negative_prompt": (
                "camera movement, zoom, close-up, cuts, transitions, greeting, playing, dancing, slow introduction, long celebration, static action, "
                "character redesign, changed face, changed proportions, duplicate character, extra character, morphing, disappearing character, unresolved ending"
            ),
            "required_end_state": "The airplane is safely beside the spool, visibly connected to it by taut red thread; the fan is stopped.",
        }],
        forbidden=["human", "human hand", "copyrighted character", "text", "watermark"],
        automation={"mode": "single_shot_test", "caption_cues": captions, "duration_seconds": 10},
    )
    result = {"production_id": production["production_id"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def submit(root: Path) -> dict:
    production = get_production(root, initialise(root)["production_id"])
    scene = production["scenes"][0]
    prompt, negative = compile_scene_prompt(production, scene)
    request = ComfyI2VRequest(
        image_path=scene["start_asset"], prompt=prompt, negative_prompt=negative,
        seed=20260827, frames=scene["frames"], width=512, height=896,
        workflow_path="workflows/comfy/ltx23_i2v_api.json", generate_audio=False,
        metadata={"source": TEST_NAME, "production_id": production["production_id"], "scene_id": scene["scene_id"]},
    )
    job = submit_i2v_job(root, request, auto_start=False)
    mark_scene_submitted(root, production["production_id"], scene["scene_id"], job["job_id"])
    return job


def poll(root: Path) -> dict:
    production = get_production(root, initialise(root)["production_id"])
    scene = production["scenes"][0]
    poll_i2v_jobs(root)
    job = next(item for item in list_i2v_jobs(root) if item["job_id"] == scene["job_id"])
    if job["status"] != "built":
        return {"job_id": job["job_id"], "prompt_id": job["prompt_id"], "status": job["status"], "stage": job["current_stage"]}
    if scene["status"] == "generating":
        production = record_scene_output(root, production["production_id"], scene["scene_id"], job["output_path"])
        scene = production["scenes"][0]
    validation = validate_scene_video(root / job["output_path"], 10, source_path=root / scene["start_asset"])
    if scene["status"] == "review" and validation["valid"]:
        review_scene(root, production["production_id"], scene["scene_id"], approved=True, note="Technical validation passed.")
    if not validation["valid"]:
        return {"status": "validation_failed", "validation": validation}
    production = get_production(root, production["production_id"])
    output, subtitle = publish_single_shot(root, production["production_id"], root / job["output_path"], production["automation"]["caption_cues"])
    production["status"] = "published"
    production["raw_output"] = job["output_path"]
    production["final_output"] = str(output.relative_to(root)).replace("\\", "/")
    production["subtitle_output"] = str(subtitle.relative_to(root)).replace("\\", "/")
    from lucretia_runtime.production import save_production
    save_production(root, production)
    return {"status": "published", "output": str(output), "subtitle": str(subtitle), "validation": validation}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "submit", "poll", "status"])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("LUCRETIA_COMFY_MODE", "external")
    os.environ.setdefault("LUCRETIA_COMFY_URL", "http://127.0.0.1:8188")
    if args.action == "init":
        result = initialise(root)
    elif args.action == "submit":
        result = submit(root)
    elif args.action == "poll":
        result = poll(root)
    else:
        result = get_production(root, initialise(root)["production_id"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
