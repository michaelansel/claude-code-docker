"""Test runtime detection and utility functions."""

import pytest
from unittest.mock import patch, MagicMock
from claude_docker import detect_runtime, build_hash, needs_rebuild


def test_detect_runtime_docker():
    """Test detecting docker runtime."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        assert detect_runtime() == "docker"


def test_detect_runtime_finch():
    """Test detecting finch runtime."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1)  # docker not found
        mock_run.return_value = MagicMock(returncode=0)  # finch found
        assert detect_runtime() == "finch"


def test_detect_runtime_no_runtime():
    """Test error when no runtime found."""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1)  # docker not found
        mock_run.return_value = MagicMock(returncode=1)  # finch not found
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


def test_needs_rebuild_no_force():
    """Test no rebuild when image exists and hash matches."""
    with patch('subprocess.run') as mock_run:
        # Image exists
        mock_run.return_value = MagicMock(returncode=0)
        # Image inspect returns matching hash
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123")
        mock_run.return_value = MagicMock(returncode=0, stdout="abc123")
        assert needs_rebuild("docker") is False


def test_needs_rebuild_hash_mismatch():
    """Test rebuild when image hash doesn't match."""
    with patch('subprocess.run') as mock_run:
        # Image exists
        mock_run.return_value = MagicMock(returncode=0)
        # Image inspect returns different hash
        mock_run.return_value = MagicMock(returncode=0, stdout="different-hash")
        mock_run.return_value = MagicMock(returncode=0, stdout="different-hash")
        assert needs_rebuild("docker") is True


def test_needs_rebuild_force():
    """Test rebuild when -b flag is set."""
    with patch('subprocess.run') as mock_run:
        # Force rebuild
        with patch.dict('os.environ', {'CLAUSE_DOCKER_FORCE_BUILD': '1'}):
            assert needs_rebuild("docker") is True


def test_needs_rebuild_force_env():
    """Test rebuild with FORCE_BUILD environment variable."""
    with patch('subprocess.run') as mock_run:
        with patch.dict('os.environ', {'CLAUSE_DOCKER_FORCE_BUILD': '1'}):
            assert needs_rebuild("docker") is True


def test_needs_rebuild_no_force_env():
    """Test no rebuild when FORCE_BUILD is not set."""
    with patch('subprocess.run') as mock_run:
        with patch.dict('os.environ', {}, clear=True):
            # Image exists with matching hash
            mock_run.return_value = MagicMock(returncode=0)
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123")
            mock_run.return_value = MagicMock(returncode=0, stdout="abc123")
            assert needs_rebuild("docker") is False
