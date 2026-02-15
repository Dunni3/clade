"""Tests for Ember setup detection helpers and service template."""

from unittest.mock import patch

from clade.cli.ember_setup import (
    SERVICE_NAME,
    SERVICE_TEMPLATE,
    detect_clade_dir,
    detect_clade_ember_path,
    detect_remote_user,
    detect_tailscale_ip,
    generate_manual_instructions,
)
from clade.cli.ssh_utils import SSHResult


class TestDetectRemoteUser:
    @patch("clade.cli.ember_setup.run_remote")
    def test_success(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="ian\n")
        assert detect_remote_user("ian@masuda") == "ian"

    @patch("clade.cli.ember_setup.run_remote")
    def test_failure(self, mock_run):
        mock_run.return_value = SSHResult(success=False, message="timeout")
        assert detect_remote_user("ian@masuda") is None


class TestDetectCladeEmberPath:
    @patch("clade.cli.ember_setup.run_remote")
    def test_success(self, mock_run):
        mock_run.return_value = SSHResult(
            success=True, stdout="/home/ian/opt/miniconda3/envs/clade/bin/clade-ember\n"
        )
        assert detect_clade_ember_path("ian@masuda") == "/home/ian/opt/miniconda3/envs/clade/bin/clade-ember"

    @patch("clade.cli.ember_setup.run_remote")
    def test_not_found(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="")
        assert detect_clade_ember_path("ian@masuda") is None

    @patch("clade.cli.ember_setup.run_remote")
    def test_failure(self, mock_run):
        mock_run.return_value = SSHResult(success=False, message="error")
        assert detect_clade_ember_path("ian@masuda") is None


class TestDetectCladeDir:
    @patch("clade.cli.ember_setup.run_remote")
    def test_success(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="/home/ian/.local/share/clade\n")
        assert detect_clade_dir("ian@masuda") == "/home/ian/.local/share/clade"

    @patch("clade.cli.ember_setup.run_remote")
    def test_not_absolute(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="relative/path\n")
        assert detect_clade_dir("ian@masuda") is None

    @patch("clade.cli.ember_setup.run_remote")
    def test_failure(self, mock_run):
        mock_run.return_value = SSHResult(success=False, message="error")
        assert detect_clade_dir("ian@masuda") is None


class TestDetectTailscaleIp:
    @patch("clade.cli.ember_setup.run_remote")
    def test_success(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="100.71.57.52\n")
        assert detect_tailscale_ip("ian@masuda") == "100.71.57.52"

    @patch("clade.cli.ember_setup.run_remote")
    def test_not_available(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="")
        assert detect_tailscale_ip("ian@masuda") is None

    @patch("clade.cli.ember_setup.run_remote")
    def test_non_tailscale_ip(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="192.168.1.50\n")
        assert detect_tailscale_ip("ian@masuda") is None


class TestServiceTemplate:
    def test_template_formatting(self):
        result = SERVICE_TEMPLATE.format(
            brother_name="oppy",
            remote_user="ian",
            clade_ember_path="/usr/local/bin/clade-ember",
            clade_dir="/home/ian/clade",
            port=8100,
            working_dir="/home/ian/projects",
            hearth_url="https://example.com",
            api_key="test-key-123",
        )
        assert "Description=Clade Ember Server (oppy)" in result
        assert "User=ian" in result
        assert "WorkingDirectory=/home/ian/clade" in result
        assert "ExecStart=/usr/local/bin/clade-ember" in result
        assert 'EMBER_PORT=8100' in result
        assert 'EMBER_BROTHER_NAME=oppy' in result
        assert 'EMBER_WORKING_DIR=/home/ian/projects' in result
        assert 'HEARTH_URL=https://example.com' in result
        assert 'HEARTH_API_KEY=test-key-123' in result
        assert 'HEARTH_NAME=oppy' in result
        assert "WantedBy=multi-user.target" in result


class TestGenerateManualInstructions:
    def test_includes_service_content(self):
        result = generate_manual_instructions(
            brother_name="oppy",
            remote_user="ian",
            clade_ember_path="/usr/local/bin/clade-ember",
            clade_dir="/home/ian/clade",
            port=8100,
            working_dir="/home/ian/projects",
            hearth_url="https://example.com",
            api_key="test-key",
        )
        assert SERVICE_NAME in result
        assert "sudo systemctl daemon-reload" in result
        assert "sudo systemctl enable" in result
        assert "sudo systemctl restart" in result
        assert "curl http://localhost:8100/health" in result
        assert "ExecStart=/usr/local/bin/clade-ember" in result

    def test_includes_correct_port(self):
        result = generate_manual_instructions(
            brother_name="jerry",
            remote_user="ian",
            clade_ember_path="/usr/bin/clade-ember",
            clade_dir="/home/ian/clade",
            port=9200,
            working_dir="/tmp",
            hearth_url="https://example.com",
            api_key="key",
        )
        assert "9200" in result
