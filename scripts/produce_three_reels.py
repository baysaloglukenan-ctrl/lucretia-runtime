from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from lucretia_runtime.comfy.adapter import ComfyI2VRequest, list_i2v_jobs, poll_i2v_jobs, submit_i2v_job
from lucretia_runtime.production import (
    assemble_production,
    compile_scene_prompt,
    create_production,
    get_production,
    mark_scene_submitted,
    record_scene_output,
    review_scene,
    scene_for_submission,
)
from lucretia_runtime.video_validation import validate_scene_video


BATCH_NAME = "lucretia_three_reels_20260825"
NEGATIVE = (
    "identity drift, changed face, changed colors, changed proportions, duplicate character, extra character, "
    "human, human hand, text, captions, logo, watermark, morphing, melting, broken anatomy, random camera cut, "
    "static scene, unresolved action, character disappears"
)


def kf(story: int, scene: int, name: str) -> str:
    return (
        f"data/generated/productions/{BATCH_NAME}/keyframes/"
        f"{story:02d}_{name}_storyboard_scene_{scene:02d}.png"
    )


STORIES = [
    {
        "title": "Șurubul, Piulița și Magnetul",
        "universe_id": "atelierul_obiectelor_vii",
        "rules": "Household objects are alive. Material interactions drive cause and effect. Warm miniature workshop city.",
        "plot": "A happy screw approaches its nut friend, an evil magnet kidnaps it, and the nut blocks the magnet with wood.",
        "characters": [
            {"name": "Șurubel", "description": "tiny cheerful silver screw with large green eyes", "visual_rules": "silver metal, round screw head, green eyes, tiny arms, exact reference design"},
            {"name": "Piuli", "description": "friendly golden hex nut with large green eyes", "visual_rules": "golden brass hex body, central hole, green eyes, tiny arms and feet, exact reference design"},
            {"name": "Magnetul", "description": "angry red horseshoe magnet with black poles", "visual_rules": "red horseshoe body, black rectangular poles, angry face, exact reference design"},
        ],
        "scenes": [
            {"title": "Întâlnirea", "duration_seconds": 3.0, "caption": "Șurubel și-a găsit perechea!", "start_asset": kf(1, 1, "screw_nut_magnet"), "prompt": "The tiny silver screw rolls quickly and happily across the wooden workbench toward the welcoming golden nut. The screw rotates physically as it travels; the nut opens its arms. One continuous stable shot, immediate readable motion.", "required_end_state": "The screw reaches directly in front of the smiling nut; both are joyful.", "required_characters": ["Șurubel", "Piuli"]},
            {"title": "Atacul", "duration_seconds": 3.5, "caption": "Dar magnetul avea alt plan…", "start_asset": kf(1, 2, "screw_nut_magnet"), "prompt": "The angry red horseshoe magnet lunges from the right and strongly pulls the silver screw through the air toward its black pole. The screw struggles and spins, visibly frightened. The golden nut reacts instantly and reaches for the screw. Fast escalating action, no lingering celebration.", "required_end_state": "The screw is almost trapped at the magnet pole while the nut prepares to act.", "required_characters": ["Șurubel", "Piuli", "Magnetul"]},
            {"title": "Scutul de lemn", "duration_seconds": 3.5, "caption": "Lemnul nu ascultă de magnet!", "start_asset": kf(1, 3, "screw_nut_magnet"), "prompt": "The golden nut forcefully pushes the triangular wooden wedge between the red magnet and the silver screw. The magnetic pull breaks immediately; the screw drops safely beside the nut. The magnet bumps into the wood and recoils, defeated. Clear rescue, quick comic payoff, happy final pose.", "required_end_state": "Screw and nut stand safe together behind the wooden wedge; the magnet is blocked and defeated.", "required_characters": ["Șurubel", "Piuli", "Magnetul"]},
        ],
    },
    {
        "title": "Avionul și Firul de Salvare",
        "universe_id": "orasul_mesei_de_croit",
        "rules": "Craft objects are alive on a vast rooftop-like worktable. Wind and thread obey clear physical rules.",
        "plot": "A playful paper airplane is blown toward the edge by a mean fan, and its spool friend catches it with thread.",
        "characters": [
            {"name": "Pli", "description": "cheerful white paper airplane with large green eyes", "visual_rules": "crisp white folded paper, green eyes on nose, exact reference design"},
            {"name": "Mosorel", "description": "friendly turquoise wooden thread spool", "visual_rules": "turquoise cylinder, wooden rims, green eyes, golden feet, vivid red thread, exact reference design"},
            {"name": "Ventilatorul", "description": "grumpy vintage teal desk fan", "visual_rules": "round metal cage, teal blades and stand, angry eyes on center hub, exact reference design"},
        ],
        "scenes": [
            {"title": "Zborul", "duration_seconds": 3.0, "caption": "Pli zbura fără nicio grijă.", "start_asset": kf(2, 1, "plane_spool_fan"), "prompt": "The white paper airplane glides in a playful smooth loop toward the smiling turquoise thread spool. The spool waves. The distant fan remains still but watches angrily. Immediate flight motion, stable camera, bright joyful opening.", "required_end_state": "The airplane passes close to the spool while the fan is about to start.", "required_characters": ["Pli", "Mosorel", "Ventilatorul"]},
            {"title": "Rafala", "duration_seconds": 3.5, "caption": "O rafală îl împinge spre margine!", "start_asset": kf(2, 2, "plane_spool_fan"), "prompt": "The teal desk fan spins up violently and sends a visible powerful gust across the worktable. The paper airplane tumbles sideways toward the table edge, flapping and frightened. The spool reacts immediately and rapidly unrolls its red thread toward the airplane. Urgent continuous action.", "required_end_state": "The airplane hangs dangerously near the edge as the red thread reaches it.", "required_characters": ["Pli", "Mosorel", "Ventilatorul"]},
            {"title": "Linia de salvare", "duration_seconds": 3.5, "caption": "Un fir subțire poate fi foarte puternic.", "start_asset": kf(2, 3, "plane_spool_fan"), "prompt": "The turquoise spool braces both golden feet and pulls hard on the taut red rescue thread tied around the paper airplane. The airplane slides safely back from the edge and lands beside the spool. The angry fan strains, sputters, and stops in defeat. Clear rescue and warm relieved final beat.", "required_end_state": "The airplane is safely beside the smiling spool, connected by red thread; the stopped fan is defeated behind them.", "required_characters": ["Pli", "Mosorel", "Ventilatorul"]},
        ],
    },
    {
        "title": "Buretele Oprește Valul",
        "universe_id": "canalele_de_langa_chiuveta",
        "rules": "Sink-side objects are alive. Water shapes the world, and absorbent materials can change its flow.",
        "plot": "A paper boat is swept toward danger by a cruel pitcher, but a brave sponge absorbs the wave.",
        "characters": [
            {"name": "Barcuta", "description": "tiny cheerful pale-blue paper boat with large green eyes", "visual_rules": "pale-blue folded paper, green eyes on bow, exact reference design"},
            {"name": "Burețel", "description": "friendly square yellow kitchen sponge", "visual_rules": "yellow porous square body, green eyes, orange boots, exact reference design"},
            {"name": "Ulciorul", "description": "grumpy tall purple metal water pitcher", "visual_rules": "purple painted metal, curved handle and spout, expressive face, exact reference design"},
        ],
        "scenes": [
            {"title": "Plimbarea", "duration_seconds": 3.0, "caption": "O plimbare liniștită pe canal…", "start_asset": kf(3, 1, "boat_sponge_pitcher"), "prompt": "The pale-blue paper boat floats cheerfully along the sparkling shallow channel past the smiling yellow sponge. Small ripples move naturally. The purple pitcher watches from farther back. Smooth immediate motion and calm playful opening.", "required_end_state": "The boat reaches the sponge while the pitcher begins to tip.", "required_characters": ["Barcuta", "Burețel", "Ulciorul"]},
            {"title": "Valul", "duration_seconds": 3.5, "caption": "Ulciorul pornește un val uriaș!", "start_asset": kf(3, 2, "boat_sponge_pitcher"), "prompt": "The giant purple pitcher tips forward and pours a sudden rushing wave. The wave catches the paper boat and drives it rapidly toward the channel drop. The frightened yellow sponge turns and jumps directly into the water path. Fast clear cause and effect, no pause.", "required_end_state": "The boat is moments from the drop while the sponge blocks the wave path.", "required_characters": ["Barcuta", "Burețel", "Ulciorul"]},
            {"title": "Super-absorbția", "duration_seconds": 3.5, "caption": "Burețel a băut tot pericolul!", "start_asset": kf(3, 3, "boat_sponge_pitcher"), "prompt": "The yellow sponge plants its orange boots and rapidly absorbs the rushing water, swelling only slightly while keeping the same face and square design. The wave shrinks to nothing before the edge. The paper boat settles safely beside the sponge. The empty purple pitcher droops in defeat. Clear complete resolution and happy final pose.", "required_end_state": "The boat is safe beside the smiling sponge on a calm dry channel; the pitcher is empty and defeated.", "required_characters": ["Barcuta", "Burețel", "Ulciorul"]},
        ],
    },
]


