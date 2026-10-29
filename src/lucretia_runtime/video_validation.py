from __future__ import annotations

import re
import subprocess
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image


_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _first_frame_report(video_path: Path, source_path: Path | None) -> dict:
    report = {
        "width": 0,
        "height": 0,
        "portrait": False,
        "source_similarity": None,
        "errors": [],
    }
    try:
        reader = imageio.get_reader(video_path)
        try:
            frame = reader.get_data(0)
        finally:
            reader.close()
    except Exception as exc:
        report["errors"].append(f"first video frame cannot be read: {exc}")
        return report
    height, width = frame.shape[:2]
    report.update({"width": int(width), "height": int(height), "portrait": bool(height > width)})
    if not report["portrait"]:
        report["errors"].append(f"video is not portrait: {width}x{height}")
    if source_path is None:
        return report
    if not source_path.exists():
        report["errors"].append("source keyframe is missing")
        return report
    try:
        source = Image.open(source_path).convert("RGB").resize((32, 32), Image.Resampling.LANCZOS)
        first = Image.fromarray(frame).convert("RGB").resize((32, 32), Image.Resampling.LANCZOS)
        source_values = np.asarray(source, dtype=np.float32)
        first_values = np.asarray(first, dtype=np.float32)
        similarity = 1.0 - float(np.mean(np.abs(source_values - first_values))) / 255.0
        report["source_similarity"] = round(similarity, 4)
        # This is deliberately conservative: it catches a completely unrelated
        # opening frame while allowing normal I2V relighting and recomposition.
        if similarity < 0.35:
            report["errors"].append(f"first frame does not preserve the source keyframe: similarity {similarity:.3f}")
    except Exception as exc:
        report["errors"].append(f"source keyframe comparison failed: {exc}")
    return report


def validate_scene_video(path: Path, expected_seconds: float, source_path: Path | None = None) -> dict:
    """Decode an uploaded scene and enforce a conservative duration floor."""

    result = {
        "valid": False,
        "path": str(path),
        "size_bytes": 0,
        "duration_seconds": 0.0,
        "expected_seconds": float(expected_seconds),
        "first_frame": {},
        "errors": [],
    }
    if not path.exists() or not path.is_file():
        result["errors"].append("output file is missing")
        return result
    result["size_bytes"] = path.stat().st_size
    if result["size_bytes"] < 1024:
        result["errors"].append("output file is too small to be a valid scene video")
        return result

    command = [_ffmpeg_exe(), "-v", "info", "-i", str(path), "-map", "0:v:0", "-f", "null", "-"]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["errors"].append(f"video decoder failed: {exc}")
        return result
    diagnostic = (completed.stderr or "") + "\n" + (completed.stdout or "")
    match = _DURATION.search(diagnostic)
    if match:
        hours, minutes, seconds = match.groups()
        result["duration_seconds"] = round(int(hours) * 3600 + int(minutes) * 60 + float(seconds), 3)
    if completed.returncode != 0:
        result["errors"].append("video cannot be decoded completely")
    if not match:
        result["errors"].append("video duration could not be measured")
    minimum = max(0.25, float(expected_seconds) * 0.65)
    if match and result["duration_seconds"] < minimum:
        result["errors"].append(
            f"video is too short: {result['duration_seconds']:.2f}s; minimum accepted is {minimum:.2f}s"
        )
    first_frame = _first_frame_report(path, source_path)
    result["first_frame"] = first_frame
    result["errors"].extend(first_frame["errors"])
    result["valid"] = not result["errors"]
    return result
