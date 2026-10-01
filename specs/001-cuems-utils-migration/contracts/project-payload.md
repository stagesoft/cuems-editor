<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract — the `project` frame

The client action is `project_load`. The server frame is `{"type":"project","value": ...}`
(`CuemsWsUser.send_project`, `tests/ws-command-responses.txt`). This contract is about `value`.
It is not a claim of unconditional byte identity.

## Who produces `value`

`CuemsDBProject.load` calls `CuemsScript.load_with_report(path)` and returns `script.to_wire()`.
`send_project` puts that dict in `value` and does not walk it. No other function adds, drops,
or reorders keys on that dict to change an object-level outcome. The DB duration fix and the
dangling-reference behaviour run on the object or in the library, never on this dict.

Open does not write the script file, the database, or `trash/`.

## Sanctioned deltas

Compared with a capture of `value` committed before any source change other than the task-zero
import:

| Id | Change |
|---|---|
| (a) | `schemaLocation` is absent. It was present. |
| (b) | Each `Media.duration` is `{"CTimecode": "HH:MM:SS.mmm"}`, not a bare string. |

Everything else stays: every other key, key order (the absent key is the only removal), and
the string form of cue booleans (`"True"` / `"False"`, not JSON `true` / `false`).
`doc_version` is not a key. A third difference fails `tests/test_project_payload.py`.

The capture's fixture set is named in the test. Where a fixture is taken from `cuems-utils`
`tests/golden/`, the test records the golden's path and checks `tests/golden/MANIFEST.sha256`.
The test does not rewrite the golden or the capture.

## Handover for delta (a)

`cuems-frontend` `src/app/services/projects/projects.service.ts` declares
`schemaLocation: string` as a required property of the interface for this payload (measured at
line 120). The edit is the frontend's. This repository's PR names that line. The WebSocket
payload is untyped at runtime, so nothing throws; the interface would be lying.

## What this frame is not

- Not `initial_template`. That message is the script example, then (milestone 2) it is retired.
  Its own deltas are listed in `tests/ws-command-responses.txt` when FR-008 lands.
- Not the repair report. A clean, converted, or repaired open sends `document_load_report` as
  a second frame. The `project` value is still only `to_wire()`.
- Not sent at all when load raises. The session gets `document_load_failed` instead
  ([ws-messages.md](ws-messages.md)).
