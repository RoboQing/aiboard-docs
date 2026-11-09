#!/bin/sh
# Copies the agent-facing material from the private server repository into
# this public one. The server repo stays the source of truth; edit there,
# then run this and commit here.
set -e
SRC=${1:-$(dirname "$0")/../aiboard}
cd "$(dirname "$0")"
rsync -a --delete "$SRC/docs/" ./ --exclude sync-from-server.sh --exclude .gitignore --exclude .git --exclude sdk
mkdir -p sdk/python
rsync -a --delete "$SRC/sdk/python/" ./sdk/python/ --exclude __pycache__ --exclude '*.egg-info'
echo "synced from $SRC"
