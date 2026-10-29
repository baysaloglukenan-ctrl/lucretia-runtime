from __future__ import annotations

import html
from pathlib import Path

from .comfy import relay_worker_status
from .production import load_productions


STATUS_LABELS = {
    "planning": "pregătit",
    "ready": "pregătită",
    "generating": "se generează",
    "review": "generată",
    "approved": "finalizată",
    "assembled": "reel finalizat",
    "published": "gata de publicat",
    "retry": "de reluat",
}


def _production_card(production: dict, worker_connected: bool) -> str:
    production_id = html.escape(str(production["production_id"]))
    characters = ", ".join(html.escape(str(item.get("name", ""))) for item in production.get("characters", []))
    scenes = []
    for scene in sorted(production.get("scenes", []), key=lambda item: int(item.get("order", 0))):
        asset = Path(str(scene.get("start_asset", ""))).name
        scenes.append(
            f'<div class="scene"><img src="/short_assets/{html.escape(asset)}" alt="Keyframe">'
            f'<div><strong>{int(scene.get("order", 0))}. {html.escape(str(scene.get("title", "Scenă")))}</strong>'
            f'<span class="state">{html.escape(STATUS_LABELS.get(str(scene.get("status", "ready")), str(scene.get("status", "ready"))))}</span></div></div>'
        )
    status = str(production.get("status", "planning"))
    automation = production.get("automation", {})
    action = ""
    if automation.get("mode") == "autonomous_single_shot" and not automation.get("running") and not automation.get("completed"):
        if worker_connected:
            action = f'<form method="POST" action="/productions/{production_id}/start"><button>2. Pornește producția</button></form>'
        else:
            action = '<button disabled>2. Pornește producția</button><p class="worker-help">Pornește „Lucretia Worker” pe stația Windows.</p>'
    final_output = str(production.get("final_output", ""))
    if final_output:
        subtitle_output = str(production.get("subtitle_output", ""))
        subtitle_link = f' <a class="subtitle" href="/subtitles/{html.escape(Path(subtitle_output).name)}">Descarcă subtitrarea</a>' if subtitle_output else ""
        action = f'<a class="button done" href="/videos/{html.escape(Path(final_output).name)}">3. Deschide reelul</a>{subtitle_link}'
    progress = sum(scene.get("status") == "approved" for scene in production.get("scenes", []))
    total = len(production.get("scenes", []))
    error = str(automation.get("error", ""))
    return f"""
    <article class="production">
      <div class="head"><div><h2>{html.escape(str(production.get('title', 'Reel original')))}</h2><p>{characters}</p></div><span class="badge">{html.escape(STATUS_LABELS.get(status, status))}</span></div>
      <p class="plot">{html.escape(str(production.get('plot', '')))}</p>
      <p class="progress">Video complet: {progress}/{total}. Lucreția continuă automat până la MP4-ul publicabil.</p>
      {f'<p class="error">{html.escape(error)}</p>' if error else ''}
      <div class="scenes">{''.join(scenes)}</div>{action}
    </article>"""


def render_production_home(root: Path) -> str:
    productions = load_productions(root)
    worker = relay_worker_status(root, public=True)
    worker_connected = bool(worker["connected"])
    cards = "".join(_production_card(item, worker_connected) for item in productions[:6])
    running = any(item.get("automation", {}).get("running") for item in productions)
    refresh = '<meta http-equiv="refresh" content="15">' if running else ""
    return f"""<!doctype html><html lang="ro"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">{refresh}<title>Lucreția</title>
<style>
:root{{--bg:#07111f;--panel:#111c2e;--line:#293b59;--text:#f1f6ff;--muted:#a8b7ce;--accent:#704dff;--green:#25b77d}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:16px Segoe UI,Arial,sans-serif}}header,main{{max-width:1040px;margin:auto;padding:28px 22px}}header{{padding-bottom:8px}}h1{{font-size:42px;margin:0 0 8px}}p{{color:var(--muted);line-height:1.55}}.hero,.production{{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:22px;margin:18px 0}}button,.button{{display:inline-block;border:0;border-radius:12px;padding:14px 18px;background:var(--accent);color:white;font-weight:800;text-decoration:none;cursor:pointer;font-size:16px}}button:disabled{{background:#46536a;color:#c4ccda;cursor:not-allowed}}.done{{background:var(--green)}}.subtitle{{display:inline-block;margin-left:12px;color:#bcd7ff}}.advanced{{float:right;color:#9fc8ff}}.head{{display:flex;justify-content:space-between;gap:16px;align-items:start}}h2{{margin:0}}.badge,.state,.worker-state{{display:inline-block;background:#22334e;border-radius:999px;padding:6px 10px;font-size:12px;margin-left:8px}}.worker-state.online{{background:#164d3d;color:#a9f2d5}}.worker-state.offline{{background:#542936;color:#ffd0d8}}.plot{{font-size:17px;color:#dce8fa}}.progress{{padding:11px 13px;background:#0a1526;border-radius:10px}}.error{{color:#ffb8c4}}.worker-help{{display:inline-block;margin:0 0 0 12px;color:#ffcad2}}.scenes{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:16px 0}}.scene{{background:#091425;border:1px solid var(--line);border-radius:13px;overflow:hidden}}.scene img{{width:100%;aspect-ratio:9/16;object-fit:cover;display:block}}.scene div{{padding:11px}}@media(max-width:650px){{.head{{display:block}}h1{{font-size:34px}}.worker-help{{display:block;margin:8px 0 0}}}}
</style></head><body><header><a class="advanced" href="/advanced">Tehnic</a><h1>Lucreția</h1><p>Motor autonom de animații originale.</p></header><main>
<section class="hero"><span class="worker-state {'online' if worker_connected else 'offline'}">{'Stația este conectată' if worker_connected else 'Stația nu este conectată'}</span><h2>Un reel complet de 10 secunde</h2><p>Lucreția alege universul, scrie povestea și creează cadrul inițial. ComfyUI generează un singur video continuu, iar Lucreția adaugă automat sunetul și subtitrările.</p><form method="POST" action="/productions/autonomous"><button>1. Creează reelul</button></form></section>
{cards or '<p>Nu există încă nicio producție.</p>'}
</main></body></html>"""
