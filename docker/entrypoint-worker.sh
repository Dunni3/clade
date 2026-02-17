#!/bin/bash
# Start SSH server in background (runs as root)
/usr/sbin/sshd

# Start Ember server as testuser (runuser preserves env vars from docker-compose)
exec runuser -u testuser -- clade-ember
