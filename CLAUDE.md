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
finch build -t claude-code .
```

**Run directly:**
```bash
./claude-docker "prompt here"
./claude-docker -d ~/some/dir "prompt"
./claude-docker agent list
./claude-docker agent <name>
```

## Architecture

- **`claude-docker`** (bash) — Main CLI entry point. Parses args, resolves agents, builds/runs Finch containers with proper mounts for credentials and config. Two modes: direct prompt and agent mode (auto-streams, uses `/c3po auto`).
- **`format-stream`** (Python) — Reads Claude's `stream-json` output from stdin and formats it with ANSI colors for terminal display. Handles system, assistant, user (tool results), and result message types.
- **`test-claude-docker`** (bash) — Self-contained test suite with no external framework. Mocks `finch` and `format-stream` as stub scripts in `$PATH`, validates argument parsing and command construction.
- **`Dockerfile`** — Node 20-slim base, installs claude-code globally. Version configurable via `CLAUDE_CODE_VERSION` build arg.

## Runtime Details

- Uses **Finch** (not Docker) as the container runtime
- Credentials: `~/.claude/.credentials.json` (mounted read-only)
- User config: `~/.claude-docker/.claude.json` (MCP servers, etc.)
- Agent registry: `~/.claude-docker/agents.yaml` (simple `name: directory` YAML, parsed with sed/grep — no yq)
- Container naming: `claude-code-$$` (PID-based), with trap cleanup on EXIT/INT/TERM for graceful shutdown
- Agent mode streams by default; direct mode buffers by default

## Conventions

- Bash scripts use `set -euo pipefail`
- No external dependencies beyond standard Unix tools (bash, sed, grep, Python3)
- Tests mock external binaries by prepending fake scripts to `$PATH`
- `PIPESTATUS[0]` preserves exit codes through stream pipes
