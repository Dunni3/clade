"""Tests for conductor_setup module."""

import json

import yaml

from clade.cli.clade_config import BrotherEntry
from clade.cli.conductor_setup import (
    build_conductor_env,
    build_conductor_mcp_config,
    build_workers_config,
)


class TestBuildWorkersConfig:
    """Tests for build_workers_config()."""

    def test_basic(self):
        """Brothers with ember_host are included."""
        brothers = {
            "oppy": BrotherEntry(
                ssh="ian@masuda",
                working_dir="~/projects/OMTRA",
                ember_host="100.71.57.52",
                ember_port=8100,
            ),
        }
        keys = {"oppy": "key-oppy-123"}

        result = build_workers_config(brothers, keys)
        data = yaml.safe_load(result)

        assert "workers" in data
        assert "oppy" in data["workers"]
        w = data["workers"]["oppy"]
        assert w["ember_url"] == "http://100.71.57.52:8100"
        assert w["ember_api_key"] == "key-oppy-123"
        assert w["hearth_api_key"] == "key-oppy-123"
        assert w["working_dir"] == "~/projects/OMTRA"

    def test_skips_brothers_without_ember(self):
        """Brothers without ember_host are excluded."""
        brothers = {
            "oppy": BrotherEntry(
                ssh="ian@masuda",
                ember_host="100.71.57.52",
                ember_port=8100,
            ),
            "jerry": BrotherEntry(
                ssh="ian@cluster",
                # no ember_host
            ),
        }
        keys = {"oppy": "key-oppy", "jerry": "key-jerry"}

        result = build_workers_config(brothers, keys)
        data = yaml.safe_load(result)

        assert "oppy" in data["workers"]
        assert "jerry" not in data["workers"]

    def test_empty_when_no_ember_brothers(self):
        """Empty workers dict when no brothers have Ember."""
        brothers = {
            "jerry": BrotherEntry(ssh="ian@cluster"),
        }
        keys = {"jerry": "key-jerry"}

        result = build_workers_config(brothers, keys)
        data = yaml.safe_load(result)

        assert data["workers"] == {}

    def test_default_port(self):
        """Uses port 8100 when ember_port is None."""
        brothers = {
            "oppy": BrotherEntry(
                ssh="ian@masuda",
                ember_host="10.0.0.1",
                # ember_port=None (default)
            ),
        }
        keys = {"oppy": "key-oppy"}

        result = build_workers_config(brothers, keys)
        data = yaml.safe_load(result)

        assert data["workers"]["oppy"]["ember_url"] == "http://10.0.0.1:8100"

    def test_multiple_workers(self):
        """Multiple brothers with Ember are all included."""
        brothers = {
            "oppy": BrotherEntry(
                ssh="ian@masuda",
                ember_host="100.71.57.52",
                ember_port=8100,
                working_dir="~/work",
            ),
            "jerry": BrotherEntry(
                ssh="ian@cluster",
                ember_host="100.99.88.77",
                ember_port=8200,
            ),
        }
        keys = {"oppy": "key-oppy", "jerry": "key-jerry"}

        result = build_workers_config(brothers, keys)
        data = yaml.safe_load(result)

        assert len(data["workers"]) == 2
        assert data["workers"]["oppy"]["ember_url"] == "http://100.71.57.52:8100"
        assert data["workers"]["jerry"]["ember_url"] == "http://100.99.88.77:8200"

    def test_no_working_dir(self):
        """Workers without working_dir omit that field."""
        brothers = {
            "oppy": BrotherEntry(
                ssh="ian@masuda",
                ember_host="10.0.0.1",
                ember_port=8100,
                # working_dir=None
            ),
        }
        keys = {"oppy": "key-oppy"}

        result = build_workers_config(brothers, keys)
        data = yaml.safe_load(result)

        assert "working_dir" not in data["workers"]["oppy"]


class TestBuildConductorEnv:
    """Tests for build_conductor_env()."""

    def test_basic(self):
        """Produces correct env file content."""
        result = build_conductor_env(
            kamaji_key="test-key-123",
            server_url="https://54.84.119.14",
        )

        assert "HEARTH_URL=https://54.84.119.14" in result
        assert "HEARTH_API_KEY=test-key-123" in result
        assert "HEARTH_NAME=kamaji" in result
        assert "CONDUCTOR_WORKERS_CONFIG=" in result

    def test_custom_workers_path(self):
        """Uses custom workers config path."""
        result = build_conductor_env(
            kamaji_key="key",
            server_url="https://example.com",
            workers_config_path="/custom/path/workers.yaml",
        )

        assert "CONDUCTOR_WORKERS_CONFIG=/custom/path/workers.yaml" in result


class TestBuildConductorMcpConfig:
    """Tests for build_conductor_mcp_config()."""

    def test_valid_json(self):
        """Produces valid JSON with correct structure."""
        result = build_conductor_mcp_config(
            kamaji_key="test-key",
            server_url="https://example.com",
        )

        data = json.loads(result)
        assert "mcpServers" in data
        assert "clade-conductor" in data["mcpServers"]

    def test_correct_env_vars(self):
        """MCP config has correct environment variables."""
        result = build_conductor_mcp_config(
            kamaji_key="test-key-456",
            server_url="https://54.84.119.14",
            workers_config_path="/home/ubuntu/.config/clade/conductor-workers.yaml",
        )

        data = json.loads(result)
        env = data["mcpServers"]["clade-conductor"]["env"]

        assert env["HEARTH_URL"] == "https://54.84.119.14"
        assert env["HEARTH_API_KEY"] == "test-key-456"
        assert env["HEARTH_NAME"] == "kamaji"
        assert env["CONDUCTOR_WORKERS_CONFIG"] == "/home/ubuntu/.config/clade/conductor-workers.yaml"

    def test_command_and_args(self):
        """MCP config uses entry point to launch the conductor server."""
        result = build_conductor_mcp_config(
            kamaji_key="key",
            server_url="https://example.com",
        )

        data = json.loads(result)
        server = data["mcpServers"]["clade-conductor"]
        assert server["command"] == "clade-conductor"
        assert server["args"] == []

    def test_custom_conductor_cmd(self):
        """MCP config uses provided entry point path."""
        result = build_conductor_mcp_config(
            kamaji_key="key",
            server_url="https://example.com",
            conductor_cmd="/home/ubuntu/.local/venv/bin/clade-conductor",
        )

        data = json.loads(result)
        server = data["mcpServers"]["clade-conductor"]
        assert server["command"] == "/home/ubuntu/.local/venv/bin/clade-conductor"
        assert server["args"] == []
