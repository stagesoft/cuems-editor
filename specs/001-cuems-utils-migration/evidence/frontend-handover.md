<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Frontend handover — what `cuems-frontend` reads that 001 changes

Line numbers measured against `cuems-frontend` @ `3183845`. This repository does not edit the
frontend. Each row names the consumer of a delta recorded in `tests/ws-command-responses.txt`.

## `initial_template` (T015, FR-008, FR-042)

Value is now `ConfigManager.generate_example(SchemaName.SCRIPT)`, envelope unchanged. Deltas
(a)–(f) are listed beside `initial_template` in `tests/ws-command-responses.txt`. Delta (c),
hardware cues keyed `Cue` / `CueOutput` with `class`, is not omitted to keep the old envelope.

| File:line | What it does |
|---|---|
| `src/app/services/projects/projects.service.ts:240` | `response.type === 'initial_template'` |
| `src/app/services/projects/projects.service.ts:243` | writes `localStorage` key `initial_template` with the value |
| `src/app/services/projects/projects.service.ts:159` | reads that key back on start. A pre-001 template cached there survives until the next connect overwrites it |

## `project` frame (T027, FR-018, FR-042)

Deltas (a), (b), (c) are listed beside `project` in `tests/ws-command-responses.txt`. They are
payload version 1, not a bump to 2.

| File:line | What it does |
|---|---|
| `src/app/services/projects/projects.service.ts:120` | declares `schemaLocation: string` as a required property of the project payload interface. Delta (a) removes the key. Nothing throws at runtime (the WebSocket payload is untyped), so the interface lies until the frontend drops it |
| (delta (c)) | every reader of `AudioCue` / `VideoCue` / `DmxCue` keys in a project. The frontend 05 work owns finding them; a pre-05 UI mis-reads `Cue` |
| (open, UR-3) | `"opacity": 100` on a video cue whose document has none. Not sanctioned; see `../upstream-reports/UR-3-to-wire-emits-absent-optional-default.md` |
