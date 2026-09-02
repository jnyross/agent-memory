#!/bin/sh
# skills/verify-agent-memory/drive.sh <run-dir> <host> <role> <command> [args...]
# role may be empty: drive.sh "$RUN" mini "" status
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
run=$1
host=$2
role=$3
shift 3
mkdir -p "$run/user" "$run/am"
export HOME="$run/user"
export AGENT_MEMORY_HOME="$run/am"
export AGENT_MEMORY_HOST="$host"
if [ -n "$role" ]; then
  export AGENT_MEMORY_ROLE="$role"
else
  unset AGENT_MEMORY_ROLE || true
fi
exec /usr/bin/python3 "$root/agent_memory.py" "$@"
