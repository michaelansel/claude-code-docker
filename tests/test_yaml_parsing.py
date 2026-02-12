"""Test YAML parsing for agents.yaml."""

import pytest
import tempfile
from pathlib import Path
from claude_docker import load_agents, get_agent_config


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
