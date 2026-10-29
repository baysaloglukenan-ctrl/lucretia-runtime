# Contributing

Thanks for helping improve Lucreția Runtime.

## Good contribution areas

- Windows/local setup reliability;
- Intel Arc/XPU and other non-NVIDIA compatibility;
- worker/relay resilience;
- state recovery and validation;
- provider-independent runtime interfaces;
- tests, diagnostics and documentation.

## Development setup

```powershell
python -m pip install -e .
python scripts/local_doctor.py
```

Run the existing tests with your preferred pytest environment before opening a pull request.

## Pull requests

Keep changes small and reproducible. Include:
- the failure or use case being addressed;
- the environment used for testing;
- the command or workflow that reproduces the result;
- tests for behavior changes when practical.

Do not commit model weights, generated user media, secrets, API keys or commercial/private product code.

By submitting a contribution, you agree that it is provided under the repository's Apache-2.0 license.
