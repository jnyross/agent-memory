# Capture

Capture reads this machine's agent chat files and appends new user and assistant lines to `out/<host>.jsonl`.

## Sub-features

- `capture-new` writes a new OMP user line into `out/<host>.jsonl`.
- `capture-skip` does not grow the file when run again with no new source lines.
- `capture-torn` waits until a source line ends with a newline.

## How to get to it (user POV)

- Run `agent-memory capture`.
- Wait for the 60s timer `agent-memory cycle`, which captures first.

## Driving it with drive.sh

Preconditions:

- Fresh `$RUN`.
- Unittest `OK`.
- An OMP session file exists under `$RUN/user/.omp/agent/sessions/proj/`.

- **Seed one message.** Write a complete JSONL line. Run `mkdir -p "$RUN/user/.omp/agent/sessions/proj"` and write `{"type":"message","id":"abcd1234","timestamp":"2026-09-02T00:00:00.000Z","message":{"role":"user","content":[{"type":"text","text":"hello from verify"}]}}` plus a newline to `$RUN/user/.omp/agent/sessions/proj/2026-09-02T00-00-00-000Z_verify.jsonl`.
- **Capture.** Run `skills/verify-agent-memory/drive.sh "$RUN" mini "" capture`. Exit code `0`. `$RUN/am/out/mini.jsonl` has one object whose `text` is `hello from verify` and whose `host` is `mini`.
- **Idempotent.** Run the same capture command again. Exit code `0`. `wc -l` of `$RUN/am/out/mini.jsonl` is still `1`.
- **Proof.** Copy `$RUN/am/out/mini.jsonl` to `skills/verify-agent-memory/artifacts/capture/out.jsonl`. The artifact contains `hello from verify`.

## Gotchas

- Capture reads `$HOME`, which `drive.sh` points at `$RUN/user`. Seeding under the real `~/.omp` pollutes the live machine.
- A last source line without a newline is held until the next capture.
- Leaf host must not pass role `hub`, or later merge in this `$RUN` will treat the box as the hub.
