"""Tests for the bootstrap CLI command."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from clade.cli.main import cli
from clade.cli.ssh_utils import SSHResult


class TestBootstrapHelp:
    def test_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "--help"])
        assert result.exit_code == 0
        assert "Bootstrap a remote machine" in result.output
        assert "SSH_HOST" in result.output


class TestBootstrapSSHFailure:
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_ssh_failure_exits(self, mock_ssh):
        mock_ssh.return_value = SSHResult(success=False, message="Connection refused")

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "ian@badhost"])
        assert result.exit_code != 0
        assert "SSH failed" in result.output


class TestBootstrapCondaDetection:
    @patch("clade.cli.deploy_utils.deploy_clade_package")
    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_conda_found_env_exists(self, mock_ssh, mock_run_remote, mock_deploy):
        mock_ssh.return_value = SSHResult(success=True)

        env_output = (
            "CONDA_FOUND:/home/ian/miniforge3/bin/mamba\n"
            "ENV_EXISTS\n"
            "PIP_FOUND:/home/ian/miniforge3/envs/clade/bin/pip\n"
        )
        deploy_output = "Using pip: /home/ian/miniforge3/envs/clade/bin/pip\nDEPLOY_OK\n"
        verify_output = (
            "CLADE_WORKER:/home/ian/miniforge3/envs/clade/bin/clade-worker\n"
            "CLADE_EMBER:/home/ian/miniforge3/envs/clade/bin/clade-ember\n"
            "CLAUDE:yes\n"
            "TMUX:yes\n"
            "GIT:yes\n"
            "VERIFY_OK\n"
        )

        mock_run_remote.side_effect = [
            SSHResult(success=True, stdout=env_output),
            SSHResult(success=True, stdout=verify_output),
        ]
        mock_deploy.return_value = SSHResult(success=True, stdout=deploy_output)

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "ian@masuda"])
        assert result.exit_code == 0
        assert "Bootstrap complete" in result.output
        assert "clade add-brother" in result.output

    @patch("clade.cli.deploy_utils.deploy_clade_package")
    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_conda_missing_installs_miniforge(self, mock_ssh, mock_run_remote, mock_deploy):
        mock_ssh.return_value = SSHResult(success=True)

        env_output = "CONDA_MISSING\n"
        install_output = "Installing miniforge3...\nPIP_FOUND:/home/ian/miniforge3/envs/clade/bin/pip\n"
        verify_output = (
            "CLADE_WORKER:/home/ian/miniforge3/envs/clade/bin/clade-worker\n"
            "CLAUDE:yes\nTMUX:yes\nGIT:yes\nVERIFY_OK\n"
        )

        mock_run_remote.side_effect = [
            SSHResult(success=True, stdout=env_output),
            SSHResult(success=True, stdout=install_output),
            SSHResult(success=True, stdout=verify_output),
        ]
        mock_deploy.return_value = SSHResult(success=True, stdout="DEPLOY_OK\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "ian@masuda"])
        assert result.exit_code == 0
        assert "No conda/mamba found" in result.output
        assert "Bootstrap complete" in result.output

    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_conda_missing_no_install(self, mock_ssh, mock_run_remote):
        mock_ssh.return_value = SSHResult(success=True)

        mock_run_remote.return_value = SSHResult(success=True, stdout="CONDA_MISSING\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "--no-install-conda", "ian@masuda"])
        assert result.exit_code != 0
        assert "No conda/mamba found" in result.output


class TestBootstrapDeployFailure:
    @patch("clade.cli.deploy_utils.deploy_clade_package")
    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_deploy_failure_exits(self, mock_ssh, mock_run_remote, mock_deploy):
        mock_ssh.return_value = SSHResult(success=True)

        env_output = (
            "CONDA_FOUND:/home/ian/miniforge3/bin/mamba\n"
            "ENV_EXISTS\n"
            "PIP_FOUND:/home/ian/miniforge3/envs/clade/bin/pip\n"
        )
        mock_run_remote.return_value = SSHResult(success=True, stdout=env_output)
        mock_deploy.return_value = SSHResult(
            success=False, stdout="", stderr="", message="Connection lost"
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "ian@masuda"])
        assert result.exit_code != 0
        assert "Deploy failed" in result.output


class TestBootstrapVerifyWarnings:
    @patch("clade.cli.deploy_utils.deploy_clade_package")
    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_missing_tools_shows_warnings(self, mock_ssh, mock_run_remote, mock_deploy):
        mock_ssh.return_value = SSHResult(success=True)

        env_output = (
            "CONDA_FOUND:/home/ian/miniforge3/bin/mamba\n"
            "ENV_EXISTS\n"
            "PIP_FOUND:/home/ian/miniforge3/envs/clade/bin/pip\n"
        )
        verify_output = (
            "CLADE_WORKER:/home/ian/miniforge3/envs/clade/bin/clade-worker\n"
            "CLAUDE:no\n"
            "TMUX:no\n"
            "GIT:yes\n"
            "VERIFY_OK\n"
        )
        mock_run_remote.side_effect = [
            SSHResult(success=True, stdout=env_output),
            SSHResult(success=True, stdout=verify_output),
        ]
        mock_deploy.return_value = SSHResult(success=True, stdout="DEPLOY_OK\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "ian@masuda"])
        assert result.exit_code == 0
        assert "claude" in result.output.lower()
        assert "tmux" in result.output.lower()
        assert "NOT FOUND" in result.output


class TestBootstrapEmberOnly:
    @patch("clade.cli.deploy_utils.deploy_clade_to_ember_venv")
    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_ember_only_success(self, mock_ssh, mock_run_remote, mock_deploy_venv):
        mock_ssh.return_value = SSHResult(success=True)

        venv_output = "CREATING_VENV:python3.11\nVENV_CREATED\nPIP:~/.local/ember-venv/bin/pip\n"
        verify_output = (
            "CLADE_EMBER:/home/ian/.local/ember-venv/bin/clade-ember\n"
            "CLAUDE:yes\nTMUX:yes\nGIT:yes\nVERIFY_OK\n"
        )

        mock_run_remote.side_effect = [
            SSHResult(success=True, stdout=venv_output),
            SSHResult(success=True, stdout=verify_output),
        ]
        mock_deploy_venv.return_value = SSHResult(success=True, stdout="DEPLOY_OK\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "--ember-only", "ian@masuda"])
        assert result.exit_code == 0
        assert "Bootstrap complete" in result.output
        assert "ember venv" in result.output.lower()
        mock_deploy_venv.assert_called_once()

    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_ember_only_no_python(self, mock_ssh, mock_run_remote):
        mock_ssh.return_value = SSHResult(success=True)

        mock_run_remote.return_value = SSHResult(success=True, stdout="NO_PYTHON\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "--ember-only", "ian@masuda"])
        assert result.exit_code != 0

    @patch("clade.cli.deploy_utils.deploy_clade_to_ember_venv")
    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_ember_only_existing_venv(self, mock_ssh, mock_run_remote, mock_deploy_venv):
        mock_ssh.return_value = SSHResult(success=True)

        venv_output = "VENV_EXISTS\nPIP:~/.local/ember-venv/bin/pip\n"
        verify_output = (
            "CLADE_EMBER:/home/ian/.local/ember-venv/bin/clade-ember\n"
            "CLAUDE:yes\nTMUX:yes\nGIT:yes\nVERIFY_OK\n"
        )

        mock_run_remote.side_effect = [
            SSHResult(success=True, stdout=venv_output),
            SSHResult(success=True, stdout=verify_output),
        ]
        mock_deploy_venv.return_value = SSHResult(success=True, stdout="DEPLOY_OK\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "--ember-only", "ian@masuda"])
        assert result.exit_code == 0
        assert "already exists" in result.output


class TestBootstrapPipPathPassthrough:
    @patch("clade.cli.deploy_utils.deploy_clade_package")
    @patch("clade.cli.bootstrap_cmd.run_remote")
    @patch("clade.cli.bootstrap_cmd.test_ssh")
    def test_pip_path_passed_to_deploy(self, mock_ssh, mock_run_remote, mock_deploy):
        mock_ssh.return_value = SSHResult(success=True)

        env_output = (
            "CONDA_FOUND:/home/ian/miniforge3/bin/mamba\n"
            "ENV_EXISTS\n"
            "PIP_FOUND:/home/ian/miniforge3/envs/clade/bin/pip\n"
        )
        verify_output = "CLAUDE:yes\nTMUX:yes\nGIT:yes\nVERIFY_OK\n"
        mock_run_remote.side_effect = [
            SSHResult(success=True, stdout=env_output),
            SSHResult(success=True, stdout=verify_output),
        ]
        mock_deploy.return_value = SSHResult(success=True, stdout="DEPLOY_OK\n")

        runner = CliRunner()
        result = runner.invoke(cli, ["bootstrap", "ian@masuda"])
        assert result.exit_code == 0

        # Verify pip_path was passed to deploy_clade_package
        mock_deploy.assert_called_once()
        call_kwargs = mock_deploy.call_args
        assert call_kwargs.kwargs.get("pip_path") == "/home/ian/miniforge3/envs/clade/bin/pip"
