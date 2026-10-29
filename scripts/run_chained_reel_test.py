from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import imageio_ffmpeg

from lucretia_runtime.comfy.adapter import ComfyI2VRequest, list_i2v_jobs, poll_i2v_jobs, submit_i2v_job
from lucretia_runtime.final_reel_composer import publish_single_shot
from lucretia_runtime.production import frames_for_duration
from lucretia_runtime.video_validation import validate_scene_video


TEST_NAME = "plane_spool_fan_chained_15s"
INITIAL_SOURCE = "data/generated/productions/single_reel_plane_spool_fan_conflict/plane_spool_fan_conflict_start.png"
SEGMENT_SECONDS = 5.0
OUTPUT_FPS = 24
TOTAL_SECONDS = SEGMENT_SECONDS * 3
NEGATIVE = (
    "camera movement, zoom, close-up, cuts, transition, greeting, playing, dancing, character redesign, "
    "changed face, changed proportions, duplicate character, extra character, morphing, disappearing character, "
    "airplane behind the fan, airplane behind the spool, airplane entering from the right, airplane moving upward, "
    "airplane leaving the frame, spool changing position, new thread, broken thread, human, human hand, "
    "text, subtitle, logo, watermark"
)
SEGMENTS = (
    {
        "title": "Pericolul",
        "caption": "Vântul îl împinge spre margine!",
        "prompt": (
            "Continue exactly from the input frame for five seconds with a fixed camera. The large angry fan spins at full speed. "
            "Its visible wind pushes the frightened paper airplane farther left toward the open table edge. The existing red thread stays attached and stretches completely taut. "
            "The turquoise spool braces both feet and strains against the pull. End in a clear dangerous state: the airplane is partly over the edge, held only by the taut red thread, while the spool is still anchored on the table."
        ),
    },
    {
        "title": "Salvarea",
        "caption": "Mosorel nu îi dă drumul.",
        "prompt": (
            "Continue exactly from this input frame for five seconds with a locked camera and unchanged composition. "
            "There is exactly one paper airplane. It begins beyond the LEFT table edge, mostly outside the frame, attached to the existing taut red thread. "
            "It may return only through that same LEFT edge; it never appears behind the spool, behind the fan, or on the right side. "
            "The turquoise spool stays planted in its current place, leans away from the left edge, and rotates its cylindrical body to wind the thread shorter. "
            "The thread visibly pulls the same airplane upward from below the left edge. End with the airplane only halfway back onto the tabletop at the LEFT edge, still in danger. "
            "The angry fan keeps spinning at full speed throughout this segment."
        ),
    },
    {
        "title": "Rezoluția",
        "caption": "Împreună sunt mai puternici.",
        "prompt": (
            "Continue exactly from the actual input frame for five seconds with a locked camera and unchanged composition. "
            "There is exactly one paper airplane suspended high in the UPPER-LEFT corner above the table, connected by the existing red thread to the turquoise spool below. "
            "The spool stays planted in exactly its current position and winds the thread shorter while guiding the airplane DIAGONALLY DOWN AND RIGHT. "
            "The same airplane descends continuously from the upper-left corner, never rises, never leaves the frame, and never passes behind another object. "
            "It lands gently on the tabletop immediately to the LEFT of the spool. Only after it has landed, the fan blades visibly slow and become completely still. "
            "Hold the final safe pose for the last second: airplane and spool together and fully visible, red thread still attached, fan stopped."
        ),
    },
)


def root_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def run_dir(root: Path) -> Path:
    path = root / "data" / "generated" / "productions" / TEST_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_path(root: Path) -> Path:
    return run_dir(root) / "chain.json"


def save(root: Path, state: dict) -> dict:
    state["updated_at"] = time.time()
    target = state_path(root)
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, target)
    return state


