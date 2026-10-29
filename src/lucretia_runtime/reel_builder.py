from __future__ import annotations

import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

from .provider_gateway import list_jobs, provider_assets_dir, save_job
from .provider_models import utc_now_iso


def _safe_rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def _ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def stage_runway_outputs(root: Path) -> list:
    updates = []
    assets_dir = provider_assets_dir(root)
    for job in list_jobs(root):
        if job.provider != "runway" or job.status != "built" or not job.output_path:
            continue
        if not str(job.output_path).startswith("http"):
            continue
        target = assets_dir / f"{job.job_id}.mp4"
        with urllib.request.urlopen(str(job.output_path), timeout=120) as response:
            target.write_bytes(response.read())
        updated = job.with_status(
            "built",
            output_path=_safe_rel(target, root),
            output_type="video/mp4",
            provider_response={
                **job.provider_response,
                "remote_output_url": job.output_path,
                "local_asset_path": _safe_rel(target, root),
                "localized_at": utc_now_iso(),
            },
        )
        save_job(root, updated)
        updates.append(updated)
    return updates


def _normalize_clip(src: Path, dst: Path, width: int = 720, height: int = 1280, fps: int = 24) -> None:
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
    )
    cmd = [
        _ffmpeg_exe(),
        "-y",
        "-i",
        str(src),
        "-an",
        "-r",
        str(fps),
        "-vf",
        vf,
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        str(dst),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def build_final_reel_from_latest_runway_jobs(root: Path, output_dir: Path, limit: int = 3, width: int = 720, height: int = 1280, fps: int = 24) -> Path:
    stage_runway_outputs(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        job
        for job in list_jobs(root)
        if job.provider == "runway" and job.status == "built" and job.output_path and not str(job.output_path).startswith("http")
    ]
    if not jobs:
        raise RuntimeError("No localized Runway clips are available. Poll built jobs first.")
    selected = list(reversed(jobs[:limit]))
    temp_dir = output_dir / "_tmp_runway_reel"
    temp_dir.mkdir(parents=True, exist_ok=True)
    normalized: list[Path] = []
    for idx, job in enumerate(selected, start=1):
        src = root / str(job.output_path)
        dst = temp_dir / f"{idx:02d}_{job.job_id}.mp4"
        _normalize_clip(src, dst, width=width, height=height, fps=fps)
        normalized.append(dst)
    stamp = utc_now_iso().replace(":", "-").replace("+", "Z")
    final_path = output_dir / f"FINAL_REEL_RUNWAY_{stamp}.mp4"
    if len(normalized) == 1:
        shutil.copy2(normalized[0], final_path)
    else:
        concat_list = temp_dir / "concat.txt"
        concat_list.write_text("\n".join([f"file '{clip.name}'" for clip in normalized]), encoding="utf-8")
        cmd = [_ffmpeg_exe(), "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(final_path)]
        subprocess.run(cmd, cwd=temp_dir, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    summary = {
        "sprint": 12,
        "builder": "runway_final_reel",
        "selected_jobs": [job.job_id for job in selected],
        "clip_count": len(selected),
        "output_file": _safe_rel(final_path, root),
        "status": "built",
        "built_at": utc_now_iso(),
    }
    (output_dir / "runway_final_reel_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return final_path
