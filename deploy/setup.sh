#!/usr/bin/env bash
# EC2 provisioning script for the Hearth server.
# Run on a fresh Ubuntu 24.04 LTS instance (t3.micro).
#
# Usage:
#   scp -r hearth/ deploy/ ec2-user@<ip>:~/
#   ssh ec2-user@<ip> 'bash ~/deploy/setup.sh'
#
# After running, configure API keys:
#   export HEARTH_API_KEYS="<key1>:doot,<key2>:oppy,<key3>:jerry"
#   Then restart the service: sudo systemctl restart hearth

set -euo pipefail

echo "==> Updating system packages"
sudo apt-get update -y
sudo apt-get upgrade -y

echo "==> Installing Python 3, pip, and nginx"
sudo apt-get install -y python3 python3-pip python3-venv nginx

echo "==> Creating hearth directory"
sudo mkdir -p /opt/hearth/hearth
sudo cp -r ~/hearth/* /opt/hearth/hearth/
sudo mv /opt/hearth/hearth/requirements.txt /opt/hearth/requirements.txt

echo "==> Creating Python virtual environment"
cd /opt/hearth
sudo python3 -m venv venv
sudo venv/bin/pip install -r requirements.txt

echo "==> Creating data directory"
sudo mkdir -p /opt/hearth/data

echo "==> Installing systemd service"
sudo cp ~/deploy/hearth.service /etc/systemd/system/hearth.service
sudo systemctl daemon-reload
sudo systemctl enable hearth
sudo systemctl start hearth

echo "==> Setting up self-signed SSL certificate"
sudo mkdir -p /etc/nginx/ssl
if [ ! -f /etc/nginx/ssl/hearth.crt ]; then
    sudo openssl req -x509 -nodes -days 3650 \
        -newkey rsa:2048 \
        -keyout /etc/nginx/ssl/hearth.key \
        -out /etc/nginx/ssl/hearth.crt \
        -subj "/CN=hearth"
fi

echo "==> Configuring nginx"
sudo tee /etc/nginx/sites-available/hearth > /dev/null << 'NGINX'
server {
    listen 80;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;

    ssl_certificate /etc/nginx/ssl/hearth.crt;
    ssl_certificate_key /etc/nginx/ssl/hearth.key;

    root /var/www/hearth;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
NGINX
sudo ln -sf /etc/nginx/sites-available/hearth /etc/nginx/sites-enabled/hearth
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo "==> Setting up web UI directory"
sudo mkdir -p /var/www/hearth
sudo chown -R www-data:www-data /var/www/hearth

echo "==> Done! Check status with: sudo systemctl status hearth"
echo "    View logs with: sudo journalctl -u hearth -f"
echo ""
echo "IMPORTANT: Set API keys in /etc/systemd/system/hearth.service"
echo "  Environment=\"HEARTH_API_KEYS=<key1>:doot,<key2>:oppy,<key3>:jerry\""
echo "  Then: sudo systemctl daemon-reload && sudo systemctl restart hearth"
echo ""
echo "To deploy the web UI, SCP the frontend build to /var/www/hearth/"
