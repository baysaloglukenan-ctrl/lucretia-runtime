from __future__ import annotations

import hashlib
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image

from lucretia_runtime.production import (
    compile_scene_prompt,
    create_production,
    frames_for_duration,
    get_production,
    mark_scene_submitted,
    record_scene_output,
    review_scene,
    save_production,
    scene_for_submission,
)
from lucretia_runtime.comfy.adapter import ComfyI2VRequest
from lucretia_runtime.comfy.relay import complete_relay_job, enqueue_relay_job
from lucretia_runtime.comfy.relay import claim_relay_job
from lucretia_runtime.production_ui import render_production_home
from lucretia_runtime.autonomous_production import advance_original_reel, create_original_reel, start_original_reel
from lucretia_runtime.story_compiler import compile_original_story


def _asset(root: Path, name: str) -> str:
    path = root / "data" / "generated" / "short_assets" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"image")
    return str(path.relative_to(root)).replace("\\", "/")


def test_manifest_accepts_variable_cast_and_scene_counts(tmp_path: Path) -> None:
    assets = [_asset(tmp_path, f"scene_{index}.png") for index in range(4)]
    characters = [
        {"name": f"Character {index}", "description": "original object", "visual_rules": "keep exact shape"}
        for index in range(7)
    ]
    scenes = [
        {
            "title": f"Scene {index}",
            "prompt": f"Action {index}",
            "required_characters": ["Character 1", "Character 4"],
            "required_end_state": f"State {index}",
            "duration_seconds": 5,
            "start_asset": assets[index],
        }
        for index in range(4)
    ]

    production = create_production(
        tmp_path,
        title="Variable universe",
        universe_id="custom_universe",
        universe_rules="Objects are alive.",
        plot="A complete plot.",
        characters=characters,
        scenes=scenes,
        forbidden=["human", "human hand"],
    )

    assert len(production["characters"]) == 7
    assert len(production["scenes"]) == 4
    assert production["scenes"][0]["frames"] == frames_for_duration(5)
    assert production["scenes"][0]["required_characters"] == ["CHAR_02", "CHAR_05"]


def test_scene_gate_requires_review_and_approval(tmp_path: Path) -> None:
    first_asset = _asset(tmp_path, "first.png")
    second_asset = _asset(tmp_path, "second.png")
    production = create_production(
        tmp_path,
        title="Gate test",
        universe_id="objects",
        universe_rules="No outside intervention.",
        plot="Conflict and resolution.",
        characters=[{"name": "Screw"}, {"name": "Nut"}, {"name": "Magnet"}],
        scenes=[
            {"prompt": "Magnet captures screw", "required_end_state": "Screw is captured", "start_asset": first_asset},
            {"prompt": "Nut rescues screw", "required_end_state": "Screw is free", "start_asset": second_asset},
        ],
        forbidden=["human hand"],
    )
    production_id = production["production_id"]
    first, second = production["scenes"]

    try:
        scene_for_submission(tmp_path, production_id, second["scene_id"])
        raise AssertionError("second scene bypassed approval gate")
    except RuntimeError:
        pass

    scene_for_submission(tmp_path, production_id, first["scene_id"])
    mark_scene_submitted(tmp_path, production_id, first["scene_id"], "JOB_1")
    record_scene_output(tmp_path, production_id, first["scene_id"], "data/generated/videos/scene1.mp4")
    review_scene(tmp_path, production_id, first["scene_id"], approved=True)
    _, ready_second = scene_for_submission(tmp_path, production_id, second["scene_id"])
    assert ready_second["scene_id"] == second["scene_id"]


def test_prompt_compiler_enforces_cast_and_forbidden_entities(tmp_path: Path) -> None:
    asset = _asset(tmp_path, "keyframe.png")
    production = create_production(
        tmp_path,
        title="Compiler",
        universe_id="living_objects",
        universe_rules="Only household objects can act.",
        plot="A test.",
        characters=[{"name": "Screw", "description": "hero", "visual_rules": "silver round smiling head"}],
        scenes=[{"prompt": "Screw rolls forward", "required_end_state": "Screw reaches the door", "start_asset": asset}],
        forbidden=["human", "human hand"],
    )
    prompt, negative = compile_scene_prompt(production, production["scenes"][0])
    assert "Screw" in prompt
    assert "Mandatory final state" in prompt
    assert "human hand" in negative
    assert get_production(tmp_path, production["production_id"])["title"] == "Compiler"


