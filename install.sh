#!/bin/sh
set -eu

HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LIB="${HOME}/.local/lib/agent-memory"
SHARE="${HOME}/.local/share/agent-memory"
BIN="${HOME}/.local/bin"

if [ "${1:-}" = --code-only ]; then
  [ "$#" -eq 1 ] || { echo 'usage: install.sh [--code-only]' >&2; exit 2; }
  exec /usr/bin/python3 - "$HERE/agent_memory.py" "$LIB/agent_memory.py" "$BIN/agent-memory" "$SHARE" <<'PY'
import hashlib, os, pathlib, re, stat, sys, tempfile
source, target, wrapper, share = map(pathlib.Path, sys.argv[1:])
def checked(path, directory=False):
    info = path.lstat()
    if info.st_uid != os.getuid() or not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError('Existing installation has an unsafe type or owner.')
    if not directory and info.st_nlink != 1:
        raise ValueError('Existing installation must not contain hard links.')
    return info
def replace(path, data, mode):
    fd, temporary = tempfile.mkstemp(prefix='.code-only-', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'wb') as output:
            os.fchmod(output.fileno(), mode)
            output.write(data); output.flush(); os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)
try:
    for path in (target.parent, wrapper.parent, share): checked(path, True)
    info = checked(target); checked(wrapper)
    if str(target) not in wrapper.read_text():
        raise ValueError('Existing wrapper does not use this collector.')
    previous = target.read_bytes(); desired = source.read_bytes()
    compile(desired, str(target), 'exec')
    current = hashlib.sha256(previous).hexdigest()
    if desired == previous:
        print('code unchanged; wrappers and schedules preserved')
    else:
        expected = os.environ.get('AGENT_MEMORY_EXPECTED_SHA256', '')
        if not re.fullmatch(r'[0-9a-f]{64}', expected) or current != expected:
            raise ValueError('Installed code does not match the approved preflight checksum.')
        backup = target.parent / ('.code-only-backup-' + current + '.py')
        if backup.exists():
            checked(backup)
            if backup.read_bytes() != previous: raise ValueError('Rollback code checksum mismatch.')
        else:
            replace(backup, previous, 0o600)
        # Recheck before replacement to avoid overwriting concurrent maintenance.
        fresh = checked(target)
        if (fresh.st_dev, fresh.st_ino) != (info.st_dev, info.st_ino) or target.read_bytes() != previous:
            raise ValueError('Installed code changed during deployment.')
        replace(target, desired, stat.S_IMODE(info.st_mode))
        print('code updated atomically; wrappers and schedules preserved')
except (OSError, ValueError, SyntaxError) as error:
    print('code-only installation refused: ' + str(error), file=sys.stderr)
    sys.exit(1)
PY
fi
[ "$#" -eq 0 ] || { echo 'usage: install.sh [--code-only]' >&2; exit 2; }
HOST="${AGENT_MEMORY_HOST:?set AGENT_MEMORY_HOST to the fleet name}"
ROLE="${AGENT_MEMORY_ROLE:-}"
umask 077

mkdir -p "$LIB" "$SHARE/out" "$SHARE/in" "$SHARE/logs" "$BIN"
cp "$HERE/agent_memory.py" "$LIB/agent_memory.py"

{
  printf '%s\n' '#!/bin/sh'
  printf '%s\n' ": \"\${AGENT_MEMORY_HOST:=${HOST}}\""
  printf '%s\n' 'export AGENT_MEMORY_HOST'
  if [ -n "$ROLE" ]; then
    printf '%s\n' ": \"\${AGENT_MEMORY_ROLE:=${ROLE}}\""
    printf '%s\n' 'export AGENT_MEMORY_ROLE'
  fi
  printf '%s\n' "exec /usr/bin/python3 ${LIB}/agent_memory.py \"\$@\""
} > "$BIN/agent-memory"
chmod +x "$BIN/agent-memory" "$LIB/agent_memory.py"

