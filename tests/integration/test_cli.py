"""Integration tests for the Clade CLI using click.testing.CliRunner."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from click.testing import CliRunner

from clade.cli.main import cli
from clade.cli.ssh_utils import SSHResult


class TestCLIHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "The Clade" in result.output
        assert "init" in result.output
        assert "add-brother" in result.output
        assert "status" in result.output
        assert "doctor" in result.output

    def test_version(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "version" in result.output


class TestInit:
    def test_init_with_flags(self, tmp_path: Path):
        """Non-interactive init with all flags."""
        config_file = tmp_path / "clade.yaml"
        keys_file = tmp_path / "keys.json"
        claude_json = tmp_path / "claude.json"

        runner = CliRunner()
        with patch("clade.cli.init_cmd.default_config_path", return_value=config_file), \
             patch("clade.cli.init_cmd.keys_path", return_value=keys_file), \
             patch("clade.cli.init_cmd.is_mcp_registered", return_value=False), \
             patch("clade.cli.init_cmd.register_mcp_server") as mock_register:

            result = runner.invoke(cli, [
                "init",
                "--name", "Test Clade",
                "--personal-name", "testy",
                "--personal-desc", "A test coordinator",
                "--server-url", "https://example.com",
                "-y",
            ])

        assert result.exit_code == 0, result.output
        assert config_file.exists()
        assert keys_file.exists()

        # Verify config content
        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert data["clade"]["name"] == "Test Clade"
        assert data["personal"]["name"] == "testy"
        assert data["server"]["url"] == "https://example.com"

        # Verify key was generated
        with open(keys_file) as f:
            keys = json.load(f)
        assert "testy" in keys

        # MCP registration was called
        mock_register.assert_called_once()

    def test_init_defaults_with_yes(self, tmp_path: Path):
        """Init with -y should use all defaults."""
        config_file = tmp_path / "clade.yaml"
        keys_file = tmp_path / "keys.json"

        runner = CliRunner()
        with patch("clade.cli.init_cmd.default_config_path", return_value=config_file), \
             patch("clade.cli.init_cmd.keys_path", return_value=keys_file), \
             patch("clade.cli.init_cmd.is_mcp_registered", return_value=True):

            result = runner.invoke(cli, ["init", "-y"])

        assert result.exit_code == 0, result.output
        assert config_file.exists()
        with open(config_file) as f:
            data = yaml.safe_load(f)
        assert data["clade"]["name"] == "My Clade"

    def test_init_no_mcp(self, tmp_path: Path):
        """Init with --no-mcp should skip MCP registration."""
        config_file = tmp_path / "clade.yaml"
        keys_file = tmp_path / "keys.json"

        runner = CliRunner()
        with patch("clade.cli.init_cmd.default_config_path", return_value=config_file), \
             patch("clade.cli.init_cmd.keys_path", return_value=keys_file), \
             patch("clade.cli.init_cmd.register_mcp_server") as mock_register:

            result = runner.invoke(cli, ["init", "-y", "--no-mcp"])

        assert result.exit_code == 0, result.output
        mock_register.assert_not_called()

    def test_init_interactive(self, tmp_path: Path):
        """Init with interactive prompts."""
        config_file = tmp_path / "clade.yaml"
        keys_file = tmp_path / "keys.json"

        runner = CliRunner()
        with patch("clade.cli.init_cmd.default_config_path", return_value=config_file), \
             patch("clade.cli.init_cmd.keys_path", return_value=keys_file), \
             patch("clade.cli.init_cmd.is_mcp_registered", return_value=True):

            result = runner.invoke(cli, ["init"], input="My Test Clade\ndoot\nCoordinator\nn\n")

        assert result.exit_code == 0, result.output
        assert config_file.exists()


class TestAddBrother:
    def test_no_config(self, tmp_path: Path):
        """Should fail if no clade.yaml exists."""
        runner = CliRunner()
        with patch("clade.cli.add_brother.load_clade_config", return_value=None):
            result = runner.invoke(cli, ["add-brother", "-y"])
        assert result.exit_code == 1
        assert "clade init" in result.output

    @patch("clade.cli.add_brother.test_ssh")
    @patch("clade.cli.add_brother.check_remote_prereqs")
    @patch("clade.cli.add_brother.run_remote")
    @patch("clade.cli.add_brother.register_mcp_remote")
    def test_add_with_flags(self, mock_mcp_remote, mock_run, mock_prereqs, mock_ssh, tmp_path: Path):
        """Non-interactive add with all flags."""
        config_file = tmp_path / "clade.yaml"
        keys_file = tmp_path / "keys.json"

        # Create initial config
        from clade.cli.clade_config import CladeConfig, save_clade_config
        cfg = CladeConfig(clade_name="Test", server_url="https://example.com")
        save_clade_config(cfg, config_file)

        # Mock SSH success
        mock_ssh.return_value = SSHResult(success=True, stdout="ok")
        mock_prereqs.return_value = MagicMock(
            python="/usr/bin/python3", python_version="3.12.0",
            claude=True, tmux=True, git=True, errors=[], all_ok=True,
        )
        mock_run.return_value = SSHResult(success=True, stdout="DEPLOY_OK")
        mock_mcp_remote.return_value = SSHResult(success=True, stdout="MCP_REGISTERED")

        runner = CliRunner()
        with patch("clade.cli.add_brother.load_clade_config") as mock_load, \
             patch("clade.cli.add_brother.default_config_path", return_value=config_file), \
             patch("clade.cli.add_brother.save_clade_config") as mock_save, \
             patch("clade.cli.add_brother.keys_path", return_value=keys_file):

            mock_load.return_value = cfg
            result = runner.invoke(cli, [
                "add-brother",
                "--name", "oppy",
                "--ssh", "ian@masuda",
                "--working-dir", "~/projects/OMTRA",
                "--role", "worker",
                "--description", "The architect",
                "-y",
            ])

        assert result.exit_code == 0, result.output
        assert "oppy" in result.output
        assert "ian@masuda" in result.output

        # Config was saved with new brother
        mock_save.assert_called_once()
        saved_config = mock_save.call_args[0][0]
        assert "oppy" in saved_config.brothers

    @patch("clade.cli.add_brother.test_ssh")
    def test_add_duplicate(self, mock_ssh, tmp_path: Path):
        """Should fail if brother name already exists."""
        from clade.cli.clade_config import BrotherEntry, CladeConfig
        cfg = CladeConfig(
            brothers={"oppy": BrotherEntry(ssh="ian@masuda")},
        )

        runner = CliRunner()
        with patch("clade.cli.add_brother.load_clade_config", return_value=cfg):
            result = runner.invoke(cli, ["add-brother", "--name", "oppy", "--ssh", "ian@masuda", "-y"])

        assert result.exit_code == 1
        assert "already exists" in result.output

    @patch("clade.cli.add_brother.test_ssh")
    @patch("clade.cli.add_brother.check_remote_prereqs")
    def test_add_ssh_failure_warns(self, mock_prereqs, mock_ssh, tmp_path: Path):
        """SSH failure should warn but allow continuing."""
        from clade.cli.clade_config import CladeConfig, save_clade_config
        config_file = tmp_path / "clade.yaml"
        keys_file = tmp_path / "keys.json"

        cfg = CladeConfig(clade_name="Test")
        save_clade_config(cfg, config_file)

        mock_ssh.return_value = SSHResult(success=False, message="Connection refused")

        runner = CliRunner()
        with patch("clade.cli.add_brother.load_clade_config", return_value=cfg), \
             patch("clade.cli.add_brother.default_config_path", return_value=config_file), \
             patch("clade.cli.add_brother.save_clade_config"), \
             patch("clade.cli.add_brother.keys_path", return_value=keys_file):

            # With -y, it continues despite SSH failure
            result = runner.invoke(cli, [
                "add-brother",
                "--name", "oppy",
                "--ssh", "bad@host",
                "--no-deploy",
                "--no-mcp",
                "-y",
            ])

        assert result.exit_code == 0, result.output
        assert "SSH failed" in result.output


class TestStatus:
    def test_no_config(self):
        runner = CliRunner()
        with patch("clade.cli.status_cmd.load_clade_config", return_value=None):
            result = runner.invoke(cli, ["status"])
        assert result.exit_code == 1
        assert "clade init" in result.output

    @patch("clade.cli.status_cmd.test_ssh")
    @patch("clade.cli.status_cmd.load_keys")
    def test_status_output(self, mock_keys, mock_ssh):
        """Status should show clade name, server, and brothers."""
        from clade.cli.clade_config import BrotherEntry, CladeConfig
        cfg = CladeConfig(
            clade_name="Test Clade",
            personal_name="doot",
            server_url="https://example.com",
            brothers={
                "oppy": BrotherEntry(ssh="ian@masuda", role="worker"),
            },
        )
        mock_keys.return_value = {"doot": "key1", "oppy": "key2"}
        mock_ssh.return_value = SSHResult(success=True)

        runner = CliRunner()
        with patch("clade.cli.status_cmd.load_clade_config", return_value=cfg), \
             patch("clade.cli.status_cmd._check_server", return_value=True):
            result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0, result.output
        assert "Test Clade" in result.output
        assert "doot" in result.output
        assert "oppy" in result.output


class TestDoctor:
    def test_no_config(self):
        runner = CliRunner()
        with patch("clade.cli.doctor.load_clade_config", return_value=None):
            result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    @patch("clade.cli.doctor.test_ssh")
    @patch("clade.cli.doctor.run_remote")
    def test_doctor_all_pass(self, mock_run, mock_ssh):
        """Doctor with everything healthy."""
        from clade.cli.clade_config import BrotherEntry, CladeConfig
        cfg = CladeConfig(
            clade_name="Test",
            personal_name="doot",
            server_url="https://example.com",
            brothers={
                "oppy": BrotherEntry(ssh="ian@masuda"),
            },
        )

        mock_ssh.return_value = SSHResult(success=True)
        # Different responses for different remote checks
        mock_run.side_effect = [
            SSHResult(success=True, stdout="OK"),        # clade package check
            SSHResult(success=True, stdout="True"),       # MCP check
            SSHResult(success=True, stdout="HEARTH_OK"),  # Hearth check
        ]

        runner = CliRunner()
        with patch("clade.cli.doctor.load_clade_config", return_value=cfg), \
             patch("clade.cli.doctor.load_keys", return_value={"doot": "k1", "oppy": "k2"}), \
             patch("clade.cli.doctor.is_mcp_registered", return_value=True), \
             patch("clade.cli.doctor._check_server", return_value=True):
            result = runner.invoke(cli, ["doctor"])

        assert result.exit_code == 0, result.output
        assert "All checks passed" in result.output

    def test_doctor_missing_mcp(self):
        """Doctor should report missing personal MCP."""
        from clade.cli.clade_config import CladeConfig
        cfg = CladeConfig(clade_name="Test", personal_name="doot")

        runner = CliRunner()
        with patch("clade.cli.doctor.load_clade_config", return_value=cfg), \
             patch("clade.cli.doctor.load_keys", return_value={"doot": "k1"}), \
             patch("clade.cli.doctor.is_mcp_registered", return_value=False), \
             patch("clade.cli.doctor._check_server", return_value=False):
            result = runner.invoke(cli, ["doctor"])

        assert result.exit_code == 1
        assert "FAIL" in result.output
