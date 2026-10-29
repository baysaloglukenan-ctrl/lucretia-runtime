from __future__ import annotations

import hashlib
import html
import json
import mimetypes
import os
import re
import secrets
import time
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .asset_short_builder import MOTIONS, AssetSceneSpec, AssetShortSpec, build_asset_short, list_short_assets, short_assets_dir
from .autonomous_production import create_original_reel, start_original_reel
from .comfy import (
    ComfyI2VRequest,
    ComfyManager,
    claim_relay_job,
    comfy_status,
    complete_relay_job,
    enqueue_relay_job,
    list_i2v_jobs,
    poll_i2v_jobs,
    relay_source_path,
    relay_worker_status,
    submit_i2v_job,
    update_relay_job,
)
from .local_video_builder import build_local_video_from_plan
from .final_reel_composer import compose_final_reel
from .motion_core import render_magnet_pull_demo
from .motion_reel_builder import MotionReelSpec, build_motion_reel, get_motion_templates
from .prompt_catalog import compose_prompt, get_catalog
from .production import (
    assemble_production,
    compile_scene_prompt,
    create_production,
    mark_scene_submitted,
    review_scene,
    scene_for_submission,
    update_scene,
)
from .production_ui import render_production_home
from .provider_gateway import (
    materialize_provider_assets_into_plan,
    poll_runway_jobs,
    provider_assets_dir,
    provider_summary,
    submit_mock_jobs_for_plan,
    submit_provider_request,
)
from .provider_models import ProviderAssetRequest
from .reel_builder import build_final_reel_from_latest_runway_jobs, stage_runway_outputs
from .state_backup import export_relay_state, restore_relay_state

ACCESS_TOKEN_ENV = "LUCRETIA_ACCESS_TOKEN"
ACCESS_COOKIE = "lucretia_runtime_access"
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".webm", ".mov"}
AUDIO_SUFFIXES = {".mp3", ".wav", ".m4a", ".aac"}


def _json(path: Path, fallback=None):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return fallback if fallback is not None else {}


def _configured_token() -> str:
    return os.environ.get(ACCESS_TOKEN_ENV, "").strip()


def _worker_token() -> str:
    return os.environ.get("LUCRETIA_WORKER_TOKEN", "").strip()


def _worker_authorized(handler: BaseHTTPRequestHandler) -> bool:
    configured = _worker_token()
    supplied = handler.headers.get("Authorization", "")
    return bool(configured) and supplied.startswith("Bearer ") and secrets.compare_digest(supplied[7:], configured)


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _cookie_value(cookie_header: str | None, name: str) -> str:
    if not cookie_header:
        return ""
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return ""
    morsel = cookie.get(name)
    return morsel.value if morsel else ""


def _access_cookie_header(token: str, handler: BaseHTTPRequestHandler) -> str:
    cookie = SimpleCookie()
    cookie[ACCESS_COOKIE] = _token_fingerprint(token)
    cookie[ACCESS_COOKIE]["path"] = "/"
    cookie[ACCESS_COOKIE]["httponly"] = True
    cookie[ACCESS_COOKIE]["samesite"] = "Lax"
    if handler.headers.get("X-Forwarded-Proto", "").lower() == "https":
        cookie[ACCESS_COOKIE]["secure"] = True
    return cookie.output(header="").strip()


def _access_decision(handler: BaseHTTPRequestHandler, parsed) -> tuple[bool, str | None, str, int]:
    token = _configured_token()
    if not token:
        return False, None, f"{ACCESS_TOKEN_ENV} is not configured on this host.", 503
    query_token = parse_qs(parsed.query).get("token", [""])[0]
    if query_token:
        if hashlib.sha256(query_token.encode("utf-8")).hexdigest() == _token_fingerprint(token):
            return True, _access_cookie_header(token, handler), "", 200
        return False, None, "Invalid access token.", 401
    expected_cookie = _token_fingerprint(token)
    actual_cookie = _cookie_value(handler.headers.get("Cookie"), ACCESS_COOKIE)
    if actual_cookie and actual_cookie == expected_cookie:
        return True, None, "", 200
    return False, None, "Access token required. Open with ?token=<your-token> once.", 401