UNAME=$(uname)
if [ "$UNAME" = "Linux" ]; then
  if systemctl --user show-environment >/dev/null 2>&1; then
    mkdir -p "${HOME}/.config/systemd/user"
    {
      printf '%s\n' '[Unit]'
      printf '%s\n' 'Description=Capture and synchronize agent memory'
      printf '%s\n' 'After=network-online.target'
      printf '%s\n' ''
      printf '%s\n' '[Service]'
      printf '%s\n' 'Type=oneshot'
      printf '%s\n' 'ExecStart=%h/.local/bin/agent-memory cycle'
      printf '%s\n' 'Nice=10'
      printf '%s\n' 'IOSchedulingClass=idle'
      printf '%s\n' ''
      printf '%s\n' '[Install]'
      printf '%s\n' 'WantedBy=default.target'
    } > "${HOME}/.config/systemd/user/agent-memory.service"

    {
      printf '%s\n' '[Unit]'
      printf '%s\n' 'Description=Run agent-memory every minute'
      printf '%s\n' ''
      printf '%s\n' '[Timer]'
      printf '%s\n' 'OnBootSec=30s'
      printf '%s\n' 'OnUnitActiveSec=60s'
      printf '%s\n' 'RandomizedDelaySec=10s'
      printf '%s\n' 'Persistent=true'
      printf '%s\n' ''
      printf '%s\n' '[Install]'
      printf '%s\n' 'WantedBy=timers.target'
    } > "${HOME}/.config/systemd/user/agent-memory.timer"

    systemctl --user daemon-reload
    systemctl --user enable --now agent-memory.timer
  elif command -v crontab >/dev/null 2>&1; then
    mkdir -p "${SHARE}/logs"
    cron_job="* * * * * ${BIN}/agent-memory cycle >> ${SHARE}/logs/cycle.log 2>&1"
    (crontab -l 2>/dev/null | grep -Fv "agent-memory cycle"; echo "$cron_job") | crontab -
  else
    printf '%s\n' "neither systemctl --user nor crontab available" >&2
    exit 1
  fi
elif [ "$UNAME" = "Darwin" ]; then
  mkdir -p "${HOME}/Library/LaunchAgents"
  PLIST="${HOME}/Library/LaunchAgents/io.johnross.agent-memory.plist"
  {
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>'
    printf '%s\n' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    printf '%s\n' '<plist version="1.0">'
    printf '%s\n' '<dict>'
    printf '%s\n' '	<key>Label</key>'
    printf '%s\n' '	<string>io.johnross.agent-memory</string>'
    printf '%s\n' '	<key>LowPriorityIO</key>'
    printf '%s\n' '	<true/>'
    printf '%s\n' '	<key>ProcessType</key>'
    printf '%s\n' '	<string>Background</string>'
    printf '%s\n' '	<key>ProgramArguments</key>'
    printf '%s\n' '	<array>'
    printf '%s\n' "		<string>${HOME}/.local/bin/agent-memory</string>"
    printf '%s\n' '		<string>cycle</string>'
    printf '%s\n' '	</array>'
    printf '%s\n' '	<key>RunAtLoad</key>'
    printf '%s\n' '	<true/>'
    printf '%s\n' '	<key>StandardErrorPath</key>'
    printf '%s\n' "		<string>${SHARE}/logs/cycle.err.log</string>"
    printf '%s\n' '	<key>StandardOutPath</key>'
    printf '%s\n' "		<string>${SHARE}/logs/cycle.out.log</string>"
    printf '%s\n' '	<key>StartInterval</key>'
    printf '%s\n' '	<integer>60</integer>'
    printf '%s\n' '</dict>'
    printf '%s\n' '</plist>'
  } > "$PLIST"

  UID_NUM=$(id -u)
  launchctl bootout "gui/${UID_NUM}" "$PLIST" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/${UID_NUM}" "$PLIST"
else
  printf '%s\n' "unsupported uname: ${UNAME}" >&2
  exit 1
fi
