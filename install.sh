#!/bin/sh
set -eu

HOST="${AGENT_MEMORY_HOST:?set AGENT_MEMORY_HOST to the fleet name}"
ROLE="${AGENT_MEMORY_ROLE:-}"
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LIB="${HOME}/.local/lib/agent-memory"
SHARE="${HOME}/.local/share/agent-memory"
BIN="${HOME}/.local/bin"

mkdir -p "$LIB" "$SHARE/out" "$SHARE/in" "$SHARE/logs" "$BIN"
cp "$HERE/agent_memory.py" "$LIB/agent_memory.py"

printf '%s\n' '#!/bin/sh' "exec /usr/bin/python3 ${LIB}/agent_memory.py \"\$@\"" > "$BIN/agent-memory"
chmod +x "$BIN/agent-memory" "$LIB/agent_memory.py"

if [ "$ROLE" = "hub" ]; then
  printf '%s\n' '["johns-macbook-air","mbp","mini","agent-box"]' > "$SHARE/hosts.json"
fi

UNAME=$(uname)
if [ "$UNAME" = "Linux" ]; then
  mkdir -p "${HOME}/.config/systemd/user"
  {
    printf '%s\n' '[Unit]'
    printf '%s\n' 'Description=Capture and synchronize agent memory'
    printf '%s\n' 'After=network-online.target'
    printf '%s\n' ''
    printf '%s\n' '[Service]'
    printf '%s\n' 'Type=oneshot'
    printf '%s\n' "Environment=AGENT_MEMORY_HOST=${HOST}"
    if [ -n "$ROLE" ]; then
      printf '%s\n' "Environment=AGENT_MEMORY_ROLE=${ROLE}"
    fi
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
  systemctl --user disable --now john-agent-archive-cycle.timer >/dev/null 2>&1 || true

elif [ "$UNAME" = "Darwin" ]; then
  mkdir -p "${HOME}/Library/LaunchAgents"
  PLIST="${HOME}/Library/LaunchAgents/io.johnross.agent-memory.plist"
  {
    printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>'
    printf '%s\n' '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
    printf '%s\n' '<plist version="1.0">'
    printf '%s\n' '<dict>'
    printf '%s\n' '	<key>EnvironmentVariables</key>'
    printf '%s\n' '	<dict>'
    printf '%s\n' '		<key>AGENT_MEMORY_HOST</key>'
    printf '%s\n' "		<string>${HOST}</string>"
    if [ -n "$ROLE" ]; then
      printf '%s\n' '		<key>AGENT_MEMORY_ROLE</key>'
      printf '%s\n' "		<string>${ROLE}</string>"
    fi
    printf '%s\n' '		<key>PYTHONDONTWRITEBYTECODE</key>'
    printf '%s\n' '		<string>1</string>'
    printf '%s\n' '	</dict>'
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
  launchctl bootout "gui/${UID_NUM}" "${HOME}/Library/LaunchAgents/io.johnross.agent-archive.cycle.plist" >/dev/null 2>&1 || true
else
  printf '%s\n' "unsupported uname: ${UNAME}" >&2
  exit 1
fi
