# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A bash/Python wrapper for running Claude Code inside Docker containers. Supports Docker, nerdctl (containerd), and Finch as container runtimes. Provides isolated AI workspaces with credential management, streaming output, and multi-agent support via c3po.

## Key Commands

**Run ALL tests (always run both suites):**
```bash
./test-claude-docker          # Bash unit tests (~160 tests, mocks runtime)
python3 -m pytest tests/      # Python unit tests (~92 tests, mocks containers)
./test-acceptance             # Acceptance tests (real container runtime, auto-skips if image not built)
```

These are three independent test suites. `./test-claude-docker` passing does NOT mean
`pytest tests/` passes — always run both. `test-acceptance` requires a built image and
working container runtime.

**Build the container image:**
```bash
docker build -t claude-code .
```

## Conventions

- Bash scripts use `set -euo pipefail`
- No external dependencies beyond standard Unix tools (bash, sed, grep, Python3)
- Tests mock external binaries by prepending fake scripts to `$PATH`
- `PIPESTATUS[0]` preserves exit codes through stream pipes
- Uses **Docker** (preferred), **nerdctl** (containerd), or **Finch** as the container runtime
- Agent registry (`agents.yaml`) is parsed with sed/grep — no yq dependency
- Prefer CLI commands and exit codes over parsing internal file formats
