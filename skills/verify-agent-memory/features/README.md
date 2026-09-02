# agent-memory verification map

This directory is the maintained source for verifying the user-facing behavior of agent-memory. Read the index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- Work in `~/Work/agent-memory`.
- Create a throwaway run directory with `RUN=$(mktemp -d /tmp/am-verify-XXXXXX)`.
- Drive only through `skills/verify-agent-memory/drive.sh`.
- Run `python3 -m unittest discover -s tests` and require `OK` before the first drive of a session.
- Never set `AGENT_MEMORY_HOME` to `~/.local/share/agent-memory` in these recipes.
- Never drive a live host timer as part of an isolated feature recipe. Use `sh verify.sh` for the fleet.

## Driving conventions

- Start every recipe from a fresh `$RUN` unless its preconditions reuse one.
- Treat every command as literal. Keep quoted names and flags unchanged.
- Hub recipes use host `agent-box` and role `hub`. Leaf capture uses host `mini` and role `""`.
- Restore nothing to disk outside `$RUN`. Do not remove proof artifacts during cleanup.

## Proof and skip reporting

- CLI proof includes the command, stdout, stderr, and exit code.
- Mutation proof includes a read-only second view of the stored file.
- Record the feature ID with every artifact under `skills/verify-agent-memory/artifacts/<feature>/`.
- Report an unreachable path with the attempted command and the unmet precondition.
- Do not report a skipped entry point as verified through a different path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with drive.sh` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Capture](./capture.md) copies new chat lines into `out/<host>.jsonl`.
- [Merge](./merge.md) appends unique hub records into `memory.jsonl` and `memory.sqlite`.
- [Search](./search.md) returns matching snippets from the index, or from `memory.jsonl` if the index is missing.
- [Status](./status.md) prints JSON counts for this host.
- [Cycle](./cycle.md) captures, then merges on the hub.
