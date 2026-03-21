"""Test runtime detection and utility functions."""

import json
import pytest
from unittest.mock import patch, MagicMock
from claude_docker import detect_runtime, build_hash, needs_rebuild, claude_docker


@pytest.fixture(autouse=True)
def reset_runtime_cache():
    """Reset the cached runtime between tests."""
    claude_docker._runtime = None
    yield
    claude_docker._runtime = None


def test_detect_runtime_docker():
    """Test detecting docker runtime."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert detect_runtime() == "docker"


def test_detect_runtime_nerdctl():
    """Test detecting nerdctl runtime when docker is not available."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1),  # docker not found
            MagicMock(returncode=0),  # nerdctl found
        ]
        assert detect_runtime() == "nerdctl"


def test_detect_runtime_finch():
    """Test detecting finch runtime when docker and nerdctl are not available."""
    with patch('subprocess.run') as mock_run:
        mock_run.side_effect = [
            MagicMock(returncode=1),  # docker not found
            MagicMock(returncode=1),  # nerdctl not found
            MagicMock(returncode=0),  # finch found
        ]
        assert detect_runtime() == "finch"


def test_detect_runtime_no_runtime():
    """Test error when no runtime found."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1)
        with pytest.raises(SystemExit):
            detect_runtime()


def test_build_hash():
    """Test build hash calculation."""
    hash1 = build_hash()
    hash2 = build_hash()
    assert len(hash1) == 64  # SHA-256 hash length
    assert hash1 == hash2


def test_build_hash_consistency():
    """Test that build hash is consistent across calls."""
    hashes = [build_hash() for _ in range(5)]
    assert len(set(hashes)) == 1  # All hashes should be identical


def test_needs_rebuild_no_image():
    """Test rebuild when image doesn't exist."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1)  # image inspect fails
        assert needs_rebuild("docker") is True


def test_needs_rebuild_matching_hash():
    """Test no rebuild when image exists and hash matches."""
    current_hash = build_hash()
    image_json = json.dumps([{"Config": {"Labels": {"build.hash": current_hash}}}])
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=image_json)
        assert needs_rebuild("docker") is False


def test_needs_rebuild_hash_mismatch():
    """Test rebuild when image hash doesn't match."""
    image_json = json.dumps([{"Config": {"Labels": {"build.hash": "different-hash"}}}])
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=image_json)
        assert needs_rebuild("docker") is True


def test_needs_rebuild_force():
    """Test rebuild when -b flag is set."""
    with patch('subprocess.run') as mock_run:
        with patch.dict('os.environ', {'CLAUSE_DOCKER_FORCE_BUILD': '1'}):
            assert needs_rebuild("docker") is True


def test_needs_rebuild_force_env():
    """Test rebuild with FORCE_BUILD environment variable."""
    with patch('subprocess.run') as mock_run:
        with patch.dict('os.environ', {'CLAUSE_DOCKER_FORCE_BUILD': '1'}):
            assert needs_rebuild("docker") is True


def test_needs_rebuild_no_force_env():
    """Test no rebuild when FORCE_BUILD is not set."""
    current_hash = build_hash()
    image_json = json.dumps([{"Config": {"Labels": {"build.hash": current_hash}}}])
    with patch('subprocess.run') as mock_run:
        with patch.dict('os.environ', {}, clear=True):
            mock_run.return_value = MagicMock(returncode=0, stdout=image_json)
            assert needs_rebuild("docker") is False


def test_needs_rebuild_invalid_json():
    """Test rebuild when image inspect returns invalid JSON."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="not json")
        assert needs_rebuild("docker") is True


def test_needs_rebuild_nerdctl_dict_format():
    """Test needs_rebuild works when nerdctl returns a dict instead of a list."""
    current_hash = build_hash()
    image_json = json.dumps({"Config": {"Labels": {"build.hash": current_hash}}})
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=image_json)
        assert needs_rebuild("nerdctl") is False
