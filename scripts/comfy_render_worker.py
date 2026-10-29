from __future__ import annotations

import argparse
import json
import os
import socket
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lucretia_runtime.comfy import ComfyI2VRequest, poll_i2v_jobs, submit_i2v_job


def request(server: str, token: str, path: str, *, data: bytes | None = None, headers: dict | None = None) -> bytes:
    merged = {"Authorization": f"Bearer {token}", **(headers or {})}
    req = urllib.request.Request(server.rstrip("/") + path, data=data, headers=merged, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=300) as response:
        return response.read()


def post_json(server: str, token: str, path: str, payload: dict) -> dict:
    raw = request(
        server,
        token,
        path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(raw.decode("utf-8"))


def sync_server_state(root: Path, server: str, token: str, *, restore: bool = False) -> None:
    backup = root / "data" / "generated" / "comfy" / "render_state_backup.json"
    backup.parent.mkdir(parents=True, exist_ok=True)
    known = ""
    if backup.exists():
        try:
            local = json.loads(backup.read_text(encoding="utf-8"))
            known = str(local.get("revision", ""))
            if restore:
                post_json(server, token, "/worker/state/restore", local)
        except Exception as exc:
            print(f"State restore skipped: {exc}")
    encoded_known = urllib.parse.quote(known, safe="")
    remote = json.loads(request(server, token, f"/worker/state?known={encoded_known}").decode("utf-8"))
    if remote.get("unchanged") or not remote.get("safe"):
        return
    temp = backup.with_suffix(".tmp")
    temp.write_text(json.dumps(remote, ensure_ascii=False), encoding="utf-8")
    temp.replace(backup)


def process_job(root: Path, server: str, token: str, worker_id: str, claimed: dict, poll_seconds: int) -> None:
    remote_id = claimed["job_id"]
    spec = claimed["request"]
    source_bytes = request(server, token, claimed["image_url"])
    suffix = Path(claimed["image_url"]).suffix or ".png"
    with tempfile.NamedTemporaryFile(prefix="lucretia_relay_", suffix=suffix, delete=False) as handle:
        handle.write(source_bytes)
        source = Path(handle.name)
    try:
        local = submit_i2v_job(
            root,
            ComfyI2VRequest(
                image_path=str(source),
                prompt=spec["prompt"],
                negative_prompt=spec.get("negative_prompt", ""),
                seed=int(spec.get("seed", 12345)),
                frames=int(spec.get("frames", 121)),
                width=int(spec.get("width", 320)),
                height=int(spec.get("height", 576)),
                workflow_path=spec.get("workflow_path", "workflows/comfy/ltx23_i2v_api.json"),
                generate_audio=False,
                metadata={"source": "render_relay", "remote_job_id": remote_id},
            ),
            auto_start=False,
        )
        post_json(server, token, f"/worker/jobs/{remote_id}/status", {
            "status": "running",
            "worker_id": worker_id,
            "local_job_id": local["job_id"],
            "prompt_id": local["prompt_id"],
            "stage": "scene_generation",
        })
        while True:
            current = next(item for item in poll_i2v_jobs(root, import_outputs=True) if item["job_id"] == local["job_id"])
            if current.get("status") == "built":
                output = root / current["output_path"]
                request(
                    server,
                    token,
                    f"/worker/jobs/{remote_id}/output",
                    data=output.read_bytes(),
                    headers={
                        "Content-Type": "video/mp4",
                        "X-Filename": output.name,
                        "X-Prompt-ID": str(current.get("prompt_id", "")),
                    },
                )
                return
            if current.get("status") == "failed":
                raise RuntimeError(current.get("error") or "Local ComfyUI job failed")
            post_json(server, token, f"/worker/jobs/{remote_id}/status", {
                "status": "running",
                "worker_id": worker_id,
                "local_job_id": local["job_id"],
                "prompt_id": local["prompt_id"],
                "stage": current.get("current_stage", "scene_generation"),
            })
            time.sleep(poll_seconds)
    except Exception as exc:
        post_json(server, token, f"/worker/jobs/{remote_id}/status", {
            "status": "failed",
            "worker_id": worker_id,
            "error": str(exc),
        })
    finally:
        source.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Lucretia Render to local ComfyUI worker")
    parser.add_argument("--server", default=os.environ.get("LUCRETIA_RENDER_URL", "https://lucretia-runtime-milestone-8-assembly.onrender.com"))
    parser.add_argument("--token", default=os.environ.get("LUCRETIA_WORKER_TOKEN", ""))
    parser.add_argument("--root", default=".")
    parser.add_argument("--interval", type=int, default=10)
    args = parser.parse_args()
    if not args.token:
        raise SystemExit("Set LUCRETIA_WORKER_TOKEN or pass --token.")
    root = Path(args.root).resolve()
    worker_id = f"{socket.gethostname()}-{os.getpid()}"
    print(f"Lucretia worker {worker_id} connected to {args.server}")
    first_sync = True
    while True:
        try:
            sync_server_state(root, args.server, args.token, restore=first_sync)
            first_sync = False
            claimed = json.loads(request(args.server, args.token, f"/worker/claim?worker_id={worker_id}").decode("utf-8"))
            if claimed.get("job"):
                process_job(root, args.server, args.token, worker_id, claimed["job"], args.interval)
            else:
                time.sleep(args.interval)
        except urllib.error.HTTPError as exc:
            print(f"Worker HTTP error {exc.code}: {exc.read().decode('utf-8', errors='replace')}")
            time.sleep(args.interval)
        except Exception as exc:
            print(f"Worker error: {exc}")
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
