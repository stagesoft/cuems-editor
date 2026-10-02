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

## Milestone 2 (T061, FR-008, FR-018, FR-046)

The editor sends `{"type":"payload_version","value":1}` first. A UI built for version 0 should
refuse version 1 and say so; that refusal is cuems-frontend 05's. New message types (ignored by
today's UI until 05 renders them): `document_load_report`, `document_load_failed`,
`repair_acknowledge`, `repair_save_refused`, `network_map_error`, `schema_descriptor`, `config_save`.

| File:line | What changes for it |
|---|---|
| `src/app/services/projects/projects.service.ts:120` | `schemaLocation: string` is absent from the `project` value (delta (a)) |
| `src/app/services/projects/projects.service.ts:240` | `initial_template` is no longer sent. Build new scripts from `schema_descriptor("script")`'s per-type `instance` |
| `src/app/services/projects/projects.service.ts:243` | nothing writes `localStorage` `initial_template` any more |
| `src/app/services/projects/projects.service.ts:159` | a template cached there before 001 milestone 2 is never refreshed: evict it on version 1 |
| `src/app/components/settings/settings.component.ts` (`:59` reads `new_nodes`) | the node arrays and `nodeconf_available` move to a `node_list` frame (T058, **not landed**: see `tasks.md`). Also show `network_map_error` |
| `src/app/components/projects/project-show/audio-mixer/audio-mixer.component.ts:80` | reads `localStorage` `initial_mappings`, `value.nodes[].node.audio`. After cuems-utils 013 a mapping node has `devices` / `device` / `class`, not `audio`. The cache needs an eviction story on payload version 1 |
| `src/app/components/projects/project-show/video-mixer/video-mixer.component.ts:94` | same, for `video` |
| (project open / save) | render `document_load_report`, offer `repair_acknowledge` for a non-clean report, handle `repair_save_refused`; render `document_load_failed` with its three `next_steps` |
