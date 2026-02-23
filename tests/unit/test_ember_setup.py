"""Tests for Ember setup detection helpers and service template."""

from unittest.mock import MagicMock, patch

from clade.cli.ember_setup import (
    SERVICE_NAME,
    SERVICE_TEMPLATE,
    detect_clade_dir,
    detect_clade_ember_path,
    detect_remote_user,
    detect_systemctl_path,
    detect_tailscale_ip,
    generate_manual_instructions,
    generate_sudoers_command,
    generate_sudoers_rule,
    install_sudoers_remote,
    setup_ember,
    verify_sudoers_remote,
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


class TestDetectSystemctlPath:
    @patch("clade.cli.ember_setup.run_remote")
    def test_success(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="/bin/systemctl\n")
        assert detect_systemctl_path("ian@masuda") == "/bin/systemctl"

    @patch("clade.cli.ember_setup.run_remote")
    def test_usr_bin(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="/usr/bin/systemctl\n")
        assert detect_systemctl_path("ian@masuda") == "/usr/bin/systemctl"

    @patch("clade.cli.ember_setup.run_remote")
    def test_failure(self, mock_run):
        mock_run.return_value = SSHResult(success=False, message="error")
        assert detect_systemctl_path("ian@masuda") is None

    @patch("clade.cli.ember_setup.run_remote")
    def test_empty_output(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="")
        assert detect_systemctl_path("ian@masuda") is None


class TestGenerateSudoersRule:
    def test_basic(self):
        rule = generate_sudoers_rule("ian", "/bin/systemctl")
        assert rule == (
            "ian ALL=(ALL) NOPASSWD: "
            "/bin/systemctl restart clade-ember, "
            "/bin/systemctl status clade-ember"
        )

    def test_custom_service_name(self):
        rule = generate_sudoers_rule("bob", "/usr/bin/systemctl", service_name="custom-ember")
        assert "custom-ember" in rule
        assert "bob" in rule
        assert "/usr/bin/systemctl" in rule


class TestGenerateSudoersCommand:
    def test_basic(self):
        cmd = generate_sudoers_command("ian@masuda", "ian", "/bin/systemctl")
        assert "ssh -t ian@masuda" in cmd
        assert "sudo tee /etc/sudoers.d/clade-ember" in cmd
        assert "chmod 440" in cmd
        assert "ian ALL=(ALL) NOPASSWD" in cmd


class TestInstallSudoersRemote:
    @patch("clade.cli.ember_setup.run_remote")
    def test_success(self, mock_run):
        mock_run.return_value = SSHResult(success=True, stdout="SUDOERS_OK")
        result = install_sudoers_remote("ian@masuda", "ian", "/bin/systemctl")
        assert result.success
        assert "SUDOERS_OK" in result.stdout
        # Verify the script contains the sudoers rule
        call_args = mock_run.call_args
        script = call_args[0][1]
        assert "ian ALL=(ALL) NOPASSWD" in script
        assert "/etc/sudoers.d/clade-ember" in script

    @patch("clade.cli.ember_setup.run_remote")
    def test_failure(self, mock_run):
        mock_run.return_value = SSHResult(success=False, message="sudo: a password is required")
        result = install_sudoers_remote("ian@masuda", "ian", "/bin/systemctl")
        assert not result.success


class TestVerifySudoersRemote:
    @patch("clade.cli.ember_setup.run_remote")
    def test_success_running(self, mock_run):
        """Verify passes when service is running (exit 0)."""
        mock_run.return_value = SSHResult(success=True, stdout="active\nEXIT_0")
        assert verify_sudoers_remote("ian@masuda", "/bin/systemctl") is True

    @patch("clade.cli.ember_setup.run_remote")
    def test_success_stopped(self, mock_run):
        """Verify passes when service is stopped (exit 3) — sudo still worked."""
        mock_run.return_value = SSHResult(success=True, stdout="inactive\nEXIT_3")
        assert verify_sudoers_remote("ian@masuda", "/bin/systemctl") is True

    @patch("clade.cli.ember_setup.run_remote")
    def test_failure_password_required(self, mock_run):
        """Verify fails when sudo requires password (exit 1)."""
        mock_run.return_value = SSHResult(success=True, stdout="EXIT_1")
        assert verify_sudoers_remote("ian@masuda", "/bin/systemctl") is False

    @patch("clade.cli.ember_setup.run_remote")
    def test_failure_ssh_error(self, mock_run):
        mock_run.return_value = SSHResult(success=False, message="Connection refused")
        assert verify_sudoers_remote("ian@masuda", "/bin/systemctl") is False


def _make_deploy_ok():
    return SSHResult(success=True, stdout="EMBER_DEPLOY_OK", stderr="", message="ok")


def _detection_patches():
    """Context manager stack for all detection function patches."""
    return (
        patch("clade.cli.ember_setup.detect_remote_user", return_value="testuser"),
        patch("clade.cli.ember_setup.detect_clade_ember_path", return_value="/usr/bin/clade-ember"),
        patch("clade.cli.ember_setup.detect_clade_dir", return_value="/opt/clade"),
        patch("clade.cli.ember_setup.detect_tailscale_ip", return_value="100.1.2.3"),
        patch("clade.cli.ember_setup.deploy_systemd_service", return_value=_make_deploy_ok()),
        patch("clade.cli.ember_setup.check_ember_health_remote", return_value=True),
    )


class TestSetupEmberRegistration:
    def test_registration_called_after_health_check(self):
        """After successful deployment and health check, register_ember_sync is called."""
        patches = _detection_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            mock_client_instance = MagicMock()
            mock_client_instance.register_ember_sync.return_value = True
            mock_client_cls = MagicMock(return_value=mock_client_instance)

            with patch("clade.communication.mailbox_client.MailboxClient", mock_client_cls):
                ember_host, port = setup_ember(
                    ssh_host="masuda",
                    name="oppy",
                    api_key="oppy-key",
                    port=8100,
                    working_dir="/home/testuser/projects",
                    server_url="https://hearth.example.com",
                    hearth_api_key="doot-key",
                )

            assert ember_host == "100.1.2.3"
            assert port == 8100
            mock_client_cls.assert_called_once_with(
                "https://hearth.example.com", "doot-key", verify_ssl=True
            )
            mock_client_instance.register_ember_sync.assert_called_once_with(
                "oppy", "http://100.1.2.3:8100"
            )

    def test_registration_failure_is_graceful(self):
        """If register_ember_sync raises, setup_ember should still return successfully."""
        patches = _detection_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            mock_client_instance = MagicMock()
            mock_client_instance.register_ember_sync.side_effect = Exception("Network error")
            mock_client_cls = MagicMock(return_value=mock_client_instance)

            with patch("clade.communication.mailbox_client.MailboxClient", mock_client_cls):
                ember_host, port = setup_ember(
                    ssh_host="masuda",
                    name="oppy",
                    api_key="oppy-key",
                    port=8100,
                    working_dir="/home/testuser/projects",
                    server_url="https://hearth.example.com",
                    hearth_api_key="doot-key",
                )

            # Should still succeed despite registration failure
            assert ember_host == "100.1.2.3"
            assert port == 8100

    def test_no_server_url_skips_registration(self):
        """If server_url is None, no registration attempt should be made."""
        patches = _detection_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            mock_client_cls = MagicMock()

            with patch("clade.communication.mailbox_client.MailboxClient", mock_client_cls):
                ember_host, port = setup_ember(
                    ssh_host="masuda",
                    name="oppy",
                    api_key="oppy-key",
                    port=8100,
                    working_dir="/home/testuser/projects",
                    server_url=None,
                    hearth_api_key="doot-key",
                )

            assert ember_host == "100.1.2.3"
            assert port == 8100
            mock_client_cls.assert_not_called()

    def test_no_hearth_key_skips_registration(self):
        """If hearth_api_key is None, no registration attempt should be made."""
        patches = _detection_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            mock_client_cls = MagicMock()

            with patch("clade.communication.mailbox_client.MailboxClient", mock_client_cls):
                ember_host, port = setup_ember(
                    ssh_host="masuda",
                    name="oppy",
                    api_key="oppy-key",
                    port=8100,
                    working_dir="/home/testuser/projects",
                    server_url="https://hearth.example.com",
                    hearth_api_key=None,
                )

            assert ember_host == "100.1.2.3"
            assert port == 8100
            mock_client_cls.assert_not_called()
