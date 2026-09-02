#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ -z "$(git status --porcelain)" ] || { echo "working tree dirty" >&2; exit 1; }
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "HEAD is not origin/main; push first" >&2; exit 1; }
for h in agent-box mini mbp; do
  role=; [ "$h" = agent-box ] && role=hub
  scp -q agent_memory.py install.sh "$h:/tmp/"
  ssh "$h" "AGENT_MEMORY_HOST=$h AGENT_MEMORY_ROLE=$role sh /tmp/install.sh"
done
AGENT_MEMORY_HOST=johns-macbook-air sh install.sh
