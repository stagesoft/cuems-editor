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

## `project` frame

Delta (a) of the `project` frame, `projects.service.ts:120`, is added with the User Story 3
handover (T027).
