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
| (c) | A hardware cue's key is `Cue`, with `class` inside. A hardware cue output's key is `CueOutput`, with `class` likewise. `ActionCue`, `FadeCue`, and `CueList` stay their own keys. |

Everything else stays: every other key, key order aside from the absent key and the renamed cue
keys, and the string form of cue booleans (`"True"` / `"False"`, not JSON `true` / `false`).
`doc_version` is not a key. An unlisted difference fails `tests/test_project_payload.py`.
A fourth difference is that failure. Delta (c) is listed, so it is not.

The capture's fixture set is this repository's `tests/fixtures/` (today `script_minimal.xml`).
It is not taken from `cuems-utils` `tests/golden/xml`. Those files may hold a superseded state.
The XSD files in `cuems-utils/src/cuemsutils/xml/schemas/` are the schema, enforced by the
library's public load and save. A golden that contradicts that XSD is regenerated in
`cuems-utils` and the corpus is restated after the system refactoring. This test does not
check `MANIFEST.sha256` and does not rewrite a golden or the editor capture.

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
