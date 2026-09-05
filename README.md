# agent-memory

One append-only JSONL of agent conversation text. Any of the four machines can search it with `jq`.

## Why the old archive died

The complexity was not warranted. Of ~16.1k source lines in john-agent-archive, about 5.2k served the actual goal, about 7.2k were integrity hardening (replica, hash chain, receipts, quarantine, anti-rollback), about 0.6k medication, about 1.8k fleet deploy, and 1.6k dead (`archive.py`). The stated requirements came from reviewer agents (GPT Pro gates, pstack review), not from John. The replica covers only `mini`, so even fully deployed it fails "search from any machine". The only three ideas worth keeping are: consume only up to the last `\n`; detect inode/size changes before trusting a saved offset; upsert by primary key for SQLite sources.

This repo is one stdlib Python file that runs on 3.9.6. No LLM, embeddings, summaries, or network API calls. Capture is JSON-path extraction and SQL. Merge is sort/dedupe by `key`. Search is FTS5 or a substring scan.

## What it writes

Each line:

```json
{"host":"mini","key":"codex/<session>/<id>","path":".codex/sessions/...jsonl","role":"user","runtime":"codex","session_id":"...","text":"...","ts":"2026-09-01T12:00:00.000Z"}
```

Text is stored verbatim. Roles are `user` or `assistant` only.

The private memory store uses owner-only directories (0700) and data files
(0600), including capture files, indexes, logs and temporary outputs. Capture
and synchronization preserve these permissions without changing conversation
text. Before upgrading an existing installation, verify its configured readers
run as the owner; do not apply this policy to an unverified shared store.

On a hub, every sender must also preserve private transfer permissions. An old
sender using `rsync -a` can reset an incoming file to its source permissions
between hub cycles. The collector normalizes known files on its next cycle,
but that does not guarantee continuous 0600 modes with old senders. Defer the
hub permission rollout while any sender's compatibility is unverified; leaf
installations can still keep their own store private when pulling from an old
hub.

On disk, under `~/.local/share/agent-memory` (or `$AGENT_MEMORY_HOME`):

- `out/<host>.jsonl` — this machine's capture
- `in/<host>.jsonl` — hub copies of the others
- `memory.jsonl` — merged, append-only, arrival order; written on the hub, rsync'd back
- `merge.sqlite` — hub working index (keys + FTS5)
- `memory.sqlite` — disposable FTS5 index
- `state.json` — tail cursors and sqlite high-water marks

Host id is `$AGENT_MEMORY_HOST`, else the short hostname. The hub is `agent-box` with `$AGENT_MEMORY_ROLE=hub`.

## Commands

```console
agent-memory capture
agent-memory cycle
agent-memory merge
agent-memory pull
agent-memory search 'repeat prescription'
agent-memory status
```

`cycle` is capture, then merge on the hub, or push+pull everywhere else. Push uses `rsync --append-verify` when the local rsync has it.

Search prefers `memory.sqlite`. If the index is missing it scans `memory.jsonl`. Agents that want the raw file can skip the wrapper:

```console
jq -c 'select(.text|test("prescription";"i"))' ~/.local/share/agent-memory/memory.jsonl
```

## Install

To deploy updates across the existing fleet from a clean checkout:

```console
sh deploy.sh
```

`deploy.sh` refuses to run unless the working tree is clean and `HEAD` is `origin/main`. Host names come from `fleet`.

For an existing, verified installation, use `sh deploy.sh --code-only HOST...`
to update collector code without modifying wrappers, schedules or services.
Set `AGENT_MEMORY_EXPECTED_SHA256` to the installed collector checksum approved
during preflight. The installer refuses unexpected installed code and saves a
private code-only rollback copy before atomic replacement. It neither copies
conversation data nor reads credentials. Reapplying identical code is a no-op.
`sh install.sh --code-only` provides the same operation locally, using the
existing wrapper's identity rather than requiring a new host configuration.

Record permission/ACL metadata separately before tightening existing data.
Verify normal capture/sync cycles and downstream readers after deployment.
If a regression occurs, restore the previous collector using its saved code
and the current checksum, and restore the recorded permission policy without
rewinding live data. Skip inaccessible hosts and unverified consumers.

