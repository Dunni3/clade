#!/bin/bash
set -e

cd "$(dirname "$0")/.."

# Generate SSH test keys if missing
if [ ! -f test-keys/id_ed25519 ]; then
    echo "Generating SSH test keys..."
    mkdir -p test-keys
    ssh-keygen -t ed25519 -f test-keys/id_ed25519 -N "" -q
fi

# Build and start
docker compose -f docker/docker-compose.test.yml up --build -d

echo ""
echo "Containers are up. Attaching to personal brother..."
echo ""
echo "Quick start:"
echo "  clade init --name 'Test Clade' --personal-name darwin --server-url http://hearth:8000 --server-key testkey-personal --no-mcp -y"
echo ""
echo "Other services:"
echo "  docker compose -f docker/docker-compose.test.yml exec worker bash     # worker + Ember"
echo "  docker compose -f docker/docker-compose.test.yml exec hearth bash     # Hearth + Conductor"
echo "  curl http://worker:8100/health          # Ember health (from inside any container)"
echo "  curl http://hearth:8000/api/v1/health   # Hearth health (from inside any container)"
echo ""

# Attach to personal brother
docker compose -f docker/docker-compose.test.yml exec personal bash
