# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A bash/Python wrapper for running Claude Code inside Docker containers (via Finch on macOS). Provides isolated AI workspaces with credential management, streaming output, and multi-agent support via c3po.

## Key Commands

**Run tests:**
```bash
./test-claude-docker
```

**Build the container image:**
```bash
docker build -t claude-code .
```

## Conventions

- Bash scripts use `set -euo pipefail`
- No external dependencies beyond standard Unix tools (bash, sed, grep, Python3)
- Tests mock external binaries by prepending fake scripts to `$PATH`
- `PIPESTATUS[0]` preserves exit codes through stream pipes
- Uses **Docker** (preferred) or **Finch** as the container runtime
- Agent registry (`agents.yaml`) is parsed with sed/grep — no yq dependency
- Prefer CLI commands and exit codes over parsing internal file formats
