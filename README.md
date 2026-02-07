# claude-code-docker

Run Claude Code inside isolated Docker/Finch containers with credential management, streaming output, and multi-agent support via c3po.

## Prerequisites

- Docker or [Finch](https://github.com/runfinch/finch)
- Claude Code authentication (one of):
  - OAuth token via `claude-docker setup`
  - `CLAUDE_CODE_OAUTH_TOKEN` environment variable
  - Credentials file at `~/.claude/.credentials.json`

## Installation

Clone this repo, then symlink the executables somewhere in your `$PATH`:

```bash
ln -s /path/to/claude-code-docker/claude-docker ~/.local/bin/claude-docker
ln -s /path/to/claude-code-docker/format-stream ~/.local/bin/format-stream
```

Build the container image (or use `-b` to auto-build on first run):

```bash
docker build -t claude-code .
```

## Setup

Set up authentication:

```bash
claude-docker setup
```

Set up c3po multi-agent coordination (optional):

```bash
claude-docker setup-c3po <coordinator_url> <admin_token>
```

This installs the michaelansel marketplace and c3po plugin inside the container, then enrolls with the coordinator for `docker/*` agent identities.

## Agent Setup

Copy the example agent registry and edit it:

```bash
mkdir -p ~/.claude-docker
cp agents.yaml.example ~/.claude-docker/agents.yaml
# Edit to map agent names to your project directories
```

## Usage

Run a one-off prompt:

```bash
claude-docker "explain this codebase"
```

Run against a specific directory:

```bash
claude-docker -d ~/Code/my-project "add tests"
```

Stream formatted output:

```bash
claude-docker -s "explain this codebase"
```

List registered agents:

```bash
claude-docker agent list
```

Start an agent session (streams by default):

```bash
claude-docker agent my-agent
```

Drop into an interactive shell inside the container:

```bash
claude-docker shell
```

### Options

| Flag | Description |
|------|-------------|
| `-d, --dir <path>` | Working directory to mount (default: `$PWD`) |
| `-s, --stream` | Stream formatted output |
| `-sj, --stream-json` | Stream raw JSON output |
| `--no-stream` | Disable streaming (for agent mode) |
| `-b, --build` | Rebuild the image before running |

## Testing

```bash
./test-claude-docker
```
