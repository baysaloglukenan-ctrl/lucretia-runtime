from __future__ import annotations

import os
import socket
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]


def ok(label: str, detail: str = "") -> None:
    print(f"[OK]   {label}{' — ' + detail if detail else ''}")


def warn(label: str, detail: str = "") -> None:
    print(f"[WARN] {label}{' — ' + detail if detail else ''}")


def fail(label: str, detail: str = "") -> None:
    print(f"[FAIL] {label}{' — ' + detail if detail else ''}")


def port_open(host: str, port: int, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(url: str) -> bool:
    try:
        with urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except (URLError, TimeoutError, OSError):
        return False
    except Exception:
        return False


def main() -> int:
    print("Lucretia local doctor")
    print("====================")
    print(f"Project root: {ROOT}")
    print(f"Python: {sys.executable}")
    print(f"Python version: {sys.version.split()[0]}")
    print("")

    if (ROOT / ".git").exists():
        ok("Git checkout detected")
    else:
        warn("Not a Git checkout", "git pull works only inside the cloned repo folder")

    if (ROOT / "pyproject.toml").exists() and (ROOT / "src" / "lucretia_runtime").exists():
        ok("Lucretia source present")
    else:
        fail("Lucretia source missing", "run this from the repository root")

    comfy_mode = os.environ.get("LUCRETIA_COMFY_MODE", "managed").strip().lower()
    comfy_root = Path(os.environ.get("LUCRETIA_COMFY_ROOT", str(ROOT / "vendor" / "ComfyUI")))
    if comfy_mode == "external":
        ok("External ComfyUI mode selected", os.environ.get("LUCRETIA_COMFY_URL", "http://127.0.0.1:8188"))
    else:
        if not comfy_root.is_absolute():
            comfy_root = ROOT / comfy_root
        comfy_main = comfy_root / "main.py"
        if comfy_main.exists():
            ok("ComfyUI main.py found", str(comfy_main))
        else:
            warn("ComfyUI main.py not found", f"expected at {comfy_main}")
            print("       Fix: set LUCRETIA_COMFY_ROOT to your ComfyUI folder or run python scripts/setup_comfyui.py")

    workflow = Path(os.environ.get("LUCRETIA_COMFY_WORKFLOW", str(ROOT / "workflows" / "comfy" / "ltx23_i2v_api.json")))
    if not workflow.is_absolute():
        workflow = ROOT / workflow
    if workflow.exists():
        ok("Comfy workflow file present", str(workflow))
    else:
        warn("Comfy workflow file missing", str(workflow))

    url = os.environ.get("LUCRETIA_COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
    host = os.environ.get("LUCRETIA_COMFY_HOST", "127.0.0.1")
    port = int(os.environ.get("LUCRETIA_COMFY_PORT", "8188"))
    if port_open(host, port):
        ok("ComfyUI port is open", f"{host}:{port}")
    else:
        warn("ComfyUI port is closed", f"{host}:{port}")

    if http_ok(f"{url}/system_stats"):
        ok("ComfyUI API healthy", f"{url}/system_stats")
    else:
        warn("ComfyUI API not healthy", f"{url}/system_stats")

    print("")
    print("Useful commands:")
    print("  git pull --ff-only")
    print("  python -m pip install -e .")
    print("  python scripts/setup_comfyui.py")
    print("  python -m lucretia_runtime.cli serve --host 127.0.0.1 --port 8787")
    print("  open http://127.0.0.1:8787/?token=local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
