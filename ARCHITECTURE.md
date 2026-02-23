# Architecture

## Files

- **`claude-docker`** (bash wrapper) — Shell wrapper that sets up Python venv and invokes `claude-docker.py`
- **`claude-docker.py`** (Python) — Main CLI implementation. Parses args, resolves agents, builds/runs containers (Docker or Finch) with proper mounts for credentials and config
- **`requirements.txt`** — Python dependencies (PyYAML for YAML parsing)
- **`format-stream`** (Python) — Reads Claude's `stream-json` output from stdin and formats it with ANSI colors for terminal display. Handles system, assistant, user (tool results), and result message types.
- **`test-claude-docker`** (bash) — Self-contained test suite with no external framework. Mocks the container runtime and `format-stream` as stub scripts in `$PATH`, validates argument parsing and command construction.
- **`entrypoint.sh`** (bash) — Container entrypoint. Updates plugins and validates c3po credentials (agent mode) before launching claude.
- **`Dockerfile`** — Node 20-slim base, installs claude-code globally and PyYAML. Version configurable via `CLAUDE_CODE_VERSION` build arg.

## Python Implementation

The Python implementation (`claude-docker.py`) provides:

- **PyYAML for robust YAML parsing** - Uses `yaml.safe_load()` instead of hand-rolled sed/grep parsing
- **JSON for init command transfer** - Base64-encoded JSON arrays instead of `|||` delimited strings
- **Dataclasses for agent config** - Clean structure for agent configuration
- **Same CLI interface** - All flags and subcommands work identically to the bash version

### Agent Config Parsing

The Python implementation uses PyYAML to parse `agents.yaml`:

**Simple format:**
```yaml
notes: ~/Documents/Notes
```
→ `AgentConfig(name="notes", workspace="/Users/.../Documents/Notes")`

**Block format:**
```yaml
coder:
  workspace: ~/Code/project
  model: opus
  env:
    ANTHROPIC_BASE_URL: https://api.anthropic.com
  init:
    - "source ~/venv/bin/activate"
```
→ Full `AgentConfig` with all fields populated

### Init Commands Transfer

Init commands are encoded as:
1. JSON array: `["cmd1", "cmd2"]`
2. Base64 encoded: `WyJjbWQxIiwgImNtZDIiXQ==`
3. Passed via `AGENT_INIT` environment variable

The `entrypoint.sh` decodes using:
```bash
DECODED=$(printf '%s' "$AGENT_INIT" | base64 -d)
jq -r '.[]' <<< "$DECODED"
```

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
| `~/.claude-docker/claude-docker.yaml` | `/home/node/claude-docker.yaml` | Config file with streamLogging; auto-created if missing |
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
- An EXIT/INT/TERM trap calls container stop for graceful shutdown (important for c3po session hooks)
- `--rm` ensures containers are cleaned up after exit

## Streaming

- **Direct mode**: buffers output by default. Use `-s` for formatted streaming or `-sj` for raw JSON.
- **Agent mode**: streams formatted output by default. Use `--no-stream` to disable.
- Streaming pipes container run output through `format-stream`. Exit code is preserved via `PIPESTATUS[0]`.

## Config Paths

| Path | Purpose |
|------|---------|
| `~/.claude-docker/` | All persistent container state |
| `~/.claude-docker/.claude.json` | MCP server configuration |
| `~/.claude-docker/.oauth-token` | Stored OAuth token |
| `~/.claude-docker/agents.yaml` | Agent registry (YAML) |
| `~/.claude-docker/plugins/` | Installed Claude Code plugins |

## Trigger Loop

When an agent has `triggers` configured in `agents.yaml`, `claude-docker agent run <name>` enters a host-side loop instead of running the container once. This eliminates idle token consumption — the container exits after doing work, and claude-docker restarts it only when a trigger fires.

**Limitation**: Each container run starts with no session memory. Suitable for task-processor agents where each trigger is independent. Not suitable for conversational agents needing multi-turn context. Agents should document work to files/git before exiting.

### Loop behavior

```
claude-docker agent run <name>     (triggers set → enters host loop)
  │
  ├── [first run] start container immediately
  │     prompt: one-shot (process work, exit)
  │     entrypoint.sh post-exit: write agent ID to handoff file
  │
  ├── read agent ID from handoff file
  │
  ├── run post_run commands (workspace cwd, fail-open)
  │
  ├── [loop] run all triggers in parallel threads
  │     first to fire → cancel others → start container
  │
  └── repeat; SIGINT/SIGTERM → kill trigger threads, unregister agent_id, exit
```

Use `--once` to skip the loop for debugging: `claude-docker agent run <name> --once`

### Agent ID handoff

The c3po plugin writes the agent ID to `/tmp/c3po-agent-id-{session_id}` inside the container. On exit, `entrypoint.sh` globs this file and copies the contents to the handoff file (mounted from host).

| Location | Path |
|----------|------|
| Host | `~/.claude-docker/agents/{name}-trigger-handoff` |
| Container | `/tmp/claude-docker-trigger-handoff` (via volume mount) |
| Env var | `CLAUDE_DOCKER_TRIGGER_HANDOFF=/tmp/claude-docker-trigger-handoff` |

### Trigger types

| Type | Behavior |
|------|----------|
| `c3po` | Long-polls C-3PO inbox (`/agent/api/wait`, fallback `/agent/api/pending`); fires when message count > 0 |
| `script` | Runs `command` as subprocess (cwd=workspace); fires on exit 0; nonzero retries with exponential backoff (5s→60s) |

All triggers run in parallel; the first to fire cancels the others and starts the container.

### post_run

Shell commands listed under `post_run` run after each container exit (before the next trigger wait). Failures are logged but the loop continues (fail-open).

### Implicit /c3po auto deprecation

When no `prompt` is configured and no `triggers` are set, `agent run` defaults to `/c3po auto` (Claude owns the restart loop internally). This is preserved for backward compatibility but deprecated — a warning is emitted. Prefer setting `prompt` explicitly in `agents.yaml`.

## setup-c3po Flow

1. Ensures `~/.claude-docker/.claude.json` exists
2. Runs an interactive container with config mounts
3. Inside the container:
   - Updates or adds the `michaelansel/claude-code-plugins` marketplace
   - Updates or installs the `c3po@michaelansel` plugin
   - Finds `setup.py` via `find` in the plugins directory
   - Enrolls with the coordinator using `--machine docker --pattern 'docker/*'`
4. All state persists in `~/.claude-docker/`