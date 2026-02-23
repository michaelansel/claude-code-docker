"""Test CLI flag parsing."""

import pytest
from pathlib import Path
import tempfile
from claude_docker import main
import sys


def test_help_flag():
    """Test -h/--help flag."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "-h"]
        main()
    assert exc_info.value.code == 0


def test_no_args_shows_usage():
    """Test that no arguments shows usage."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker"]
        main()
    assert exc_info.value.code == 1


def test_direct_prompt_with_p_flag():
    """Test direct prompt with -p flag."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "-p", "hello world"]
        main()
    assert exc_info.value.code == 0


def test_direct_prompt_positional():
    """Test direct prompt with positional args."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "hello world"]
        main()
    assert exc_info.value.code == 0


def test_agent_list():
    """Test agent list subcommand."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "agent", "list"]
        main()
    assert exc_info.value.code == 0


def test_agent_run():
    """Test agent run subcommand."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "agent", "notes"]
        main()
    assert exc_info.value.code == 0


def test_agent_unknown():
    """Test agent with unknown name."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "agent", "unknown"]
        main()
    assert exc_info.value.code == 1


def test_shell_subcommand():
    """Test shell subcommand."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "shell"]
        main()
    assert exc_info.value.code == 0


def test_setup_subcommand():
    """Test setup subcommand."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "setup"]
        main()
    assert exc_info.value.code == 0


def test_setup_c3po_subcommand():
    """Test setup-c3po subcommand."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "setup-c3po", "http://example.com", "token"]
        main()
    assert exc_info.value.code == 0


def test_stream_flags():
    """Test stream-related flags."""
    # --no-stream
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "--no-stream", "-p", "hello"]
        main()
    assert exc_info.value.code == 0

    # -s
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "-s", "-p", "hello"]
        main()
    assert exc_info.value.code == 0

    # -sj
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "-sj", "-p", "hello"]
        main()
    assert exc_info.value.code == 0


def test_dir_flag():
    """Test -d/--dir flag."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "-d", "/tmp", "-p", "hello"]
        main()
    assert exc_info.value.code == 0


def test_build_flag():
    """Test -b/--build flag."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "-b", "-p", "hello"]
        main()
    assert exc_info.value.code == 0


def test_agent_run_once_flag():
    """Test --once flag is recognized by agent run."""
    with pytest.raises(SystemExit) as exc_info:
        sys.argv = ["claude-docker", "agent", "run", "notes", "--once"]
        main()
    assert exc_info.value.code == 0