Linux gets a user systemd timer every 60s. macOS gets `io.johnross.agent-memory`. `install.sh` removes old archive units, plists, code, and CLI. Raw data under `~/.local/share/john-agent-archive` is left in place.

Rollout order is the hub first, then the remotes, then this machine.

## Tests

```console
python3 -m unittest discover -s tests -v
```

## Verify

After you change `agent_memory.py` or `install.sh`, run:

```console
sh verify.sh --local
```

After `sh deploy.sh`, run the fleet check (needs ssh to every host in `fleet`):

```console
sh verify.sh
```

Each line is `PASS` or `FAIL`. The script exits 1 if any check fails. Fix the source and redeploy. Do not edit `verify.sh` or the tests to make a check pass.

The first hub cycle after `merge.sqlite` is deleted takes about 40 seconds and fails the timing check once. Wait for the next cycle, then run `sh verify.sh` again.

## Install on a new device

To add a new device to the fleet, choose one of two paths.

### Path A. Self-install by an agent on the device

Copy and paste this instruction directly to the agent running on the target machine:

```text
Install agent-memory on this machine from https://github.com/jnyross/agent-memory:

0. Stop if this machine is already enrolled:
   [ -e ~/.local/bin/agent-memory ] && { echo "already installed as $(grep -o 'AGENT_MEMORY_HOST:=[^}]*' ~/.local/bin/agent-memory)"; exit 1; }

1. Check prerequisites:
   - python3 >= 3.9: python3 -V
   - rsync: command -v rsync
   - Linux (systemd user session or crontab) or macOS

2. Clone and enter the repository:
   git clone https://github.com/jnyross/agent-memory.git
   cd agent-memory

3. Pick a device name for this machine (for example, grok-bot). Do not use an existing fleet name: agent-box, mini, mbp, johns-macbook-air.

4. Install the service:
   AGENT_MEMORY_HOST=<device-name> sh install.sh
   (If no systemd user session is available, install.sh automatically sets up a minutely cron job.)

5. Ensure you have an SSH key:
   [ -f ~/.ssh/id_ed25519.pub ] || ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
6. Add the hub to ~/.ssh/config:
   mkdir -p ~/.ssh && chmod 700 ~/.ssh

   If this machine has Tailscale installed and joined to the tailnet:
   cat << 'EOF' >> ~/.ssh/config

Host agent-box
  HostName 100.89.131.80
  User john
  IdentityFile ~/.ssh/id_ed25519
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
EOF

   If this machine does not have Tailscale, replace 100.89.131.80 with the hub's regular LAN IP or public hostname/IP provided by the operator.
7. Verify the local daemon:
   ~/.local/bin/agent-memory status
   Confirm "host" matches <device-name> and "errors" is [].

   Until step 8 is complete, the 60 second cycle logs push and pull errors. That is expected.
8. Test hub access and hand off:
   Test connection to hub:
   ssh -o BatchMode=yes agent-box true

   - If it succeeds (e.g. over Tailscale SSH), no key authorization is needed.
     Just inform the operator to add "<device-name> leaf" to the fleet file.
   - If it fails (Permission denied), print your public key (`cat ~/.ssh/id_ed25519.pub`)
     and inform the operator to append it to agent-box:~/.ssh/authorized_keys
     and add "<device-name> leaf" to the fleet file.

### Path B. Push-install from an existing machine

If an existing machine can already reach the new device over SSH:

1. Add a row to `fleet`. The first column is the SSH alias and `AGENT_MEMORY_HOST`. The second is `hub` or `leaf`.
2. Commit and push.
3. Add an SSH alias for that name in `~/.ssh/config` on the deploying machine.
4. Run `sh onboard.sh <device-name>`.

The script checks Python 3.9, rsync, and the OS. It configures hub SSH access, runs `deploy.sh` for that host, and waits until `memory.jsonl` matches the hub.

Then run `sh verify.sh` to check the full fleet.