def initialise(root: Path) -> dict:
    path = state_path(root)
    if path.exists():
        state = json.loads(path.read_text(encoding="utf-8"))
        if not state.get("run_id"):
            state["run_id"] = f"{int(state.get('created_at', time.time()))}"
            save(root, state)
        return state
    if not (root / INITIAL_SOURCE).exists():
        raise FileNotFoundError(root / INITIAL_SOURCE)
    state = {
        "test": TEST_NAME,
        "run_id": str(int(time.time())),
        "status": "ready",
        "segments": [
            {
                "order": index,
                "title": spec["title"],
                "caption": spec["caption"],
                "prompt": spec["prompt"],
                "source_image": INITIAL_SOURCE if index == 1 else "",
                "job_id": "",
                "prompt_id": "",
                "output_path": "",
                "end_frame": "",
                "status": "ready" if index == 1 else "waiting",
            }
            for index, spec in enumerate(SEGMENTS, start=1)
        ],
        "final_output": "",
        "raw_output": "",
        "created_at": time.time(),
    }
    return save(root, state)


def _submit(root: Path, state: dict, segment: dict) -> dict:
    segment["status"] = "submitting"
    segment["error"] = ""
    segment.pop("validation", None)
    state["status"] = f"submitting_segment_{segment['order']}"
    save(root, state)
    request = ComfyI2VRequest(
        image_path=segment["source_image"],
        prompt=segment["prompt"],
        negative_prompt=NEGATIVE,
        seed=20260900 + int(segment["order"]),
        frames=frames_for_duration(SEGMENT_SECONDS),
        width=512,
        height=896,
        workflow_path="workflows/comfy/ltx23_i2v_api.json",
        generate_audio=False,
        metadata={"source": TEST_NAME, "run_id": state["run_id"], "segment": segment["order"]},
    )
    try:
        job = submit_i2v_job(root, request, auto_start=False)
    except Exception as exc:
        segment["status"] = "failed"
        segment["error"] = str(exc)
        state["status"] = "failed"
        save(root, state)
        raise
    segment["job_id"] = job["job_id"]
    segment["prompt_id"] = job["prompt_id"]
    segment["status"] = "generating"
    state["status"] = f"generating_segment_{segment['order']}"
    save(root, state)
    return job


def submit_next(root: Path) -> dict:
    state = initialise(root)
    if any(item["status"] in {"submitting", "generating"} for item in state["segments"]):
        raise RuntimeError("A chained segment is already generating.")
    segment = next((item for item in state["segments"] if item["status"] == "ready"), None)
    if not segment:
        raise RuntimeError("No chained segment is ready.")
    return _submit(root, state, segment)


def _extract_end_frame(root: Path, output: Path, order: int) -> str:
    target = run_dir(root) / f"segment_{order:02d}_end.png"
    frame_count, _ = imageio_ffmpeg.count_frames_and_secs(str(output))
    if frame_count < 1:
        raise RuntimeError(f"No decoded frames found in {output}")
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-i", str(output),
            "-vf", f"select=eq(n\\,{frame_count - 1})", "-fps_mode", "vfr",
            "-frames:v", "1", "-update", "1", str(target),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return str(target.relative_to(root)).replace("\\", "/")


def _assemble(root: Path, state: dict) -> Path:
    outputs = [root / item["output_path"] for item in state["segments"]]
    target = run_dir(root) / f"plane_spool_fan_chained_{state['run_id']}_raw.mp4"
    temporary = target.with_name(f".{target.stem}.{time.time_ns()}.tmp.mp4")
    filters = []
    for index in range(len(outputs)):
        filters.append(
            f"[{index}:v]trim=start=0:end={SEGMENT_SECONDS:g},setpts=PTS-STARTPTS,"
            f"fps={OUTPUT_FPS},scale=512:896:force_original_aspect_ratio=decrease,"
            f"pad=512:896:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p[v{index}]"
        )
    filters.append("".join(f"[v{index}]" for index in range(len(outputs))) + f"concat=n={len(outputs)}:v=1:a=0[outv]")
    command = [imageio_ffmpeg.get_ffmpeg_exe(), "-y"]
    for output in outputs:
        command.extend(["-i", str(output)])
    command.extend(
        [
            "-filter_complex", ";".join(filters), "-map", "[outv]", "-an",
            "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-r", str(OUTPUT_FPS), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary),
        ]
    )
    try:
        subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return target


