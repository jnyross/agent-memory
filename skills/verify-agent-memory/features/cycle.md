# Cycle

Cycle captures this host, then merges if the host is the hub. Leaves would push and pull. Isolated recipes only cover the hub path.

## Sub-features

- `cycle-hub` captures then merges in one invocation.
- `cycle-empty` exits 0 when there is nothing new.

## How to get to it (user POV)

- Run `agent-memory cycle`.
- Wait for the 60s systemd timer or LaunchAgent.

## Driving it with drive.sh

Preconditions:

- Fresh `$RUN`.
- Unittest `OK`.
- Host `agent-box` and role `hub`.
- One OMP message seeded as in [Capture](./capture.md).

- **Hub cycle.** Run `skills/verify-agent-memory/drive.sh "$RUN" agent-box hub cycle`. Exit code `0`. `$RUN/am/out/agent-box.jsonl` has the captured line. `$RUN/am/memory.jsonl` has the same key.
- **Idle cycle.** Run cycle again. Exit code `0`. `wc -l` of `memory.jsonl` is unchanged.
- **Proof.** Copy `$RUN/am/memory.jsonl` to `skills/verify-agent-memory/artifacts/cycle/memory.jsonl`.

## Gotchas

- Isolated cycle with role `hub` does not rsync. Do not use this recipe to prove push or pull.
- Prove push, pull, and timers with `sh verify.sh` against the live fleet.
