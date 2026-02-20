#!/bin/bash
# Export env vars to testuser's profile so SSH login shells can access them.
# Docker compose env vars are only available to the entrypoint process; SSH sessions
# start fresh login shells that don't inherit them. This writes key vars to .bashrc
# so both SSH-based tasks and Ember-based tasks have access.
{
    [ -n "$ANTHROPIC_API_KEY" ] && echo "export ANTHROPIC_API_KEY='$ANTHROPIC_API_KEY'"
    [ -n "$HEARTH_URL" ]        && echo "export HEARTH_URL='$HEARTH_URL'"
    [ -n "$HEARTH_API_KEY" ]    && echo "export HEARTH_API_KEY='$HEARTH_API_KEY'"
    [ -n "$HEARTH_NAME" ]       && echo "export HEARTH_NAME='$HEARTH_NAME'"
} >> /home/testuser/.bashrc

# Start SSH server in background (runs as root)
/usr/sbin/sshd

# Start Ember server as testuser (runuser preserves env vars from docker-compose)
exec runuser -u testuser -- clade-ember
