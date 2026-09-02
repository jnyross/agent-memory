---
name: verify-agent-memory
description: "Drive the agent-memory CLI the way a user does: isolated capture, hub merge, search, status, and cycle. Use after changing agent_memory.py, install.sh, or deploy.sh, or when asked if search, merge, or the fleet still work."
---

# Verify agent-memory

Primary surface is the CLI `python3 agent_memory.py` (installed as `~/.local/bin/agent-memory`). There is no server. Isolate every feature drive with a throwaway directory. Never set `AGENT_MEMORY_HOME` to `~/.local/share/agent-memory` for those drives.

The live four-host fleet is a separate check. Use `sh verify.sh` at the repo root for that. Do not mix fleet ssh into an isolated drive.

Repo root: `~/Work/agent-memory`.

## Launch

There is no long-lived process. Launch means one isolated run directory and `drive.sh`.

```bash
cd ~/Work/agent-memory
RUN=$(mktemp -d /tmp/am-verify-XXXXXX)
skills/verify-agent-memory/drive.sh "$RUN" agent-box hub status
```

Ready when that command exits 0 and prints JSON with `"host":"agent-box"`. `drive.sh` sets `HOME=$RUN/user` and `AGENT_MEMORY_HOME=$RUN/am`.

Teardown the run directory after the drive. Keep proof files under `skills/verify-agent-memory/artifacts/`.

For a short-lived CLI there is nothing to keep alive between commands in one recipe besides `$RUN`. Reuse `$RUN` inside one feature recipe. Use a new `$RUN` for the next feature.

## Doctor

Run this first whenever a drive looks off.

```bash
cd ~/Work/agent-memory
python3 -m unittest discover -s tests
skills/verify-agent-memory/drive.sh "$RUN" agent-box hub status
```

Worth driving when unittest prints `OK` and `status` exits 0 with `"errors":[]`. If `$RUN` does not exist yet, create it with the Launch command.

Fleet doctor, after deploy only:

```bash
cd ~/Work/agent-memory
sh verify.sh --local
```

Full fleet (ssh to `agent-box`, `mini`, `mbp`):

```bash
cd ~/Work/agent-memory
sh verify.sh
```

## Drive

Harness is `skills/verify-agent-memory/drive.sh`. Read `features/README.md`, then the feature file. Treat every command in the map as literal.

```bash
skills/verify-agent-memory/drive.sh "$RUN" <host> <role> <command> [args...]
```

Empty role is `""`. Host `agent-box` with role `hub` for merge, search of a merged index, and hub cycle. Host `mini` with role `""` for a leaf capture.

## Evidence

Put proof in `skills/verify-agent-memory/artifacts/<feature>/`. Cleanup must not delete this tree.

Capture the command, stdout, stderr, and exit code. For merge and capture, also capture a second read of the file that changed (`out/<host>.jsonl` or `memory.jsonl`). Search proof is stdout JSON with a snippet plus `jq -r .key` of `memory.jsonl` showing the same key.

Exercise `python3 agent_memory.py`, not sqlite inserts by hand except as seed data the CLI would have written.

## Cleanup

```bash
rm -rf "$RUN"
```

Only remove the run directory this run created. Do not kill by process name. Do not delete `skills/verify-agent-memory/artifacts/`.

## Helpers

`skills/verify-agent-memory/drive.sh` is executable. Invocation is under Launch and Drive.

`verify.sh` at the repo root is executable. `--local` is tests, hub simulation, and git state. Full run is the deployed fleet. A line is `PASS` or `FAIL`. Exit 1 on any FAIL. On FAIL, fix source, commit, `git push origin main`, `sh deploy.sh`. Do not edit `verify.sh` or tests to make a check pass.

The first hub cycle after `merge.sqlite` is deleted takes about 40 seconds and fails the fleet timing check once. Wait one more cycle, then rerun `sh verify.sh`.
