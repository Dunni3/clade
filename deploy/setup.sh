#!/usr/bin/env bash
# EC2 provisioning script for the Hearth server.
# Run on a fresh Ubuntu 24.04 LTS instance (t3.micro).
#
# Usage:
#   scp -r mailbox/ deploy/ ec2-user@<ip>:~/
#   ssh ec2-user@<ip> 'bash ~/deploy/setup.sh'
#
# After running, configure API keys:
#   export MAILBOX_API_KEYS="<key1>:doot,<key2>:oppy,<key3>:jerry"
#   Then restart the service: sudo systemctl restart mailbox

set -euo pipefail

echo "==> Updating system packages"
sudo apt-get update -y
sudo apt-get upgrade -y

echo "==> Installing Python 3 and pip"
sudo apt-get install -y python3 python3-pip python3-venv

echo "==> Creating mailbox directory"
sudo mkdir -p /opt/mailbox/mailbox
sudo cp -r ~/mailbox/* /opt/mailbox/mailbox/
sudo mv /opt/mailbox/mailbox/requirements.txt /opt/mailbox/requirements.txt

echo "==> Creating Python virtual environment"
cd /opt/mailbox
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt

echo "==> Creating data directory"
sudo mkdir -p /opt/mailbox/data

echo "==> Installing systemd service"
sudo cp ~/deploy/mailbox.service /etc/systemd/system/mailbox.service
sudo systemctl daemon-reload
sudo systemctl enable mailbox
sudo systemctl start mailbox

echo "==> Done! Check status with: sudo systemctl status mailbox"
echo "    View logs with: sudo journalctl -u mailbox -f"
echo ""
echo "IMPORTANT: Set API keys in /etc/systemd/system/mailbox.service"
echo "  Environment=\"MAILBOX_API_KEYS=<key1>:doot,<key2>:oppy,<key3>:jerry\""
echo "  Then: sudo systemctl daemon-reload && sudo systemctl restart mailbox"
