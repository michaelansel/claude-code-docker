#!/usr/bin/env python3
"""Python implementation of claude-docker."""

import argparse
import atexit
import base64
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional


# Configuration
SCRIPT_DIR = Path(__file__).resolve().parent
IMAGE_NAME = "claude-code"
CONFIG_DIR = Path.home() / ".claude-docker"
CREDENTIALS = Path.home() / ".claude" / ".credentials.json"
TOKEN_FILE = CONFIG_DIR / ".oauth-token"
USER_CONFIG = CONFIG_DIR / ".claude.json"
DOCKER_YAML_CONFIG = CONFIG_DIR / "claude-docker.yaml"
AGENTS_FILE = CONFIG_DIR / "agents.yaml"


class ClaudeDocker:
    """Main claude-docker class with encapsulated state."""

    def __init__(self):
        self._running_container: Optional[str] = None
        self._runtime: Optional[str] = None

    @property
    def runtime(self) -> str:
        """Get or detect container runtime."""
        if self._runtime is None:
            self._runtime = self._detect_runtime()
        return self._runtime

    def _detect_runtime(self) -> str:
        """Auto-select docker or finch."""
        if subprocess.run(["which", "docker"], capture_output=True, env=os.environ).returncode == 0:
            return "docker"
        elif subprocess.run(["which", "finch"], capture_output=True, env=os.environ).returncode == 0:
            return "finch"
        else:
            print(f"Error: No container runtime found. Install docker or finch.", file=sys.stderr)
            sys.exit(1)

    def cleanup_container(self) -> None:
        """Stop the running container if it exists."""
        if self._running_container:
            try:
                subprocess.run([self.runtime, "stop", self._running_container],
                             capture_output=True)
            except Exception:
                pass
            self._running_container = None

    def signal_handler(self, signum, frame):
        """Handle SIGINT and SIGTERM to cleanup container."""
        self.cleanup_container()
        sys.exit(130)


# Global instance (must be defined before functions that use it)
claude_docker = ClaudeDocker()


# Keep helper functions module-level for backward compatibility
def detect_runtime() -> str:
    """Auto-select docker or finch (module-level wrapper)."""
    return claude_docker.runtime


def cleanup_container(runtime: Optional[str] = None):
    """Stop the running container if it exists (global wrapper)."""
    claude_docker.cleanup_container()


# Register cleanup on exit (including signal termination)
atexit.register(cleanup_container)


def signal_handler(signum, frame):
    """Handle SIGINT and SIGTERM to cleanup container (global wrapper)."""
    claude_docker.signal_handler(signum, frame)


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
        capture_output=True,
        env=os.environ
    )
    if result.returncode != 0:
        return True

    result = subprocess.run(
        [runtime, "image", "inspect", IMAGE_NAME, "--format", "{{index .Config.Labels \"build.hash\"}}"],
        capture_output=True, text=True,
        env=os.environ
    )
    image_hash = result.stdout.strip()
    return image_hash != build_hash()


def load_agents(yaml_content: str = None) -> Optional[Dict]:
    """Load and parse agents.yaml with PyYAML.

    Args:
        yaml_content: Optional YAML string to parse. If not provided, reads from AGENTS_FILE.
    """
    try:
        import yaml
    except ImportError:
        print(f"Error: PyYAML is required. Run: pip install pyyaml", file=sys.stderr)
        sys.exit(1)

    if yaml_content is not None:
        return yaml.safe_load(yaml_content)

    # No yaml_content provided - try to read from file
    if not AGENTS_FILE.exists():
        return None
    with open(AGENTS_FILE) as f:
        return yaml.safe_load(f)


@dataclass(frozen=True)
class AgentConfig:
    """Represents an agent's configuration."""
    name: str
    workspace: str
    model: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    init: List[str] = field(default_factory=list)