def manifest_path(root: Path) -> Path:
    return root / "data" / "generated" / "productions" / BATCH_NAME / "batch.json"


def load_manifest(root: Path) -> dict:
    return json.loads(manifest_path(root).read_text(encoding="utf-8"))


def initialise(root: Path) -> dict:
    target = manifest_path(root)
    if target.exists():
        return load_manifest(root)
    production_ids = []
    for story in STORIES:
        production = create_production(
            root,
            title=story["title"],
            universe_id=story["universe_id"],
            universe_rules=story["rules"],
            plot=story["plot"],
            characters=story["characters"],
            scenes=[{**scene, "negative_prompt": NEGATIVE} for scene in story["scenes"]],
            forbidden=["human", "human hand", "copyrighted character"],
        )
        production_ids.append(production["production_id"])
    payload = {"batch": BATCH_NAME, "production_ids": production_ids, "created_at": time.time()}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def selected(root: Path, reel: int, scene: int) -> tuple[str, str]:
    production_id = load_manifest(root)["production_ids"][reel - 1]
    production = get_production(root, production_id)
    scene_id = sorted(production["scenes"], key=lambda item: item["order"])[scene - 1]["scene_id"]
    return production_id, scene_id


def submit(root: Path, reel: int, scene_number: int) -> dict:
    production_id, scene_id = selected(root, reel, scene_number)
    production, scene = scene_for_submission(root, production_id, scene_id)
    prompt, negative = compile_scene_prompt(production, scene)
    request = ComfyI2VRequest(
        image_path=scene["start_asset"], prompt=prompt, negative_prompt=negative,
        seed=12000 + reel * 100 + scene_number + int(scene.get("attempts", 0)) * 1000,
        frames=scene["frames"], width=512, height=896,
        workflow_path="workflows/comfy/ltx23_i2v_api.json", generate_audio=False,
        metadata={"batch": BATCH_NAME, "production_id": production_id, "scene_id": scene_id},
    )
    job = submit_i2v_job(root, request, auto_start=False)
    mark_scene_submitted(root, production_id, scene_id, job["job_id"])
    return job


