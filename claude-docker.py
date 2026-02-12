#!/usr/bin/env python3
"""Python implementation of claude-docker."""

import argparse
import atexit
import base64
import hashlib
import json
import os
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


# Configuration
SCRIPT_DIR = Path(__file__).resolve().parent
IMAGE_NAME = "claude-code"
CONFIG_DIR = Path.home() / ".claude-docker"
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
TOKEN_FILE = CONFIG_DIR / ".oauth-token"
USER_CONFIG = CONFIG_DIR / ".claude.json"
AGENTS_FILE = CONFIG_DIR / "agents.yaml"

# Track running container for cleanup
_running_container: Optional[str] = None


def cleanup_container(runtime: Optional[str] = None):
    """Stop the running container if it exists."""
    global _running_container
    if _running_container:
        if runtime is None:
            runtime = detect_runtime()
        try:
            subprocess.run([runtime, "stop", _running_container], capture_output=True)
        except Exception:
            pass
        _running_container = None


# Register cleanup on exit (including signal termination)
atexit.register(cleanup_container)


def signal_handler(signum, frame):
    """Handle SIGINT and SIGTERM to cleanup container."""
    cleanup_container()
    sys.exit(130)


def detect_runtime() -> str:
    """Auto-select docker or finch."""
    if subprocess.run(["which", "docker"], capture_output=True).returncode == 0:
        return "docker"
    elif subprocess.run(["which", "finch"], capture_output=True).returncode == 0:
        return "finch"
    else:
        print("Error: No container runtime found. Install docker or finch.", file=sys.stderr)
        sys.exit(1)


def build_hash() -> str:
    """Compute SHA-256 hash of Dockerfile + entrypoint.sh."""
    h = hashlib.sha256()
    h.update((SCRIPT_DIR / "Dockerfile").read_bytes())
    h.update((SCRIPT_DIR / "entrypoint.sh").read_bytes())
    return h.hexdigest()


def needs_rebuild(runtime: str) -> bool:
    """Check if image needs rebuilding."""
    if os.environ.get("CLAUSE_DOCKER_FORCE_BUILD") == "1":
        return True

    result = subprocess.run(
        [runtime, "image", "inspect", IMAGE_NAME],
        capture_output=True
    )
    if result.returncode != 0:
        return True

    result = subprocess.run(
        [runtime, "image", "inspect", IMAGE_NAME, "--format", "{{index .Config.Labels \"build.hash\"}}"],
        capture_output=True, text=True
    )
    image_hash = result.stdout.strip()
    return image_hash != build_hash()


