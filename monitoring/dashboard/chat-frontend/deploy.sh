#!/bin/bash
# Deploy chat-frontend to static directory
# Usage: ./deploy.sh

set -e

cd "$(dirname "$0")"

echo "Building chat-frontend..."
npm run build

echo "Deploying to ../static/chat/..."
rm -rf ../static/chat/*
cp -r build/* ../static/chat/

echo "✓ Deployment complete. Restart monitoring_server.py to see changes."
echo "  Access at: http://localhost:3000"
