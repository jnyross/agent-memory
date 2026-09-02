FLEET_FILE=${FLEET_FILE:-$(dirname -- "$0")/fleet}
[ -f "$FLEET_FILE" ] || FLEET_FILE=fleet

fleet_hosts() {
  while read -r _fn _fr _fx; do
    case $_fn in ''|\#*) continue ;; esac
    [ -n "$_fr" ] || continue
    printf '%s\n' "$_fn"
  done < "$FLEET_FILE"
  return 0
}

fleet_hub() {
  while read -r _fn _fr _fx; do
    case $_fn in ''|\#*) continue ;; esac
    if [ "$_fr" = hub ]; then printf '%s\n' "$_fn"; return 0; fi
  done < "$FLEET_FILE"
  return 1
}

fleet_role() {
  while read -r _fn _fr _fx; do
    case $_fn in ''|\#*) continue ;; esac
    if [ "$_fn" = "$1" ]; then
      [ -n "$_fr" ] || return 1
      printf '%s\n' "$_fr"
      return 0
    fi
  done < "$FLEET_FILE"
  return 1
}

local_host() {
  h=$(sed -n 's/.*AGENT_MEMORY_HOST:=\([^}]*\)}.*/\1/p' "$HOME/.local/bin/agent-memory" 2>/dev/null | head -n 1)
  [ -n "$h" ] || h=$(hostname -s)
  printf '%s\n' "$h"
}

is_local() { [ "$1" = "$(local_host)" ]; }

fails=0
pass() { printf 'PASS %s\n' "$1"; }
fail() { printf 'FAIL %s: %s\n' "$1" "$2"; fails=$((fails + 1)); }
digits() { tr -cd '0-9'; }
on() {
  h=$1; shift
  if is_local "$h"; then sh -c "$*"; else ssh -o BatchMode=yes -o ConnectTimeout=10 "$h" "$*"; fi
}
md5_of() { on "$1" "md5sum $2 2>/dev/null | cut -c1-32 || md5 -q $2"; }
is_mac() { on "$1" uname | grep -q Darwin; }