def load_agents() -> Dict:
    """Load and parse agents.yaml with PyYAML."""
    try:
        import yaml
    except ImportError:
        print("Error: PyYAML is required. Run: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    if not AGENTS_FILE.exists():
        print(f"Error: agents.yaml not found at {AGENTS_FILE}", file=sys.stderr)
        sys.exit(1)

    with open(AGENTS_FILE) as f:
        return yaml.safe_load(f) or {}


@dataclass
class AgentConfig:
    """Represents an agent's configuration."""
    name: str
    workspace: str
    model: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    init: List[str] = field(default_factory=list)


def get_agent_config(name: str, agents: Dict) -> Optional[AgentConfig]:
    """Extract agent configuration from parsed YAML."""
    raw = agents.get(name)
    if raw is None:
        return None

    if isinstance(raw, str):
        return AgentConfig(
            name=name,
            workspace=os.path.expanduser(raw)
        )
    elif isinstance(raw, dict):
        return AgentConfig(
            name=name,
            workspace=os.path.expanduser(raw.get("workspace", "")),
            model=raw.get("model"),
            env=raw.get("env", {}) or {},
            init=raw.get("init", []) or []
        )
    return None


def list_agents(agents: Dict, output_file=None, file=None) -> None:
    """Print formatted list of agents."""
    output = output_file or file or sys.stdout
    print("Available agents:", file=output)
    for name, config in agents.items():
        if isinstance(config, str):
            workspace = config
            print(f"  {name:<15} {workspace}", file=output)
        elif isinstance(config, dict):
            workspace = config.get("workspace", "")
            model = config.get("model")
            env_count = len(config.get("env", {}) or {})
            init_count = len(config.get("init", []) or {})

            parts = [f"  {name:<15} {workspace}"]
            if model:
                parts.append(f"(model: {model})")
            extras = []
            if env_count > 0:
                extras.append(f"env: {env_count}")
            if init_count > 0:
                extras.append(f"init: {init_count}")
            if extras:
                parts.append(f"[{' '.join(extras)}]")
            print(" ".join(parts), file=output)


def encode_init_commands(init_list: List[str]) -> str:
    """Convert init commands list to base64-encoded JSON."""
    json_str = json.dumps(init_list)
    return base64.b64encode(json_str.encode()).decode()


def decode_init_commands(encoded: str) -> List[str]:
    """Decode base64-encoded JSON back to command list."""
    json_str = base64.b64decode(encoded).decode()
    return json.loads(json_str)


def run_container(args: List[str], stream: bool = True, stream_raw: bool = False) -> int:
    """Run the container and return exit code."""
    global _running_container

    runtime = detect_runtime()

    # Extract container name for cleanup
    for i, arg in enumerate(args):
        if arg == "--name" and i + 1 < len(args):
            _running_container = args[i + 1]
            break

    cmd = [runtime] + args

    if stream and not stream_raw:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        format_proc = subprocess.Popen(
            [str(SCRIPT_DIR / "format-stream")],
            stdin=proc.stdout,
            stdout=sys.stdout,
            stderr=sys.stderr
        )
        proc.stdout.close()
        format_proc.wait()
        # Cleanup on normal exit
        cleanup_container(runtime)
        return format_proc.returncode
    else:
        result = subprocess.run(cmd)
        # Cleanup on normal exit
        cleanup_container(runtime)
        return result.returncode


def build_docker_args(
    prompt: str,
    work_dir: str,
    project_name: str,
    agent_mode: bool,
    agent_model: Optional[str],
    agent_env: Dict[str, str],
    agent_init: List[str],
    stream: bool,
    stream_raw: bool
) -> tuple:
    """Build the docker/finch run arguments."""
    runtime = detect_runtime()

    mounts = [
        "-v", f"{CONFIG_DIR}:/home/node/.claude",
        "-v", f"{work_dir}:/workspace",
    ]

    if CREDENTIALS.exists():
        mounts.extend(["-v", f"{CREDENTIALS}:/home/node/.claude/.credentials.json:ro"])

    mounts.extend(["-v", f"{USER_CONFIG}:/home/node/.claude.json"])

    env_args = ["-e", f"CLAUDE_PROJECT_NAME={project_name}"]
    if agent_mode:
        env_args.extend(["-e", "CLAUDE_AGENT_MODE=1"])

    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        env_args.extend(["-e", f"CLAUDE_CODE_OAUTH_TOKEN={os.environ['CLAUDE_CODE_OAUTH_TOKEN']}"])
    elif TOKEN_FILE.exists():
        env_args.extend(["-e", f"CLAUDE_CODE_OAUTH_TOKEN={TOKEN_FILE.read_text().strip()}"])

    if os.environ.get("C3PO_DEBUG"):
        env_args.extend(["-e", f"C3PO_DEBUG={os.environ['C3PO_DEBUG']}"])

    for key, value in agent_env.items():
        env_args.extend(["-e", f"{key}={value}"])

    if agent_init:
        init_b64 = encode_init_commands(agent_init)
        env_args.extend(["-e", f"AGENT_INIT={init_b64}"])

    if agent_mode:
        prompt = "/c3po auto"

    claude_args = ["-p", prompt]
    if stream or stream_raw:
        claude_args = ["--output-format", "stream-json", "--verbose", "-p", prompt]
    if agent_model:
        claude_args.extend(["--model", agent_model])

    container_name = f"claude-code-{os.getpid()}"

    docker_args = [
        "run", "--rm", "--name", container_name,
        *env_args,
        *mounts,
        IMAGE_NAME,
        *claude_args
    ]

    return docker_args, stream


def cmd_setup(args: argparse.Namespace) -> int:
    """Handle setup subcommand."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    if args.token:
        token = args.token
        if not (token.startswith("sk-ant-") or token.startswith("sk-at-")):
            print("Error: Token must start with 'sk-ant-' or 'sk-at-'", file=sys.stderr)
            return 1
        TOKEN_FILE.write_text(token + "\n")
        TOKEN_FILE.chmod(0o600)
        print(f"Token saved to {TOKEN_FILE}", file=sys.stderr)
        return 0

    print("Running 'claude setup-token' to generate a long-lived token...", file=sys.stderr)
    result = subprocess.run(["claude", "setup-token"], capture_output=True, text=True)
    if result.returncode != 0:
        print("Error: claude setup-token failed", file=sys.stderr)
        return 1

    import re
    clean = re.sub(r'\x1b\[[^a-zA-Z]*[a-zA-Z]', '', result.stdout)
    m = re.search(r'(sk-ant-[a-zA-Z0-9_-]+|sk-at-[a-zA-Z0-9_-]+)(?=\s|[.,!]|$)', clean)
    if not m:
        m = re.search(r'(sk-ant-[a-zA-Z0-9_-]{90,110}|sk-at-[a-zA-Z0-9_-]{90,110})', clean)

    if not m:
        print("Error: Could not extract token from claude setup-token output.", file=sys.stderr)
        print("\nPlease provide the token manually:", file=sys.stderr)
        print("  claude-docker setup <your-token>", file=sys.stderr)
        return 1

    TOKEN_FILE.write_text(m.group(1) + "\n")
    TOKEN_FILE.chmod(0o600)
    print(f"Token saved to {TOKEN_FILE}", file=sys.stderr)
    return 0


def cmd_setup_c3po(args: argparse.Namespace) -> int:
    """Handle setup-c3po subcommand."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if not USER_CONFIG.exists():
        USER_CONFIG.write_text("{}\n")

    runtime = detect_runtime()

    if needs_rebuild(runtime):
        print(f"Building {IMAGE_NAME} image...", file=sys.stderr)
        subprocess.run([
            runtime, "build",
            "--label", f"build.hash={build_hash()}",
            "-t", IMAGE_NAME,
            str(SCRIPT_DIR)
        ], check=True)

    machine_name = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()

    setup_cmd = f"""
set -euo pipefail
echo 'Adding/updating michaelansel marketplace...'
claude plugin marketplace update michaelansel 2>/dev/null || claude plugin marketplace add michaelansel/claude-code-plugins
echo 'Installing/updating c3po plugin...'
claude plugin update c3po@michaelansel 2>/dev/null || claude plugin install c3po@michaelansel
echo 'Enrolling with coordinator...'
SETUP_PY=$(find ~/.claude/plugins -path '*/c3po*/setup.py' -print -quit)
if [[ -z "$SETUP_PY" ]]; then
    echo 'Error: Could not find c3po setup.py' >&2
    exit 1
fi
python3 "$SETUP_PY" --enroll '{args.url}' '{args.token}' --machine '{machine_name}' --pattern '{machine_name}/*'
echo 'Done! c3po plugin installed and enrolled.'
"""

    setup_cmd += f"""
python3 -c "
import json, pathlib
p = pathlib.Path.home() / '.claude' / 'c3po-credentials.json'
d = json.loads(p.read_text())
d['machine_name'] = '{machine_name}'
p.write_text(json.dumps(d, indent=2) + '\\n')
"
"""

    subprocess.run([
        runtime, "run", "--rm", "-it",
        "--entrypoint", "bash",
        "-v", f"{CONFIG_DIR}:/home/node/.claude",
        "-v", f"{USER_CONFIG}:/home/node/.claude.json",
        IMAGE_NAME,
        "-c", setup_cmd
    ], check=True)

    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    """Handle shell subcommand."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not USER_CONFIG.exists():
        USER_CONFIG.write_text("{}\n")

    runtime = detect_runtime()

    if needs_rebuild(runtime):
        print(f"Building {IMAGE_NAME} image...", file=sys.stderr)
        subprocess.run([
            runtime, "build",
            "--label", f"build.hash={build_hash()}",
            "-t", IMAGE_NAME,
            str(SCRIPT_DIR)
        ], check=True)

    shell_mounts = [
        "-v", f"{CONFIG_DIR}:/home/node/.claude",
        "-v", f"{os.getcwd()}:/workspace",
        "-v", f"{USER_CONFIG}:/home/node/.claude.json",
    ]

    if CREDENTIALS.exists():
        shell_mounts.extend(["-v", f"{CREDENTIALS}:/home/node/.claude/.credentials.json:ro"])

    shell_env = []
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        shell_env.extend(["-e", f"CLAUDE_CODE_OAUTH_TOKEN={os.environ['CLAUDE_CODE_OAUTH_TOKEN']}"])
    elif TOKEN_FILE.exists():
        shell_env.extend(["-e", f"CLAUDE_CODE_OAUTH_TOKEN={TOKEN_FILE.read_text().strip()}"])

    cmd = [
        runtime, "run", "--rm", "-it",
        "--entrypoint", "bash",
        *shell_env,
        *shell_mounts,
        IMAGE_NAME
    ]

    subprocess.run(cmd, check=True)
    return 0


def cmd_agent(args_list: List[str], args: argparse.Namespace, global_flags: List[str] = None) -> int:
    """Handle agent subcommand (list or run)."""
    if global_flags is None:
        global_flags = []

    # Parse global_flags for stream settings first
    agent_stream = True  # Default for agent mode
    agent_stream_raw = False
    i = 0
    while i < len(global_flags):
        flag = global_flags[i]
        if flag == "--no-stream":
            agent_stream = False
            agent_stream_raw = False
            i += 1
        elif flag == "-s":
            agent_stream = True
            i += 1
        elif flag == "-sj":
            agent_stream = True
            agent_stream_raw = True
            i += 1
        else:
            i += 1

    if not args_list:
        print("Error: agent command requires a name or 'list'", file=sys.stderr)
        print("", file=sys.stderr)
        print("Usage: claude-docker agent <name>", file=sys.stderr)
        print("       claude-docker agent list", file=sys.stderr)
        return 1

    if args_list[0] == "list":
        agents = load_agents()
        list_agents(agents)
        return 0

    # Parse remaining flags from args_list to find the agent name
    j = 0
    while j < len(args_list):
        arg = args_list[j]
        if arg == "--no-stream":
            agent_stream = False
            agent_stream_raw = False
            j += 1
        elif arg == "-s":
            agent_stream = True
            j += 1
        elif arg == "-sj":
            agent_stream = True
            agent_stream_raw = True
            j += 1
        elif arg.startswith("-"):
            # Other flags - skip
            j += 1
        else:
            # This is the agent name
            agent_name = arg
            break
    else:
        # No agent name found
        print("Error: agent command requires a name", file=sys.stderr)
        print("", file=sys.stderr)
        print("Usage: claude-docker agent <name>", file=sys.stderr)
        print("       claude-docker agent list", file=sys.stderr)
        return 1

    agents = load_agents()
    config = get_agent_config(agent_name, agents)
    if config is None:
        print(f"Error: unknown agent '{agent_name}'", file=sys.stderr)
        print("", file=sys.stderr)
        list_agents(agents, file=sys.stderr)
        return 1

    if not config.workspace:
        print(f"Error: agent '{agent_name}' has no workspace configured", file=sys.stderr)
        return 1

    project_name = agent_name
    runtime = detect_runtime()

    # Check if -b flag forces a rebuild
    force_rebuild = "-b" in global_flags

    if force_rebuild or needs_rebuild(runtime):
        print(f"Building {IMAGE_NAME} image...", file=sys.stderr)
        subprocess.run([
            runtime, "build",
            "--label", f"build.hash={build_hash()}",
            "-t", IMAGE_NAME,
            str(SCRIPT_DIR)
        ], check=True)

    docker_args, stream = build_docker_args(
        prompt="",
        work_dir=config.workspace,
        project_name=project_name,
        agent_mode=True,
        agent_model=config.model,
        agent_env=config.env,
        agent_init=config.init,
        stream=agent_stream,
        stream_raw=agent_stream_raw
    )
    return run_container(docker_args, stream=stream, stream_raw=agent_stream_raw)


def cmd_direct_prompt(prompt: str, args: argparse.Namespace, flags: List[str]) -> int:
    """Handle direct prompt (non-agent) mode."""
    if os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"):
        pass
    elif TOKEN_FILE.exists():
        os.environ["CLAUDE_CODE_OAUTH_TOKEN"] = TOKEN_FILE.read_text().strip()
    elif CREDENTIALS.exists():
        pass
    else:
        print("Error: No Claude Code authentication found.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Run setup to generate and store a token:", file=sys.stderr)
        print("  claude-docker setup", file=sys.stderr)
        print("", file=sys.stderr)
        print("Or set CLAUDE_CODE_OAUTH_TOKEN environment variable manually.", file=sys.stderr)
        return 1

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if not USER_CONFIG.exists():
        USER_CONFIG.write_text("{}\n")

    container_claude_md = SCRIPT_DIR / "container-CLAUDE.md"
    if container_claude_md.exists():
        (CONFIG_DIR / "CLAUDE.md").write_text(container_claude_md.read_text())

    runtime = detect_runtime()

    # Check if -b flag forces a rebuild
    force_rebuild = "-b" in flags

    if force_rebuild or needs_rebuild(runtime):
        print(f"Building {IMAGE_NAME} image...", file=sys.stderr)
        subprocess.run([
            runtime, "build",
            "--label", f"build.hash={build_hash()}",
            "-t", IMAGE_NAME,
            str(SCRIPT_DIR)
        ], check=True)

    # Parse flags for options
    work_dir = None
    stream = True  # Default
    stream_raw = False
    i = 0
    while i < len(flags):
        flag = flags[i]
        if flag in ("-d", "--dir") and i + 1 < len(flags):
            work_dir = flags[i + 1]
            i += 2
        elif flag.startswith("--dir="):
            work_dir = flag[6:]
            i += 1
        elif flag.startswith("-d="):
            work_dir = flag[3:]
            i += 1
        elif flag == "-s":
            stream = True
            i += 1
        elif flag == "-sj":
            stream = True
            stream_raw = True
            i += 1
        elif flag == "--no-stream":
            stream = False
            stream_raw = False
            i += 1
        elif flag == "-b":
            i += 1
            continue
        else:
            i += 1

    if work_dir is None:
        work_dir = os.getcwd()

    project_name = Path(work_dir).name

    docker_args, stream = build_docker_args(
        prompt=prompt,
        work_dir=work_dir,
        project_name=project_name,
        agent_mode=False,
        agent_model=None,
        agent_env={},
        agent_init=[],
        stream=stream,
        stream_raw=stream_raw
    )

    return run_container(docker_args, stream=stream, stream_raw=stream_raw)


def print_help():
    """Print help message with Usage: (uppercase) header."""
    help_text = """Usage:
  claude-docker -p <prompt>        Run a prompt
  claude-docker -d <path> -p <prompt>  Run with specific working directory
  claude-docker setup              Set up authentication
  claude-docker setup-c3po <url> <token>  Install and enroll c3po plugin
  claude-docker shell              Interactive shell in container
  claude-docker agent list         List available agents
  claude-docker agent <name>       Run named agent

Options:
  -h, --help       Show this help message and exit
  -d, --dir PATH   Working directory to mount
  -s, --stream     Stream formatted output (default)
  -sj, --stream-json  Stream raw JSON output
  --no-stream      Disable streaming
  -b, --build      Rebuild image before running
  -p, --prompt PROMPT  Prompt to run

Examples:
  claude-docker -p "hello world"   Run a prompt
  claude-docker -d /path agent notes   Run agent with specific directory
  claude-docker agent <name>       Run named agent
  claude-docker agent list         List available agents
  claude-docker setup              Set up authentication
  claude-docker shell              Interactive shell
"""
    print(help_text)


def main():
    """Main entry point with manual argument parsing."""
    cmd_args = sys.argv[1:]

    # Parse global flags and identify subcommand
    global_flags = []
    subcommand = None
    subcommand_args = []
    i = 0
    while i < len(cmd_args):
        arg = cmd_args[i]

        if arg in ("-h", "--help"):
            print_help()
            return 0

        elif arg in ("-d", "--dir"):
            if i + 1 < len(cmd_args):
                global_flags.append(arg)
                global_flags.append(cmd_args[i + 1])
                i += 2
                continue
            else:
                global_flags.append(arg)
                i += 1
                continue

        elif arg.startswith("--dir=") or arg.startswith("-d="):
            global_flags.append(arg)
            i += 1
            continue

        elif arg in ("-s", "-sj", "--no-stream", "-b"):
            global_flags.append(arg)
            i += 1
            continue

        elif arg == "-p":
            if i + 1 < len(cmd_args):
                # Found -p with prompt value
                prompt = cmd_args[i + 1]
                global_flags.append(arg)
                global_flags.append(cmd_args[i + 1])
                # Skip the prompt value as it's been consumed
                subcommand_args = cmd_args[i + 2:]
                # No subcommand - direct prompt mode
                return cmd_direct_prompt(prompt, argparse.Namespace(), global_flags)
            else:
                global_flags.append(arg)
                i += 1
                continue
            break  # Stop parsing, prompt is the remaining content

        elif arg in ("setup", "shell"):
            subcommand = arg
            subcommand_args = cmd_args[i + 1:]
            break

        elif arg == "setup-c3po":
            subcommand = "setup-c3po"
            subcommand_args = cmd_args[i + 1:]
            break

        elif arg == "agent":
            subcommand = "agent"
            subcommand_args = cmd_args[i + 1:]
            break

        elif arg.startswith("-"):
            # Unknown flag - add to global flags
            global_flags.append(arg)
            i += 1
            continue

        else:
            # This is a positional argument (prompt or subcommand)
            # If we haven't seen a subcommand yet, this is a direct prompt
            if subcommand is None:
                # Direct prompt - all remaining args are the prompt
                prompt = " ".join(cmd_args[i:])
                return cmd_direct_prompt(prompt, argparse.Namespace(), global_flags)
            else:
                subcommand_args.append(arg)
                i += 1
                continue

        i += 1

    # If no subcommand was found, show help
    if subcommand is None:
        print_help()
        return 1

    # Execute subcommand
    if subcommand == "setup":
        token = subcommand_args[0] if subcommand_args else None
        args = argparse.Namespace(token=token)
        return cmd_setup(args)

    elif subcommand == "setup-c3po":
        if len(subcommand_args) < 2:
            print("Error: setup-c3po requires url and token", file=sys.stderr)
            print("Usage: claude-docker setup-c3po <url> <token>", file=sys.stderr)
            return 1
        args = argparse.Namespace(url=subcommand_args[0], token=subcommand_args[1])
        return cmd_setup_c3po(args)

    elif subcommand == "shell":
        return cmd_shell(argparse.Namespace())

    elif subcommand == "agent":
        return cmd_agent(subcommand_args, argparse.Namespace(), global_flags)

    return 1


if __name__ == "__main__":
    # Register signal handlers for cleanup
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    sys.exit(main())