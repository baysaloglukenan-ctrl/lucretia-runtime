from __future__ import annotations

import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

from .provider_models import utc_now_iso


def production_store_path(root: Path) -> Path:
    path = root / "data" / "generated" / "productions" / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_productions(root: Path) -> list[dict]:
    path = production_store_path(root)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def save_productions(root: Path, productions: list[dict]) -> None:
    path = production_store_path(root)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(productions, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def get_production(root: Path, production_id: str) -> dict:
    production = next((item for item in load_productions(root) if item.get("production_id") == production_id), None)
    if not production:
        raise KeyError(production_id)
    return production


def _upsert(root: Path, production: dict) -> dict:
    items = load_productions(root)
    for index, item in enumerate(items):
        if item.get("production_id") == production.get("production_id"):
            items[index] = production
            break
    else:
        items.insert(0, production)
    save_productions(root, items)
    return production


def save_production(root: Path, production: dict) -> dict:
    production["updated_at"] = utc_now_iso()
    return _upsert(root, production)


def frames_for_duration(seconds: float, fps: int = 24) -> int:
    groups = max(1, round(max(0.1, float(seconds)) * fps / 8))
    return groups * 8 + 1


def create_production(
    root: Path,
    *,
    title: str,
    universe_id: str,
    universe_rules: str,
    plot: str,
    characters: list[dict],
    scenes: list[dict],
    forbidden: list[str] | None = None,
    automation: dict | None = None,
) -> dict:
    clean_characters = []
    for index, character in enumerate(characters, start=1):
        name = str(character.get("name", "")).strip()
        if not name:
            continue
        clean_characters.append(
            {
                "character_id": str(character.get("character_id") or f"CHAR_{index:02d}"),
                "name": name,
                "description": str(character.get("description", "")).strip(),
                "visual_rules": str(character.get("visual_rules", "")).strip(),
                "reference_asset": str(character.get("reference_asset", "")).strip(),
            }
        )
    if not clean_characters:
        raise ValueError("At least one character is required.")
    character_ids = {item["character_id"] for item in clean_characters}
    character_names = {item["name"].casefold(): item["character_id"] for item in clean_characters}

    clean_scenes = []
    for index, scene in enumerate(scenes, start=1):
        prompt = str(scene.get("prompt", "")).strip()
        if not prompt:
            continue
        duration = max(1.0, float(scene.get("duration_seconds", 5) or 5))
        required_characters = []
        for value in scene.get("required_characters") or []:
            requested = str(value).strip()
            resolved = requested if requested in character_ids else character_names.get(requested.casefold(), "")
            if resolved and resolved not in required_characters:
                required_characters.append(resolved)
        clean_scenes.append(
            {
                "scene_id": str(scene.get("scene_id") or f"SCENE_{index:02d}"),
                "order": index,
                "title": str(scene.get("title") or f"Scene {index}").strip(),
                "prompt": prompt,
                "negative_prompt": str(scene.get("negative_prompt", "")).strip(),
                "caption": str(scene.get("caption", "")).strip(),
                "duration_seconds": duration,
                "frames": frames_for_duration(duration),
                "start_asset": str(scene.get("start_asset", "")).strip(),
                "required_characters": required_characters,
                "required_end_state": str(scene.get("required_end_state", "")).strip(),
                "status": "ready",
                "job_id": "",
                "output_path": "",
                "attempts": 0,
                "review_note": "",
            }
        )
    if not clean_scenes:
        raise ValueError("At least one scene is required.")

    now = utc_now_iso()
    production = {
        "production_id": f"PROD_{uuid.uuid4().hex[:10].upper()}",
        "title": title.strip() or "Untitled Lucretia Reel",
        "universe_id": universe_id.strip() or "custom_universe",
        "universe_rules": universe_rules.strip(),
        "plot": plot.strip(),
        "characters": clean_characters,
        "forbidden_entities": [value.strip() for value in (forbidden or []) if value.strip()],
        "scenes": clean_scenes,
        "status": "planning",
        "final_output": "",
        "subtitle_output": "",
        "automation": dict(automation or {}),
        "created_at": now,
        "updated_at": now,
    }
    return _upsert(root, production)


def scene_for_submission(root: Path, production_id: str, scene_id: str) -> tuple[dict, dict]:
    production = get_production(root, production_id)
    scenes = sorted(production.get("scenes", []), key=lambda item: int(item.get("order", 0)))
    scene = next((item for item in scenes if item.get("scene_id") == scene_id), None)
    if not scene:
        raise KeyError(scene_id)
    previous = [item for item in scenes if int(item.get("order", 0)) < int(scene.get("order", 0))]
    if any(item.get("status") != "approved" for item in previous):
        raise RuntimeError("Approve the previous scene before submitting this one.")
    if scene.get("status") not in {"ready", "retry"}:
        raise RuntimeError(f"Scene is not ready for submission: {scene.get('status')}")
    if not scene.get("start_asset"):
        raise RuntimeError("This scene needs a validated start keyframe.")
    return production, scene


def update_scene(
    root: Path,
    production_id: str,
    scene_id: str,
    *,
    prompt: str,
    start_asset: str,
    required_end_state: str,
    negative_prompt: str,
    duration_seconds: float,
    required_characters: list[str] | None = None,
) -> dict:
    production = get_production(root, production_id)
    scene = next(item for item in production["scenes"] if item["scene_id"] == scene_id)
    if scene.get("status") in {"generating", "review", "approved"}:
        raise RuntimeError("Retry the scene before editing its production contract.")
    scene["prompt"] = prompt.strip()
    scene["start_asset"] = start_asset.strip()
    scene["required_end_state"] = required_end_state.strip()
    scene["negative_prompt"] = negative_prompt.strip()
    scene["duration_seconds"] = max(1.0, float(duration_seconds))
    scene["frames"] = frames_for_duration(scene["duration_seconds"])
    if required_characters is not None:
        character_ids = {item["character_id"] for item in production.get("characters", [])}
        character_names = {
            item["name"].casefold(): item["character_id"] for item in production.get("characters", [])
        }
        resolved = []
        for value in required_characters:
            requested = str(value).strip()
            character_id = requested if requested in character_ids else character_names.get(requested.casefold(), "")
            if character_id and character_id not in resolved:
                resolved.append(character_id)
        scene["required_characters"] = resolved
    production["updated_at"] = utc_now_iso()
    return _upsert(root, production)


def compile_scene_prompt(production: dict, scene: dict) -> tuple[str, str]:
    cast_by_id = {item["character_id"]: item for item in production.get("characters", [])}
    required_ids = scene.get("required_characters") or list(cast_by_id)
    required = [cast_by_id[value] for value in required_ids if value in cast_by_id]
    if not required:
        required = list(cast_by_id.values())
    cast_text = "; ".join(
        f"{item['name']}: {item.get('description', '')}. Visual invariants: {item.get('visual_rules', '')}"
        for item in required
    )
    allowed_names = ", ".join(item["name"] for item in required)
    prompt = "\n\n".join(
        value
        for value in (
            f"Universe: {production.get('universe_id', 'custom_universe')}. {production.get('universe_rules', '')}",
            f"Canonical cast in this scene: {cast_text}",
            f"Scene action: {scene.get('prompt', '')}",
            f"Mandatory final state: {scene.get('required_end_state', '')}",
            f"Preserve the exact character designs and identities. Only the required cast may act: {allowed_names}. Clear cause and effect, readable action, stable camera.",
        )
        if value.strip()
    )
    forbidden = production.get("forbidden_entities", [])
    negative_parts = [scene.get("negative_prompt", "")]
    if forbidden:
        negative_parts.append("forbidden entities: " + ", ".join(str(value) for value in forbidden))
    negative_parts.append(
        "unlisted characters, new characters, human, human hand, human fingers, outside intervention, "
        "duplicate characters, disappearing characters, character redesign, identity drift, deformation, "
        "unresolved action, text, subtitles, watermark"
    )
    return prompt, ", ".join(value.strip(" ,") for value in negative_parts if value.strip())


def mark_scene_submitted(root: Path, production_id: str, scene_id: str, job_id: str) -> dict:
    production = get_production(root, production_id)
    scene = next(item for item in production["scenes"] if item["scene_id"] == scene_id)
    scene["status"] = "generating"
    scene["job_id"] = job_id
    scene["attempts"] = int(scene.get("attempts", 0)) + 1
    production["status"] = "generating"
    production["updated_at"] = utc_now_iso()
    return _upsert(root, production)


def record_scene_output(root: Path, production_id: str, scene_id: str, output_path: str) -> dict:
    production = get_production(root, production_id)
    scene = next(item for item in production["scenes"] if item["scene_id"] == scene_id)
    scene["status"] = "review"
    scene["output_path"] = output_path
    production["status"] = "review"
    production["updated_at"] = utc_now_iso()
    return _upsert(root, production)


def mark_scene_failed(root: Path, production_id: str, scene_id: str, error: str) -> dict:
    production = get_production(root, production_id)
    scene = next(item for item in production["scenes"] if item["scene_id"] == scene_id)
    scene["status"] = "retry"
    scene["review_note"] = error.strip()
    production["status"] = "planning"
    if str(production.get("automation", {}).get("mode", "")).startswith("autonomous"):
        production["automation"]["running"] = False
        production["automation"]["error"] = error.strip()
    production["updated_at"] = utc_now_iso()
    return _upsert(root, production)


def review_scene(root: Path, production_id: str, scene_id: str, *, approved: bool, note: str = "") -> dict:
    production = get_production(root, production_id)
    scene = next(item for item in production["scenes"] if item["scene_id"] == scene_id)
    if scene.get("status") != "review":
        raise RuntimeError("Only a generated scene awaiting review can be accepted or retried.")
    scene["status"] = "approved" if approved else "retry"
    scene["review_note"] = note.strip()
    if not approved:
        scene["output_path"] = ""
    statuses = [item.get("status") for item in production["scenes"]]
    production["status"] = "approved" if all(value == "approved" for value in statuses) else "planning"
    production["updated_at"] = utc_now_iso()
    return _upsert(root, production)


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def assemble_production(root: Path, production_id: str) -> Path:
    production = get_production(root, production_id)
    scenes = sorted(production["scenes"], key=lambda item: int(item.get("order", 0)))
    if not scenes or any(scene.get("status") != "approved" for scene in scenes):
        raise RuntimeError("Every scene must be approved before assembly.")
    segments = [root / scene["output_path"] for scene in scenes]
    if any(not path.exists() for path in segments):
        raise FileNotFoundError("One or more approved scene outputs are missing.")
    output_dir = root / "data" / "generated" / "videos"
    output_dir.mkdir(parents=True, exist_ok=True)
    output = output_dir / f"REEL_{production_id}_{int(time.time())}.mp4"
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=False) as handle:
        for segment in segments:
            handle.write(f"file '{str(segment.resolve()).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n")
        concat_file = Path(handle.name)
    try:
        subprocess.run(
            [_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", "-movflags", "+faststart", str(output)],
            check=True,
            capture_output=True,
        )
    finally:
        concat_file.unlink(missing_ok=True)
    production["status"] = "assembled"
    production["final_output"] = str(output.relative_to(root)).replace("\\", "/")
    from .final_reel_composer import CaptionCue, write_srt

    subtitle_dir = root / "data" / "generated" / "subtitles"
    subtitle_path = subtitle_dir / f"REEL_{production_id}.srt"
    cursor = 0.0
    cues = []
    for scene in scenes:
        duration = float(scene.get("duration_seconds", 0) or 0)
        caption = str(scene.get("caption", "")).strip()
        if caption:
            cues.append(CaptionCue(cursor, cursor + duration, caption))
        cursor += duration
    write_srt(subtitle_path, cues)
    production["subtitle_output"] = str(subtitle_path.relative_to(root)).replace("\\", "/")
    production["updated_at"] = utc_now_iso()
    _upsert(root, production)
    return output
