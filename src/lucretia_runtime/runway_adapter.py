from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict

from .provider_models import ProviderAssetRequest


RUNWAY_API_KEY_ENV = "RUNWAY_API_KEY"
RUNWAY_API_BASE_ENV = "RUNWAY_API_BASE"
RUNWAY_API_VERSION_ENV = "RUNWAY_API_VERSION"
RUNWAY_MODEL_ENV = "RUNWAY_MODEL"
RUNWAY_DEFAULT_DURATION_ENV = "RUNWAY_DEFAULT_DURATION"
RUNWAY_IMAGE_TO_VIDEO_PATH_ENV = "RUNWAY_IMAGE_TO_VIDEO_PATH"
RUNWAY_TEXT_TO_VIDEO_PATH_ENV = "RUNWAY_TEXT_TO_VIDEO_PATH"
RUNWAY_TASK_PATH_ENV = "RUNWAY_TASK_PATH"
RUNWAY_DRY_RUN_ENV = "RUNWAY_DRY_RUN"
DEFAULT_RUNWAY_API_VERSION = "2024-11-06"
DEFAULT_RUNWAY_MODEL = "seedance2_fast"
DEFAULT_RUNWAY_DURATION = 6
RUNWAY_MIN_DURATION = 4
RUNWAY_MAX_DURATION = 15


def _normalize_api_key(value: str) -> str:
    token = (value or "").strip().strip('"').strip("'").strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    return token


@dataclass(frozen=True)
class RunwayConfig:
    api_key: str
    api_base: str = "https://api.dev.runwayml.com/v1"
    api_version: str = DEFAULT_RUNWAY_API_VERSION
    model: str = DEFAULT_RUNWAY_MODEL
    default_duration: int = DEFAULT_RUNWAY_DURATION
    text_to_video_path: str = "/text_to_video"
    image_to_video_path: str = "/image_to_video"
    task_path_template: str = "/tasks/{task_id}"
    dry_run: bool = False

    @property
    def configured(self) -> bool:
        return self.api_key.startswith("key_")

    @property
    def api_key_present(self) -> bool:
        return bool(self.api_key.strip())


def runway_config_from_env() -> RunwayConfig:
    dry_raw = os.environ.get(RUNWAY_DRY_RUN_ENV, "").strip().lower()
    return RunwayConfig(
        api_key=_normalize_api_key(os.environ.get(RUNWAY_API_KEY_ENV, "")),
        api_base=os.environ.get(RUNWAY_API_BASE_ENV, "https://api.dev.runwayml.com/v1").strip().rstrip("/"),
        api_version=os.environ.get(RUNWAY_API_VERSION_ENV, DEFAULT_RUNWAY_API_VERSION).strip() or DEFAULT_RUNWAY_API_VERSION,
        model=os.environ.get(RUNWAY_MODEL_ENV, DEFAULT_RUNWAY_MODEL).strip() or DEFAULT_RUNWAY_MODEL,
        default_duration=max(RUNWAY_MIN_DURATION, min(RUNWAY_MAX_DURATION, int(os.environ.get(RUNWAY_DEFAULT_DURATION_ENV, str(DEFAULT_RUNWAY_DURATION)).strip() or str(DEFAULT_RUNWAY_DURATION)))),
        text_to_video_path=os.environ.get(RUNWAY_TEXT_TO_VIDEO_PATH_ENV, "/text_to_video").strip(),
        image_to_video_path=os.environ.get(RUNWAY_IMAGE_TO_VIDEO_PATH_ENV, "/image_to_video").strip(),
        task_path_template=os.environ.get(RUNWAY_TASK_PATH_ENV, "/tasks/{task_id}").strip(),
        dry_run=dry_raw in {"1", "true", "yes", "on"},
    )


def _url(config: RunwayConfig, path: str) -> str:
    if not path.startswith("/"):
        path = "/" + path
    return config.api_base + path


def _headers(config: RunwayConfig) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.api_key}",
        "X-Runway-Version": config.api_version,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _request_json(method: str, url: str, config: RunwayConfig, payload: Dict[str, Any] | None = None, timeout: int = 45) -> Dict[str, Any]:
    data = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper(), headers=_headers(config))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Runway API HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Runway API connection error: {exc.reason}") from exc


