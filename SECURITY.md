# Security policy

## Supported code

Security fixes target the current default branch and the most recent release line when one exists.

## Reporting a vulnerability

Do not open a public issue containing:
- credentials or tokens;
- exploitable authentication details;
- private user data;
- a working exploit against a live deployment.

Use GitHub's private security-advisory/reporting mechanism for this repository when available. If that mechanism is unavailable, open a minimal public issue asking the maintainer to establish a private contact channel, without disclosing exploit details.

## Secrets

Lucreția reads credentials from environment variables. Real secrets must never be committed to source, examples, logs or test fixtures.

Generated state and user media belong under `data/generated/`, which is excluded from version control.
