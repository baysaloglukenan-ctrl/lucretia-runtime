from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

from lucretia_runtime.comfy.client import ComfyClient


TEST_NAME = "minimax_h3_plane_spool_fan_15s"
START_REFERENCE = Path(
    "data/generated/productions/single_reel_plane_spool_fan_conflict/plane_spool_fan_conflict_start.png"
)
END_REFERENCE = Path(
    "data/generated/productions/lucretia_three_reels_20260825/keyframes/"
    "02_plane_spool_fan_storyboard_scene_03.png"
)
WORKFLOW = Path("workflows/comfy/minimax_h3_r2v_api.json")
PROMPT = """Warm cinematic 3D family animation in the exact handcrafted style of <Picture 1>.

Use <Picture 1> as the identity, color, material, face, proportion and environment reference for the same three characters: the white paper airplane with green eyes, the small turquoise wooden spool with green eyes and red thread, and the large antique turquoise desk fan with an angry face. The supplied first-frame and final-frame guides are mandatory. Preserve the same three character identities throughout. Do not redesign, replace, duplicate, merge, melt or transform them. No new character, no human, no text.

ONE continuous fifteen-second shot with a locked wide vertical camera and no cuts.

VISUAL HOOK, 0–1 second: start exactly on the supplied opening frame at peak danger, with all three characters already visible. A sudden powerful gust hits immediately. The airplane's nose drops partly over the left table edge, the red thread snaps completely taut, and the spool is jerked one step forward before catching itself. No greeting, introduction or pause.

1–6 seconds: the fan keeps spinning rapidly and blowing from right to left. The same frightened airplane hangs at the edge while the same spool plants both feet and braces. Keep the original red thread visibly tied to both characters.

6–12 seconds: without any cut, the spool deliberately rotates its wooden cylinder and winds the same red thread shorter. The taut thread visibly pulls the airplane continuously away from the edge, diagonally rightward and safely back across the tabletop. The airplane remains in front of the other characters and keeps its exact folded-paper shape and face.

12–15 seconds: the airplane lands immediately beside the spool and naturally reaches the supplied final-frame guide. The red thread remains attached. Only after landing, the fan blades slow visibly to a complete stop and the fan looks defeated. Hold the safe final pose for the final two seconds with airplane and spool together and fully visible."""


def production_dir(root: Path) -> Path:
    path = root / "data" / "generated" / "productions" / TEST_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(root: Path) -> Path:
    return production_dir(root) / "state.json"


def read_state(root: Path) -> dict:
    path = state_path(root)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def write_state(root: Path, state: dict) -> None:
    state_path(root).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def upload_reference(client: ComfyClient, path: Path) -> str:
    result = client.upload_image(path, subfolder="lucretia/minimax_h3")
    subfolder = result.get("subfolder", "")
    return f"{subfolder}/{result['name']}" if subfolder else result["name"]


def submit(root: Path, client: ComfyClient) -> dict:
    existing = read_state(root)
    if existing.get("prompt_id") and existing.get("status") not in {"failed", "interrupted"}:
        return existing

    start = root / START_REFERENCE
    end = root / END_REFERENCE
    if not start.exists() or not end.exists():
        raise FileNotFoundError(f"Missing references: {start}, {end}")

    queue = client.queue()
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise RuntimeError("ComfyUI queue is not empty; refusing to mix this test with another job.")

    start_name = upload_reference(client, start)
    end_name = upload_reference(client, end)
    workflow = json.loads((root / WORKFLOW).read_text(encoding="utf-8"))
    workflow["137"]["inputs"]["image"] = start_name
    workflow["139"]["inputs"]["image"] = end_name
    workflow["138"]["inputs"]["value"] = PROMPT

    response = client.submit_prompt(workflow)
    if not response.get("prompt_id"):
        raise RuntimeError(f"ComfyUI did not return a prompt id: {response}")
    state = {
        "test": TEST_NAME,
        "status": "submitted",
        "prompt_id": response["prompt_id"],
        "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "start_reference": str(START_REFERENCE).replace("\\", "/"),
        "end_reference": str(END_REFERENCE).replace("\\", "/"),
        "workflow": str(WORKFLOW).replace("\\", "/"),
        "settings": {
            "duration_seconds": 15,
            "frames": 362,
            "fps": 24,
            "width": 480,
            "height": 864,
            "steps": 4,
            "audio": "disabled",
            "visual_hook": "immediate danger in the first second",
            "frame_guides": {"opening": 0, "final": -1},
        },
    }
    write_state(root, state)
    return state


def find_video(record: dict) -> dict | None:
    for output in record.get("outputs", {}).values():
        for item in output.get("images", []):
            if str(item.get("filename", "")).lower().endswith((".mp4", ".webm", ".mov")):
                return item
    return None


def poll(root: Path, client: ComfyClient) -> dict:
    state = read_state(root)
    prompt_id = state.get("prompt_id")
    if not prompt_id:
        return {"status": "not_submitted"}
    if state.get("status") == "completed" and state.get("output"):
        return state

    history = client.history(prompt_id)
    if prompt_id not in history:
        queue = client.queue()
        running = any(str(item[1]) == prompt_id for item in queue.get("queue_running", []))
        pending = any(str(item[1]) == prompt_id for item in queue.get("queue_pending", []))
        state["status"] = "running" if running else "queued" if pending else "waiting_for_history"
        write_state(root, state)
        return state

    record = history[prompt_id]
    if record.get("status", {}).get("status_str") == "error":
        state["status"] = "failed"
        state["error"] = record.get("status", {}).get("messages", [])[-1:]
        write_state(root, state)
        return state

    video = find_video(record)
    if not video:
        state["status"] = "completed_without_video"
        state["history_outputs"] = list(record.get("outputs", {}))
        write_state(root, state)
        return state

    suffix = Path(video["filename"]).suffix or ".mp4"
    output = production_dir(root) / f"{TEST_NAME}{suffix}"
    client.download_view(video["filename"], output, video.get("subfolder", ""), video.get("type", "output"))
    state["status"] = "completed"
    state["completed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    state["output"] = str(output.relative_to(root)).replace("\\", "/")
    state["provider_output"] = video
    write_state(root, state)
    return state


def run(root: Path, client: ComfyClient, poll_seconds: int) -> dict:
    state = submit(root, client)
    while state.get("status") not in {"completed", "failed", "completed_without_video"}:
        time.sleep(max(1, poll_seconds))
        state = poll(root, client)
    if state.get("status") == "completed":
        desktop = Path.home() / "Desktop" / "Lucretia - MiniMax H3 Test 15s"
        try:
            desktop.mkdir(parents=True, exist_ok=True)
            copied = desktop / Path(state["output"]).name
            shutil.copy2(root / state["output"], copied)
            state["desktop_output"] = str(copied)
        except OSError as exc:
            state["delivery_warning"] = f"Video completed but Desktop copy failed: {exc}"
        write_state(root, state)
    return state


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["submit", "poll", "run", "status"])
    parser.add_argument("--poll-seconds", type=int, default=30)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    client = ComfyClient("http://127.0.0.1:8188")
    if args.action == "submit":
        result = submit(root, client)
    elif args.action == "poll":
        result = poll(root, client)
    elif args.action == "run":
        result = run(root, client, args.poll_seconds)
    else:
        result = read_state(root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
