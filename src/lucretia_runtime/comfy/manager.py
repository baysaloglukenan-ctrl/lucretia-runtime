from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


class ComfyManager:
    """Managed or external ComfyUI engine controller.

    managed mode expects ComfyUI checked out at LUCRETIA_COMFY_ROOT.
    external mode only checks LUCRETIA_COMFY_URL.
    """

    def __init__(self) -> None:
        self.mode = os.environ.get("LUCRETIA_COMFY_MODE", "managed").strip().lower()
        self.root = Path(os.environ.get("LUCRETIA_COMFY_ROOT", "vendor/ComfyUI")).resolve()
        self.url = os.environ.get("LUCRETIA_COMFY_URL", "http://127.0.0.1:8188").rstrip("/")
        self.host = os.environ.get("LUCRETIA_COMFY_HOST", "127.0.0.1").strip()
        self.port = os.environ.get("LUCRETIA_COMFY_PORT", "8188").strip()
        self.python = os.environ.get("LUCRETIA_COMFY_PYTHON", "python").strip()
        self.extra_args = [arg for arg in os.environ.get("LUCRETIA_COMFY_ARGS", "").split(" ") if arg]
        self.proc: subprocess.Popen | None = None

    def health(self) -> bool:
        try:
            with urlopen(f"{self.url}/system_stats", timeout=2) as resp:
                return resp.status == 200
        except (URLError, TimeoutError):
            return False
        except Exception:
            return False

    def status(self) -> dict:
        if self.mode == "relay":
            return {
                "mode": "relay",
                "url": "",
                "root": "",
                "root_exists": False,
                "main_exists": False,
                "running": False,
                "pid": None,
                "status": "waiting_for_windows_worker",
            }
        return {
            "mode": self.mode,
            "url": self.url,
            "root": str(self.root),
            "root_exists": self.root.exists(),
            "main_exists": (self.root / "main.py").exists(),
            "running": self.health(),
            "pid": self.proc.pid if self.proc else None,
        }

    def start(self, wait_seconds: int = 30) -> dict:
        if self.health():
            status = self.status()
            status["status"] = "already_running"
            return status
        if self.mode != "managed":
            raise RuntimeError(f"ComfyUI is not running at {self.url}; mode={self.mode} does not auto-start.")
        main_py = self.root / "main.py"
        if not main_py.exists():
            raise FileNotFoundError(
                f"ComfyUI main.py not found at {main_py}. Run scripts/setup_comfyui.py or set LUCRETIA_COMFY_ROOT."
            )
        cmd = [self.python, str(main_py), "--listen", self.host, "--port", self.port, *self.extra_args]
        log_dir = Path(os.environ.get("LUCRETIA_COMFY_LOG_DIR", "data/generated/comfy_logs")).resolve()
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = (log_dir / "comfyui.log").open("ab")
        self.proc = subprocess.Popen(cmd, cwd=str(self.root), stdout=log_file, stderr=subprocess.STDOUT)
        deadline = time.time() + max(1, int(wait_seconds))
        while time.time() < deadline:
            if self.health():
                status = self.status()
                status["status"] = "started"
                return status
            if self.proc.poll() is not None:
                raise RuntimeError(f"ComfyUI exited early with code {self.proc.returncode}. See {log_dir / 'comfyui.log'}")
            time.sleep(1.0)
        raise TimeoutError(f"ComfyUI did not become healthy within {wait_seconds}s. See {log_dir / 'comfyui.log'}")
