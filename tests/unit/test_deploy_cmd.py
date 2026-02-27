"""Tests for deploy CLI commands."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from clade.cli.clade_config import BrotherEntry, CladeConfig
from clade.cli.main import cli
from clade.cli.ssh_utils import SSHResult


def make_config(**kwargs):
    defaults = dict(
        clade_name="Test Clade",
        server_ssh="ubuntu@44.195.96.130",
        server_ssh_key="~/.ssh/key.pem",
        server_url="https://44.195.96.130",
        brothers={
            "oppy": BrotherEntry(
                ssh="ian@masuda",
                ember_host="100.71.57.52",
                ember_port=8100,
            ),
        },
    )
    defaults.update(kwargs)
    return CladeConfig(**defaults)


class TestDeployGroup:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "--help"])
        assert result.exit_code == 0
        assert "hearth" in result.output
        assert "frontend" in result.output
        assert "conductor" in result.output
        assert "ember" in result.output
        assert "all" in result.output


class TestDeployHearth:
    @patch("clade.cli.deploy_cmd.httpx")
    @patch("clade.cli.deploy_cmd.run_remote")
    @patch("clade.cli.deploy_cmd.scp_directory")
    @patch("clade.cli.deploy_cmd.test_ssh")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_success(self, mock_config, mock_ssh, mock_scp, mock_run, mock_httpx):
        mock_config.return_value = make_config()
        mock_ssh.return_value = SSHResult(success=True)
        mock_scp.return_value = SSHResult(success=True)
        # pip install + restart
        mock_run.side_effect = [
            SSHResult(success=True, stdout="ok"),
            SSHResult(success=True, stdout="RESTART_OK"),
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "hearth"])
        assert result.exit_code == 0
        assert "deployed successfully" in result.output

    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_no_server_ssh(self, mock_config):
        mock_config.return_value = make_config(server_ssh=None)

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "hearth"])
        assert result.exit_code != 0

    @patch("clade.cli.deploy_cmd.test_ssh")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_ssh_failure(self, mock_config, mock_ssh):
        mock_config.return_value = make_config()
        mock_ssh.return_value = SSHResult(success=False, message="Connection refused")

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "hearth"])
        assert result.exit_code != 0
        assert "SSH failed" in result.output

    @patch("clade.cli.deploy_cmd.run_remote")
    @patch("clade.cli.deploy_cmd.scp_directory")
    @patch("clade.cli.deploy_cmd.test_ssh")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_scp_failure(self, mock_config, mock_ssh, mock_scp, mock_run):
        mock_config.return_value = make_config()
        mock_ssh.return_value = SSHResult(success=True)
        mock_scp.return_value = SSHResult(success=False, message="Permission denied")

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "hearth"])
        assert result.exit_code != 0
        assert "Failed" in result.output


class TestDeployFrontend:
    @patch("clade.cli.deploy_cmd.subprocess.run")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_build_failure(self, mock_config, mock_npm):
        mock_config.return_value = make_config()
        mock_npm.return_value = MagicMock(returncode=1, stderr="build error")

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "frontend"])
        assert result.exit_code != 0
        assert "Build failed" in result.output

    @patch("clade.cli.deploy_cmd.subprocess.run")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_npm_not_found(self, mock_config, mock_npm):
        mock_config.return_value = make_config()
        mock_npm.side_effect = FileNotFoundError("npm")

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "frontend"])
        assert result.exit_code != 0
        assert "npm not found" in result.output


class TestDeployEmber:
    @patch("clade.cli.deploy_cmd.check_ember_health_remote")
    @patch("clade.cli.deploy_cmd.run_remote")
    @patch("clade.cli.deploy_cmd.deploy_ember_env")
    @patch("clade.cli.deploy_cmd.detect_remote_user")
    @patch("clade.cli.deploy_cmd.load_keys")
    @patch("clade.cli.deploy_cmd.detect_clade_entry_point")
    @patch("clade.cli.deploy_cmd.deploy_clade_to_ember_venv")
    @patch("clade.cli.deploy_cmd.test_ssh")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_success(self, mock_config, mock_ssh, mock_deploy_venv, mock_detect_entry,
                     mock_load_keys, mock_detect_user, mock_deploy_env, mock_run, mock_health):
        mock_config.return_value = make_config()
        mock_ssh.return_value = SSHResult(success=True)
        mock_deploy_venv.return_value = SSHResult(success=True, stdout="DEPLOY_OK")
        mock_detect_entry.return_value = "/home/ian/.local/ember-venv/bin/clade-ember"
        mock_load_keys.return_value = {"oppy": "test-api-key"}
        mock_detect_user.return_value = "ian"
        mock_deploy_env.return_value = SSHResult(success=True, stdout="EMBER_ENV_OK")
        # run_remote: grep ExecStart + restart
        mock_run.side_effect = [
            SSHResult(success=True, stdout="ExecStart=/home/ian/.local/ember-venv/bin/clade-ember"),
            SSHResult(success=True, stdout="RESTART_OK"),
        ]
        mock_health.return_value = True

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "ember", "oppy"])
        assert result.exit_code == 0
        assert "deployed successfully" in result.output

    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_brother_not_found(self, mock_config):
        mock_config.return_value = make_config()

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "ember", "nobody"])
        assert result.exit_code != 0
        assert "not found" in result.output

    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_no_ember(self, mock_config):
        config = make_config()
        config.brothers["jerry"] = BrotherEntry(ssh="ian@cluster")
        mock_config.return_value = config

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "ember", "jerry"])
        assert result.exit_code != 0
        assert "no ember_host" in result.output

    @patch("clade.cli.deploy_cmd.deploy_clade_to_ember_venv")
    @patch("clade.cli.deploy_cmd.test_ssh")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_deploy_failure(self, mock_config, mock_ssh, mock_deploy_venv):
        mock_config.return_value = make_config()
        mock_ssh.return_value = SSHResult(success=True)
        mock_deploy_venv.return_value = SSHResult(success=False, stdout="", message="Connection lost")

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "ember", "oppy"])
        assert result.exit_code != 0
        assert "Deploy failed" in result.output

    @patch("clade.cli.deploy_cmd.check_ember_health_remote")
    @patch("clade.cli.deploy_cmd.deploy_systemd_service")
    @patch("clade.cli.deploy_cmd.run_remote")
    @patch("clade.cli.deploy_cmd.deploy_ember_env")
    @patch("clade.cli.deploy_cmd.detect_remote_user")
    @patch("clade.cli.deploy_cmd.load_keys")
    @patch("clade.cli.deploy_cmd.detect_clade_entry_point")
    @patch("clade.cli.deploy_cmd.deploy_clade_to_ember_venv")
    @patch("clade.cli.deploy_cmd.test_ssh")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_service_migration(self, mock_config, mock_ssh, mock_deploy_venv, mock_detect_entry,
                                mock_load_keys, mock_detect_user, mock_deploy_env,
                                mock_run, mock_deploy_svc, mock_health):
        """When ExecStart differs from detected binary, service file should be regenerated."""
        mock_config.return_value = make_config()
        mock_ssh.return_value = SSHResult(success=True)
        mock_deploy_venv.return_value = SSHResult(success=True, stdout="DEPLOY_OK")
        # New binary in ember-venv, old binary was in conda
        mock_detect_entry.return_value = "/home/ian/.local/ember-venv/bin/clade-ember"
        mock_load_keys.return_value = {"oppy": "test-api-key"}
        mock_detect_user.return_value = "ian"
        mock_deploy_env.return_value = SSHResult(success=True, stdout="EMBER_ENV_OK")
        # grep ExecStart returns OLD conda path (triggers migration)
        mock_run.return_value = SSHResult(
            success=True,
            stdout="ExecStart=/home/ian/miniforge3/envs/clade/bin/clade-ember",
        )
        mock_deploy_svc.return_value = SSHResult(success=True, stdout="EMBER_DEPLOY_OK")
        mock_health.return_value = True

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "ember", "oppy"])
        assert result.exit_code == 0
        assert "Migrating service" in result.output
        assert "Service file updated" in result.output
        mock_deploy_svc.assert_called_once()


class TestDeployConductor:
    @patch("clade.cli.deploy_cmd.deploy_conductor")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_success(self, mock_config, mock_deploy):
        mock_config.return_value = make_config()
        mock_deploy.return_value = True

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "conductor"])
        assert result.exit_code == 0
        assert "deployed successfully" in result.output

    @patch("clade.cli.deploy_cmd.deploy_conductor")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_failure(self, mock_config, mock_deploy):
        mock_config.return_value = make_config()
        mock_deploy.return_value = False

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "conductor"])
        assert result.exit_code != 0
        assert "failed" in result.output


class TestDeployAll:
    @patch("clade.cli.deploy_cmd.check_ember_health_remote")
    @patch("clade.cli.deploy_cmd.deploy_clade_to_ember_venv")
    @patch("clade.cli.deploy_cmd.deploy_conductor")
    @patch("clade.cli.deploy_cmd.scp_build_directory")
    @patch("clade.cli.deploy_cmd.scp_directory")
    @patch("clade.cli.deploy_cmd.run_remote")
    @patch("clade.cli.deploy_cmd.test_ssh")
    @patch("clade.cli.deploy_cmd.httpx")
    @patch("clade.cli.deploy_cmd.subprocess.run")
    @patch("clade.cli.deploy_cmd.load_config_or_exit")
    def test_continues_on_failure(
        self, mock_config, mock_npm, mock_httpx, mock_ssh,
        mock_run, mock_scp, mock_scp_build, mock_conductor,
        mock_deploy_pkg, mock_health,
    ):
        mock_config.return_value = make_config()
        # SSH fails — hearth and frontend should fail but continue
        mock_ssh.return_value = SSHResult(success=False, message="Connection refused")
        # Conductor also fails
        mock_conductor.return_value = False

        runner = CliRunner()
        result = runner.invoke(cli, ["deploy", "all"])
        assert result.exit_code != 0
        # Should have attempted multiple components and shown summary
        assert "Deploy Summary" in result.output
