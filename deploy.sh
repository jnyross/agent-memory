#!/bin/sh
set -u
cd "$(dirname "$0")"
. ./lib.sh
code_only=
if [ "${1:-}" = --code-only ]; then
  code_only=--code-only
  shift
  case "${AGENT_MEMORY_EXPECTED_SHA256:-}" in
    ''|*[!0-9a-f]*) echo 'code-only deployment requires the approved AGENT_MEMORY_EXPECTED_SHA256' >&2; exit 2 ;;
  esac
  [ "${#AGENT_MEMORY_EXPECTED_SHA256}" -eq 64 ] || exit 2
fi
[ -z "$(git status --porcelain)" ] || { echo "working tree dirty" >&2; exit 1; }
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "HEAD is not origin/main; push first" >&2; exit 1; }
hub=$(fleet_hub)
if [ $# -gt 0 ]; then
  for a in "$@"; do
    fleet_role "$a" >/dev/null || { echo "unknown host $a: add \"$a leaf\" to fleet" >&2; exit 1; }
  done
else
  rest=
  local_host_name=
  for h in $(fleet_hosts); do
    [ "$h" = "$hub" ] && continue
    if is_local "$h"; then local_host_name=$h; else rest="$rest $h"; fi
  done
  if [ -n "$local_host_name" ]; then
    set -- "$hub" $rest "$local_host_name"
  else
    set -- "$hub" $rest
  fi
fi
failed=
for h in "$@"; do
  role=$(fleet_role "$h")
  [ "$role" = hub ] || role=
  if [ -n "$code_only" ]; then
    if is_local "$h"; then
      if sh install.sh --code-only; then echo "deployed code only: $h"; else failed="$failed $h"; fi
    else
      stage=$(ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$h" 'umask 077; mktemp -d /tmp/agent-memory-code.XXXXXXXX') || { failed="$failed $h"; continue; }
      case "$stage" in *[!a-zA-Z0-9/._-]*) echo "invalid staging path: $h" >&2; failed="$failed $h"; continue ;; esac
      case "$stage" in /tmp/agent-memory-code.*) ;; *) echo "invalid staging path: $h" >&2; failed="$failed $h"; continue ;; esac
      if scp -q agent_memory.py install.sh "$h:$stage/" && ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$h" "AGENT_MEMORY_EXPECTED_SHA256='$AGENT_MEMORY_EXPECTED_SHA256' sh '$stage/install.sh' --code-only"; then
        echo "deployed code only: $h"
      else
        echo "FAIL $h" >&2; failed="$failed $h"
      fi
      ssh -o BatchMode=yes -o StrictHostKeyChecking=yes "$h" "rm -f '$stage/agent_memory.py' '$stage/install.sh'; rmdir '$stage'" || true
    fi
    continue
  fi
  if is_local "$h"; then
    if [ "$role" = hub ]; then
      if AGENT_MEMORY_HOST=$h AGENT_MEMORY_ROLE=hub sh install.sh; then
        echo "deployed $h"
      else
        echo "FAIL $h" >&2
        failed="$failed $h"
      fi
    else
      if AGENT_MEMORY_HOST=$h sh install.sh; then
        echo "deployed $h"
      else
        echo "FAIL $h" >&2
        failed="$failed $h"
      fi
    fi
  else
    if scp -q agent_memory.py install.sh "$h:/tmp/" && ssh "$h" "AGENT_MEMORY_HOST=$h AGENT_MEMORY_ROLE=$role sh /tmp/install.sh"; then
      echo "deployed $h"
    else
      echo "FAIL $h" >&2
      failed="$failed $h"
    fi
  fi
done
[ -z "$failed" ] || { echo "not deployed:$failed" >&2; exit 1; }