def get_agent_config(name: str, agents: Dict) -> Optional[AgentConfig]:
    """Extract agent configuration from parsed YAML.

    Returns None if agent doesn't exist or workspace is missing.
    """
    raw = agents.get(name)
    if raw is None:
        return None

    if isinstance(raw, str):
        workspace = os.path.expanduser(raw)
        if not workspace:
            return None
        return AgentConfig(name=name, workspace=workspace)
    elif isinstance(raw, dict):
        workspace = os.path.expanduser(raw.get("workspace", ""))
        if not workspace:
            return None
        return AgentConfig(
            name=name,
            workspace=workspace,
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
    runtime = claude_docker.runtime

    # Extract container name for cleanup
    for i, arg in enumerate(args):
        if arg == "--name" and i + 1 < len(args):
            claude_docker._running_container = args[i + 1]
            break

    cmd = [runtime] + args

    if stream and not stream_raw:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
        # Find format-stream in SCRIPT_DIR or PATH
        format_stream_path = SCRIPT_DIR / "format-stream"
        if not format_stream_path.exists():
            # Try to find in PATH
            format_stream_path = shutil.which("format-stream")
            if not format_stream_path:
                format_stream_path = SCRIPT_DIR / "format-stream"
        format_proc = subprocess.Popen(
            [str(format_stream_path)],
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
    runtime = claude_docker.runtime

    mounts = [
        "-v", f"{CONFIG_DIR}:/home/node/.claude",
        "-v", f"{work_dir}:/workspace",
    ]

    if CREDENTIALS.exists():
        mounts.extend(["-v", f"{CREDENTIALS}:/home/node/.claude/.credentials.json:ro"])

    mounts.extend(["-v", f"{DOCKER_YAML_CONFIG}:/home/node/claude-docker.yaml"])
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

    # Initialize DOCKER_YAML_CONFIG with default logging settings if it doesn't exist
    if not DOCKER_YAML_CONFIG.exists():
        yaml_config = """streamLogging:
  enabled: true
  directory: {directory}
  retentionDays: 30
  maxFileSizeMB: 10
""".format(directory=Path.home() / ".claude-docker" / "session-logs")
        DOCKER_YAML_CONFIG.write_text(yaml_config)
        DOCKER_YAML_CONFIG.chmod(0o600)

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


def cmd_clean_logs(args: argparse.Namespace) -> int:
    """Handle clean-logs subcommand."""
    import shutil

    # Read configuration for retention settings
    try:
        if DOCKER_YAML_CONFIG.exists():
            import yaml
            with open(DOCKER_YAML_CONFIG) as f:
                config = yaml.safe_load(f) or {}
                stream_log_config = config.get("streamLogging", {})
                retention_days = stream_log_config.get("retentionDays", 30)
            log_dir = Path(stream_log_config.get("directory", str(Path.home() / ".claude-docker" / "session-logs")))
        else:
            retention_days = 30
            log_dir = Path.home() / ".claude-docker" / "session-logs"
    except Exception:
        retention_days = 30
        log_dir = Path.home() / ".claude-docker" / "session-logs"

    # If --older-than flag is provided, use it, otherwise use config
    if args.older_than:
        try:
            retention_days = int(args.older_than.rstrip('d'))
        except ValueError:
            print(f"Error: --older-than must be a number followed by 'd' (e.g., 7d)", file=sys.stderr)
            return 1

    # Calculate cutoff timestamp
    cutoff = datetime.now() - timedelta(days=retention_days)

    # Delete old log files
    deleted_count = 0
    total_size = 0

    if log_dir.exists():
        for log_file in log_dir.glob("*.json"):
            try:
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_mtime < cutoff:
                    file_size = log_file.stat().st_size
                    log_dir.joinpath(log_file).unlink()
                    deleted_count += 1
                    total_size += file_size
            except Exception as e:
                print(f"Error deleting {log_file}: {e}", file=sys.stderr)

    # Print summary
    print(f"Cleaned up {deleted_count} log file(s)", file=sys.stderr)
    if total_size > 0:
        total_size_mb = total_size / (1024 * 1024)
        print(f"Total size freed: {total_size_mb:.2f} MB", file=sys.stderr)

    return 0


def cmd_setup_c3po(args: argparse.Namespace) -> int:
    """Handle setup-c3po subcommand."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if not USER_CONFIG.exists():
        USER_CONFIG.write_text("{}\n")

    runtime = claude_docker.runtime

    if needs_rebuild(runtime):
        print(f"Building {IMAGE_NAME} image...", file=sys.stderr)
        subprocess.run([
            runtime, "build",
            "--label", f"build.hash={build_hash()}",
            "-t", IMAGE_NAME,
            str(SCRIPT_DIR)
        ], check=True)

    machine_name = subprocess.run(["hostname"], capture_output=True, text=True).stdout.strip()

    # Build setup script with proper escaping - use subprocess instead of f-strings for security
    setup_commands = [
        "set -euo pipefail",
        "echo 'Adding/updating michaelansel marketplace...'",
        "claude plugin marketplace update michaelansel 2>/dev/null || claude plugin marketplace add michaelansel/claude-code-plugins",
        "echo 'Installing/updating c3po plugin...'",
        "claude plugin update c3po@michaelansel 2>/dev/null || claude plugin install c3po@michaelansel",
        "echo 'Enrolling with coordinator...'",
        "SETUP_PY=$(find ~/.claude/plugins -path '*/c3po*/setup.py' -print -quit)",
        "if [[ -z \"$SETUP_PY\" ]]; then",
        "    echo 'Error: Could not find c3po setup.py' >&2",
        "    exit 1",
        "fi",
        f"python3 \"$SETUP_PY\" --enroll {args.url} {args.token} --machine {machine_name} --pattern {machine_name}/*",
        "echo 'Done! c3po plugin installed and enrolled.'"
    ]

    setup_script = "\n".join(setup_commands)

    # Update c3po credentials
    cred_script = f"""
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
        "-v", f"{DOCKER_YAML_CONFIG}:/home/node/claude-docker.yaml",
        "-v", f"{USER_CONFIG}:/home/node/.claude.json",
        IMAGE_NAME,
        "-c", setup_script + cred_script
    ], check=True)

    return 0


