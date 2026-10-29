from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path, PurePosixPath

from .comfy.job_store import load_jobs, save_jobs
from .production import load_productions, save_productions
from .provider_models import utc_now_iso


SCHEMA_VERSION = 1
MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_SNAPSHOT_BYTES = 100 * 1024 * 1024
ACTIVE_JOB_STATUSES = {"queued", "running", "generating", "relay_queued", "relay_claimed", "relay_running"}
BACKUP_PREFIXES = (
    "data/generated/short_assets/",
    "data/generated/videos/",
    "data/generated/subtitles/",
)


def _files(root: Path) -> list[dict]:
    records: list[dict] = []
    total = 0
    for prefix in BACKUP_PREFIXES:
        directory = root / PurePosixPath(prefix)
        if not directory.exists():
            continue
        for path in sorted(item for item in directory.rglob("*") if item.is_file()):
            data = path.read_bytes()
            if len(data) > MAX_FILE_BYTES or total + len(data) > MAX_SNAPSHOT_BYTES:
                continue
            relative = str(path.relative_to(root)).replace("\\", "/")
            records.append(
                {
                    "path": relative,
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "data": base64.b64encode(data).decode("ascii"),
                }
            )
            total += len(data)
    return records


def export_relay_state(root: Path) -> dict:
    productions = load_productions(root)
    jobs = load_jobs(root)
    safe = not any(item.get("automation", {}).get("running") for item in productions) and not any(
        str(item.get("status", "")) in ACTIVE_JOB_STATUSES for item in jobs
    )
    content = {
        "schema_version": SCHEMA_VERSION,
        "safe": safe,
        "productions": productions,
        "jobs": jobs,
        "files": _files(root) if safe else [],
    }
    canonical = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        **content,
        "captured_at": utc_now_iso(),
        "revision": hashlib.sha256(canonical).hexdigest(),
    }


def _safe_target(root: Path, relative: str) -> Path:
    value = PurePosixPath(relative)
    normalized = str(value)
    if value.is_absolute() or ".." in value.parts or not any(normalized.startswith(prefix) for prefix in BACKUP_PREFIXES):
        raise ValueError(f"Unsafe backup path: {relative}")
    return root / value


def restore_relay_state(root: Path, snapshot: dict) -> dict:
    if int(snapshot.get("schema_version", 0)) != SCHEMA_VERSION:
        raise ValueError("Unsupported relay backup schema.")
    if not snapshot.get("safe"):
        raise ValueError("Active production snapshots cannot be restored.")
    if load_productions(root) or load_jobs(root):
        return {"restored": False, "reason": "server state is not empty"}
    productions, jobs, files = snapshot.get("productions"), snapshot.get("jobs"), snapshot.get("files")
    if not isinstance(productions, list) or not isinstance(jobs, list) or not isinstance(files, list):
        raise ValueError("Malformed relay backup.")
    decoded: list[tuple[Path, bytes]] = []
    total = 0
    for record in files:
        if not isinstance(record, dict):
            raise ValueError("Malformed backup file record.")
        target = _safe_target(root, str(record.get("path", "")))
        data = base64.b64decode(str(record.get("data", "")), validate=True)
        total += len(data)
        if len(data) > MAX_FILE_BYTES or total > MAX_SNAPSHOT_BYTES:
            raise ValueError("Relay backup exceeds size limits.")
        if hashlib.sha256(data).hexdigest() != str(record.get("sha256", "")):
            raise ValueError("Relay backup checksum mismatch.")
        decoded.append((target, data))
    for target, data in decoded:
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_suffix(target.suffix + ".restore")
        temp.write_bytes(data)
        temp.replace(target)
    save_productions(root, productions)
    save_jobs(root, jobs)
    return {"restored": True, "productions": len(productions), "jobs": len(jobs), "files": len(decoded), "revision": str(snapshot.get("revision", ""))}
