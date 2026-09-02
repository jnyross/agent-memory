# Search

Search returns matching conversation lines as JSON, one object per hit, with a snippet. It prefers `memory.sqlite`. If that file is missing it scans `memory.jsonl`.

## Sub-features

- `search-hit` returns the matching hub record and a snippet that marks the query.
- `search-miss` prints nothing and exits 0 when no line matches.
- `search-fallback` still hits after `memory.sqlite` is removed.

## How to get to it (user POV)

- Run `agent-memory search 'repeat prescription'`.
- Run `jq` on `~/.local/share/agent-memory/memory.jsonl` for the raw file. That path is not this harness.

## Driving it with drive.sh

Preconditions:

- Fresh `$RUN`.
- Unittest `OK`.
- Host `agent-box` and role `hub`.
- Merge has already built an index that contains text `please handle the repeat prescription` under key `omp/s/1`, plus a second record whose text is `unrelated`.

- **Seed and merge.** Write those two objects to `$RUN/am/out/agent-box.jsonl`. Run `skills/verify-agent-memory/drive.sh "$RUN" agent-box hub merge`. Exit code `0`.
- **Hit.** Run `skills/verify-agent-memory/drive.sh "$RUN" agent-box hub search "repeat prescription"`. Exit code `0`. Stdout is one JSON object whose `host` is `agent-box` and whose `snippet` contains `[repeat prescription]`.
- **Miss.** Run `skills/verify-agent-memory/drive.sh "$RUN" agent-box hub search "volcano"`. Exit code `0`. Stdout is empty.
- **Fallback.** Remove `$RUN/am/memory.sqlite`. Run the hit search again. Exit code `0`. Stdout is again one JSON object whose snippet contains `[repeat prescription]`.
- **Proof.** Save the hit stdout to `skills/verify-agent-memory/artifacts/search/hit.jsonl` before removing the sqlite file.

## Gotchas

- Search does not read `merge.sqlite`. Fallback needs `memory.jsonl`.
- Quote the phrase as one argument.
- Isolated search never uses the live `~/.local/share/agent-memory` index.
