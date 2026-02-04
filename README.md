# claude-code-docker

Run Claude Code inside isolated Finch/Docker containers with credential management, streaming output, and multi-agent support via c3po.

## Prerequisites

- [Finch](https://github.com/runfinch/finch) (or Docker)
- Claude Code credentials at `~/.claude/.credentials.json`

## Installation

Clone this repo, then symlink the executables somewhere in your `$PATH`:

```bash
ln -s /path/to/claude-code-docker/claude-docker ~/.local/bin/claude-docker
ln -s /path/to/claude-code-docker/format-stream ~/.local/bin/format-stream
```

Build the container image:

```bash
finch build -t claude-code .
```

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

List registered agents:

```bash
claude-docker agent list
```

Start an agent session:

```bash
claude-docker agent my-agent
```

## Testing

```bash
./test-claude-docker
```
