"""Test AgentConfig dataclass."""

import pytest
from dataclasses import FrozenInstanceError
from claude_docker import AgentConfig


def test_agent_config_creation():
    """Test creating AgentConfig instance."""
    config = AgentConfig(
        name="coder",
        workspace="/home/user/project",
        model="opus",
        env={"VAR": "value"},
        init=["cmd1"]
    )
    assert config.name == "coder"
    assert config.workspace == "/home/user/project"
    assert config.model == "opus"
    assert config.env == {"VAR": "value"}
    assert config.init == ["cmd1"]


def test_agent_config_default_values():
    """Test AgentConfig with default values."""
    config = AgentConfig(
        name="notes",
        workspace="/home/user/notes"
    )
    assert config.model is None
    assert config.env == {}
    assert config.init == []


def test_agent_config_frozen():
    """Test that AgentConfig is frozen and immutable."""
    config = AgentConfig(
        name="coder",
        workspace="/home/user/project"
    )
    with pytest.raises(FrozenInstanceError):
        config.workspace = "/new/path"


def test_agent_config_equality():
    """Test AgentConfig equality."""
    config1 = AgentConfig(
        name="coder",
        workspace="/home/user/project",
        model="opus"
    )
    config2 = AgentConfig(
        name="coder",
        workspace="/home/user/project",
        model="opus"
    )
    assert config1 == config2


def test_agent_config_inequality():
    """Test AgentConfig inequality."""
    config1 = AgentConfig(
        name="coder",
        workspace="/home/user/project"
    )
    config2 = AgentConfig(
        name="builder",
        workspace="/home/user/project"
    )
    assert config1 != config2


def test_agent_config_repr():
    """Test AgentConfig string representation."""
    config = AgentConfig(
        name="coder",
        workspace="/home/user/project",
        model="opus"
    )
    repr_str = repr(config)
    assert "AgentConfig" in repr_str
    assert "coder" in repr_str