def cmd_shell(args: argparse.Namespace) -> int:
    """Handle shell subcommand."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not USER_CONFIG.exists():
        USER_CONFIG.write_text("{}\n")

    runtime = claude_docker.runtime

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
        "-v", f"{DOCKER_YAML_CONFIG}:/home/node/claude-docker.yaml",
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


def cmd_agent_list(args: argparse.Namespace) -> int:
    """Handle agent list subcommand."""
    agents = load_agents()
    list_agents(agents)
    return 0


def cmd_agent_run(args: argparse.Namespace) -> int:
    """Handle agent run subcommand."""
    agent_name = args.agent_name

    agents = load_agents()
    config = get_agent_config(agent_name, agents)
    if config is None:
        # Agent exists but has no workspace configured
        print(f"Error: agent '{agent_name}' has no workspace configured", file=sys.stderr)
        return 1

    if not config.workspace:
        print(f"Error: agent '{agent_name}' has no workspace configured", file=sys.stderr)
        return 1

    # Parse args for global flags (stream settings)
    global_flags = []
    for arg in sys.argv[1:]:
        if arg in ("-s", "-sj", "--no-stream", "-b", "--log-stream", "--no-log-stream", "--log-dir"):
            global_flags.append(arg)

    project_name = agent_name
    runtime = claude_docker.runtime

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

    # Parse global_flags for stream settings
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

    # Initialize DOCKER_YAML_CONFIG with default logging settings if it doesn't exist
    if not DOCKER_YAML_CONFIG.exists():
        yaml_config = """streamLogging:
  enabled: true
  directory: {directory}
  retentionDays: 30
  maxFileSizeMB: 10
""".format(directory=Path.home() / ".claude-docker" / "session-logs")
        DOCKER_YAML_CONFIG.write_text(yaml_config)
        DOCKER_YAML_CONFIG.chmod(0o600)

    container_claude_md = SCRIPT_DIR / "container-CLAUDE.md"
    if container_claude_md.exists():
        (CONFIG_DIR / "CLAUDE.md").write_text(container_claude_md.read_text())

    runtime = claude_docker.runtime

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


class CustomFormatter(argparse.RawDescriptionHelpFormatter):
    """Custom formatter that uses uppercase 'Usage:' instead of lowercase 'usage:'."""
    def _format_usage(self, usage, actions, groups, prefix):
        if prefix is None:
            prefix = 'Usage: '
        else:
            prefix = prefix.replace('usage:', 'Usage:')
        return super()._format_usage(usage, actions, groups, prefix)


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
  claude-docker clean-logs         Clean up old session logs

Options:
  -h, --help       Show this help message and exit
  -d, --dir PATH   Working directory to mount
  -s, --stream     Stream formatted output (default)
  -sj, --stream-json  Stream raw JSON output
  --no-stream      Disable streaming
  -b, --build      Rebuild image before running
  -p, --prompt PROMPT  Prompt to run

  --log-stream      Enable session logging (default: enabled)
  --no-log-stream   Disable session logging
  --log-dir PATH    Override log directory (default: ~/.claude-docker/session-logs)

Examples:
  claude-docker -p "hello world"   Run a prompt
  claude-docker -d /path agent notes   Run agent with specific directory
  claude-docker agent <name>       Run named agent
  claude-docker agent list         List available agents
  claude-docker setup              Set up authentication
  claude-docker shell              Interactive shell
  claude-docker clean-logs         Clean up old session logs
"""
    print(help_text)


