from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


DEFAULT_REPO = "https://github.com/comfy-org/comfyui.git"


def run(cmd: list[str], cwd: Path | None = None) -> None:
    print("$", " ".join(cmd))
    subprocess.check_call(cmd, cwd=str(cwd) if cwd else None)


def main() -> None:
    parser = argparse.ArgumentParser(description="Install/update ComfyUI under vendor/ComfyUI for Lucreția.")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--root", default="vendor/ComfyUI")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--skip-install", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    root.parent.mkdir(parents=True, exist_ok=True)
    if not root.exists():
        run(["git", "clone", args.repo, str(root)])
    else:
        run(["git", "pull", "--ff-only"], cwd=root)

    if not args.skip_install:
        req = root / "requirements.txt"
        if req.exists():
            run([args.python, "-m", "pip", "install", "-r", str(req)])
        else:
            print(f"requirements.txt not found at {req}; clone may have changed structure.")

    print("\nComfyUI prepared.")
    print(f"Root: {root}")
    print("Set LUCRETIA_COMFY_ROOT=vendor/ComfyUI and run Lucreția.")


if __name__ == "__main__":
    main()
