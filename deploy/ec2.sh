#!/usr/bin/env bash
# Manage the Hearth EC2 instance (stop/start/status/ssh)
set -euo pipefail

INSTANCE_ID="REPLACE_AFTER_PROVISIONING"
REGION="us-east-1"
SSH_KEY="$HOME/.ssh/moltbot-key.pem"
ELASTIC_IP="REPLACE_AFTER_PROVISIONING"

usage() {
    echo "Usage: $0 {start|stop|status|ssh}"
    echo ""
    echo "Commands:"
    echo "  start   - Start the EC2 instance"
    echo "  stop    - Stop the EC2 instance (saves money when not in use)"
    echo "  status  - Show instance state"
    echo "  ssh     - SSH into the instance"
    exit 1
}

case "${1:-}" in
    start)
        echo "Starting instance $INSTANCE_ID..."
        aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION" --output text
        echo "Waiting for instance to be running..."
        aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"
        echo "Instance is running at $ELASTIC_IP"
        echo "Waiting for SSH to be available..."
        for i in $(seq 1 30); do
            if ssh -i "$SSH_KEY" -o ConnectTimeout=2 -o StrictHostKeyChecking=no ubuntu@"$ELASTIC_IP" "echo 'SSH ready'" 2>/dev/null; then
                break
            fi
            sleep 2
        done
        echo "Hearth server should be available at https://$ELASTIC_IP"
        ;;
    stop)
        echo "Stopping instance $INSTANCE_ID..."
        aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" --output text
        echo "Instance is stopping. Hearth will be unavailable until you run '$0 start'."
        ;;
    status)
        STATE=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" --region "$REGION" \
            --query "Reservations[0].Instances[0].State.Name" --output text)
        echo "Instance $INSTANCE_ID: $STATE"
        echo "Elastic IP: $ELASTIC_IP"
        if [ "$STATE" = "running" ]; then
            echo "Hearth: https://$ELASTIC_IP"
        fi
        ;;
    ssh)
        exec ssh -i "$SSH_KEY" ubuntu@"$ELASTIC_IP"
        ;;
    *)
        usage
        ;;
esac
