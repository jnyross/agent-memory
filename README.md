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

On each host, from a checkout (or `/tmp` after `scp`):

```console
AGENT_MEMORY_HOST=agent-box AGENT_MEMORY_ROLE=hub sh install.sh
AGENT_MEMORY_HOST=mini sh install.sh
AGENT_MEMORY_HOST=mbp sh install.sh
AGENT_MEMORY_HOST=johns-macbook-air sh install.sh
```

Or roll out the whole fleet from a clean checkout with `sh deploy.sh`. It refuses to run unless the working tree is clean and `HEAD` is `origin/main`. Host names come from `fleet`.

Linux gets a user systemd timer every 60s. macOS gets `io.johnross.agent-memory`. `install.sh` removes the old `john-agent-archive` units, plist, code and CLI. Raw data under `~/.local/share/john-agent-archive` is left in place.

Rollout order is the hub first, then the other remotes, then this machine.

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

## Onboard a device

To add a machine, a Grok bot for example:

1. Add a row to `fleet`. The first column is the ssh alias and `AGENT_MEMORY_HOST`. The second is `hub` or `leaf`.
2. Commit and push.
3. Create an ssh alias for that name on the machine that runs `onboard.sh`.
4. Run `sh onboard.sh <name>`.

The script checks Python 3.9, rsync, and the OS. It sets up hub ssh if that is missing. It runs `deploy.sh` for that host. It waits until `memory.jsonl` matches the hub.

Then run `sh verify.sh`. That script reads `fleet`.