def main():
    """Main entry point with argparse-based argument parsing."""
    parser = argparse.ArgumentParser(
        prog="claude-docker",
        description="Run Claude Code inside Docker/Finch containers",
        formatter_class=CustomFormatter,
        usage="usage: claude-docker [-h] [-d DIR] [-s] [-sj] [--no-stream] [-b]\n"
              "                     [--log-stream] [--no-log-stream] [--log-dir LOG_DIR]\n"
              "                     {setup,setup-c3po,shell,clean-logs,agent} ...\n"
              "                     [prompt ...]",
        epilog="""
Examples:
  claude-docker -p "hello world"   Run a prompt
  claude-docker agent run notes     Run named agent
  claude-docker agent list          List available agents
  claude-docker setup               Set up authentication
  claude-docker shell               Interactive shell
        """
    )

    # Global flags
    parser.add_argument("-d", "--dir", help="Working directory to mount")
    parser.add_argument("-s", "--stream", action="store_true",
                        help="Stream formatted output")
    parser.add_argument("-sj", "--stream-json", action="store_true",
                        help="Stream raw JSON output")
    parser.add_argument("--no-stream", action="store_true",
                        help="Disable streaming")
    parser.add_argument("-b", "--build", action="store_true",
                        help="Rebuild image before running")
    parser.add_argument("--log-stream", action="store_true",
                        help="Enable session logging")
    parser.add_argument("--no-log-stream", action="store_true",
                        help="Disable session logging")
    parser.add_argument("--log-dir", help="Override log directory")
    parser.add_argument("-p", "--prompt", help="Prompt to run (direct mode)")

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Subcommands")

    # setup
    setup_parser = subparsers.add_parser("setup", help="Set up authentication")
    setup_parser.add_argument("token", nargs="?", help="OAuth token")

    # setup-c3po
    setup_c3po_parser = subparsers.add_parser("setup-c3po",
        help="Install and enroll c3po plugin")
    setup_c3po_parser.add_argument("url", help="Coordinator URL")
    setup_c3po_parser.add_argument("token", help="Admin token")

    # shell
    subparsers.add_parser("shell", help="Interactive shell in container")

    # clean-logs
    clean_logs_parser = subparsers.add_parser("clean-logs", help="Clean up old session logs")
    clean_logs_parser.add_argument("--older-than", help="Delete logs older than X days (e.g., 7d, 30d)")

    # agent
    agent_parser = subparsers.add_parser("agent", help="Run named agent")
    # Add global flags to agent parser so they're recognized
    agent_parser.add_argument("-s", "--stream", action="store_true",
                        help="Stream formatted output")
    agent_parser.add_argument("-sj", "--stream-json", action="store_true",
                        help="Stream raw JSON output")
    agent_parser.add_argument("--no-stream", action="store_true",
                        help="Disable streaming")
    agent_parser.add_argument("-b", "--build", action="store_true",
                        help="Rebuild image before running")
    agent_parser.add_argument("--log-stream", action="store_true",
                        help="Enable session logging")
    agent_parser.add_argument("--no-log-stream", action="store_true",
                        help="Disable session logging")
    agent_parser.add_argument("--log-dir", help="Override log directory")

    agent_subparsers = agent_parser.add_subparsers(dest="agent_cmd", help="Agent command")
    agent_subparsers.add_parser("list", help="List available agents")
    agent_run_parser = agent_subparsers.add_parser("run", help="Run named agent")
    agent_run_parser.add_argument("agent_name", help="Agent name")

    args = parser.parse_args()

    # Determine mode and dispatch
    if args.command == "setup":
        return cmd_setup(args)
    elif args.command == "setup-c3po":
        return cmd_setup_c3po(args)
    elif args.command == "shell":
        return cmd_shell(args)
    elif args.command == "clean-logs":
        return cmd_clean_logs(args)
    elif args.command == "agent":
        if args.agent_cmd == "list":
            return cmd_agent_list(args)
        elif args.agent_cmd == "run":
            return cmd_agent_run(args)
        else:
            agent_parser.print_help()
            return 2
    elif args.command is None:
        if args.prompt:
            # Direct prompt mode with -p flag
            global_flags = []
            for arg in sys.argv[1:]:
                if arg in ("--log-stream", "--no-log-stream", "--log-dir"):
                    global_flags.append(arg)
            return cmd_direct_prompt(args.prompt, args, global_flags)
        else:
            # No subcommand and no prompt - show help
            parser.print_help()
            return 2
    else:
        # Unknown command
        parser.print_help()
        return 2


if __name__ == "__main__":
    # Register signal handlers for cleanup
    signal.signal(signal.SIGINT, claude_docker.signal_handler)
    signal.signal(signal.SIGTERM, claude_docker.signal_handler)
    sys.exit(main())