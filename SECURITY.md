<!--
SPDX-License-Identifier: CC-BY-4.0
Copyright 2026 João Harrison
-->
# Security Policy

Thank you for helping keep Human Margin and its users safe.

## Supported versions

This project is pre-1.0. Security fixes are applied to the latest release and
to `main`. Older tagged versions are not maintained.

| Version | Supported |
|---------|-----------|
| `main` / latest release | ✅ |
| older tags | ❌ |

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Report it privately via one of:

- GitHub's **private vulnerability reporting** — on the repository, go to
  **Security → Report a vulnerability** (preferred).
- Email: jokelhar26@gmail.com

Please include:

- a description of the issue and its impact,
- steps to reproduce (a minimal example helps),
- affected version or commit, and
- any suggested remediation.

## What to expect

- Acknowledgement of your report within a reasonable time.
- An honest assessment of whether it is in scope and how it will be handled.
- Credit for the report if you would like it, once a fix is released.

## Scope notes

This is **decision-support software that runs locally**. It never writes to ad
accounts, stores no credentials (API keys come only from environment variables,
never from the repo), and sends no telemetry. The most relevant classes of
issue are therefore: handling of untrusted input files (scenario YAML, CSV
exports, benchmark data), unsafe deserialisation, path traversal in export or
logging paths, and dependency vulnerabilities.
