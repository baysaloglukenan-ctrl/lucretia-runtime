from __future__ import annotations

import argparse
import json
from pathlib import Path

from .asset_short_builder import AssetSceneSpec, AssetShortSpec, build_asset_short
from .comfy import ComfyI2VRequest, ComfyManager, comfy_status, list_i2v_jobs, poll_i2v_jobs, submit_i2v_job
from .local_video_builder import build_local_video_from_plan, build_local_videos_from_dir
from .motion_core import render_magnet_pull_demo
from .motion_reel_builder import MotionReelSpec, build_motion_reel
from .provider_gateway import (
    materialize_provider_assets_into_plan,
    poll_runway_jobs,
    submit_mock_jobs_for_plan,
    submit_runway_jobs_for_plan,
)
from .reel_builder import build_final_reel_from_latest_runway_jobs, stage_runway_outputs
from .web_app import serve


def command_comfy_status(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    print(json.dumps(comfy_status(root), indent=2, ensure_ascii=False))


def command_comfy_start(args: argparse.Namespace) -> None:
    manager = ComfyManager()
    print(json.dumps(manager.start(wait_seconds=args.wait_seconds), indent=2, ensure_ascii=False))


def command_comfy_i2v_submit(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    request = ComfyI2VRequest(
        image_path=args.image,
        prompt=args.prompt,
        negative_prompt=args.negative_prompt,
        seed=args.seed,
        frames=args.frames,
        width=args.width,
        height=args.height,
        workflow_path=args.workflow,
        generate_audio=False,
        metadata={"source": "cli"},
    )
    job = submit_i2v_job(root, request, auto_start=not args.no_auto_start)
    print(json.dumps(job, indent=2, ensure_ascii=False))


def command_comfy_i2v_poll(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    jobs = poll_i2v_jobs(root, import_outputs=True)
    print(json.dumps(jobs, indent=2, ensure_ascii=False))


def command_comfy_i2v_jobs(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    print(json.dumps(list_i2v_jobs(root), indent=2, ensure_ascii=False))


def command_build_local_video(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    if args.assembly_plan:
        out = build_local_video_from_plan(root / args.assembly_plan, output_dir, project_root=root, fps=args.fps, width=args.width, height=args.height)
        print(f"Built local video: {out}")
    else:
        paths = build_local_videos_from_dir(root / args.assembly_dir, output_dir, project_root=root, fps=args.fps, width=args.width, height=args.height)
        print(f"Built {len(paths)} local video file(s).")
        for path in paths:
            print(f"- {path}")


def command_asset_short(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    assets = args.asset or []
    captions = args.caption or []
    motions = args.motion or []
    scenes = []
    for idx, asset in enumerate(assets[:6]):
        scenes.append(AssetSceneSpec(asset_path=asset, caption=captions[idx] if idx < len(captions) else "", motion=motions[idx] if idx < len(motions) else "zoom_in"))
    spec = AssetShortSpec(title=args.title, hook_text=args.hook_text, outro_text=args.outro_text, duration_seconds=args.duration_seconds, fps=args.fps, width=args.width, height=args.height, publish_mode=not args.storyboard_mode, scenes=tuple(scenes))
    out = build_asset_short(root, spec, output_dir)
    print(f"Built asset-first short: {out}")


def command_motion_core_demo(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    out = render_magnet_pull_demo(root, output_dir=output_dir, width=args.width, height=args.height, duration=args.duration_seconds, fps=args.fps)
    print(f"Built Motion Core object-animation demo: {out}")


def command_motion_reel(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    spec = MotionReelSpec(universe_id=args.universe_id, scene_id=args.scene_id, preset_id=args.preset_id, custom_prompt=args.custom_prompt, template_id=args.template_id, duration_seconds=args.duration_seconds, fps=args.fps, width=args.width, height=args.height)
    out = build_motion_reel(spec, output_dir)
    print(f"Built zero-credit template motion reel: {out}")


def _assembly_plan_paths(root: Path, assembly_plan: str | None, assembly_dir: str) -> list[Path]:
    if assembly_plan:
        return [root / assembly_plan]
    return sorted((root / assembly_dir).glob("ASP_*.json"))


def command_provider_mock_build(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    plans = _assembly_plan_paths(root, args.assembly_plan, args.assembly_dir)
    total = 0
    for plan_path in plans:
        jobs = submit_mock_jobs_for_plan(root, plan_path, width=args.width, height=args.height)
        print(f"Built {len(jobs)} mock provider job(s) from {plan_path}")
        for job in jobs:
            print(f"- {job.job_id} {job.status} {job.output_path or ''}")
        total += len(jobs)
    print(f"Provider mock build complete: {total} job(s).")


def command_provider_runway_submit(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    plans = _assembly_plan_paths(root, args.assembly_plan, args.assembly_dir)
    total = 0
    for plan_path in plans:
        jobs = submit_runway_jobs_for_plan(root, plan_path, width=args.width, height=args.height, max_segments=args.max_segments)
        print(f"Submitted {len(jobs)} Runway provider job(s) from {plan_path}")
        for job in jobs:
            task_id = job.provider_response.get("task_id", "")
            print(f"- {job.job_id} {job.status} task={task_id} error={job.error or ''}")
        total += len(jobs)
    print(f"Runway submit complete: {total} job(s).")


def command_provider_runway_poll(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    jobs = poll_runway_jobs(root)
    print(f"Polled {len(jobs)} Runway job(s).")
    for job in jobs:
        print(f"- {job.job_id} {job.status} output={job.output_path or ''} error={job.error or ''}")


def command_provider_stage_runway(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    jobs = stage_runway_outputs(root)
    print(f"Localized {len(jobs)} Runway output(s).")
    for job in jobs:
        print(f"- {job.job_id} -> {job.output_path or ''}")


def command_provider_build_final_reel(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    out = build_final_reel_from_latest_runway_jobs(root, output_dir, limit=args.limit, width=args.width, height=args.height, fps=args.fps)
    print(f"Built final Runway reel: {out}")


def command_provider_build_video(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    output_dir = root / args.output_dir
    plans = _assembly_plan_paths(root, args.assembly_plan, args.assembly_dir)
    built = 0
    for plan_path in plans:
        if args.build_assets:
            submit_mock_jobs_for_plan(root, plan_path, width=args.width, height=args.height)
        provider_plan = materialize_provider_assets_into_plan(root, plan_path)
        out = build_local_video_from_plan(provider_plan, output_dir, project_root=root, fps=args.fps, width=args.width, height=args.height)
        print(f"Built provider-backed video: {out}")
        print(f"- provider assembly plan: {provider_plan}")
        built += 1
    print(f"Provider-backed video build complete: {built} file(s).")


def command_serve(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    serve(host=args.host, port=args.port, root=root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Lucreția Runtime CLI")
    sub = parser.add_subparsers(dest="command", required=False)

    comfy_status_p = sub.add_parser("comfy-status", help="Show managed/external ComfyUI engine status.")
    comfy_status_p.add_argument("--root", default=".")
    comfy_status_p.set_defaults(func=command_comfy_status)

    comfy_start = sub.add_parser("comfy-start", help="Start managed ComfyUI engine.")
    comfy_start.add_argument("--wait-seconds", type=int, default=30)
    comfy_start.set_defaults(func=command_comfy_start)

    comfy_submit = sub.add_parser("comfy-i2v-submit", help="Submit image-to-video job to ComfyUI.")
    comfy_submit.add_argument("--root", default=".")
    comfy_submit.add_argument("--image", required=True, help="Relative or absolute source image path.")
    comfy_submit.add_argument("--prompt", required=True)
    comfy_submit.add_argument("--negative-prompt", default="")
    comfy_submit.add_argument("--seed", type=int, default=12345)
    comfy_submit.add_argument("--frames", type=int, default=9)
    comfy_submit.add_argument("--width", type=int, default=512)
    comfy_submit.add_argument("--height", type=int, default=320)
    comfy_submit.add_argument("--workflow", default="workflows/comfy/ltx23_i2v_api.json")
    comfy_submit.add_argument("--no-auto-start", action="store_true")
    comfy_submit.set_defaults(func=command_comfy_i2v_submit)

    comfy_poll = sub.add_parser("comfy-i2v-poll", help="Poll ComfyUI I2V jobs and import outputs.")
    comfy_poll.add_argument("--root", default=".")
    comfy_poll.set_defaults(func=command_comfy_i2v_poll)

    comfy_jobs = sub.add_parser("comfy-i2v-jobs", help="List ComfyUI I2V jobs.")
    comfy_jobs.add_argument("--root", default=".")
    comfy_jobs.set_defaults(func=command_comfy_i2v_jobs)

    mcore = sub.add_parser("motion-core-demo", help="Build a local object-animation demo: screw pulled to magnet.")
    mcore.add_argument("--root", default=".")
    mcore.add_argument("--output-dir", default="data/generated/videos")
    mcore.add_argument("--duration-seconds", type=float, default=5.0)
    mcore.add_argument("--fps", type=int, default=24)
    mcore.add_argument("--width", type=int, default=720)
    mcore.add_argument("--height", type=int, default=1280)
    mcore.set_defaults(func=command_motion_core_demo)

    asset = sub.add_parser("asset-short", help="Build a publish-mode short from uploaded/generated image assets.")
    asset.add_argument("--root", default=".")
    asset.add_argument("--output-dir", default="data/generated/videos")
    asset.add_argument("--asset", action="append", help="Relative image asset path. Repeat 1-6 times.")
    asset.add_argument("--caption", action="append", help="Scene caption. Repeat to match assets.")
    asset.add_argument("--motion", action="append", help="Scene motion: zoom_in, zoom_out, pan_left, pan_right, hold, slide_up, parallax_soft.")
    asset.add_argument("--title", default="Lucretia Asset Short")
    asset.add_argument("--hook-text", default="")
    asset.add_argument("--outro-text", default="")
    asset.add_argument("--duration-seconds", type=int, default=30)
    asset.add_argument("--fps", type=int, default=12)
    asset.add_argument("--width", type=int, default=720)
    asset.add_argument("--height", type=int, default=1280)
    asset.add_argument("--storyboard-mode", action="store_true")
    asset.set_defaults(func=command_asset_short)

    motion = sub.add_parser("motion-reel", help="Build a zero-credit local template motion reel.")
    motion.add_argument("--root", default=".")
    motion.add_argument("--output-dir", default="data/generated/videos")
    motion.add_argument("--template-id", default="atlas_object_lab")
    motion.add_argument("--universe-id", default="atlas_lab")
    motion.add_argument("--scene-id", default="lab_object_awake")
    motion.add_argument("--preset-id", default="hook_fast")
    motion.add_argument("--custom-prompt", default="")
    motion.add_argument("--duration-seconds", type=int, default=30)
    motion.add_argument("--fps", type=int, default=12)
    motion.add_argument("--width", type=int, default=720)
    motion.add_argument("--height", type=int, default=1280)
    motion.set_defaults(func=command_motion_reel)

    vid = sub.add_parser("build-local-video", help="Build local MP4 videos from assembly plans.")
    vid.add_argument("--root", default=".")
    vid.add_argument("--assembly-plan", default=None)
    vid.add_argument("--assembly-dir", default="data/generated/assembly")
    vid.add_argument("--output-dir", default="data/generated/videos")
    vid.add_argument("--fps", type=int, default=12)
    vid.add_argument("--width", type=int, default=720)
    vid.add_argument("--height", type=int, default=1280)
    vid.set_defaults(func=command_build_local_video)

    provider = sub.add_parser("provider-mock-build", help="Build mock provider assets from assembly plans.")
    provider.add_argument("--root", default=".")
    provider.add_argument("--assembly-plan", default=None)
    provider.add_argument("--assembly-dir", default="data/generated/assembly")
    provider.add_argument("--width", type=int, default=720)
    provider.add_argument("--height", type=int, default=1280)
    provider.set_defaults(func=command_provider_mock_build)

    runway_submit = sub.add_parser("provider-runway-submit", help="Submit Runway provider jobs from assembly plans.")
    runway_submit.add_argument("--root", default=".")
    runway_submit.add_argument("--assembly-plan", default=None)
    runway_submit.add_argument("--assembly-dir", default="data/generated/assembly")
    runway_submit.add_argument("--width", type=int, default=720)
    runway_submit.add_argument("--height", type=int, default=1280)
    runway_submit.add_argument("--max-segments", type=int, default=1)
    runway_submit.set_defaults(func=command_provider_runway_submit)

    runway_poll = sub.add_parser("provider-runway-poll", help="Poll submitted Runway provider jobs.")
    runway_poll.add_argument("--root", default=".")
    runway_poll.set_defaults(func=command_provider_runway_poll)

    runway_stage = sub.add_parser("provider-stage-runway", help="Download built Runway outputs into provider_assets.")
    runway_stage.add_argument("--root", default=".")
    runway_stage.set_defaults(func=command_provider_stage_runway)

    final_reel = sub.add_parser("provider-build-final-reel", help="Build final local MP4 from built Runway clips.")
    final_reel.add_argument("--root", default=".")
    final_reel.add_argument("--output-dir", default="data/generated/videos")
    final_reel.add_argument("--limit", type=int, default=3)
    final_reel.add_argument("--fps", type=int, default=24)
    final_reel.add_argument("--width", type=int, default=720)
    final_reel.add_argument("--height", type=int, default=1280)
    final_reel.set_defaults(func=command_provider_build_final_reel)

    provider_video = sub.add_parser("provider-build-video", help="Build provider-backed MP4 videos from assembly plans.")
    provider_video.add_argument("--root", default=".")
    provider_video.add_argument("--assembly-plan", default=None)
    provider_video.add_argument("--assembly-dir", default="data/generated/assembly")
    provider_video.add_argument("--output-dir", default="data/generated/videos")
    provider_video.add_argument("--fps", type=int, default=12)
    provider_video.add_argument("--width", type=int, default=720)
    provider_video.add_argument("--height", type=int, default=1280)
    provider_video.add_argument("--build-assets", action="store_true", help="Build mock provider assets before materializing the provider-backed plan.")
    provider_video.set_defaults(func=command_provider_build_video)

    srv = sub.add_parser("serve", help="Run the Lucreția Runtime web app.")
    srv.add_argument("--root", default=".")
    srv.add_argument("--host", default="0.0.0.0")
    srv.add_argument("--port", type=int, default=None)
    srv.set_defaults(func=command_serve)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        args = parser.parse_args(["serve"])
    args.func(args)


if __name__ == "__main__":
    main()
