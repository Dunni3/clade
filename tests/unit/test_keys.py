"""Tests for API key management."""

import json
import os
import stat
from pathlib import Path

from clade.cli.keys import (
    add_key,
    format_api_keys_env,
    generate_api_key,
    load_keys,
    save_keys,
)


class TestGenerateApiKey:
    def test_returns_string(self):
        key = generate_api_key()
        assert isinstance(key, str)

    def test_reasonable_length(self):
        key = generate_api_key()
        assert len(key) >= 32

    def test_unique(self):
        keys = {generate_api_key() for _ in range(100)}
        assert len(keys) == 100


class TestLoadSaveKeys:
    def test_load_nonexistent(self, tmp_path: Path):
        result = load_keys(tmp_path / "missing.json")
        assert result == {}

    def test_round_trip(self, tmp_path: Path):
        kp = tmp_path / "keys.json"
        keys = {"doot": "abc123", "oppy": "def456"}
        save_keys(keys, kp)
        loaded = load_keys(kp)
        assert loaded == keys

    def test_permissions(self, tmp_path: Path):
        kp = tmp_path / "keys.json"
        save_keys({"test": "key"}, kp)
        mode = os.stat(kp).st_mode
        assert mode & stat.S_IRUSR  # owner read
        assert mode & stat.S_IWUSR  # owner write
        assert not (mode & stat.S_IRGRP)  # no group read
        assert not (mode & stat.S_IROTH)  # no other read

    def test_creates_parent_dirs(self, tmp_path: Path):
        kp = tmp_path / "deep" / "nested" / "keys.json"
        save_keys({"test": "key"}, kp)
        assert kp.exists()


class TestAddKey:
    def test_adds_and_returns_key(self, tmp_path: Path):
        kp = tmp_path / "keys.json"
        key = add_key("oppy", kp)
        assert isinstance(key, str)
        assert len(key) >= 32

        loaded = load_keys(kp)
        assert loaded["oppy"] == key

    def test_preserves_existing(self, tmp_path: Path):
        kp = tmp_path / "keys.json"
        save_keys({"doot": "existing"}, kp)
        add_key("oppy", kp)

        loaded = load_keys(kp)
        assert loaded["doot"] == "existing"
        assert "oppy" in loaded


class TestFormatApiKeysEnv:
    def test_single_key(self):
        result = format_api_keys_env({"doot": "abc123"})
        assert result == "abc123:doot"

    def test_multiple_keys(self):
        result = format_api_keys_env({"doot": "abc", "oppy": "def"})
        assert "abc:doot" in result
        assert "def:oppy" in result
        assert "," in result

    def test_empty(self):
        result = format_api_keys_env({})
        assert result == ""
