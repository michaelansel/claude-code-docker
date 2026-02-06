# Architecture

## Files

- **`claude-docker`** (bash) — Main CLI entry point. Parses args, resolves agents, builds/runs Finch containers with proper mounts for credentials and config.
- **`format-stream`** (Python) — Reads Claude's `stream-json` output from stdin and formats it with ANSI colors for terminal display. Handles system, assistant, user (tool results), and result message types.
- **`test-claude-docker`** (bash) — Self-contained test suite with no external framework. Mocks `finch` and `format-stream` as stub scripts in `$PATH`, validates argument parsing and command construction.
- **`entrypoint.sh`** (bash) — Container entrypoint. Updates plugins and validates c3po credentials (agent mode) before launching claude.
- **`Dockerfile`** — Node 20-slim base, installs claude-code globally. Version configurable via `CLAUDE_CODE_VERSION` build arg.

## Subcommands

| Subcommand | Description |
|------------|-------------|
| `<prompt>` | Run a one-off prompt (buffers output by default) |
| `setup` | Generate and store an OAuth token via `claude setup-token` |
| `setup-c3po <url> <token>` | Install michaelansel marketplace + c3po plugin, enroll with coordinator |
| `shell` | Interactive bash shell inside the container with all standard mounts |
| `agent list` | List agents from the registry |
| `agent <name>` | Run a named agent with `/c3po auto` (streams by default) |

## Authentication

Checked in priority order:

1. `CLAUDE_CODE_OAUTH_TOKEN` environment variable
2. Token file at `~/.claude-docker/.oauth-token` (written by `setup`)
3. Credentials file at `~/.claude/.credentials.json` (mounted read-only)

## Container Mounts

| Host path | Container path | Notes |
|-----------|---------------|-------|
| `~/.claude-docker/` | `/home/node/.claude` | Plugins, settings, credentials persist here |
| `~/.claude-docker/.claude.json` | `/home/node/.claude.json` | MCP server config; auto-created if missing |
| `$WORK_DIR` | `/workspace` | Working directory |
| `~/.claude/.credentials.json` | `/home/node/.claude/.credentials.json` | Read-only; only if using credentials file auth |

## Pre-launch Checks

The container entrypoint (`entrypoint.sh`) runs checks before launching claude:

| Mode | Plugin updates | C3PO credential check |
|------|---------------|----------------------|
| `claude-docker "prompt"` | Yes (best-effort) | No |
| `claude-docker agent <name>` | Yes (best-effort) | Yes (hard-fail) |
| `claude-docker shell` | No (bypasses entrypoint) | No |
| `claude-docker setup-c3po` | No (bypasses entrypoint) | No |

- Plugin updates discover installed plugins from `~/.claude/plugins/` and update each via `claude plugin update`. Failures are ignored.
- C3PO credential validation (agent mode only) checks `c3po-credentials.json` and pings the coordinator. Invalid or missing credentials abort the launch.
- `--entrypoint bash` overrides (used by `shell` and `setup-c3po`) bypass all pre-launch checks.

## Image Auto-rebuild

The image is automatically rebuilt when build inputs change. A SHA-256 hash of `Dockerfile` and `entrypoint.sh` is embedded as a `build.hash` label in the image at build time. On each launch, the hash is recomputed from the source files and compared to the image label. A rebuild is triggered when:

- The image doesn't exist
- The hash doesn't match (build inputs changed, e.g. after `git pull`)
- The `-b` / `--build` flag is passed

This avoids unnecessary rebuilds when only non-image files change (tests, docs, scripts).

## Container Lifecycle

- Containers are named `claude-code-$$` (PID-based) for identification
- An EXIT/INT/TERM trap calls `finch stop` for graceful shutdown (important for c3po session hooks)
- `--rm` ensures containers are cleaned up after exit

## Streaming

- **Direct mode**: buffers output by default. Use `-s` for formatted streaming or `-sj` for raw JSON.
- **Agent mode**: streams formatted output by default. Use `--no-stream` to disable.
- Streaming pipes `finch run` output through `format-stream`. Exit code is preserved via `PIPESTATUS[0]`.

## Config Paths

| Path | Purpose |
|------|---------|
| `~/.claude-docker/` | All persistent container state |
| `~/.claude-docker/.claude.json` | MCP server configuration |
| `~/.claude-docker/.oauth-token` | Stored OAuth token |
| `~/.claude-docker/agents.yaml` | Agent registry (`name: directory` YAML) |
| `~/.claude-docker/plugins/` | Installed Claude Code plugins |

## setup-c3po Flow

1. Ensures `~/.claude-docker/.claude.json` exists
2. Runs an interactive container with config mounts
3. Inside the container:
   - Updates or adds the `michaelansel/claude-code-plugins` marketplace
   - Updates or installs the `c3po@michaelansel` plugin
   - Finds `setup.py` via `find` in the plugins directory
   - Enrolls with the coordinator using `--machine docker --pattern 'docker/*'`
4. All state persists in `~/.claude-docker/`
