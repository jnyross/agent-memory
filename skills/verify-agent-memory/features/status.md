# Status

Status prints one JSON object describing this host's capture home: host id, line counts, last capture time, and errors.

## Sub-features

- `status-empty` works on a new home and names the host from `drive.sh`.
- `status-counts` reports `lines_out` after capture and `memory_lines` after merge.

## How to get to it (user POV)

- Run `agent-memory status`.
- The installed wrapper sets the host id, so a shell without extra env still prints the fleet name.

## Driving it with drive.sh

Preconditions:

- Fresh `$RUN`.
- Unittest `OK`.

- **Empty hub.** Run `skills/verify-agent-memory/drive.sh "$RUN" agent-box hub status`. Exit code `0`. JSON `host` is `agent-box`. `memory_lines` is `0`. `errors` is `[]`.
- **Empty leaf.** Run `skills/verify-agent-memory/drive.sh "$RUN" mini "" status`. Exit code `0`. JSON `host` is `mini`.
- **Proof.** Save the hub status stdout to `skills/verify-agent-memory/artifacts/status/status.json`.

## Gotchas

- `status` does not merge or capture. Counts stay at 0 until those commands run in the same `$RUN`.
- The live wrapper on a host is out of scope here. Use `sh verify.sh` to check wrapper host ids on the fleet.