def _strict_validation(path: Path, expected_seconds: float) -> dict:
    report = validate_scene_video(path, expected_seconds)
    errors = list(report.get("errors", []))
    duration = float(report.get("duration_seconds", 0) or 0)
    if abs(duration - expected_seconds) > 0.15:
        errors.append(f"duration is {duration:.3f}s; expected {expected_seconds:.3f}s ± 0.150s")
    first = report.get("first_frame", {})
    if (first.get("width"), first.get("height")) != (720, 1280):
        errors.append(f"publish dimensions are {first.get('width')}x{first.get('height')}; expected 720x1280")
    probe = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    diagnostic = (probe.stderr or "") + (probe.stdout or "")
    report["has_video"] = " Video:" in diagnostic
    report["has_audio"] = " Audio:" in diagnostic
    if not report["has_video"]:
        errors.append("publish output has no video stream")
    if not report["has_audio"]:
        errors.append("publish output has no audio stream")
    report["errors"] = errors
    report["valid"] = not errors
    return report


def _publish(root: Path, state: dict) -> dict:
    raw = _assemble(root, state)
    cues = [
        {
            "start": (item["order"] - 1) * SEGMENT_SECONDS,
            "end": item["order"] * SEGMENT_SECONDS,
            "text": item["caption"],
        }
        for item in state["segments"]
    ]
    output, subtitle = publish_single_shot(
        root,
        f"CHAINED_PLANE_15S_{state['run_id']}",
        raw,
        cues,
        duration_seconds=TOTAL_SECONDS,
    )
    validation = _strict_validation(output, TOTAL_SECONDS)
    if not validation["valid"]:
        state["status"] = "failed"
        state["publish_validation"] = validation
        save(root, state)
        raise RuntimeError("Final publish validation failed: " + "; ".join(validation["errors"]))
    state["status"] = "published"
    state["raw_output"] = str(raw.relative_to(root)).replace("\\", "/")
    state["final_output"] = str(output.relative_to(root)).replace("\\", "/")
    state["subtitle_output"] = str(subtitle.relative_to(root)).replace("\\", "/")
    state["publish_validation"] = validation
    save(root, state)
    return state


def poll(root: Path) -> dict:
    state = initialise(root)
    segment = next((item for item in state["segments"] if item["status"] in {"submitting", "generating"}), None)
    if not segment:
        return state
    poll_i2v_jobs(root)
    jobs = list_i2v_jobs(root)
    job = next((item for item in jobs if item["job_id"] == segment.get("job_id")), None)
    if job is None:
        candidates = [
            item for item in jobs
            if item.get("metadata", {}).get("source") == TEST_NAME
            and int(item.get("metadata", {}).get("segment", 0) or 0) == int(segment["order"])
            and item.get("metadata", {}).get("run_id", state["run_id"]) == state["run_id"]
        ]
        if candidates:
            job = candidates[-1]
            segment["job_id"] = job["job_id"]
            segment["prompt_id"] = job["prompt_id"]
            segment["status"] = "generating"
            save(root, state)
        else:
            return {"status": "job_record_missing", "segment": segment["order"], "job_id": segment.get("job_id", "")}
    if job["status"] == "failed":
        segment["status"] = "failed"
        segment["error"] = job.get("error", "ComfyUI failed")
        state["status"] = "failed"
        return save(root, state)
    if job["status"] != "built":
        return {"status": job["status"], "segment": segment["order"], "job_id": job["job_id"], "prompt_id": job["prompt_id"]}
    output = root / job["output_path"]
    validation = validate_scene_video(output, SEGMENT_SECONDS, source_path=root / segment["source_image"])
    measured = float(validation.get("duration_seconds", 0) or 0)
    if abs(measured - SEGMENT_SECONDS) > 0.15:
        validation["errors"].append(
            f"segment duration is {measured:.3f}s; expected {SEGMENT_SECONDS:.3f}s ± 0.150s"
        )
        validation["valid"] = False
    segment["validation"] = validation
    if not validation["valid"]:
        segment["status"] = "failed"
        state["status"] = "failed"
        return save(root, state)
    segment["output_path"] = job["output_path"]
    segment["end_frame"] = _extract_end_frame(root, output, int(segment["order"]))
    segment["status"] = "complete"
    segment["error"] = ""
    next_segment = next((item for item in state["segments"] if item["status"] == "waiting"), None)
    if next_segment:
        next_segment["source_image"] = segment["end_frame"]
        next_segment["status"] = "ready"
        save(root, state)
        job = _submit(root, state, next_segment)
        return {"status": "next_segment_submitted", "segment": next_segment["order"], "job_id": job["job_id"], "prompt_id": job["prompt_id"]}
    return _publish(root, state)


