# Lucreția Runtime — local Windows app setup

## Unde dai `git pull`

Nu în ComfyUI și nu în Render.

`git pull` se dă în folderul local al repo-ului Lucreția, adică folderul care conține:

```text
pyproject.toml
src/
scripts/
workflows/
```

Exemplu pentru repo-ul public OSS:

```bat
cd C:\Lucretia\lucretia-runtime
git pull --ff-only
```

Dacă nu ai repo-ul clonat local:

```bat
git clone https://github.com/baysaloglukenan-ctrl/lucretia-runtime.git
cd lucretia-runtime
```

## Varianta rapidă cu butoane `.bat`

În repo există:

```text
scripts/windows/pull_latest.bat
scripts/windows/setup_comfyui_vendor.bat
scripts/windows/run_lucretia_local.bat
scripts/windows/run_lucretia_with_external_comfy.bat
```

### 1. Update Lucreția

Rulează `scripts/windows/pull_latest.bat`.

Face:
- `git pull --ff-only`
- `python -m pip install -e .`
- `python scripts/local_doctor.py`

### 2A. ComfyUI managed în proiect

Rulează:
```text
scripts/windows/setup_comfyui_vendor.bat
scripts/windows/run_lucretia_local.bat
```

ComfyUI este clonat local în `vendor/ComfyUI`.

Deschide `http://127.0.0.1:8787/?token=local`.

### 2B. ComfyUI extern deja pornit

Verifică `http://127.0.0.1:8188`, apoi rulează `scripts/windows/run_lucretia_with_external_comfy.bat`.

## Doctor local

```bat
python scripts/local_doctor.py
```

Verifică repo-ul, pachetul `src/lucretia_runtime`, locația ComfyUI, workflow-ul, portul 8188 și endpointul local de status.

## Workflow ComfyUI

`workflows/comfy/i2v_api_template.json` este contract/placeholder. Pentru image-to-video real se folosește un workflow API JSON compatibil cu backend-ul local.

## Setări importante

Managed:
```bat
set LUCRETIA_COMFY_MODE=managed
set LUCRETIA_COMFY_ROOT=vendor\ComfyUI
set LUCRETIA_COMFY_URL=http://127.0.0.1:8188
```

External:
```bat
set LUCRETIA_COMFY_MODE=external
set LUCRETIA_COMFY_URL=http://127.0.0.1:8188
```

Cheile și tokenurile reale se setează doar prin environment variables și nu se comit în Git.
