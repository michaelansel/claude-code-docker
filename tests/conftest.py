"""Shared test fixtures that prevent tests from actually running containers."""

import pytest
import subprocess
from unittest.mock import MagicMock


@pytest.fixture(autouse=True)
def mock_container_ops(monkeypatch):
    """Mock container/subprocess operations so tests run without real containers."""
    import claude_docker as cd

    # Pre-set runtime so subprocess detection calls are skipped
    monkeypatch.setattr(cd.claude_docker, '_runtime', 'docker')
    monkeypatch.setattr(cd.claude_docker, '_needs_sudo', False)

    # Mock heavy container operations
    monkeypatch.setattr(cd, 'run_container', lambda *a, **kw: 0)
    monkeypatch.setattr(cd, 'needs_rebuild', lambda *a, **kw: False)
    monkeypatch.setattr(cd, 'needs_cli_update', lambda: False)
    monkeypatch.setattr(cd, 'build_image', lambda *a, **kw: None)

    # Provide a minimal agents dict so 'notes' is always a known agent
    monkeypatch.setattr(cd, 'load_agents', lambda: {'notes': '/tmp/notes'})

    # Mock subprocess.run (used by cmd_setup's 'claude setup-token' and cmd_shell)
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = 'sk-ant-' + 'a' * 95 + '\n'
    mock_result.stderr = ''
    monkeypatch.setattr(subprocess, 'run', lambda *a, **kw: mock_result)
