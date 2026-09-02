#!/bin/sh
# sh verify.sh          full fleet check (needs ssh to agent-box, mini, mbp)
# sh verify.sh --local  tests, hub simulation, git state only
set -u
cd "$(dirname "$0")"

. ./lib.sh
HUB=$(fleet_hub)
SHARE='$HOME/.local/share/agent-memory'
BIN='$HOME/.local/bin/agent-memory'
FAN_OUT_DEADLINE=150
MAX_CYCLE_SECS=10


check_tests() {
  out=$(python3 -m unittest discover -s tests 2>&1)
  case "$out" in *"OK"*) pass "unit tests";; *) fail "unit tests" "$(printf '%s' "$out" | tail -3 | tr '\n' ' ')";; esac
}

check_sim() {
  home=$(mktemp -d)
  if ! AGENT_MEMORY_HOME="$home" AGENT_MEMORY_HOST=$HUB AGENT_MEMORY_ROLE=hub python3 agent_memory.py cycle; then
    fail "hub sim" "first cycle failed"; rm -rf "$home"; return
  fi
  lines=$(wc -l < "$home/memory.jsonl" | digits)
  keys=$(python3 -c "import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('select count(*) from keys').fetchone()[0])" "$home/memory.sqlite")
  dupes=$(jq -r .key "$home/memory.jsonl" | sort | uniq -d | wc -l | digits)
  AGENT_MEMORY_HOME="$home" AGENT_MEMORY_HOST=$HUB AGENT_MEMORY_ROLE=hub python3 agent_memory.py cycle
  after=$(wc -l < "$home/memory.jsonl" | digits)
  rm -rf "$home"
  [ "$lines" = "$keys" ] && pass "hub sim keys == lines ($lines)" || fail "hub sim keys == lines" "lines=$lines keys=$keys"
  [ "$dupes" = 0 ] && pass "hub sim no duplicate keys" || fail "hub sim duplicate keys" "$dupes"
  [ "$after" -ge "$lines" ] && pass "hub sim second cycle append-only ($lines -> $after)" || fail "hub sim second cycle" "$lines -> $after"
}

check_git() {
  dirty=$(git status --porcelain)
  [ -z "$dirty" ] && pass "working tree clean" || fail "working tree clean" "$(printf '%s' "$dirty" | tr '\n' ' ')"
  git fetch -q origin main
  head=$(git rev-parse HEAD); origin=$(git rev-parse origin/main)
  [ "$head" = "$origin" ] && pass "HEAD == origin/main" || fail "HEAD == origin/main" "$head != $origin"
  gh_sha=$(gh api repos/jnyross/agent-memory/commits/main --jq .sha 2>/dev/null)
  [ "$head" = "$gh_sha" ] && pass "GitHub main == HEAD" || fail "GitHub main == HEAD" "gh=$gh_sha"
}

check_deployed_code() {
  want=$(git show origin/main:agent_memory.py | md5sum | cut -c1-32)
  for h in $(fleet_hosts); do
    got=$(md5_of "$h" '$HOME/.local/lib/agent-memory/agent_memory.py')
    [ "$got" = "$want" ] && pass "$h runs origin/main agent_memory.py" || fail "$h agent_memory.py md5" "got $got want $want"
  done
}

check_wrappers() {
  for h in $(fleet_hosts); do
    n=$h
    w=$(on "$h" "cat $BIN")
    case "$w" in *"AGENT_MEMORY_HOST:=$n}"*) pass "$h wrapper host $n";; *) fail "$h wrapper host" "$w";; esac
    if [ "$h" = "$HUB" ]; then
      case "$w" in *"AGENT_MEMORY_ROLE:=hub}"*) pass "$h wrapper role hub";; *) fail "$h wrapper role" "$w";; esac
    else
      case "$w" in *AGENT_MEMORY_ROLE*) fail "$h wrapper has role" "$w";; *) pass "$h wrapper no role";; esac
    fi
    got=$(on "$h" "$BIN status | jq -r .host")
    [ "$got" = "$n" ] && pass "$h status.host == $n" || fail "$h status.host" "$got"
  done
}