def recover_segment(root: Path, order: int) -> dict:
    """Retry one segment from the preceding segment's observed final frame."""
    state = initialise(root)
    if order < 2 or order > len(state["segments"]):
        raise ValueError("Only chained segments 2..N can be recovered.")
    if any(item["status"] in {"submitting", "generating"} for item in state["segments"]):
        raise RuntimeError("Cannot recover while another chained segment is active.")
    previous = state["segments"][order - 2]
    segment = state["segments"][order - 1]
    if previous.get("status") != "complete" or not previous.get("end_frame"):
        raise RuntimeError(f"Segment {order - 1} has no validated end frame.")
    segment["prompt"] = SEGMENTS[order - 1]["prompt"]
    segment["source_image"] = previous["end_frame"]
    segment["job_id"] = ""
    segment["prompt_id"] = ""
    segment["output_path"] = ""
    segment["end_frame"] = ""
    segment["error"] = ""
    segment.pop("validation", None)
    segment["status"] = "ready"
    for later in state["segments"][order:]:
        later["prompt"] = SEGMENTS[int(later["order"]) - 1]["prompt"]
        later["source_image"] = ""
        later["job_id"] = ""
        later["prompt_id"] = ""
        later["output_path"] = ""
        later["end_frame"] = ""
        later["error"] = ""
        later.pop("validation", None)
        later["status"] = "waiting"
    state["final_output"] = ""
    state["raw_output"] = ""
    state["subtitle_output"] = ""
    state.pop("publish_validation", None)
    state["status"] = f"ready_segment_{order}_retry"
    save(root, state)
    return _submit(root, state, segment)


def recover_third(root: Path) -> dict:
    return recover_segment(root, 3)


def recover_second(root: Path) -> dict:
    return recover_segment(root, 2)


def run_until_complete(root: Path, *, poll_seconds: float = 20.0, timeout_seconds: float = 0.0) -> dict:
    """Resume a persisted chain and advance it until the publish artifact is verified."""

    started = time.monotonic()
    while True:
        state = initialise(root)
        if state.get("status") == "published":
            return state
        if state.get("status") == "failed":
            raise RuntimeError("Chained reel is failed; recover the failed segment before resuming.")
        if timeout_seconds > 0 and time.monotonic() - started > timeout_seconds:
            raise TimeoutError(f"Chained reel did not finish within {timeout_seconds:g} seconds.")
        active = any(item["status"] in {"submitting", "generating"} for item in state["segments"])
        ready = any(item["status"] == "ready" for item in state["segments"])
        if ready and not active:
            submit_next(root)
        else:
            result = poll(root)
            if result.get("status") == "published":
                return result
        time.sleep(max(2.0, poll_seconds))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action",
        choices=["init", "submit", "poll", "run", "status", "recover-second", "recover-third"],
    )
    parser.add_argument("--poll-seconds", type=float, default=20.0)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=0.0,
        help="Optional safety timeout. Zero keeps long local generations running until completion.",
    )
    args = parser.parse_args()
    root = root_dir()
    os.environ.setdefault("LUCRETIA_COMFY_MODE", "external")
    os.environ.setdefault("LUCRETIA_COMFY_URL", "http://127.0.0.1:8188")
    actions = {
        "init": initialise,
        "submit": submit_next,
        "poll": poll,
        "status": initialise,
        "recover-second": recover_second,
        "recover-third": recover_third,
    }
    result = (
        run_until_complete(root, poll_seconds=args.poll_seconds, timeout_seconds=args.timeout_seconds)
        if args.action == "run"
        else actions[args.action](root)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
