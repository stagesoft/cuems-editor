<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Merge notes — `002-config-round-trip` into `feat/xml-refactor`

002 FR-048, SC-010. The text for the merge the maintainer performs. `002-config-round-trip` is
local only: it has never been pushed and has no upstream.

## The branch

Branched from `feat/xml-refactor` @ `a3309ab`. The feature's commits, oldest first:

| Commit | What |
|---|---|
| `8e7a0b7` | T001–T003: evidence directory, environment, the refused config instances |
| `62cf24d` | T004–T008: `repair_gates`, `file_locks`, `open`/`inspect` return the script md5 |
| `29b22ee` | US1: the repair gate per project, outliving the connection |
| `1c48be7` | US2: `config_load` and the revision-checked `config_save` |
| `206e233` | US3: payload version 1 restated with JSON booleans |
| `e0f8308` | US4: `node_set` to cuems-nodeconf |
| `1502d64` | US6: media values ported from 869fat84r `0b291d1` |
| `a44c032` | US6: stale media values in the load report |
| `2b1edc4` | US5: documentation, gate G3 |

The polish commit that adds this file follows them. Seven strict xfails stand (G1–G4): see
`tag-readiness.md`. The merge does not make the tag ready.

## 869fat84r: what came in from `0b291d1`

`origin/feat/869fat84r-media-dimensions` @ `0b291d1` (9 commits off `d9e0a39`) was **ported onto
the object line, never merged** (spec Q5 = C, research R11). Commit `1502d64` names the source
commits; `a44c032` the decision logic.

| File | Came in | Source commit |
|---|---|---|
| `CuemsDBModel.py` | the `Media` columns `pixel_width`, `pixel_height`, `file_size`, `file_md5`; the extended `all_fields`; `MEDIA_ADDED_COLUMNS`, `missing_media_columns`, `ensure_media_columns` (verbatim) | `83d8460`, `cd37792` |
| `CuemsProjectManager.py` | `ensure_media_columns(database)` at start-up, logged and re-raised (verbatim) | `83d8460` |
| `repair_durations.py` | the migration after the `--apply` backup; the dry run on a migrated temporary copy. Nothing else | `83d8460` |
| `CuemsDBMedia.py` | `DIMENSIONS_PROBE_TIMEOUT`, `probe_dimensions`, `media_file_size`; `new(…, md5=None)` storing the pixel size (movies), the size and the md5, normalised with `CuemsDBProject._md5` | `83d8460`, `cd37792` |
| `CuemsUpload.py` | `received_md5` passed to `db.media.new`; the relink guard (`could not relink …`) | `cd37792`, `b29d40e` |
| `CuemsDBProject.py` | `PIXEL_KEYS`, `STORED_KEYS`, `_positive_int`, `_md5`, `_valid`, `dimensions_of_row` (its plain dict filled with `update()`), `db_dimensions_resolver` (verbatim); `_allowed_keys`, `_set_stored`, `_fix_one_media` and the walk **rewritten for objects** (cue identity, attribute setters); `media_staleness`, the object form of `stale_changes`'s decisions | `83d8460`, `cd37792` |

**Not taken: the `pyproject.toml` hunk** (spec S1). `0b291d1` raises the pin to
`cuemsutils>=0.1.0rc15`; this branch keeps `>=0.1.0rc16,<0.1.1` and `debian/control` unchanged. Its
SPDX header lines were not taken either.

**Deferred** (spec M9), to a follow-on feature:
- `CuemsMediaRefresh.py`: `refresh_media_before_load`, `check_media_on_open`, `_IN_PROGRESS`,
  `_OPEN_IN_PROGRESS`, the indexer;
- the save-time re-probe (`_save_resolvers` → `_verify_row_for_save`, `REFRESH_DEADLINE_S`);
- `media_report`, `plan_media_refresh`, `MediaFileCheck`, `_light_media_blocks`, `stale_by_file`,
  `cap_report_files`, the `_FAILED/_VERIFIED/_INDEX_FAILED` marks, `mark_index_failed`;
- `media_check_report` and `send_to_project_sessions`;
- `repair_durations`' stored-value re-measurement (`_check_stored`, `--no-md5`, `DIMS_CHANGED`,
  `MD5_CHANGED`);
- `CuemsDBMedia`'s `MediaProbe`, `probe_media`, `PROBE_*`, and the video-index helpers (`new()`
  does not use them);
- `tests/test_media_refresh.py`, and the parts of `tests/test_media_dimensions.py` that exercise
  any of the above.

**The collision surface for that follow-on feature**, verbatim from spec M9:

> **Collision surface for the follow-on feature.** It is bound by Q6:
> - Its findings enter `document_load_report.media_repairs[]` (FR-046). It sends no frame of its own
>   that gates a save.
> - `GateState` is the only per-project report state. Any in-flight registry it brings is request
>   de-duplication and lives outside `GateState` (Q8).
> - Its re-probe changes library rows. That invalidates an outstanding report through FR-045's rows
>   digest, not through a second identity.
> - Its script reader must be the library's object load, not `_light_media_blocks` (M10).
> - It lands in `CuemsDBProject.py` beside FR-038's object walk, and calls it rather than copying
>   it.

## `cuems-frontend` handover

Consumers and their lines are in `contracts/ws-messages.md`, "Consumers of each changed message"
(measured at `cuems-frontend` `f5453a3`).

**Workarounds this feature retires** (SC-010):

| Workaround | Where | Retired by |
|---|---|---|
| Reload the project on reconnect, and re-acknowledge after it | `src/app/services/projects/load-report.service.ts:50-52`, `:200-203` | FR-006 to FR-011: the gate is per project and an acknowledgment survives a reconnect with the same `session_id` (contracts, "Repair gate frames") |
| The `'True'` string branch for `enabled` | `src/app/components/projects/project-edit/sequence/sequence.component.ts:479` | FR-001 to FR-004: version 1 is restated with JSON booleans (contracts, "Restated version 1") |
| The `"True"`/`"False"` arm of the `adopted`/`online` type union and its dual read | `src/app/services/projects/projects.service.ts:75-76`, `src/app/components/nodes/node-adoption.component.ts:201` | the same |

**New and changed frames**, by `contracts/ws-messages.md` section:
- "`config_load`: new": `config_load`, and `config_load_failed`;
- "`config_save`: changed": `base_revision` is required; the reply is
  `{schema, project_uuid, revision, restart}`, not `"OK"`; `network_map` is refused;
- "`config_conflict`: new", "`config_save_refused` / `config_load_failed`: new",
  "`config_changed`: new";
- "`node_set`: new": `node_set` and `node_set_refused` (reasons `unavailable`, `timeout`,
  `nodeconf_error`, `not_operator_field`, `invalid_value`);
- "`document_load_report`: two new optional keys": `media_repairs` and `acknowledgment_required`.
  Gate the save UI on `acknowledgment_required`, not `outcome`;
- "Documentation-only rows": `project_save`'s value is `{"CuemsScript": …}` alone; the descriptor
  `instance` is not directly usable until `cuems-frontend` UR-1 is fixed; `network_map`'s node
  `uuid` renders as text.

Payload version stays 1. The protocol document is `tests/ws-command-responses.txt`.