def poll_one(root: Path, reel: int, scene_number: int) -> dict:
    production_id, scene_id = selected(root, reel, scene_number)
    scene = next(item for item in get_production(root, production_id)["scenes"] if item["scene_id"] == scene_id)
    poll_i2v_jobs(root)
    job = next(item for item in list_i2v_jobs(root) if item["job_id"] == scene["job_id"])
    if job["status"] == "built" and scene["status"] == "generating":
        record_scene_output(root, production_id, scene_id, job["output_path"])
        scene = next(item for item in get_production(root, production_id)["scenes"] if item["scene_id"] == scene_id)
    report = None
    if job["status"] == "built":
        report = validate_scene_video(root / job["output_path"], scene["duration_seconds"], root / scene["start_asset"])
    return {"job": job, "validation": report}


def approve(root: Path, reel: int, scene_number: int) -> dict:
    production_id, scene_id = selected(root, reel, scene_number)
    return review_scene(root, production_id, scene_id, approved=True, note="Visual review passed")


def reject(root: Path, reel: int, scene_number: int) -> dict:
    production_id, scene_id = selected(root, reel, scene_number)
    return review_scene(root, production_id, scene_id, approved=False, note="Visual review failed; retry with a new seed")


def status(root: Path) -> dict:
    manifest = initialise(root)
    return {"batch": manifest["batch"], "productions": [get_production(root, value) for value in manifest["production_ids"]]}


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["init", "status", "submit", "poll", "approve", "reject", "assemble"])
    parser.add_argument("--reel", type=int, choices=[1, 2, 3])
    parser.add_argument("--scene", type=int, choices=[1, 2, 3])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.environ.setdefault("LUCRETIA_COMFY_MODE", "external")
    os.environ.setdefault("LUCRETIA_COMFY_URL", "http://127.0.0.1:8188")
    initialise(root)
    if args.action == "init":
        result = load_manifest(root)
    elif args.action == "status":
        result = status(root)
    elif args.action == "assemble":
        if args.reel is None:
            parser.error("--reel is required")
        production_id = load_manifest(root)["production_ids"][args.reel - 1]
        result = {"output": str(assemble_production(root, production_id))}
    else:
        if args.reel is None or args.scene is None:
            parser.error("--reel and --scene are required")
        result = {"submit": submit, "poll": poll_one, "approve": approve, "reject": reject}[args.action](root, args.reel, args.scene)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