check_hub_state() {
  st=$(on $HUB "$BIN status")
  lines=$(printf '%s' "$st" | jq -r .memory_lines)
  errs=$(printf '%s' "$st" | jq -r '.errors | length')
  [ "$errs" = 0 ] && pass "hub status.errors empty" || fail "hub status.errors" "$(printf '%s' "$st" | jq -c .errors)"
  keys=$(on $HUB "python3 -c \"import os,sqlite3;print(sqlite3.connect(os.path.expanduser('~/.local/share/agent-memory/memory.sqlite')).execute('select count(*) from keys').fetchone()[0])\"")
  [ "$keys" = "$lines" ] && pass "hub memory.sqlite keys == memory_lines ($lines)" || fail "hub keys == lines" "keys=$keys lines=$lines"
  got=$(on $HUB "jq -r .host $SHARE/memory.jsonl | sort -u")
  want=$(on $HUB "for f in $SHARE/out/*.jsonl $SHARE/in/*.jsonl; do [ -s \"\$f\" ] && basename \"\$f\" .jsonl; done | sort -u")
  [ "$got" = "$want" ] && pass "hub memory.jsonl hosts match transfers" || fail "hub memory.jsonl hosts" "jsonl=[$(printf '%s' "$got" | tr '\n' ' ')] files=[$(printf '%s' "$want" | tr '\n' ' ')]"
  dupes=$(on $HUB "jq -r .key $SHARE/memory.jsonl | sort | uniq -d | wc -l" | digits)
  [ "$dupes" = 0 ] && pass "hub memory.jsonl no duplicate keys" || fail "hub duplicate keys" "$dupes"
  stale=$(on $HUB "ls $SHARE/hosts.json $SHARE/in/$HUB.jsonl 2>/dev/null | wc -l" | digits)
  [ "$stale" = 0 ] && pass "hub has no hosts.json or in/$HUB.jsonl" || fail "hub stale files" "$stale present"
  for f in merge.sqlite memory.sqlite memory.jsonl; do
    on $HUB "test -s $SHARE/$f" && pass "hub $f present" || fail "hub $f" "missing or empty"
  done
}

check_hub_timing() {
  raw=$(on $HUB "journalctl --user -u agent-memory.service -o short-unix --since -10min --no-pager 2>/dev/null | grep -E 'Starting|Finished'")
  gaps=$(printf '%s\n' "$raw" | awk '/Starting/{s=$1} /Finished/&&s{printf "%.1f\n", $1-s; s=0}')
  [ -n "$gaps" ] || { fail "hub cycle timing" "no Starting/Finished pairs in last 10min"; return; }
  worst=$(printf '%s\n' "$gaps" | sort -n | tail -1)
  n=$(printf '%s\n' "$gaps" | wc -l | digits)
  if [ "$(awk -v w="$worst" -v m="$MAX_CYCLE_SECS" 'BEGIN{print (w < m)}')" = 1 ]; then
    pass "hub cycles < ${MAX_CYCLE_SECS}s ($n cycles, worst ${worst}s)"
  else
    fail "hub cycle timing" "worst ${worst}s over $n cycles"
  fi
}

check_old_install_gone() {
  for h in $(fleet_hosts); do
    if is_mac "$h"; then
      c=$(on "$h" 'ls $HOME/Library/LaunchAgents | grep -c agent-archive')
      [ "$c" = 0 ] && pass "$h no agent-archive plist" || fail "$h agent-archive plist" "$c present"
    else
      c=$(on "$h" 'systemctl --user list-unit-files 2>/dev/null | grep -c john-agent-archive')
      [ "$c" = 0 ] && pass "$h no john-agent-archive units" || fail "$h john-agent-archive units" "$c present"
    fi
    c=$(on "$h" 'ls -d $HOME/.local/lib/john-agent-archive $HOME/.local/bin/john-archive $HOME/.config/john-agent-archive 2>/dev/null | wc -l' | digits)
    [ "$c" = 0 ] && pass "$h old archive code removed" || fail "$h old archive code" "$c paths remain"
    on "$h" 'test -d $HOME/.local/share/john-agent-archive' && pass "$h old archive data kept" || fail "$h old archive data" "missing"
  done
}

check_fan_out() {
  deadline=$(( $(date +%s) + FAN_OUT_DEADLINE ))
  while :; do
    hub=$(md5_of $HUB "$SHARE/memory.jsonl")
    behind=
    for h in $(fleet_hosts); do
      [ "$h" = "$HUB" ] && continue
      [ "$(md5_of "$h" "$SHARE/memory.jsonl")" = "$hub" ] || behind="$behind $h"
    done
    [ -z "$behind" ] && { pass "fan-out converged on hub md5 $hub"; return; }
    [ "$(date +%s)" -ge "$deadline" ] && { fail "fan-out" "behind after ${FAN_OUT_DEADLINE}s:$behind"; return; }
    sleep 15
  done
}

check_tests
check_sim
check_git
if [ "${1:-}" != --local ]; then
  check_deployed_code
  check_wrappers
  check_hub_state
  check_hub_timing
  check_old_install_gone
  check_fan_out
fi

[ "$fails" = 0 ] && echo "ALL PASS" || { echo "$fails FAILED"; exit 1; }
