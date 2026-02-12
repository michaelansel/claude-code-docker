"""Test init command encoding/decoding."""

import pytest
import json
import base64
from claude_docker import encode_init_commands, decode_init_commands


def test_encode_decode_basic():
    """Test basic command list encoding/decoding."""
    original = ["cmd1", "cmd2"]
    encoded = encode_init_commands(original)
    decoded = decode_init_commands(encoded)
    assert decoded == original


def test_encode_decode_with_spaces():
    """Test commands with spaces."""
    original = ["echo hello world", "run script.py arg1 arg2"]
    encoded = encode_init_commands(original)
    decoded = decode_init_commands(encoded)
    assert decoded == original


def test_encode_decode_with_quotes():
    """Test commands with special characters."""
    original = ['echo "quoted"', "echo \'single\'"]
    encoded = encode_init_commands(original)
    decoded = decode_init_commands(encoded)
    assert decoded == original


def test_encode_decode_empty_list():
    """Test empty command list."""
    original = []
    encoded = encode_init_commands(original)
    decoded = decode_init_commands(encoded)
    assert decoded == []


def test_encode_decode_complex():
    """Test complex command list with various elements."""
    original = [
        "source ~/venv/bin/activate",
        "git pull origin main",
        "npm install",
        "echo 'multi-line\ncommand'"
    ]
    encoded = encode_init_commands(original)
    decoded = decode_init_commands(encoded)
    assert decoded == original


def test_decode_invalid_base64():
    """Test decoding invalid base64 string."""
    with pytest.raises(Exception):
        decode_init_commands("not-valid-base64")


def test_decode_invalid_json():
    """Test decoding base64 that encodes invalid JSON."""
    with pytest.raises(Exception):
        decode_init_commands("SGVsbG8gV29ybGQ=")  # "Hello World" in base64


def test_roundtrip_json_structure():
    """Test that JSON structure is preserved through encoding/decoding."""
    original = {"commands": ["cmd1", "cmd2"]}
    json_str = json.dumps(original)
    encoded = base64.b64encode(json_str.encode()).decode()
    decoded = base64.b64decode(encoded).decode()
    parsed = json.loads(decoded)
    assert parsed == original
