# Capture

Capture reads this machine's agent chat files and appends new user and assistant lines to `out/<host>.jsonl`.

## Sub-features

- `capture-new` writes a new OMP user line into `out/<host>.jsonl`.
- `capture-skip` does not grow the file when run again with no new source lines.
- `capture-torn` waits until a source line ends with a newline.
- `capture-muse` writes a Muse Code user line and assistant line into `out/<host>.jsonl`.
## How to get to it (user POV)

- Run `agent-memory capture`.
- Wait for the 60s timer `agent-memory cycle`, which captures first.

## Driving it with drive.sh

Preconditions:

- Fresh `$RUN`.
- Unittest `OK`.
- An OMP session file exists under `$RUN/user/.omp/agent/sessions/proj/`.
- For `capture-muse`, a Muse session file exists under `$RUN/user/.local/share/muse/sessions/2026/09/02/verify-sid/`.

- **Seed one message.** Write a complete JSONL line. Run `mkdir -p "$RUN/user/.omp/agent/sessions/proj"` and write `{"type":"message","id":"abcd1234","timestamp":"2026-09-02T00:00:00.000Z","message":{"role":"user","content":[{"type":"text","text":"hello from verify"}]}}` plus a newline to `$RUN/user/.omp/agent/sessions/proj/2026-09-02T00-00-00-000Z_verify.jsonl`.
- **Capture.** Run `skills/verify-agent-memory/drive.sh "$RUN" mini "" capture`. Exit code `0`. `$RUN/am/out/mini.jsonl` has one object whose `text` is `hello from verify` and whose `host` is `mini`.
- **Idempotent.** Run the same capture command again. Exit code `0`. `wc -l` of `$RUN/am/out/mini.jsonl` is still `1`.
- **Proof.** Copy `$RUN/am/out/mini.jsonl` to `skills/verify-agent-memory/artifacts/capture/out.jsonl`. The artifact contains `hello from verify`.
- **Seed Muse.** Run `mkdir -p "$RUN/user/.local/share/muse/sessions/2026/09/02/verify-sid"` and write two JSONL lines to `$RUN/user/.local/share/muse/sessions/2026/09/02/verify-sid/session.jsonl`: `{"schema_version":1,"id":"v1","stream":{"kind":"main","id":"verify-sid"},"sequence":1,"recorded_at":1788380179006471,"record_type":"envelope","payload_type":"runtime.user_intent.accepted","payload":{"surface":"main","intent_id":"verify-intent-1","model_messages":[{"content":[{"kind":"text","text":"muse hello from verify"}]}]}}` plus a newline, then `{"schema_version":1,"id":"v2","stream":{"kind":"main","id":"verify-sid"},"sequence":2,"recorded_at":1788380179006471,"record_type":"envelope","payload_type":"runtime.session","payload":{"kind":"run","event":{"kind":"assistant_message_committed","text":"muse hi from verify","message_id":"verify-msg-1"}}}` plus a newline.
- **Capture Muse.** Run `skills/verify-agent-memory/drive.sh "$RUN" mini "" capture`. Exit code `0`. `$RUN/am/out/mini.jsonl` gains exactly 2 rows with `runtime` `muse` (`wc -l` is now `3`).
- **Proof (muse).** Copy the muse rows (`jq -c 'select(.runtime=="muse")' "$RUN/am/out/mini.jsonl"`) to `skills/verify-agent-memory/artifacts/capture/muse-out.jsonl`. The artifact has two rows with texts `muse hello from verify` / `muse hi from verify` and keys `muse/verify-sid/verify-intent-1` and `muse/verify-sid/verify-msg-1`.

## Gotchas

- Capture reads `$HOME`, which `drive.sh` points at `$RUN/user`. Seeding under the real `~/.omp` pollutes the live machine.
- A last source line without a newline is held until the next capture.
- Leaf host must not pass role `hub`, or later merge in this `$RUN` will treat the box as the hub.