def _safe_prompt(request: ProviderAssetRequest) -> str:
    base = request.prompt.strip() or request.scene_id
    return (
        f"Vertical short-form reel shot. {base}. "
        "Cinematic social-media composition, clear subject, smooth camera motion, clean lighting, no captions or text overlay."
    )


def _submit_payload(request: ProviderAssetRequest, config: RunwayConfig) -> Dict[str, Any]:
    requested = int(round(float(request.duration_seconds or config.default_duration)))
    duration = max(RUNWAY_MIN_DURATION, min(RUNWAY_MAX_DURATION, requested))
    return {
        "model": config.model,
        "promptText": _safe_prompt(request),
        "duration": duration,
        "ratio": "720:1280",
    }


def _require_valid_key(config: RunwayConfig) -> None:
    if config.configured:
        return
    if not config.api_key_present:
        raise RuntimeError(f"{RUNWAY_API_KEY_ENV} is not configured.")
    raise RuntimeError(
        f"{RUNWAY_API_KEY_ENV} must be the Runway developer API key that starts with 'key_'. "
        "Do not paste a browser token, JWT, MCP token, or the word 'Bearer'."
    )


def submit_runway_text_to_video(request: ProviderAssetRequest, config: RunwayConfig | None = None) -> Dict[str, Any]:
    config = config or runway_config_from_env()
    payload = _submit_payload(request, config)

    if config.dry_run:
        return {
            "dry_run": True,
            "provider": "runway",
            "task_id": f"DRY_RUN_{request.segment_id}_{int(time.time())}",
            "status": "submitted",
            "request_payload": payload,
            "api_version": config.api_version,
            "note": "RUNWAY_DRY_RUN is enabled; no external API call was made.",
        }

    _require_valid_key(config)

    response = _request_json("POST", _url(config, config.text_to_video_path), config, payload=payload)
    task_id = str(response.get("id") or response.get("task_id") or response.get("taskId") or "")
    if not task_id:
        raise RuntimeError(f"Runway response did not include a task id: {json.dumps(response)[:500]}")
    return {
        "provider": "runway",
        "task_id": task_id,
        "status": str(response.get("status", "submitted")),
        "api_version": config.api_version,
        "request_payload": payload,
        "response": response,
    }


def poll_runway_task(task_id: str, config: RunwayConfig | None = None) -> Dict[str, Any]:
    config = config or runway_config_from_env()
    if task_id.startswith("DRY_RUN_") or config.dry_run:
        return {
            "dry_run": True,
            "id": task_id,
            "status": "SUCCEEDED",
            "output": [],
            "api_version": config.api_version,
            "note": "Dry-run task; no external provider output exists.",
        }
    _require_valid_key(config)
    path = config.task_path_template.format(task_id=task_id)
    return _request_json("GET", _url(config, path), config)


def extract_runway_output_url(payload: Dict[str, Any]) -> str | None:
    for key in ("output", "outputs", "assets", "videos"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, str):
                return first
            if isinstance(first, dict):
                for nested_key in ("url", "uri", "src", "assetUrl"):
                    if first.get(nested_key):
                        return str(first[nested_key])
        if isinstance(value, dict):
            for nested_key in ("url", "uri", "src", "assetUrl"):
                if value.get(nested_key):
                    return str(value[nested_key])
    for key in ("url", "assetUrl", "videoUrl"):
        if payload.get(key):
            return str(payload[key])
    return None


def runway_status_from_payload(payload: Dict[str, Any]) -> str:
    raw = str(payload.get("status") or payload.get("state") or "unknown").lower()
    if raw in {"succeeded", "success", "completed", "complete", "done"}:
        return "built"
    if raw in {"failed", "failure", "error", "errored", "cancelled", "canceled"}:
        return "failed"
    if raw in {"running", "processing", "pending", "queued", "throttled", "submitted", "in_progress"}:
        return "submitted"
    return raw or "unknown"
