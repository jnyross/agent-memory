# Merge

Merge, on the hub, folds `in/*.jsonl` and `out/*.jsonl` into `memory.jsonl` and `memory.sqlite`. Only new keys are appended.

## Sub-features

- `merge-first` writes `memory.jsonl` and `memory.sqlite` from one input record.
- `merge-append` adds a second key without rewriting the first line.
- `merge-dedupe` ignores a second copy of the same key.

## How to get to it (user POV)

- On the hub, run `agent-memory merge`.
- On the hub, run `agent-memory cycle` after capture.

## Driving it with drive.sh

Preconditions:

- Fresh `$RUN`.
- Unittest `OK`.
- Host `agent-box` and role `hub`.

- **Seed one record.** Create `$RUN/am/out/agent-box.jsonl` with one JSON object whose `key` is `omp/s/1`, `text` is `first`, `host` is `agent-box`, `role` is `user`, `runtime` is `omp`, `session_id` is `s`, `path` is `x`, `ts` is `2026-09-01T12:00:00.000Z`.
- **First merge.** Run `skills/verify-agent-memory/drive.sh "$RUN" agent-box hub merge`. Exit code `0`. `wc -l` of `$RUN/am/memory.jsonl` is `1`. `$RUN/am/memory.sqlite` and `$RUN/am/merge.sqlite` exist.
- **Append.** Add a second object with `key` `omp/s/2` and `text` `second` to the same input file. Run merge again. `memory.jsonl` texts are `first` then `second`.
- **Dedupe.** Run merge a third time with no new keys. `wc -l` of `memory.jsonl` stays `2`.
- **Proof.** Copy `$RUN/am/memory.jsonl` to `skills/verify-agent-memory/artifacts/merge/memory.jsonl`.

## Gotchas

- Merge is hub-only. Role must be `hub`.
- Order is arrival order, not sorted by `ts`.
- Deleting `merge.sqlite` rebuilds `memory.jsonl` from inputs on the next merge.