def _locked_page(reason: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lucreția Locked</title>
<style>body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#07111f;color:#edf4ff;font-family:Inter,Segoe UI,Arial}}.card{{max-width:760px;margin:24px;padding:28px;border:1px solid #24344f;border-radius:20px;background:#101a2b}}p{{color:#aab8cf;line-height:1.5}}code{{color:#a8d9ff}}</style></head>
<body><main class="card"><h1>Lucreția Runtime Locked</h1><p>{html.escape(reason)}</p><p>Health: <code>/healthz</code></p></main></body></html>"""


def _safe_filename(name: str) -> str:
    stem = Path(name or "asset").stem
    suffix = Path(name or "").suffix.lower()
    suffix = suffix if suffix in IMAGE_SUFFIXES else ".jpg"
    safe = re.sub(r"[^a-zA-Z0-9_.-]+", "_", stem).strip("._") or "asset"
    return f"{int(time.time())}_{safe[:60]}{suffix}"


def _ensure_demo_plan(root: Path) -> Path:
    assembly_dir = root / "data" / "generated" / "assembly"
    assembly_dir.mkdir(parents=True, exist_ok=True)
    plan_path = assembly_dir / "ASP_DEMO_ATLAS.json"
    if plan_path.exists():
        return plan_path
    plan = {
        "assembly_plan_id": "ASP_DEMO_ATLAS",
        "episode_id": "EP_DEMO_001",
        "project": "Atlas",
        "timeline": [
            {"segment_id": "SEG_001", "scene_id": "SCN_001_MAGNET_WAKE", "order": 1, "start_time": 0, "end_time": 2.5, "duration_seconds": 2.5, "render_job_id": "RND_DEMO_001"},
            {"segment_id": "SEG_002", "scene_id": "SCN_002_OBJECTS_SLIDE", "order": 2, "start_time": 2.5, "end_time": 5, "duration_seconds": 2.5, "render_job_id": "RND_DEMO_002"},
            {"segment_id": "SEG_003", "scene_id": "SCN_003_SPONGE_REACTS", "order": 3, "start_time": 5, "end_time": 7.5, "duration_seconds": 2.5, "render_job_id": "RND_DEMO_003"},
        ],
        "caption_slots": [{"text": "A strange magnet hum wakes the sponge."}],
        "audio_slots": [],
        "transitions": [],
    }
    plan_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    return plan_path


def _videos(root: Path) -> list[dict]:
    out_dir = root / "data" / "generated" / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = list_i2v_jobs(root)
    rows = []
    for mp4 in sorted(out_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True):
        if mp4.name.endswith("_silent.mp4"):
            continue
        rel = str(mp4.relative_to(root)).replace("\\", "/")
        i2v_job = next((job for job in jobs if job.get("output_path") == rel), None)
        rows.append({"name": mp4.name, "size": mp4.stat().st_size, "href": f"/videos/{mp4.name}", "i2v": i2v_job})
    return rows


def _video_cards(root: Path) -> str:
    cards = []
    for item in _videos(root):
        badges = ""
        if item.get("i2v"):
            job = item["i2v"]
            badges = f'<p><span class="metric">comfy i2v</span><span class="metric">frames: {html.escape(str(job.get("frames")))}</span><span class="metric">credits: 0</span><span class="metric">sprint: 17</span></p>'
        cards.append(f"""
        <article class="video-card">
          <h3>{html.escape(item['name'])}</h3>
          <p>{item['size']:,} bytes</p>{badges}
          <video controls src="{html.escape(item['href'])}"></video>
          <p><a href="{html.escape(item['href'])}" download>Download MP4</a></p>
        </article>""")
    return "\n".join(cards) if cards else '<div class="empty">No final videos yet.</div>'


def _asset_cards(root: Path) -> str:
    assets = list_short_assets(root)
    if not assets:
        return '<div class="empty">No image assets yet. Upload source images first.</div>'
    rows = []
    for idx, asset in enumerate(assets[:24], start=1):
        checked = " checked" if idx == 1 else ""
        rows.append(f"""
        <label class="asset-card">
          <input type="radio" name="image_path" value="{html.escape(asset['path'])}"{checked}>
          <img src="/short_assets/{html.escape(asset['name'])}" alt="asset">
          <span>{html.escape(asset['name'])}</span>
        </label>""")
    return "\n".join(rows)


def _multi_asset_cards(root: Path) -> str:
    assets = list_short_assets(root)
    if not assets:
        return '<div class="empty">No image assets yet.</div>'
    rows = []
    for idx, asset in enumerate(assets[:18], start=1):
        checked = " checked" if idx <= 6 else ""
        rows.append(f'<label class="asset-card"><input type="checkbox" name="asset_path" value="{html.escape(asset["path"])}"{checked}><img src="/short_assets/{html.escape(asset["name"])}" alt="asset"><span>{html.escape(asset["name"])}</span></label>')
    return "\n".join(rows)


def _scene_inputs() -> str:
    defaults = ["zoom_in", "pan_right", "zoom_out", "parallax_soft", "pan_left", "hold"]
    rows = []
    for idx in range(1, 7):
        opts = "".join([f'<option value="{m}"{" selected" if m == defaults[idx-1] else ""}>{m}</option>' for m in MOTIONS])
        rows.append(f'<div class="scene-row"><label>Scene {idx} caption</label><input name="caption_{idx}" placeholder="Caption {idx}"><label>Motion</label><select name="motion_{idx}">{opts}</select></div>')
    return "\n".join(rows)


def _provider_cards(root: Path) -> str:
    summary = provider_summary(root)
    rows = []
    for job in summary.get("jobs", [])[:12]:
        rows.append(f'<article class="provider-job"><h3>{html.escape(job.get("job_id", "PJOB"))}</h3><p>Status: <code>{html.escape(job.get("status", "unknown"))}</code> · Provider: <code>{html.escape(job.get("provider", "mock"))}</code></p><p>{html.escape(job.get("request", {}).get("prompt", "")[:220])}</p></article>')
    return "\n".join(rows) if rows else '<div class="empty">No provider jobs yet.</div>'


def _i2v_jobs_html(root: Path) -> str:
    jobs = list_i2v_jobs(root)
    if not jobs:
        return '<div class="empty">No ComfyUI I2V jobs yet.</div>'
    rows = []
    for job in jobs[:12]:
        link = f'<a href="/videos/{html.escape(Path(job.get("output_path", "")).name)}">Open output</a>' if job.get("output_path") else ""
        rows.append(f'<article class="provider-job"><h3>{html.escape(job.get("job_id", "CI2V"))}</h3><p>Status: <code>{html.escape(job.get("status", "unknown"))}</code> · Prompt ID: <code>{html.escape(str(job.get("prompt_id", "")))}</code></p><p>{html.escape(job.get("prompt", "")[:220])}</p><p>{link}</p><p class="error">{html.escape(job.get("error", ""))}</p></article>')
    return "\n".join(rows)


def _advanced_html_page(root: Path) -> str:
    provider = provider_summary(root)
    templates = get_motion_templates()
    comfy = comfy_status(root)
    assets = _asset_cards(root)
    multi_assets = _multi_asset_cards(root)
    videos = _video_cards(root)
    i2v_jobs = _i2v_jobs_html(root)
    provider_cards = _provider_cards(root)
    access_label = "enabled" if _configured_token() else "not configured"
    template_options = "".join([f'<option value="{html.escape(t.get("id", ""))}">{html.escape(t.get("label", t.get("id", "")))}</option>' for t in templates])
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Lucreția Runtime</title>
<style>
:root{{--bg:#07111f;--panel:#101a2b;--line:#24344f;--text:#edf4ff;--muted:#9aabc5;--accent:#7c5cff;--danger:#ff5c7a;--ok:#35d399}}
*{{box-sizing:border-box}} body{{margin:0;font-family:Inter,Segoe UI,Arial,sans-serif;color:var(--text);background:radial-gradient(circle at top left,#1c2a55,#07111f 45%)}} header{{padding:32px 38px;border-bottom:1px solid var(--line);background:rgba(7,17,31,.82)}} main{{max-width:1280px;margin:0 auto;padding:30px 34px 60px}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} .card,.video-card,.provider-job{{background:linear-gradient(180deg,rgba(16,26,43,.98),rgba(10,17,30,.98));border:1px solid var(--line);border-radius:18px;padding:22px;box-shadow:0 18px 40px rgba(0,0,0,.25)}} button{{border:0;border-radius:12px;padding:13px 18px;min-height:46px;color:white;font-weight:850;cursor:pointer;background:linear-gradient(135deg,var(--accent),#5538ff);margin:0 8px 8px 0}} .danger-button{{background:linear-gradient(135deg,var(--danger),#b91c1c)}} select,textarea,input{{width:100%;border-radius:12px;padding:12px;color:var(--text);background:#091425;border:1px solid #253755;margin:6px 0 14px}} input[type=checkbox],input[type=radio]{{width:auto;margin-right:8px}} label{{color:#c9d8ef;font-weight:800}} code,.path{{color:#a8d9ff}} .note{{color:#ffe0a3;background:rgba(255,209,102,.08);border:1px solid rgba(255,209,102,.28);border-radius:14px;padding:14px;line-height:1.45}} .core{{color:#d8cbff;background:rgba(124,92,255,.10);border-color:rgba(124,92,255,.35)}} .safe{{color:#b9ffdf;background:rgba(53,211,153,.08);border-color:rgba(53,211,153,.28)}} .paid{{color:#ffc3ce;background:rgba(255,92,122,.08);border-color:rgba(255,92,122,.28)}} .asset-grid,.video-list,.provider-list{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:14px;margin-top:14px}} .asset-card{{display:block;padding:8px;border:1px solid #253755;border-radius:14px;background:#091425}} .asset-card img{{width:100%;aspect-ratio:9/16;object-fit:cover;border-radius:12px;background:#000;margin:6px 0}} video,img{{width:100%;border-radius:14px;background:#000;margin-top:8px}} .metric{{display:inline-block;margin:0 10px 10px 0;padding:8px 10px;border-radius:999px;border:1px solid #2f4568;color:#c9d8ef;background:#091425}} .empty{{padding:24px;border:1px dashed #3a4d72;border-radius:16px;color:var(--muted);background:#091425}} .error{{color:#ffb3b3}} .scene-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:12px}} .scene-row{{border:1px solid #253755;border-radius:14px;padding:12px;background:#091425}} a{{color:#9fdcff}} @media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>Lucreția Integrations</h1><div>Provider, motion and diagnostic controls</div></header><main>
<section class="grid">
  <div class="card"><h2>ComfyUI Engine</h2><p class="note core">În Render, Lucreția pune joburile într-o coadă securizată. Workerul Windows le rulează în ComfyUI local și trimite rezultatul înapoi.</p><p>Mode: <code>{html.escape(str(comfy.get('mode')))}</code> · Status: <code>{html.escape(str(comfy.get('status', 'running' if comfy.get('running') else 'offline')))}</code></p><p>URL: <code>{html.escape(str(comfy.get('url')))}</code></p><p><a href="/comfy/health">Comfy health JSON</a> · <a href="/comfy/jobs">I2V jobs JSON</a></p></div>
  <div class="card"><h2>Image-to-Video via ComfyUI</h2><p class="note safe">Generează numai animația verticală, fără pistă audio. Vocea, muzica și efectele comice pentru copii se adaugă separat, după aprobarea imaginii.</p><form method="POST" action="/i2v/build"><label>Source image</label><div class="asset-grid">{assets}</div><label>Prompt</label><textarea name="prompt" rows="5" placeholder="Begin with an immediate visual danger in the first second..." required></textarea><label>Negative prompt</label><textarea name="negative_prompt" rows="3" placeholder="slow introduction, greeting, multiple characters, text, watermark, blurry, distorted"></textarea><label>Frames</label><input name="frames" value="241"><label>Width</label><input name="width" value="320"><label>Height</label><input name="height" value="576"><label>Seed</label><input name="seed" value="12345"><label>Workflow path</label><input name="workflow_path" value="workflows/comfy/ltx23_i2v_api.json"><button type="submit">Submit Silent I2V to ComfyUI</button></form><form method="POST" action="/i2v/poll"><button type="submit">Poll & Import I2V Output</button></form></div>
  <div class="card"><h2>Upload Source Assets</h2><form method="POST" action="/assets/upload" enctype="multipart/form-data"><label>Upload images</label><input type="file" name="files" accept="image/png,image/jpeg,image/webp" multiple><button type="submit">Upload Assets</button></form><p><a href="/assets/list">Assets JSON</a></p></div>
  <div class="card"><h2>Final Reel Composer</h2><p class="note safe">Combină animația LTX cu vocea și generează automat subtitrarea din text.</p><form method="POST" action="/reels/compose" enctype="multipart/form-data"><label>Animation video</label><input type="file" name="video" accept="video/mp4,video/webm,video/quicktime" required><label>Voice audio</label><input type="file" name="audio" accept="audio/mpeg,audio/wav,audio/mp4,audio/aac" required><label>Spoken text / subtitles</label><textarea name="transcript" rows="4" required></textarea><label>Voice starts at second</label><input name="audio_start" value="1"><label>Subtitle duration</label><input name="audio_duration" value="6"><button type="submit">Build Final Reel</button></form></div>
  <div class="card"><h2>Motion Core — Object Animation</h2><p class="note core">2.5D sprite/keyframe fallback. Nu este I2V generativ.</p><form method="POST" action="/motion-core/magnet-pull"><label>Duration</label><select name="duration_seconds"><option value="4">4 sec</option><option value="5" selected>5 sec</option><option value="6">6 sec</option><option value="8">8 sec</option></select><button type="submit">Build Screw → Magnet Demo — 0 credits</button></form></div>
  <div class="card"><h2>Asset-First Shorts Builder</h2><form method="POST" action="/shorts/build"><label>Title</label><input name="title" value="Lucretia Asset Short"><label>Hook text</label><input name="hook_text"><label>Duration</label><select name="duration_seconds"><option value="15">15 sec</option><option value="30" selected>30 sec</option><option value="45">45 sec</option><option value="60">60 sec</option></select><label>Outro / CTA</label><input name="outro_text"><p><label><input type="checkbox" name="publish_mode" value="yes" checked> Publish mode</label></p><h3>Assets</h3><div class="asset-grid">{multi_assets}</div><h3>Scene captions & motion</h3><div class="scene-grid">{_scene_inputs()}</div><button type="submit">Build Asset Short — 0 credits</button></form></div>
  <div class="card"><h2>Runway Provider — Paid Guard</h2><p class="note paid">Runway rămâne plătit și blocat după confirmare.</p><form method="POST" action="/provider/runway-generate"><label>Universe</label><input name="universe_id" value="atlas_lab"><label>Scene</label><input name="scene_id" value="lab_object_awake"><label>Preset</label><input name="preset_id" value="hook_fast"><label>Duration</label><select name="duration_seconds"><option value="4">4 sec</option><option value="8">8 sec</option><option value="12" selected>12 sec</option><option value="15">15 sec</option></select><label>Prompt</label><textarea name="custom_prompt" rows="4"></textarea><p><label><input type="checkbox" name="confirm_paid" value="yes"> Confirm spend Runway credits</label></p><button class="danger-button" type="submit">PAID: Generate Runway Clip</button></form><form method="POST" action="/provider/runway-poll"><button>Poll Runway Jobs</button></form><form method="POST" action="/provider/stage-runway"><button>Import Built Runway Clips</button></form><form method="POST" action="/provider/build-final-reel"><button>Build Final Reel</button></form></div>
  <div class="card"><h2>Template Motion Engine</h2><form method="POST" action="/motion/build"><label>Template</label><select name="template_id">{template_options}</select><label>Duration</label><select name="duration_seconds"><option value="15">15 sec</option><option value="30" selected>30 sec</option></select><input type="hidden" name="universe_id" value="atlas_lab"><input type="hidden" name="scene_id" value="lab_object_awake"><input type="hidden" name="preset_id" value="hook_fast"><button>Build Template Reel</button></form></div>
  <div class="card"><h2>Host status</h2><p>Output: <code>data/generated/videos/</code></p><p>Comfy jobs: <code>data/generated/comfy/i2v_jobs.json</code></p><p>Workflow: <code>workflows/comfy/</code></p><p>Provider jobs: {provider.get('job_count', 0)}</p><p>Access gate: <code>{access_label}</code></p></div>
</section>
<section><h2>ComfyUI I2V jobs</h2><div class="provider-list">{i2v_jobs}</div></section>
<section><h2>Generated videos</h2><div class="video-list">{videos}</div></section>
<section><h2>Provider jobs</h2><div class="provider-list">{provider_cards}</div></section>
</main></body></html>"""


def _html_page(root: Path) -> str:
    return render_production_home(root)


def _parse_multipart(raw: bytes, content_type: str) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", content_type, re.I)
    if not match:
        return {}, {}
    boundary = (match.group(1) or match.group(2) or "").strip()
    if not boundary:
        return {}, {}
    marker = b"--" + boundary.encode("utf-8")
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for part in raw.split(marker):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        header_blob, sep, body = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = header_blob.decode("utf-8", errors="ignore")
        filename_match = re.search(r'filename="([^"]*)"', headers)
        name_match = re.search(r'name="([^"]*)"', headers)
        if not name_match:
            continue
        name = name_match.group(1)
        data = body.rstrip(b"\r\n")
        if filename_match:
            filename = Path(filename_match.group(1)).name
            if filename and data:
                files[name] = (filename, data)
        else:
            fields[name] = data.decode("utf-8", errors="replace")
    return fields, files


def _parse_multipart_files(raw: bytes, content_type: str) -> list[tuple[str, bytes]]:
    match = re.search(r"boundary=(?:\"([^\"]+)\"|([^;]+))", content_type, re.I)
    if not match:
        return []
    boundary = (match.group(1) or match.group(2) or "").strip()
    marker = b"--" + boundary.encode("utf-8")
    results: list[tuple[str, bytes]] = []
    for part in raw.split(marker):
        header_blob, sep, body = part.strip(b"\r\n").partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = header_blob.decode("utf-8", errors="ignore")
        name_match = re.search(r'name="([^"]*)"', headers)
        filename_match = re.search(r'filename="([^"]*)"', headers)
        if name_match and name_match.group(1) == "files" and filename_match:
            filename = Path(filename_match.group(1)).name
            data = body.rstrip(b"\r\n")
            if filename and data:
                results.append((filename, data))
    return results


class LucretiaHandler(BaseHTTPRequestHandler):
    root: Path = Path.cwd()

    def _send(self, body: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200, headers: dict[str, str] | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.end_headers()

    def _require_access(self, parsed) -> tuple[bool, str | None]:
        allowed, cookie_header, reason, status = _access_decision(self, parsed)
        if allowed:
            return True, cookie_header
        self._send(_locked_page(reason).encode("utf-8"), status=status)
        return False, None

    def _read_form_values(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else ""
        return parse_qs(raw)

    def _read_form(self) -> dict[str, str]:
        data = self._read_form_values()
        return {key: values[0] for key, values in data.items() if values}

    def _read_body(self) -> bytes:
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length) if length > 0 else b""

    def _read_json_body(self) -> dict:
        raw = self._read_body()
        payload = json.loads(raw.decode("utf-8")) if raw else {}
        return payload if isinstance(payload, dict) else {}

    def _require_worker(self) -> bool:
        if _worker_authorized(self):
            return True
        self._send(b'{"error":"worker authorization failed"}', "application/json; charset=utf-8", 401)
        return False

    def _save_uploads(self) -> int:
        dest = short_assets_dir(self.root)
        dest.mkdir(parents=True, exist_ok=True)
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        saved = 0
        for filename, data in _parse_multipart_files(raw, self.headers.get("Content-Type", "")):
            suffix = Path(filename).suffix.lower()
            if suffix not in IMAGE_SUFFIXES:
                continue
            (dest / _safe_filename(filename)).write_bytes(data)
            saved += 1
        return saved

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            payload = {"status": "ok", "service": "lucretia-runtime", "revision": os.environ.get("RENDER_GIT_COMMIT", "local")[:12], "videos": len(_videos(self.root)), "short_assets": len(list_short_assets(self.root)), "comfy": comfy_status(self.root), "worker": relay_worker_status(self.root, public=True), "access_configured": bool(_configured_token())}
            self._send(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/worker/claim":
            if not self._require_worker():
                return
            worker_id = parse_qs(parsed.query).get("worker_id", ["windows-worker"])[0]
            job = claim_relay_job(self.root, worker_id)
            self._send(json.dumps({"job": job}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/worker/state":
            if not self._require_worker():
                return
            snapshot = export_relay_state(self.root)
            known = parse_qs(parsed.query).get("known", [""])[0]
            payload = {"unchanged": True, "revision": snapshot["revision"]} if known == snapshot["revision"] else snapshot
            self._send(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        worker_source = re.fullmatch(r"/worker/jobs/([^/]+)/source", parsed.path)
        if worker_source:
            if not self._require_worker():
                return
            source = relay_source_path(self.root, worker_source.group(1))
            if not source:
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            self._send(source.read_bytes(), mimetypes.guess_type(str(source))[0] or "application/octet-stream")
            return
        allowed, cookie_header = self._require_access(parsed)
        if not allowed:
            return
        if cookie_header and parse_qs(parsed.query).get("token"):
            self._redirect(parsed.path or "/", {"Set-Cookie": cookie_header})
            return
        if parsed.path == "/advanced":
            self._send(_advanced_html_page(self.root).encode("utf-8"))
            return
        if parsed.path == "/comfy/health":
            self._send(json.dumps(comfy_status(self.root), indent=2, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/comfy/jobs":
            self._send(json.dumps(list_i2v_jobs(self.root), indent=2, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/assets/list":
            self._send(json.dumps({"assets": list_short_assets(self.root)}, indent=2, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path == "/catalog/prompts":
            payload = get_catalog()
            payload["motion_templates"] = get_motion_templates()
            payload["asset_motions"] = MOTIONS
            payload["comfy"] = comfy_status(self.root)
            self._send(json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path.startswith("/short_assets/"):
            file_path = short_assets_dir(self.root) / Path(parsed.path).name
            if not file_path.exists() or file_path.suffix.lower() not in IMAGE_SUFFIXES:
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            self._send(file_path.read_bytes(), mimetypes.guess_type(str(file_path))[0] or "image/jpeg")
            return
        if parsed.path == "/provider/jobs":
            self._send(json.dumps(provider_summary(self.root), indent=2).encode("utf-8"), "application/json; charset=utf-8")
            return
        if parsed.path.startswith("/provider/assets/"):
            file_path = provider_assets_dir(self.root) / Path(parsed.path).name
            if not file_path.exists():
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            self._send(file_path.read_bytes(), mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")
            return
        if parsed.path.startswith("/videos/"):
            name = Path(parsed.path).name
            if name.endswith("_silent.mp4"):
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            file_path = self.root / "data" / "generated" / "videos" / name
            if not file_path.exists() or file_path.suffix.lower() not in {".mp4", ".png", ".webm", ".mov"}:
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            self._send(file_path.read_bytes(), mimetypes.guess_type(str(file_path))[0] or "video/mp4")
            return
        if parsed.path.startswith("/subtitles/"):
            file_path = self.root / "data" / "generated" / "subtitles" / Path(parsed.path).name
            if not file_path.exists() or file_path.suffix.lower() != ".srt":
                self._send(b"Not found", "text/plain; charset=utf-8", 404)
                return
            self._send(file_path.read_bytes(), "application/x-subrip; charset=utf-8")
            return
        self._send(_html_page(self.root).encode("utf-8"))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        production_scene_action = re.fullmatch(r"/productions/([^/]+)/scenes/([^/]+)/(update|submit|approve|retry)", parsed.path)
        production_assemble = re.fullmatch(r"/productions/([^/]+)/assemble", parsed.path)
        production_start = re.fullmatch(r"/productions/([^/]+)/start", parsed.path)
        worker_status = re.fullmatch(r"/worker/jobs/([^/]+)/status", parsed.path)
        worker_output = re.fullmatch(r"/worker/jobs/([^/]+)/output", parsed.path)
        worker_restore = parsed.path == "/worker/state/restore"
        if worker_status or worker_output or worker_restore:
            if not self._require_worker():
                return
            try:
                if worker_restore:
                    restored = restore_relay_state(self.root, self._read_json_body())
                    self._send(json.dumps(restored, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
                    return
                match = worker_status or worker_output
                job_id = match.group(1)
                if worker_status:
                    job = update_relay_job(self.root, job_id, self._read_json_body())
                else:
                    job = complete_relay_job(
                        self.root,
                        job_id,
                        self.headers.get("X-Filename", f"{job_id}.mp4"),
                        self._read_body(),
                        self.headers.get("X-Prompt-ID", ""),
                    )
                self._send(json.dumps({"job": job}, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
            except KeyError:
                self._send(b'{"error":"job not found"}', "application/json; charset=utf-8", 404)
            except Exception as exc:
                self._send(json.dumps({"error": str(exc)}).encode("utf-8"), "application/json; charset=utf-8", 500)
            return
        allowed, cookie_header = self._require_access(parsed)
        if not allowed:
            return
        headers = {"Set-Cookie": cookie_header} if cookie_header else None
        if parsed.path == "/productions/autonomous":
            try:
                create_original_reel(self.root)
                self._redirect("/", headers)
            except Exception as exc:
                self._send(f"Autonomous production failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 500)
            return
        if production_start:
            try:
                if os.environ.get("LUCRETIA_COMFY_MODE", "managed").strip().lower() != "relay":
                    raise RuntimeError("Autonomous production requires the Windows relay worker.")
                if not relay_worker_status(self.root, public=True)["connected"]:
                    raise RuntimeError("Windows worker is not connected. Start Lucretia Worker on the workstation.")
                start_original_reel(self.root, production_start.group(1))
                self._redirect("/", headers)
            except Exception as exc:
                self._send(f"Production start failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 500)
            return
        if parsed.path == "/productions/create":
            values = self._read_form_values()
            try:
                names = values.get("character_name", [])
                descriptions = values.get("character_description", [])
                rules = values.get("character_rules", [])
                characters = [
                    {
                        "name": name,
                        "description": descriptions[index] if index < len(descriptions) else "",
                        "visual_rules": rules[index] if index < len(rules) else "",
                    }
                    for index, name in enumerate(names)
                    if name.strip()
                ]
                titles = values.get("scene_title", [])
                prompts = values.get("scene_prompt", [])
                end_states = values.get("scene_end_state", [])
                durations = values.get("scene_duration", [])
                assets = values.get("scene_asset", [])
                negatives = values.get("scene_negative", [])
                scene_characters = values.get("scene_characters", [])
                scenes = [
                    {
                        "title": title,
                        "prompt": prompts[index] if index < len(prompts) else "",
                        "required_end_state": end_states[index] if index < len(end_states) else "",
                        "duration_seconds": durations[index] if index < len(durations) else "5",
                        "start_asset": assets[index] if index < len(assets) else "",
                        "negative_prompt": negatives[index] if index < len(negatives) else "",
                        "required_characters": (
                            scene_characters[index].split(",") if index < len(scene_characters) else []
                        ),
                    }
                    for index, title in enumerate(titles)
                    if title.strip()
                ]
                create_production(
                    self.root,
                    title=values.get("title", [""])[0],
                    universe_id=values.get("universe_id", ["custom_universe"])[0],
                    universe_rules=values.get("universe_rules", [""])[0],
                    plot=values.get("plot", [""])[0],
                    characters=characters,
                    scenes=scenes,
                    forbidden=values.get("forbidden", [""])[0].split(","),
                )
                self._redirect("/", headers)
            except Exception as exc:
                self._send(f"Production creation failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 400)
            return
        if production_scene_action:
            production_id, scene_id, action = production_scene_action.groups()
            form = self._read_form()
            try:
                if action == "update":
                    update_scene(
                        self.root,
                        production_id,
                        scene_id,
                        prompt=form.get("prompt", ""),
                        start_asset=form.get("start_asset", ""),
                        required_end_state=form.get("required_end_state", ""),
                        negative_prompt=form.get("negative_prompt", ""),
                        duration_seconds=float(form.get("duration_seconds", "5") or "5"),
                        required_characters=form.get("required_characters", "").split(","),
                    )
                elif action == "submit":
                    update_scene(
                        self.root,
                        production_id,
                        scene_id,
                        prompt=form.get("prompt", ""),
                        start_asset=form.get("start_asset", ""),
                        required_end_state=form.get("required_end_state", ""),
                        negative_prompt=form.get("negative_prompt", ""),
                        duration_seconds=float(form.get("duration_seconds", "5") or "5"),
                        required_characters=form.get("required_characters", "").split(","),
                    )
                    production, scene = scene_for_submission(self.root, production_id, scene_id)
                    prompt, negative = compile_scene_prompt(production, scene)
                    seed = int(hashlib.sha256(f"{production_id}:{scene_id}:{scene.get('attempts', 0)}".encode()).hexdigest()[:8], 16)
                    request = ComfyI2VRequest(
                        image_path=scene["start_asset"],
                        prompt=prompt,
                        negative_prompt=negative,
                        seed=seed,
                        frames=int(scene["frames"]),
                        width=320,
                        height=576,
                        workflow_path="workflows/comfy/ltx23_i2v_api.json",
                        generate_audio=False,
                        metadata={"source": "production", "production_id": production_id, "scene_id": scene_id},
                    )
                    if os.environ.get("LUCRETIA_COMFY_MODE", "managed").strip().lower() != "relay":
                        raise RuntimeError("Production scenes require the Render-to-Windows relay worker.")
                    job = enqueue_relay_job(self.root, request)
                    mark_scene_submitted(self.root, production_id, scene_id, job["job_id"])
                else:
                    review_scene(
                        self.root,
                        production_id,
                        scene_id,
                        approved=action == "approve",
                        note=form.get("review_note", ""),
                    )
                self._redirect("/", headers)
            except Exception as exc:
                self._send(f"Scene action failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 400)
            return
        if production_assemble:
            try:
                assemble_production(self.root, production_assemble.group(1))
                self._redirect("/", headers)
            except Exception as exc:
                self._send(f"Assembly failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 400)
            return
        if parsed.path == "/comfy/start":
            try:
                ComfyManager().start(wait_seconds=int(os.environ.get("LUCRETIA_COMFY_START_TIMEOUT", "30")))
                self._redirect("/#comfy", headers)
            except Exception as exc:
                self._send(f"ComfyUI start failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 500)
            return
        if parsed.path == "/i2v/build":
            form = self._read_form()
            try:
                request = ComfyI2VRequest(
                    image_path=form.get("image_path", ""),
                    prompt=form.get("prompt", ""),
                    negative_prompt=form.get("negative_prompt", ""),
                    seed=int(float(form.get("seed", "12345") or "12345")),
                    frames=max(1, int(float(form.get("frames", "97") or "97"))),
                    width=int(float(form.get("width", "512") or "512")),
                    height=int(float(form.get("height", "320") or "320")),
                    workflow_path=form.get("workflow_path", "workflows/comfy/ltx23_i2v_api.json"),
                    generate_audio=False,
                    metadata={"source": "web_ui"},
                )
                if os.environ.get("LUCRETIA_COMFY_MODE", "managed").strip().lower() == "relay":
                    enqueue_relay_job(self.root, request)
                else:
                    submit_i2v_job(self.root, request, auto_start=True)
                self._redirect("/#comfy", headers)
            except Exception as exc:
                self._send(f"I2V submit failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 500)
            return
        if parsed.path == "/i2v/poll":
            try:
                if os.environ.get("LUCRETIA_COMFY_MODE", "managed").strip().lower() != "relay":
                    poll_i2v_jobs(self.root, import_outputs=True)
                self._redirect("/#generated-videos", headers)
            except Exception as exc:
                self._send(f"I2V poll failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 500)
            return
        if parsed.path == "/assets/upload":
            self._save_uploads()
            self._redirect("/", headers)
            return
        if parsed.path == "/reels/compose":
            try:
                raw = self._read_body()
                fields, files = _parse_multipart(raw, self.headers.get("Content-Type", ""))
                video_name, video_data = files["video"]
                audio_name, audio_data = files["audio"]
                if Path(video_name).suffix.lower() not in VIDEO_SUFFIXES:
                    raise ValueError("Unsupported video format.")
                if Path(audio_name).suffix.lower() not in AUDIO_SUFFIXES:
                    raise ValueError("Unsupported audio format.")
                transcript = fields.get("transcript", "").strip()
                if not transcript:
                    raise ValueError("Spoken text is required for subtitles.")
                uploads = self.root / "data" / "generated" / "manual_uploads"
                uploads.mkdir(parents=True, exist_ok=True)
                stamp = int(time.time())
                video_path = uploads / f"{stamp}_{_safe_filename(video_name)}"
                audio_path = uploads / f"{stamp}_{_safe_filename(audio_name)}"
                video_path.write_bytes(video_data)
                audio_path.write_bytes(audio_data)
                compose_final_reel(
                    video_path,
                    audio_path,
                    self.root / "data" / "generated" / "videos",
                    transcript=transcript,
                    audio_start=max(0.0, float(fields.get("audio_start", "1") or "1")),
                    audio_duration=max(0.1, float(fields.get("audio_duration", "6") or "6")),
                )
                self._redirect("/#generated-videos", headers)
            except Exception as exc:
                self._send(f"Final reel build failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 500)
            return
        if parsed.path == "/motion-core/magnet-pull":
            form = self._read_form()
            duration = max(2.0, min(12.0, float(form.get("duration_seconds", "5") or "5")))
            render_magnet_pull_demo(self.root, output_dir=self.root / "data" / "generated" / "videos", width=720, height=1280, duration=duration, fps=24)
            self._redirect("/#generated-videos", headers)
            return
        if parsed.path == "/shorts/build":
            values = self._read_form_values()
            asset_paths = values.get("asset_path", [])[:6]
            if not asset_paths:
                self._send(b"No assets selected.", "text/plain; charset=utf-8", 400)
                return
            scenes = [AssetSceneSpec(asset_path=p, caption=(values.get(f"caption_{i}", [""])[0] or "").strip(), motion=(values.get(f"motion_{i}", ["zoom_in"])[0] or "zoom_in")) for i, p in enumerate(asset_paths, start=1)]
            duration = int(float(values.get("duration_seconds", ["30"])[0] or "30"))
            spec = AssetShortSpec(title=values.get("title", ["Lucretia Asset Short"])[0], hook_text=values.get("hook_text", [""])[0], outro_text=values.get("outro_text", [""])[0], duration_seconds=duration, fps=12, width=720, height=1280, publish_mode=values.get("publish_mode", [""])[0] == "yes", scenes=tuple(scenes))
            build_asset_short(self.root, spec, self.root / "data" / "generated" / "videos")
            self._redirect("/#generated-videos", headers)
            return
        if parsed.path == "/motion/build":
            form = self._read_form()
            duration = int(float(form.get("duration_seconds", "30") or "30"))
            spec = MotionReelSpec(universe_id=form.get("universe_id", "atlas_lab"), scene_id=form.get("scene_id", "lab_object_awake"), preset_id=form.get("preset_id", "hook_fast"), custom_prompt=form.get("custom_prompt", ""), template_id=form.get("template_id", "atlas_object_lab"), duration_seconds=duration, fps=12, width=720, height=1280)
            build_motion_reel(spec, self.root / "data" / "generated" / "videos")
            self._redirect("/#generated-videos", headers)
            return
        if parsed.path == "/provider/mock-demo":
            plan = _ensure_demo_plan(self.root)
            submit_mock_jobs_for_plan(self.root, plan, width=360, height=640)
            self._redirect("/#provider-jobs", headers)
            return
        if parsed.path == "/provider/build-video":
            plan = _ensure_demo_plan(self.root)
            submit_mock_jobs_for_plan(self.root, plan, width=360, height=640)
            provider_plan = materialize_provider_assets_into_plan(self.root, plan)
            build_local_video_from_plan(provider_plan, self.root / "data" / "generated" / "videos", project_root=self.root, fps=8, width=360, height=640)
            self._redirect("/#generated-videos", headers)
            return
        if parsed.path == "/provider/runway-generate":
            form = self._read_form()
            if form.get("confirm_paid") != "yes":
                self._send(b"Runway paid generation blocked. Tick confirm_paid explicitly.", "text/plain; charset=utf-8", 402)
                return
            duration_seconds = max(4.0, min(15.0, float(form.get("duration_seconds", "12") or "12")))
            prompt = compose_prompt(form.get("universe_id", "atlas_lab"), form.get("scene_id", "lab_object_awake"), form.get("preset_id", "hook_fast"), form.get("custom_prompt", ""))
            stamp = int(time.time())
            request = ProviderAssetRequest(provider="runway", assembly_plan_id="ASP_UI_COMFY_GUARDED", episode_id=f"EP_UI_{stamp}", segment_id=f"SEG_UI_{stamp}", scene_id=form.get("scene_id", "lab_object_awake"), render_job_id=f"RND_UI_{stamp}", prompt=prompt, duration_seconds=duration_seconds, width=720, height=1280, seed=str(stamp), metadata={"source": "guarded_runway_ui"})
            submit_provider_request(self.root, request)
            self._redirect("/#provider-jobs", headers)
            return
        if parsed.path == "/provider/runway-poll":
            poll_runway_jobs(self.root)
            self._redirect("/#provider-jobs", headers)
            return
        if parsed.path == "/provider/stage-runway":
            stage_runway_outputs(self.root)
            self._redirect("/#provider-jobs", headers)
            return
        if parsed.path == "/provider/build-final-reel":
            try:
                build_final_reel_from_latest_runway_jobs(self.root, self.root / "data" / "generated" / "videos", limit=3, width=720, height=1280, fps=24)
                self._redirect("/#generated-videos", headers)
            except Exception as exc:
                self._send(f"Build final reel failed: {html.escape(str(exc))}".encode("utf-8"), "text/plain; charset=utf-8", 500)
            return
        self._send(b"Not found", "text/plain; charset=utf-8", 404)


def serve(host: str = "0.0.0.0", port: int | None = None, root: Path | None = None) -> None:
    root = root or Path.cwd()
    port = int(port or os.environ.get("PORT", "8787"))
    LucretiaHandler.root = root
    server = ThreadingHTTPServer((host, port), LucretiaHandler)
    print(f"Lucretia Runtime serving on http://{host}:{port}")
    server.serve_forever()
