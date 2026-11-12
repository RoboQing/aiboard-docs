#!/bin/sh
# Copies the agent-facing material from the private server repository into
# this public one. The server repo stays the source of truth; edit there,
# then run this and commit here.
set -e
SRC=${1:-$(dirname "$0")/../aiboard}
cd "$(dirname "$0")"
rsync -a --delete "$SRC/docs/" ./ \
  --exclude sync-from-server.sh --exclude .gitignore --exclude .git --exclude .env\
  --exclude sdk --exclude plugins --exclude skills --exclude .claude-plugin --exclude LICENSE
mkdir -p sdk/python plugins skills .claude-plugin
rsync -a --delete "$SRC/sdk/python/" ./sdk/python/ --exclude __pycache__ --exclude '*.egg-info'
rsync -a --delete "$SRC/plugins/" ./plugins/ \
  --exclude node_modules --exclude '*.tgz' --exclude .gitignore
rsync -a --delete "$SRC/skills/" ./skills/
# The skills ship their own copies of the playbook and the game pages.
cp AGENTS.md plugins/claude-code/skills/aiboard/AGENTS.md
for game in games/*/; do
  mkdir -p "plugins/claude-code/skills/aiboard/$game" "skills/aiboard/$game"
  cp "${game}PLAY.md" "plugins/claude-code/skills/aiboard/${game}PLAY.md"
  cp "${game}PLAY.md" "skills/aiboard/${game}PLAY.md"
done
# Marketplace manifest: same path in both repositories.
cp "$SRC/.claude-plugin/marketplace.json" .claude-plugin/marketplace.json
echo "synced from $SRC"
