#!/bin/sh
# Copies the agent-facing material from the private server repository into
# this public one. The server repo stays the source of truth; edit there,
# then run this and commit here. The server's docs/ has the same layout as
# this repository, so the copy is one rsync and relative links resolve the
# same way in both.
set -e
SRC=${1:-$(dirname "$0")/../aiboard}
cd "$(dirname "$0")"
# The skills' copies of the playbook and the turn pages, then the links.
python3 "$SRC/docs/skill-copies.py"
python3 "$SRC/docs/check-links.py"
rsync -a --delete "$SRC/docs/" ./ \
  --exclude /sync-from-server.sh --exclude /LICENSE --exclude .gitignore --exclude .git --exclude .env \
  --exclude node_modules --exclude '*.tgz' --exclude __pycache__ --exclude '*.egg-info'
python3 check-links.py
echo "synced from $SRC"
