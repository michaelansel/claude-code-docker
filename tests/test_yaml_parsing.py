"""Test YAML parsing for agents.yaml."""

import pytest
import tempfile
import yaml
from pathlib import Path
from unittest.mock import patch
from claude_docker import load_agents, get_agent_config, AGENTS_FILE


def test_simple_format():
    """Test simple format: name: directory"""
    yaml_content = "notes: ~/Documents/Notes"
    agents = load_agents(yaml_content)
    assert agents == {"notes": "~/Documents/Notes"}


def test_block_format():
    """Test block format with all fields."""
    yaml_content = """
coder:
  workspace: ~/Code/project
  model: opus
  env:
    ANTHROPIC_BASE_URL: https://api.anthropic.com
  init:
    - "source ~/venv/bin/activate"
    - "git pull origin main"
"""
    agents = load_agents(yaml_content)
    assert agents["coder"]["workspace"] == "~/Code/project"
    assert agents["coder"]["model"] == "opus"
    assert agents["coder"]["env"] == {"ANTHROPIC_BASE_URL": "https://api.anthropic.com"}
    assert agents["coder"]["init"] == ["source ~/venv/bin/activate", "git pull origin main"]


def test_empty_yaml():
    """Test empty YAML document."""
    yaml_content = ""
    agents = load_agents(yaml_content)
    assert agents is None


def test_get_agent_config_simple():
    """Test extracting config from simple format."""
    agents = {"notes": "~/Documents/Notes"}
    config = get_agent_config("notes", agents)
    assert config is not None
    assert config.name == "notes"
    assert config.workspace == "/Users/michaelansel/Documents/Notes"
    assert config.model is None
    assert config.env == {}
    assert config.init == []


def test_get_agent_config_block():
    """Test extracting config from block format."""
    agents = {
        "coder": {
            "workspace": "~/Code/project",
            "model": "opus",
            "env": {"VAR": "value"},
            "init": ["cmd1", "cmd2"]
        }
    }
    config = get_agent_config("coder", agents)
    assert config is not None
    assert config.name == "coder"
    assert config.workspace == "/Users/michaelansel/Code/project"
    assert config.model == "opus"
    assert config.env == {"VAR": "value"}
    assert config.init == ["cmd1", "cmd2"]


def test_get_agent_config_missing():
    """Test getting config for non-existent agent."""
    agents = {"notes": "~/Documents/Notes"}
    config = get_agent_config("unknown", agents)
    assert config is None


def test_get_agent_config_no_workspace():
    """Test agent with missing workspace field."""
    agents = {"coder": {"model": "opus"}}
    config = get_agent_config("coder", agents)
    assert config is None  # No workspace means invalid config


def test_get_agent_config_triggers_and_post_run():
    """Test parsing triggers and post_run fields."""
    yaml_content = """
worker:
  workspace: ~/Code/worker
  prompt: "Handle pending tasks."
  triggers:
    - type: c3po
    - type: script
      command: python3 check.py
  post_run:
    - bash scripts/post.sh
"""
    agents = load_agents(yaml_content)
    config = get_agent_config("worker", agents)
    assert config is not None
    assert len(config.triggers) == 2
    assert config.triggers[0] == {"type": "c3po"}
    assert config.triggers[1] == {"type": "script", "command": "python3 check.py"}
    assert config.post_run == ["bash scripts/post.sh"]


def test_get_agent_config_triggers_empty_default():
    """Test that missing triggers/post_run default to empty lists."""
    agents = {"notes": "~/Documents/Notes"}
    config = get_agent_config("notes", agents)
    assert config is not None
    assert config.triggers == []
    assert config.post_run == []


def test_load_agents_migrates_simple_format():
    """load_agents converts simple string format to dict with prompt: /c3po auto."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("notes: ~/Documents/Notes\n")
        tmp = Path(f.name)
    try:
        with patch("claude_docker.AGENTS_FILE", tmp):
            data = load_agents()
        assert data["notes"]["workspace"] == "~/Documents/Notes"
        assert data["notes"]["prompt"] == "/c3po auto"
        # File was updated too
        on_disk = yaml.safe_load(tmp.read_text())
        assert on_disk["notes"]["prompt"] == "/c3po auto"
    finally:
        tmp.unlink()


def test_load_agents_migrates_dict_no_prompt():
    """load_agents adds prompt: /c3po auto to dict agents without prompt or triggers."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"coder": {"workspace": "~/Code/project", "model": "opus"}}, f)
        tmp = Path(f.name)
    try:
        with patch("claude_docker.AGENTS_FILE", tmp):
            data = load_agents()
        assert data["coder"]["prompt"] == "/c3po auto"
        assert data["coder"]["model"] == "opus"
    finally:
        tmp.unlink()


def test_load_agents_skips_existing_prompt():
    """load_agents does not touch agents that already have a prompt."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"worker": {"workspace": "~/Code/worker", "prompt": "Do stuff."}}, f)
        tmp = Path(f.name)
    try:
        with patch("claude_docker.AGENTS_FILE", tmp):
            data = load_agents()
        assert data["worker"]["prompt"] == "Do stuff."
    finally:
        tmp.unlink()


def test_load_agents_skips_triggers():
    """load_agents does not inject prompt for agents that have triggers."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"bot": {"workspace": "~/Code/bot", "triggers": [{"type": "c3po"}]}}, f)
        tmp = Path(f.name)
    try:
        with patch("claude_docker.AGENTS_FILE", tmp):
            data = load_agents()
        assert "prompt" not in data["bot"]
    finally:
        tmp.unlink()


def test_load_agents_migration_idempotent():
    """load_agents migration is idempotent: second load does not re-write the file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write("notes: ~/Documents/Notes\n")
        tmp = Path(f.name)
    try:
        with patch("claude_docker.AGENTS_FILE", tmp):
            load_agents()
            content_after_first = tmp.read_text()
            load_agents()
            content_after_second = tmp.read_text()
        assert content_after_first == content_after_second
    finally:
        tmp.unlink()
