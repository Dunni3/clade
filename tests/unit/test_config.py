"""Unit tests for configuration loading."""

import tempfile
from pathlib import Path

import pytest

from clade.core.config import (
    FALLBACK_CONFIG,
    _convert_clade_yaml,
    _is_clade_yaml,
    load_config,
)


class TestLoadConfig:
    def test_fallback_config_when_no_file(self):
        """When no config file exists, should return fallback config."""
        config = load_config(path=Path("/nonexistent/config.yaml"))
        assert config == FALLBACK_CONFIG
        assert "jerry" in config["brothers"]
        assert "oppy" in config["brothers"]

    def test_load_valid_yaml_config(self):
        """Should load configuration from valid YAML file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
brothers:
  test-brother:
    host: test.example.com
    working_dir: ~/test
    description: "Test Brother"
mailbox:
  url: "https://example.com"
  name: "test"
""")
            f.flush()
            config_path = Path(f.name)

        try:
            config = load_config(path=config_path)
            assert "test-brother" in config["brothers"]
            assert config["brothers"]["test-brother"]["host"] == "test.example.com"
            assert config["mailbox"]["url"] == "https://example.com"
        finally:
            config_path.unlink()

    def test_fallback_on_invalid_yaml(self):
        """Should fall back to default config if YAML is invalid."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            f.flush()
            config_path = Path(f.name)

        try:
            with pytest.warns(UserWarning, match="Failed to load config"):
                config = load_config(path=config_path)
            assert config == FALLBACK_CONFIG
        finally:
            config_path.unlink()


class TestCladeYamlDetection:
    def test_is_clade_yaml_true(self):
        data = {"clade": {"name": "Test"}, "brothers": {}}
        assert _is_clade_yaml(data)

    def test_is_clade_yaml_false_legacy(self):
        data = {"brothers": {}}
        assert not _is_clade_yaml(data)

    def test_is_clade_yaml_false_no_clade_key(self):
        data = {"brothers": {}}
        assert not _is_clade_yaml(data)


class TestConvertCladeYaml:
    def test_basic_conversion(self):
        data = {
            "clade": {"name": "Test Clade"},
            "personal": {"name": "doot"},
            "server": {"url": "https://example.com"},
            "brothers": {
                "oppy": {
                    "ssh": "ian@masuda",
                    "working_dir": "~/projects/OMTRA",
                    "role": "worker",
                    "description": "The architect",
                },
            },
        }
        config = _convert_clade_yaml(data)
        assert "oppy" in config["brothers"]
        assert config["brothers"]["oppy"]["host"] == "masuda"
        assert config["brothers"]["oppy"]["working_dir"] == "~/projects/OMTRA"
        assert config["brothers"]["oppy"]["description"] == "The architect"
        assert config["mailbox"]["url"] == "https://example.com"

    def test_no_server(self):
        data = {"clade": {"name": "Test"}, "brothers": {}}
        config = _convert_clade_yaml(data)
        assert config["mailbox"] is None

    def test_no_brothers(self):
        data = {"clade": {"name": "Test"}}
        config = _convert_clade_yaml(data)
        assert config["brothers"] == {}

    def test_ssh_without_user(self):
        data = {
            "clade": {"name": "Test"},
            "brothers": {
                "jerry": {"ssh": "cluster", "description": "GPU runner"},
            },
        }
        config = _convert_clade_yaml(data)
        assert config["brothers"]["jerry"]["host"] == "cluster"


class TestLoadCladeYaml:
    def test_load_clade_yaml_format(self):
        """load_config should detect and convert clade.yaml format."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("""
clade:
  name: "Test Clade"
  created: "2026-02-13"
personal:
  name: doot
  description: "Test coordinator"
server:
  url: https://example.com
brothers:
  oppy:
    ssh: ian@masuda
    working_dir: ~/projects/OMTRA
    role: worker
    description: "The architect"
""")
            f.flush()
            config_path = Path(f.name)

        try:
            config = load_config(path=config_path)
            assert "oppy" in config["brothers"]
            assert config["brothers"]["oppy"]["host"] == "masuda"
            assert config["mailbox"]["url"] == "https://example.com"
        finally:
            config_path.unlink()


class TestFallbackConfig:
    def test_jerry_exists(self):
        assert "jerry" in FALLBACK_CONFIG["brothers"]

    def test_oppy_exists(self):
        assert "oppy" in FALLBACK_CONFIG["brothers"]
