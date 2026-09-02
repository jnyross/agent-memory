#!/bin/sh
set -u
cd "$(dirname "$0")"
. ./lib.sh
bin='$HOME/.local/bin/agent-memory'
share='$HOME/.local/share/agent-memory'

name=${1:-}
if [ -z "$name" ] || ! fleet_role "$name" >/dev/null; then
  printf 'FAIL %s not in fleet: add "%s leaf" to fleet, commit, push\n' "$name" "$name"
  exit 1
fi
hub=$(fleet_hub)

if is_local "$name" || ssh -o BatchMode=yes -o ConnectTimeout=10 "$name" true 2>/dev/null; then
  pass "$name ssh"
else
  fail "$name ssh" "add ssh alias"
  exit 1
fi

os=$(on "$name" uname 2>/dev/null)
case $os in
  Darwin|Linux) pass "$name uname $os" ;;
  *) fail "$name uname" "got '${os:-none}'" ;;
esac

pyver=$(on "$name" "python3 -V 2>&1 | sed 's/^Python //'" 2>/dev/null)
pymaj=$(printf '%s' "$pyver" | cut -d. -f1)
pymin=$(printf '%s' "$pyver" | cut -d. -f2)
case $pymaj$pymin in
  ''|*[!0-9]*) fail "$name python3" "got '$pyver'" ;;
  *)
    if [ "$pymaj" -gt 3 ] || { [ "$pymaj" -eq 3 ] && [ "$pymin" -ge 9 ]; }; then
      pass "$name python3 >= 3.9 ($pyver)"
    else
      fail "$name python3" "got $pyver"
    fi
    ;;
esac

if on "$name" "command -v rsync" >/dev/null 2>&1; then
  pass "$name rsync"
else
  fail "$name rsync" "missing"
fi

if [ "$os" = Linux ]; then
  if on "$name" "systemctl --user show-environment" >/dev/null 2>&1; then
    pass "$name systemctl --user"
  else
    fail "$name systemctl --user" "show-environment failed"
  fi
fi

if on "$name" "ssh -o BatchMode=yes -o ConnectTimeout=10 $hub true" >/dev/null 2>&1; then
  pass "$name reaches hub"
else
  on "$name" 'mkdir -p ~/.ssh; chmod 700 ~/.ssh; [ -f ~/.ssh/id_ed25519 ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519'
  tip=$(resolve_peer_ip "$hub" 2>/dev/null || true)
  ghost=$(ssh -G "$hub" 2>/dev/null | awk '/^hostname /{print $2; exit}')
  [ -n "$tip" ] && ghost=$tip
  guser=$(ssh -G "$hub" 2>/dev/null | awk '/^user /{print $2; exit}')
  dhost=$(on "$name" "ssh -G $hub 2>/dev/null | awk '/^hostname /{print \$2; exit}'")
  if [ "$dhost" = "$hub" ]; then
    on "$name" "printf '\nHost $hub\n  HostName %s\n  User %s\n  IdentityFile ~/.ssh/id_ed25519\n  IdentitiesOnly yes\n  StrictHostKeyChecking accept-new\n' '$ghost' '$guser' >> ~/.ssh/config"
  fi
  pub=$(on "$name" 'cat ~/.ssh/id_ed25519.pub')
  printf '%s\n' "$pub"
  ssh "$hub" "grep -qxF '$pub' ~/.ssh/authorized_keys 2>/dev/null || printf '%s\n' '$pub' >> ~/.ssh/authorized_keys"
  if on "$name" "ssh -o BatchMode=yes -o ConnectTimeout=10 $hub true" >/dev/null 2>&1; then
    pass "$name reaches hub"
  else
    fail "$name reaches hub" "device_setup did not restore hub access"
  fi
fi

[ "$fails" = 0 ] || exit 1

sh deploy.sh "$name"

got=$(on "$name" "$bin status 2>/dev/null | jq -r .host")
[ "$got" = "$name" ] && pass "$name status.host" || fail "$name status.host" "got '$got'"

case $os in
  Linux)
    if [ "$(on "$name" "systemctl --user is-active agent-memory.timer")" = active ]; then
      pass "$name timer active"
    else
      fail "$name timer" "not active"
    fi
    ;;
  Darwin)
    if on "$name" "launchctl print gui/\$UID/io.johnross.agent-memory" >/dev/null 2>&1; then
      pass "$name timer active"
    else
      fail "$name timer" "launchctl print failed"
    fi
    ;;
  *) fail "$name timer" "unknown os '$os'" ;;
esac

deadline=$(( $(date +%s) + 150 ))
while :; do
  [ "$(md5_of "$name" "$share/memory.jsonl")" = "$(md5_of "$hub" "$share/memory.jsonl")" ] && { pass "$name memory.jsonl == hub"; break; }
  if [ "$(date +%s)" -ge "$deadline" ]; then
    fail "$name memory.jsonl == hub" "not converged after 150s"
    break
  fi
  sleep 5
done

if on "$name" "test -s $share/out/$name.jsonl"; then
  deadline=$(( $(date +%s) + 150 ))
  while :; do
    if on "$hub" "test -f $share/in/$name.jsonl"; then
      pass "hub in/$name.jsonl"
      break
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      fail "hub in/$name.jsonl" "missing after 150s"
      break
    fi
    sleep 5
  done
else
  pass "push pending first capture"
fi

[ "$fails" = 0 ] || exit 1
