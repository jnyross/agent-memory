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

1. Check prerequisites:
   - python3 >= 3.9: python3 -V
   - rsync: command -v rsync
   - Linux with a systemd user session or macOS

2. Clone and enter the repository:
   git clone https://github.com/jnyross/agent-memory.git
   cd agent-memory

3. Pick a device name for this machine (for example, grok-bot). Do not use an existing fleet name: agent-box, mini, mbp, johns-macbook-air.

4. Install the service:
   AGENT_MEMORY_HOST=<device-name> sh install.sh

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

8. Handoff: Print your public key (cat ~/.ssh/id_ed25519.pub) and chosen <device-name>.
   Inform the operator to:
   a. Append your public key to agent-box:~/.ssh/authorized_keys
   b. Add "<device-name> leaf" to the fleet file, commit, and push
   Once authorized, test the connection with: ssh -o BatchMode=yes agent-box true
```

### Path B. Push-install from an existing machine

If an existing machine can already reach the new device over SSH:

1. Add a row to `fleet`. The first column is the SSH alias and `AGENT_MEMORY_HOST`. The second is `hub` or `leaf`.
2. Commit and push.
3. Add an SSH alias for that name in `~/.ssh/config` on the deploying machine.
4. Run `sh onboard.sh <device-name>`.

The script checks Python 3.9, rsync, and the OS. It configures hub SSH access, runs `deploy.sh` for that host, and waits until `memory.jsonl` matches the hub.

Then run `sh verify.sh` to check the full fleet.
