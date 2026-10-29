from __future__ import annotations

import json
import os
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from lucretia_runtime.comfy.adapter import ComfyI2VRequest
from lucretia_runtime.comfy.relay import (
    claim_relay_job,
    complete_relay_job,
    enqueue_relay_job,
    relay_source_path,
    relay_worker_status,
    update_relay_job,
)
from lucretia_runtime.web_app import LucretiaHandler


def _root(tmp_path: Path) -> Path:
    source_root = Path(__file__).resolve().parents[1]
    workflow_dir = tmp_path / "workflows" / "comfy"
    workflow_dir.mkdir(parents=True)
    workflow_dir.joinpath("ltx23_i2v_api.json").write_text(
        source_root.joinpath("workflows/comfy/ltx23_i2v_api.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    asset = tmp_path / "data" / "generated" / "short_assets" / "ball.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(b"fake-png")
    return tmp_path


def test_ai_generated_audio_is_rejected() -> None:
    with pytest.raises(ValueError, match="AI-generated audio is disabled"):
        ComfyI2VRequest(
            image_path="data/generated/short_assets/ball.png",
            prompt="ball rolls",
            generate_audio=True,
        )


def test_relay_job_claim_status_and_output(tmp_path: Path) -> None:
    root = _root(tmp_path)
    request = ComfyI2VRequest(
        image_path="data/generated/short_assets/ball.png",
        prompt="a metal ball rolls downhill",
    )
    queued = enqueue_relay_job(root, request)
    assert queued["status"] == "relay_queued"

    claim = claim_relay_job(root, "test-worker")
    assert claim is not None
    assert claim["job_id"] == queued["job_id"]
    assert claim["request"]["workflow_path"] == "workflows/comfy/ltx23_i2v_api.json"
    assert claim["request"]["generate_audio"] is False
    assert relay_source_path(root, queued["job_id"]).read_bytes() == b"fake-png"
    assert claim_relay_job(root, "second-worker") is None
    worker = relay_worker_status(root)
    assert worker["connected"] is True
    assert worker["worker_id"] == "second-worker"
    assert "worker_id" not in relay_worker_status(root, public=True)

    running = update_relay_job(root, queued["job_id"], {"status": "running", "prompt_id": "prompt-1"})
    assert running["status"] == "relay_running"
    assert running["prompt_id"] == "prompt-1"

    built = complete_relay_job(root, queued["job_id"], "result.mp4", b"video-data", "prompt-1")
    assert built["status"] == "built"
    assert (root / built["output_path"]).read_bytes() == b"video-data"


def test_render_blueprint_enables_relay_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    text = root.joinpath("render.yaml").read_text(encoding="utf-8")
    assert "LUCRETIA_COMFY_MODE" in text
    assert "value: relay" in text
    assert "LUCRETIA_WORKER_TOKEN" in text
    launcher = root.joinpath("scripts/windows/run_render_comfy_worker.bat").read_text(encoding="utf-8")
    assert "git pull --ff-only" in launcher
    assert "scripts\\comfy_render_worker.py --root ." in launcher


def test_worker_http_endpoints_are_authenticated(tmp_path: Path) -> None:
    root = _root(tmp_path)
    queued = enqueue_relay_job(
        root,
        ComfyI2VRequest(image_path="data/generated/short_assets/ball.png", prompt="ball rolls"),
    )
    previous = os.environ.get("LUCRETIA_WORKER_TOKEN")
    os.environ["LUCRETIA_WORKER_TOKEN"] = "test-worker-secret"
    LucretiaHandler.root = root
    server = ThreadingHTTPServer(("127.0.0.1", 0), LucretiaHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        unauthorized = urllib.request.Request(f"{base}/worker/claim")
        try:
            urllib.request.urlopen(unauthorized, timeout=5)
            raise AssertionError("worker endpoint accepted a request without a token")
        except urllib.error.HTTPError as exc:
            assert exc.code == 401
        authorized = urllib.request.Request(
            f"{base}/worker/claim?worker_id=test",
            headers={"Authorization": "Bearer test-worker-secret"},
        )
        payload = json.loads(urllib.request.urlopen(authorized, timeout=5).read())
        assert payload["job"]["job_id"] == queued["job_id"]
        state_request = urllib.request.Request(
            f"{base}/worker/state",
            headers={"Authorization": "Bearer test-worker-secret"},
        )
        state = json.loads(urllib.request.urlopen(state_request, timeout=5).read())
        assert state["schema_version"] == 1
        assert state["safe"] is False
        health = json.loads(urllib.request.urlopen(f"{base}/healthz", timeout=5).read())
        assert health["revision"] == "local"
        assert health["worker"]["connected"] is True
        assert "worker_id" not in health["worker"]
    finally:
        server.shutdown()
        server.server_close()
        if previous is None:
            os.environ.pop("LUCRETIA_WORKER_TOKEN", None)
        else:
            os.environ["LUCRETIA_WORKER_TOKEN"] = previous
