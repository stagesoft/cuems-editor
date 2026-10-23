<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Upstream report → `cuems-frontend`: the `media_check_report` frame is restored in the editor

**From:** `cuems-editor` feature 003, 2026-10-23. `cuems-editor` edits no file in your repository.

## What this is

`cuems-editor 0.1.0rc1-4 … -7` shipped a `media_check_report` frame; your `origin/dev` consumes it
(`src/app/services/ui/media-check.service.ts`, `src/app/app.component.ts:54`, `media-check.service.spec.ts`). Your
`feat/xml-refactor` does not have that consumer. The editor's 0.1.1 re-implements the **producer** on `CuemsScript`
objects and restores the frame **byte-for-byte** (key order included). It is checked against golden payloads captured from
the released editor at `69d749e` (`tests/data/golden/`, with its README).

| | |
|---|---|
| Frame | `{"type": "media_check_report", "value": {project_uuid, project_name, context, complete, reason, files[{file_name, cues, changes[{field, stored, current}]}], unverified[], total_files}}` |
| `context` | `open` (the requester, after the `project` frame and the `document_load_report`), `ready` (every session on the project, after the `project_ready` reply), `save` (every session, after the `project_save` reply) |
| `reason` | `null`, `engine_running`, `engine_silent`, `deadline`, `probe_failed`, `copy_in_progress` |
| All-clear | `complete` and no `files` and no `unverified`; a client clears its warning only on that |
| Reference | `tests/data/ws-command-responses.txt` section "media_check_report" (at `tests/ws-command-responses.txt` until the layout move) |

The report is **informational and never gates a save**; only the `document_load_report` acknowledgment does. Its
findings are the same as that report's `media_repairs`, grouped by file.

## What we ask

1. Your reconciliation (31 commits behind `origin/dev`) absorbs the consumer; confirm both halves exist at your re-cut tag.
2. **Unknown-frame handling (checked, read-only).** Your `feat/xml-refactor` (`HEAD` of the checkout read) pushes every frame that is
   not `type: "error"` to the `messages` Subject (`src/app/services/websocket.service.ts:52-72`); components filter by
   `type` (for example `project-show.component.ts:139`). A frame no component matches is ignored, so the editor can land
   its `media_check_report` before the consumer does. Nothing to change; please keep it that way.
3. The editor's `project_status` now carries three states (`running | loaded | none`) and `project_unix_name` (engine
   rc6-4); the editor relays the engine's answer unchanged.
