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


def test_agent_config_triggers_default():
    """Test AgentConfig has empty triggers and post_run by default."""
    config = AgentConfig(
        name="notes",
        workspace="/home/user/notes"
    )
    assert config.triggers == []
    assert config.post_run == []


def test_agent_config_readonly_default():
    """Test AgentConfig readonly defaults to False."""
    config = AgentConfig(
        name="notes",
        workspace="/home/user/notes"
    )
    assert config.readonly is False


def test_agent_config_readonly_true():
    """Test AgentConfig readonly=True."""
    config = AgentConfig(
        name="reviewer",
        workspace="/home/user/project",
        readonly=True,
    )
    assert config.readonly is True


def test_agent_config_with_triggers():
    """Test AgentConfig with triggers and post_run."""
    config = AgentConfig(
        name="worker",
        workspace="/home/user/worker",
        triggers=[{"type": "c3po"}, {"type": "script", "command": "python3 check.py"}],
        post_run=["bash scripts/post.sh"],
    )
    assert len(config.triggers) == 2
    assert config.triggers[0] == {"type": "c3po"}
    assert config.triggers[1] == {"type": "script", "command": "python3 check.py"}
    assert config.post_run == ["bash scripts/post.sh"]


def test_agent_config_with_schedule_trigger():
    """Test AgentConfig with a schedule trigger."""
    config = AgentConfig(
        name="daily-report",
        workspace="/home/user/reports",
        triggers=[{"type": "schedule", "cron": "0 6 * * *", "timezone": "America/Vancouver"}],
    )
    assert len(config.triggers) == 1
    assert config.triggers[0]["type"] == "schedule"
    assert config.triggers[0]["cron"] == "0 6 * * *"
    assert config.triggers[0]["timezone"] == "America/Vancouver"


def test_agent_config_with_interval_trigger():
    """Test AgentConfig with an interval trigger."""
    config = AgentConfig(
        name="poller",
        workspace="/home/user/polling",
        triggers=[{"type": "interval", "after": "4h"}],
    )
    assert len(config.triggers) == 1
    assert config.triggers[0]["type"] == "interval"
    assert config.triggers[0]["after"] == "4h"


def test_agent_config_with_mixed_triggers():
    """Test AgentConfig with multiple trigger types."""
    config = AgentConfig(
        name="multi",
        workspace="/home/user/work",
        triggers=[
            {"type": "schedule", "cron": "0 2 * * *", "timezone": "UTC"},
            {"type": "c3po"},
        ],
    )
    assert len(config.triggers) == 2
    assert config.triggers[0]["type"] == "schedule"
    assert config.triggers[1]["type"] == "c3po"
