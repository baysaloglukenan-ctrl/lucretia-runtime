# Lucreția Runtime

> **Reference release**
>
> This repository is a limited open-source reference snapshot of Lucreția Runtime. Active product development continues privately. Apache-2.0 applies to the code published in this repository; future proprietary development is not automatically released under this license.
Lucreția Runtime is a local-first production engine for original short-form animated video. It coordinates creative planning, a single opening keyframe, local or hybrid video generation, state recovery, validation, audio/subtitle composition, and publish-ready MP4 output.

The project is designed for developers and small teams that want reproducible AI-media workflows without making a paid cloud provider a mandatory runtime dependency.

## Core workflow

```text
universe selection → original cast → short plot → opening keyframe
→ one continuous local/hybrid generation → audio + burned subtitles → publish-ready MP4
```

## What is included

- Python runtime and CLI;
- Windows worker for local generation;
- local ComfyUI integration in managed or external mode;
- authenticated hosted-to-local relay;
- state backup and safe restore;
- provider gateway with a deterministic mock path and optional provider adapters;
- video validation and final reel composition;
- diagnostic scripts and automated tests;
- reusable prompt/universe examples.

Generated media, model weights, credentials, private user data, and commercial product logic are intentionally excluded from the repository.

## Local quick start

Requirements:

- Python 3.10+;
- Windows is the primary local-worker target;
- a local generation backend is optional for the basic runtime and required for real local video generation.

```powershell
python -m pip install -e .
$env:LUCRETIA_ACCESS_TOKEN="dev-token"
python -m lucretia_runtime.cli serve --host 127.0.0.1 --port 8787
```

Open:

```text
http://127.0.0.1:8787/?token=dev-token
```

For the Windows setup paths, see [LOCAL_APP_WINDOWS.md](LOCAL_APP_WINDOWS.md).

## Local generation

For managed ComfyUI:

```text
scripts/windows/setup_comfyui_vendor.bat
scripts/windows/run_lucretia_local.bat
```

For an already running external ComfyUI:

```text
scripts/windows/run_lucretia_with_external_comfy.bat
```

The default local service URL is `http://127.0.0.1:8188`.

Model weights are never committed to this repository.

## Hosted relay to a Windows worker

Lucreția can queue a complete reel contract on a hosted runtime and execute the local generation step on an authenticated Windows worker.

Configure secrets only through environment variables. Never commit them:

- `LUCRETIA_ACCESS_TOKEN`
- `LUCRETIA_WORKER_TOKEN`
- provider-specific API keys, if an optional provider adapter is enabled.

A deployment example is provided in `render.yaml`; secret values are intentionally omitted.

## Provider policy

The runtime always supports a local/mock path. Optional paid-provider integrations are adapters, not mandatory dependencies. A provider key must be supplied through the environment at runtime.

## Generated state

Everything under `data/generated/` is runtime output and is ignored by Git. Stable state can be backed up and restored by the worker, but generated user content is not part of the source repository.

## Open-source scope

See [OPEN_SOURCE_SCOPE.md](OPEN_SOURCE_SCOPE.md) for the boundary between the reusable runtime and commercial/private product logic.

## Security

See [SECURITY.md](SECURITY.md). Do not publish credentials in issues, logs, examples, or pull requests.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache License 2.0. See [LICENSE](LICENSE).