def test_relay_output_moves_scene_to_review(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    workflow = tmp_path / "workflows" / "comfy" / "ltx23_i2v_api.json"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        source_root.joinpath("workflows/comfy/ltx23_i2v_api.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    asset = _asset(tmp_path, "relay.png")
    production = create_production(
        tmp_path,
        title="Relay review",
        universe_id="objects",
        universe_rules="Objects act alone.",
        plot="One action.",
        characters=[{"name": "Screw"}],
        scenes=[{"prompt": "Screw moves", "required_end_state": "Screw stops", "start_asset": asset}],
    )
    scene = production["scenes"][0]
    request = ComfyI2VRequest(
        image_path=asset,
        prompt="Screw moves",
        metadata={"production_id": production["production_id"], "scene_id": scene["scene_id"]},
    )
    job = enqueue_relay_job(tmp_path, request)
    mark_scene_submitted(tmp_path, production["production_id"], scene["scene_id"], job["job_id"])

    complete_relay_job(tmp_path, job["job_id"], "scene.mp4", b"video", "prompt")

    updated = get_production(tmp_path, production["production_id"])
    assert updated["scenes"][0]["status"] == "review"
    assert updated["scenes"][0]["output_path"].endswith("scene.mp4")


def test_primary_ui_is_simple_and_has_no_experimental_labels(tmp_path: Path) -> None:
    page = render_production_home(tmp_path)
    assert "Creează reelul" in page
    assert "un singur video continuu" in page
    assert "Universe rules" not in page
    assert "Character name" not in page
    assert "scene_prompt" not in page
    assert "Sprint" not in page
    assert "Multi-Scene LTX" not in page
    assert "Stația nu este conectată" in page


def test_autonomous_engine_creates_one_complete_ten_second_contract(tmp_path: Path) -> None:
    production = create_original_reel(tmp_path)
    claim_relay_job(tmp_path, "test-worker")

    assert production["automation"]["mode"] == "autonomous_single_shot"
    assert 3 <= len(production["characters"]) <= 7
    assert len(production["scenes"]) == 1
    assert production["plot"]
    for scene in production["scenes"]:
        assert scene["prompt"]
        assert scene["required_end_state"]
        assert (tmp_path / scene["start_asset"]).exists()

    scene = production["scenes"][0]
    assert scene["duration_seconds"] == 10
    assert scene["frames"] == 241
    assert "ONE continuous" in scene["prompt"]
    assert Image.open(tmp_path / scene["start_asset"]).size == (320, 576)
    assert len(production["automation"]["caption_cues"]) == 3

    page = render_production_home(tmp_path)
    assert "2. Pornește producția" in page
    assert "Stația este conectată" in page
    assert "<button disabled>2. Pornește producția</button>" not in page


def test_story_compiler_is_reproducible_causal_and_ten_seconds() -> None:
    first = compile_original_story(42)
    second = compile_original_story(42)

    assert first == second
    assert len(first["characters"]) == 3
    assert sum(scene[4] for scene in first["scenes"]) == 10
    assert "No humans" in first["rules"]
    assert "Resolution" == first["scenes"][-1][0]
    assert first["resolution_visual"] in {"wedge", "thread", "dry_path"}


def test_story_compiler_covers_distinct_material_conflicts() -> None:
    stories = [compile_original_story(seed) for seed in range(100)]
    families = {story["resolution_visual"] for story in stories}

    assert families == {"wedge", "thread", "dry_path"}
    assert all(sum(scene[4] for scene in story["scenes"]) == 10 for story in stories)
    assert all("No humans" in story["rules"] for story in stories)


def test_autonomous_engine_rejects_invalid_scene_output(tmp_path: Path) -> None:
    production = create_original_reel(tmp_path)
    production["automation"]["running"] = True
    save_production(tmp_path, production)
    scene = production["scenes"][0]
    production, scene = scene_for_submission(tmp_path, production["production_id"], scene["scene_id"])
    mark_scene_submitted(tmp_path, production["production_id"], scene["scene_id"], "JOB_BAD")
    bad_output = tmp_path / "data" / "generated" / "videos" / "bad.mp4"
    bad_output.parent.mkdir(parents=True, exist_ok=True)
    bad_output.write_bytes(b"not-video")
    record_scene_output(tmp_path, production["production_id"], scene["scene_id"], str(bad_output.relative_to(tmp_path)))

    advance_original_reel(tmp_path, production["production_id"], scene["scene_id"])

    updated = get_production(tmp_path, production["production_id"])
    assert updated["scenes"][0]["status"] == "retry"
    assert updated["scenes"][0]["technical_validation"]["valid"] is False
    assert updated["automation"]["running"] is False
    assert "Technical validation failed" in updated["automation"]["error"]


def _scene_video_bytes(tmp_path: Path, source: Path, seconds: int) -> bytes:
    output = tmp_path / f"fixture_{source.stem}.mp4"
    frame = np.asarray(Image.open(source).convert("RGB"))
    writer = imageio.get_writer(output, fps=24, codec="libx264", macro_block_size=None)
    try:
        for index in range(seconds * 24):
            shifted = np.roll(frame, min(index // 8, 3), axis=1)
            writer.append_data(shifted)
    finally:
        writer.close()
    return output.read_bytes()


def test_autonomous_reel_runs_one_relay_job_and_publishes(tmp_path: Path) -> None:
    source_root = Path(__file__).resolve().parents[1]
    workflow = tmp_path / "workflows" / "comfy" / "ltx23_i2v_api.json"
    workflow.parent.mkdir(parents=True)
    workflow.write_text(
        source_root.joinpath("workflows/comfy/ltx23_i2v_api.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    production = create_original_reel(tmp_path)
    current_job = start_original_reel(tmp_path, production["production_id"])

    claimed = claim_relay_job(tmp_path, "integration-worker")
    assert claimed is not None
    assert claimed["job_id"] == current_job["job_id"]
    current = get_production(tmp_path, production["production_id"])
    scene = current["scenes"][0]
    data = _scene_video_bytes(tmp_path, tmp_path / scene["start_asset"], 10)
    complete_relay_job(tmp_path, current_job["job_id"], "single_shot.mp4", data, "complete prompt")

    completed = get_production(tmp_path, production["production_id"])
    assert completed["status"] == "published"
    assert completed["automation"]["completed"] is True
    assert completed["automation"]["running"] is False
    final_output = tmp_path / completed["final_output"]
    assert final_output.exists()
    assert final_output.stat().st_size > 1024
    subtitle_output = tmp_path / completed["subtitle_output"]
    assert subtitle_output.exists()
    subtitle_text = subtitle_output.read_text(encoding="utf-8")
    assert "00:00:00,000 --> 00:00:02,000" in subtitle_text
    assert "00:00:06,000 --> 00:00:10,000" in subtitle_text
    assert "audio" not in completed.get("automation", {})
