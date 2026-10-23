<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract: `media_check_report` (restored, byte-identical to 0.1.0rc1-4)

Wire delta: **none**. This frame shipped in `0.1.0rc1-4` and is documented in the release line's
`tests/ws-command-responses.txt` (at the time, before the move to `tests/data/`). This feature re-implements its producer on objects; the shape, key set and
audiences below are the released ones. The consumer is `cuems-frontend` `origin/dev`
(`src/app/services/ui/media-check.service.ts`, `app.component.ts:54`); its reconciliation follows this feature.

## Frame

```json
{"type": "media_check_report", "value": {
  "project_uuid": "uuid", "project_name": "name",
  "context": "open" | "ready" | "save",
  "complete": true,
  "reason": null,
  "files": [{"file_name": "a.mp4", "cues": 3,
             "changes": [{"field": "duration" | "pixel_size" | "file_size" | "file_md5",
                          "stored": "00:00:10.010", "current": "00:00:20.020" | null}]}],
  "unverified": ["b.mp4"],
  "total_files": 1}}
```

`reason` is `null` or one of `engine_running`, `engine_silent`, `deadline`, `probe_failed`,
`copy_in_progress`. `files` lists at most 20 files; `total_files` counts all. An all-clear is `complete` and no
`files` and no `unverified`; a client clears its warning only on that.

## When it is sent, and to whom (constitution II)

| Trigger | After | Context | Audience | Work done |
|---|---|---|---|---|
| `project_load` | the `project` frame | `open` | the requester | read-only: no engine query, no probe, no indexer, no DB write; simultaneous opens share one run |
| `project_ready` | the check ran, before the engine load | `ready` | the requester and every session on the project | full: engine state, re-probe of changed files and row correction (within the deadline), video-index rebuild; never raises |
| `project_save` | the `project_save` frame | `save` | every session on the project | read-only comparison of the saved script with the rows |

The check never rewrites the project file, never gates a save, and its findings equal the load report's
`media_repairs` for the same project and state (one comparison, two projections).

## Golden payloads (constitution I)

Before any US3 source edit, the released producer at `69d749e` is run on a fixture library and its frames
are committed as `tests/data/golden/media_check_report_{open,ready,save}.json` (with `copy_in_progress` and an
all-clear captured as extra cases). The re-implementation is compared against them, key set and value types
included; volatile values (uuids, names) are normalised by the comparison, never by editing the golden files.

## Tests that pin it (constitution IV gates 2 and 4)

- exact key set and `context` values; an all-clear; the 20-file cap with `total_files`;
- `copy_in_progress` for a file whose size or modification time changes during its probe;
- the four engine states (`running`, `loaded`, `none`, no answer);
- the report equals the grouped `media_repairs` for the same fixture;
- the report never changes `GateState` and a save is not refused because of it;
- the released media-refresh tests, ported (71), are the acceptance set.

## Documentation-only correction in the same reference

`project_status` is documented as `{"status": "none|running", ...}`. The engine sends `running | loaded | none`
with `project_uuid` and `project_unix_name`. Updated in `tests/data/ws-command-responses.txt`; the editor relays
the engine's dictionary unchanged.
