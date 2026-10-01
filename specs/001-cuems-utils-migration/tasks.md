<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Tasks: cuemsutils public-surface migration

**Input**: Design documents from `/specs/001-cuems-utils-migration/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The spec and constitution IV require them (smoke, wire captures, failing-first silent-wrong tests, recovery-path tests). Write each test so it fails before the fix it guards, and keep the failing run when the task says to.

**Organization**: Phases follow the user stories in spec.md. Milestone 1 is US1–US3 and US5–US7. Milestone 2 is US4 and US8. Census zero is the milestone 1 exit and does not wait for milestone 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: User story for story phases only
- Every task names a file path

## Path Conventions

Single package: `src/cuemseditor/`, `tests/` at the repository root. Feature docs stay under `specs/001-cuems-utils-migration/`.

## Phase 1: Setup (evidence that must exist before `src/` changes)

**Purpose**: Record the broken import and the payloads the later tests compare against. No `src/` edit in this phase.

- [ ] T001 Record `hatch run python -c "import cuemsutils; print(cuemsutils.__version__, cuemsutils.__file__)"` in `specs/001-cuems-utils-migration/evidence/environment.txt`. Expected version is `0.1.0rc16` from `../cuems-utils/src` or an install of that same version (quickstart.md §0)
- [ ] T002 Run `hatch run python -c "import cuemseditor.CuemsWsServer"` and save the `ModuleNotFoundError: No module named 'cuemsutils.create_script'` traceback in `specs/001-cuems-utils-migration/evidence/import-failure.txt` (FR-004, research R1)
- [ ] T003 [P] Reconstruct `create_script()` by running the last `cuemsutils` release that still ships `cuemsutils.create_script`. Save the payload, the release version, and a checksum in `specs/001-cuems-utils-migration/evidence/create-script-baseline.json` (FR-008, research R10). Do not edit `src/`
- [ ] T004 [P] Capture the current `CuemsDBProject.load_xml` dict, before any edit to `src/cuemseditor/CuemsDBProject.py`, for `tests/fixtures/script_minimal.xml` only. Do not add documents from `../cuems-utils/tests/golden/xml`: that tree may hold a superseded state. Write the capture under `specs/001-cuems-utils-migration/evidence/project-capture/` and name the fixture in a sibling `README.md` (FR-010). Do not regenerate these bytes later to make a test pass (FR-040). Schema truth is `../cuems-utils/src/cuemsutils/xml/schemas/`, not `MANIFEST.sha256`

---

## Phase 2: Foundational (blocks every user story)

**Purpose**: Freeze what the captures mean so later tasks do not reinterpret them.

**⚠️ CRITICAL**: No user story work until T001–T005 are done.

- [ ] T005 Write `specs/001-cuems-utils-migration/evidence/README.md` stating that files in this directory are immutable, that a re-baseline of the editor capture is a recorded diff and at most one, that `../cuems-utils/tests/golden/xml` is not frozen here because it may be superseded and is restated in `cuems-utils` after the system refactoring (the XSD under `../cuems-utils/src/cuemsutils/xml/schemas/` is the schema), that `doc_version` is the on-disk marker and is never a wire key, and that the payload version is a different integer (data-model.md, research R12)

**Checkpoint**: Baselines exist. User Story 1 can start.

---

## Phase 3: User Story 1 — The editor starts again (Priority: P1) 🎯 MVP

**Goal**: `cuemseditor` imports against `cuemsutils` 0.1.0rc16. The constructor still calls `create_script()` until US2.

**Independent Test**: `tests/test_import_smoke.py` passes. All six existing test files collect. The seven `TestNetworkMapWatcher` / `TestNodeconfAvailableFlag` failures are gone with no edit to `tests/test_nodelist_actions.py`. Constructing `CuemsWsServer` still fails, and that failure is recorded rather than called a listening success (FR-003).

### Tests for User Story 1

- [ ] T006 [US1] Add `tests/test_import_smoke.py` that imports every module under `cuemseditor`. Run it before T007 and save the failure in `specs/001-cuems-utils-migration/evidence/smoke-failing-first.txt` (FR-002, constitution IV.1)

### Implementation for User Story 1

- [ ] T007 [US1] In `src/cuemseditor/CuemsWsServer.py`, change only the `cuemsutils.create_script` import so `new_uuid` comes from `cuemsutils.helpers` and `create_script` is not imported (FR-001, research R1). Leave the `create_script()` call in `__init__`
- [ ] T008 [US1] Run `hatch test` and save the output in `specs/001-cuems-utils-migration/evidence/suite-after-import.txt` (FR-004). Do not edit `tests/test_nodelist_actions.py`. `tests/test_media.py` and `tests/test_repair_durations.py` must collect
- [ ] T009 [US1] After T007 and before any other `src/` edit, capture the `initial_template` envelope `{"type":"initial_template","value":{"CuemsScript": ...}}` from the T003 baseline, and capture `initial_mappings` without calling `CuemsWsServer.__init__` (it still names `create_script`), into `specs/001-cuems-utils-migration/evidence/initial-template.json` and `specs/001-cuems-utils-migration/evidence/initial-mappings.json` (FR-010, research R11)
- [ ] T010 [US1] Record in `specs/001-cuems-utils-migration/evidence/listening-blocked.txt` that `CuemsWsServer()` still raises because `__init__` calls `create_script()`. Do not claim FR-003 here

**Checkpoint**: The process imports. It does not listen yet.

---

## Phase 4: User Story 2 — Public surface, template stand-in (Priority: P1)

**Goal**: `initial_template` is `ConfigManager.generate_example(SchemaName.SCRIPT)`. The census test exists and stays red until the later stories delete the remaining `cuemsutils.xml` imports. The adoption gap is an upstream report, not an import of `partition_by_adoption`.

**Independent Test**: The server listens on `:9092` (FR-003). `initial_template` differs from `evidence/create-script-baseline.json` only by the deltas named in `tests/ws-command-responses.txt`. `tests/test_public_surface.py` is present; it is not required to pass until the milestone 1 exit.

### Tests for User Story 2

- [ ] T011 [P] [US2] Add `tests/test_public_surface.py` (FR-005, FR-006) scanning `src/` as text per `specs/001-cuems-utils-migration/contracts/public-surface.md`: no `cuemsutils.xml`, `cuemsutils.config`, `cuemsutils.create_script`, or `cuemsutils.timeoutloop`; no `CuemsParser`, `XmlReaderWriter`, `create_script`, `get_nodes_by_adoption`, `partition_by_adoption`, `node_type`, or `NodeType.`; the single allowed exception is `ProjectMappings` in `src/cuemseditor/cli.py`; the test fails if it scans zero files or finds zero `cuemsutils` imports. Run it once and keep the red output in `specs/001-cuems-utils-migration/evidence/public-surface-before.txt`
- [ ] T012 [P] [US2] Write `specs/001-cuems-utils-migration/upstream-reports/UR-1-no-public-adoption-partition.md` asking for a public non-mutating adoption partition and citing `cuems-engine` `specs/008-cuems-utils-migration/upstream-reports/UR-1-no-public-adoption-partition.md` (FR-009, research R5). Do not import `cuemsutils.xml`

### Implementation for User Story 2

- [ ] T013 [US2] In `src/cuemseditor/CuemsWsServer.py`, replace the `create_script()` call with `ConfigManager.generate_example(SchemaName.SCRIPT)`. Keep the message type `initial_template` and the `{"CuemsScript": ...}` envelope (FR-008, research R10). Do not call `cuemsutils.xml.descriptor`
- [ ] T014 [US2] Add `tests/test_initial_template.py` asserting the served payload differs from `specs/001-cuems-utils-migration/evidence/create-script-baseline.json` only by the deltas the test lists (keys, key order, value types, placeholder values)
- [ ] T015 [US2] Write those deltas into `tests/ws-command-responses.txt` next to the `initial_template` line (FR-008, FR-042)
- [ ] T016 [US2] Start the server against a temporary library and record that it accepts a WebSocket connection on `:9092` in `specs/001-cuems-utils-migration/evidence/listening.txt` (FR-003). This closes User Story 1 scenario 2

**Checkpoint**: The service listens. The census is not zero yet.

---

## Phase 5: User Story 3 — Projects open and save with two deltas (Priority: P1)

**Goal**: Script I/O goes through `CuemsScript`. The `type: project` value matches the capture except for two deltas. A load writes nothing.

**Independent Test**: `tests/test_project_payload.py` passes against `evidence/project-capture/`. Opening a project changes zero bytes of its script file. `../cuems-utils/tests/golden/` is not a pass condition.

### Tests for User Story 3

- [ ] T017 [US3] Add `tests/test_project_payload.py` before changing `src/cuemseditor/CuemsDBProject.py`. It must fail on today's `XmlReaderWriter` output. Assert the `{"type":"project"}` value differs from `specs/001-cuems-utils-migration/evidence/project-capture/` only by (a) `schemaLocation` absent and (b) `Media.duration` as `{"CTimecode": "HH:MM:SS.mmm"}`; key order otherwise unchanged; cue booleans stay `"True"` / `"False"`; `doc_version` is absent; the script file checksum is unchanged after open. Do not assert `../cuems-utils/tests/golden/MANIFEST.sha256`. If a golden contradicts `../cuems-utils/src/cuemsutils/xml/schemas/`, record it for regeneration in `cuems-utils`; do not edit the golden from this repository (FR-011, FR-014, FR-040, contracts/project-payload.md)

### Implementation for User Story 3

- [ ] T018 [US3] In `src/cuemseditor/CuemsDBProject.py` `load` / `load_xml`, call `CuemsScript.load_with_report(path)` and return `script.to_wire()` once. Do not call `CuemsScript.load()` (it discards the report). Do not walk or edit that dict. Do not write the file (FR-012, FR-014, research R3)
- [ ] T019 [US3] In `src/cuemseditor/CuemsDBProject.py`, replace `CuemsParser` in `update` and `new` with `CuemsScript.from_json` (this path does not repair). Replace `save_xml`'s `XmlReaderWriter.write_from_object` with `CuemsScript.save` (FR-013, research R3, R4)
- [ ] T020 [US3] In `duplicate` in `src/cuemseditor/CuemsDBProject.py`, `load_with_report` the source and `save` under `new_unix_name` only. Do not overwrite the source path. Do not add `validate_fade_durations_in_contents` (research R9; `duplicate` stays unvalidated beyond library load)
- [ ] T021 [US3] In `update_projects_existed_media` in `src/cuemseditor/CuemsDBProject.py`, use the `CuemsScript` from `load_with_report`. Do not `to_wire()` and parse again (plan.md script I/O table)
- [ ] T022 [US3] Rewrite `_fix_media_durations` and `fix_media_durations_in_contents` in `src/cuemseditor/CuemsDBProject.py` so they assign `CTimecode` on the loaded object from the media DB. They must not edit the wire dict. The library `media_duration` rule is unrepairable and has no DB (research R2, FR-015). In `tests/test_project_payload.py`, assert a client payload whose media duration is the string `00:00:00.000` is accepted by `from_json` and then corrected from the database by this walker, not rejected (spec edge case; constitution I)
- [ ] T023 [US3] Delete `_clean_dangling_targets`, `_nullify_dangling_refs`, and `_collect_cue_ids` from `src/cuemseditor/CuemsDBProject.py`. Do not port the `action_target` clear: `action_target_resolves` is `repairable=False` for `ActionCue` and for `FadeCue` via the MRO, and clearing it to `None` fails `action_target_required` (research R2, FR-015)
- [ ] T024 [US3] Replace `tests/test_dangling_targets.py` with a skipped module whose reason names `cuemsutils` `xml/validators.py` rules `target_resolves` (library repairs `Cue.target`) and `action_target_resolves` (library refuses). Record the same reason in `specs/001-cuems-utils-migration/evidence/test-retirements.md` (FR-017). Do not re-assert those rules here
- [ ] T025 [US3] Keep `validate_fade_durations_in_contents` on the raw client payload in `update` and `new` only, with the same `ValueError` text, in `src/cuemseditor/CuemsDBProject.py` (FR-016)
- [ ] T026 [US3] Record deltas (a) and (b) for the `type: project` frame in `tests/ws-command-responses.txt`, and name `cuems-frontend` `src/app/services/projects/projects.service.ts:120` (`schemaLocation: string`) as the frontend's edit (FR-018, FR-042)

**Checkpoint**: Open and save use the public script API. Dangling walks are gone.

---

## Phase 6: User Story 5 — Duration tool lists projects that need a save (Priority: P2)

**Goal**: Pass A still corrects the database. Pass B writes no script. The tool reports *needs a save*.

**Independent Test**: `hatch test tests/test_repair_durations.py` passes. After `--apply`, every `script.xml` checksum is unchanged and the *needs a save* list matches the fixture.

Depends on T022: the duration comparison shares the object walker's `CTimecode` rules. `src/cuemseditor/repair_durations.py` is not edited by US3, so this phase can follow US3 immediately.

### Tests for User Story 5

- [ ] T027 [US5] In `tests/test_repair_durations.py`, add a test that a structured media duration (a `CTimecode`, or `{"CTimecode": "HH:MM:SS.mmm"}` on the wire) differing from the database value is reported. Run it against the pre-change `TIMECODE_SHAPE.match` guard at `src/cuemseditor/repair_durations.py` and save the failure in `specs/001-cuems-utils-migration/evidence/timecode-guard-failing-first.txt` before T028 (FR-024, constitution IV.4)

### Implementation for User Story 5

- [ ] T028 [US5] In `src/cuemseditor/repair_durations.py`, delete pass B (`pass_b_xml`, the XML backup, `--xml-only`, and `--db-only`), `TIMECODE_SHAPE`, `CuemsParser`, and `XmlReaderWriter`. Read each script with `CuemsScript.load_with_report`. Compare durations with `CTimecode`. Print each mismatch as *needs a save* with the project, the media, the script value, and the database value. Outcomes remain corrected, unchanged, `SKIPPED_INVALID`, and *needs a save*. Write no script and run no version conversion (FR-023, FR-025, FR-025a, FR-027, contracts/repair-tool.md)
- [ ] T029 [US5] Update `tests/test_repair_durations.py`: keep the pass A cases (dry-run, `--apply` plus database backup, idempotence, trash, missing database); assert every `script.xml` checksum is unchanged after `--apply`; assert the *needs a save* list; retire the pass B assertions in the file header with this contract as the reason; remove the `XmlReaderWriter` import (FR-007, FR-026)
- [ ] T030 [US5] State in the `repair_durations` module docstring, in `--help`, and in `CLAUDE.md` field notes that script files change only when an operator saves in the editor, and that until that save the engine plays the file on disk (FR-027, FR-027a)

**Checkpoint**: This repository writes scripts only from the editor save path.

---

## Phase 7: User Story 6 — The node list stays correct (Priority: P2)

**Goal**: Merged nodes carry `node_role` and the library wire form. `NetworkMap` is gone. `node_status.alive` stays a different fact from `online`. A duplicate node identity is not retried.

**Independent Test**: `tests/test_node_merge.py` passes, including a run that failed while `basic_fields` still said `node_type`. `tests/test_nodelist_actions.py` stays green aside from the one mock edit in T033.

Depends on T013 (same file `src/cuemseditor/CuemsWsServer.py`). Not parallel with US2.

### Tests for User Story 6

- [ ] T031 [US6] Add `tests/test_node_merge.py` asserting a converted node whose `to_wire()` has `node_role` and no `node_type` still has `node_role` after `merge_node_data`. Run it before T034 and save the failure in `specs/001-cuems-utils-migration/evidence/node-type-failing-first.txt` (FR-028). Do not re-implement or re-test the node model: no assertion of `NodeRole` membership or `Uuid` parsing (FR-030)
- [ ] T032 [US6] Extend `tests/test_node_merge.py` so a merged `initial_mappings` node has string `uuid`, `adopted` and `online` as `"True"` or `"False"` (not JSON `true`/`false`), key `node_role`, and the mapping node's output blocks preserved (FR-031, research R6). Any difference from `evidence/initial-mappings.json` is either an enumerated delta in the test or a bug
- [ ] T033 [P] [US6] Add `tests/test_node_status_distinct.py` asserting `node_status` still relays engine `cluster_status` (`alive` is the sub-second set) and that nothing copies `alive` onto a node's `online` (~30 s discovery). Assert `nodelist_modify` relays the engine error string unchanged, including `Node <uuid> not found`, with no retry (FR-033, FR-036). Do not edit `tests/test_nodelist_actions.py` in this task

### Implementation for User Story 6

- [ ] T034 [US6] In one commit, in `src/cuemseditor/CuemsWsServer.py` delete `from cuemsutils.xml import NetworkMap` and replace `NetworkMap.get_nodes_by_adoption` with `_partition_by_adoption`: read `adopted` on each `network_map["node_list"]` entry, return the library node objects, write nothing. The docstring names `specs/001-cuems-utils-migration/upstream-reports/UR-1-no-public-adoption-partition.md` as the successor (FR-009, research R5). In that same commit, change only `TestNodeconfAvailableFlag._reload` in `tests/test_nodelist_actions.py` so it no longer patches `NetworkMap`; leave every assertion unchanged and say so in the commit message (FR-041)
- [ ] T035 [US6] Change `merge_node_data` in `src/cuemseditor/CuemsWsServer.py` so status fields come from `node.to_wire()` and output blocks stay from the existing mapping node. Compare a JSON identity with a map identity only through `cuemsutils.tools.coerce_identity` (FR-034, FR-035). The field list and the docstring that names `node_type` (`basic_fields` and the docstring above `merge_node_data`) name `node_role` instead. No in-memory comparison of a typed `adopted` or `online` against the string `"True"` (FR-029)
- [ ] T036 [US6] Make `reload_network_map_nodes` in `src/cuemseditor/CuemsWsServer.py` return the loaded lists and not assign `self.mappings_dict`. Assign those fields on the event-loop thread in `notify_all_node_list_update` and in `src/cuemseditor/CuemsWsUser.py` `nodelist_get` (research R8, constitution II). Leave the `__init__` call on the constructing thread. Both the refresh path and the serve path (`initial_setting_message`) still set `mappings_dict['nodeconf_available']` from a fresh `nodeconf_available()` call, not from a cached value (FR-032 milestone 1). Assert that in `tests/test_node_merge.py`
- [ ] T037 [US6] In `src/cuemseditor/CuemsWsServer.py`, if `cuemsutils.errors.node_identity_collision_message(path, exc)` is not `None`, do not retry, log once per distinct identity, keep serving the last good node list, and broadcast `{"type":"network_map_error","value":{"kind":"duplicate_identity","identity":"<string>","file":"<path>"}}` to all sessions and to each session that connects while it stands. A later successful read broadcasts `{"type":"network_map_error","value":null}` and then the usual refresh. Other exceptions keep the existing retry. `identity` is the string form (FR-036a, research R13). Add the shape to `tests/ws-command-responses.txt`
- [ ] T038 [US6] Extend `tests/test_node_merge.py` with a duplicate-identity map: no retry, last list retained, error broadcast, clear broadcast after a later good read (FR-036a)

**Checkpoint**: `node_type` is gone from `src/`. `nodeconf_available` is still injected into `mappings_dict` at both current sites and is still sampled live (FR-032 milestone 1). Do not move it yet.

---

## Phase 8: User Story 7 — The pin refuses a library that moved past this editor (Priority: P3)

**Goal**: `cuemsutils` is bounded on both sides, in `pyproject.toml` and in `debian/control`. The tag message exists and is not ready.

**Independent Test**: `grep cuemsutils pyproject.toml` shows `cuemsutils>=0.1.0rc16,<0.1.1`. `debian/control` has `python3-cuemsutils (>= 0.1.0rc16)` and `python3-cuemsutils (<< 0.1.1~)`. `debian/bookworm` was not deleted.

Can run beside US5 and US6 (different files) once US1 has landed. Do not lower the floor to make a test pass.

- [ ] T039 [P] [US7] Set the `cuemsutils` dependency in `pyproject.toml` to `cuemsutils>=0.1.0rc16,<0.1.1` (FR-037)
- [ ] T040 [P] [US7] Bring `debian/` onto `feat/xml-refactor` from `origin/debian/bookworm` at `72f952a` so the changelog history is carried (FR-038). Do not delete, rename, or force-update `debian/bookworm`
- [ ] T041 [US7] In `debian/control`, add `python3-cuemsutils (>= 0.1.0rc16), python3-cuemsutils (<< 0.1.1~)` beside `${python3:Depends}`. Add a `debian/changelog` entry for this migration (FR-038, contracts/package-relations.md)
- [ ] T042 [US7] Write `specs/001-cuems-utils-migration/debian-consolidation.md` listing every `debian/` change on this branch by commit and file, plus anything on `debian/bookworm` not in `72f952a` (expected: none). Do not apply that list yourself (FR-038a)
- [ ] T043 [P] [US7] Write the candidate tag message under `../.xml-refactor-tag-messages/` naming `feat/nodelist-adoption-api` through `886f649`, `cuems-engine` `feat/nodelist-modify-dispatch`, and `cuems-nodeconf` `feat/nodelist-modify-hardening` (47 commits behind, largely superseded, not resolved here). Do not create, move, or push the tag. State that `cuems-frontend` 05 is outstanding so the message is not ready (FR-039, FR-039a, FR-049)

**Checkpoint**: The package metadata can refuse `0.1.1`.

---

## Phase 9: Milestone 1 exit (blocks milestone 2)

**Purpose**: Census zero is the T049 input for `cuems-utils`. It is not a controller deploy (`to_wire()` wraps duration; there is no payload-version handshake yet).

- [ ] T044 Run the census grep `cuemsutils\.(xml|timeoutloop|create_script)` over `src/` and `hatch test tests/test_public_surface.py`. Both must be clean: zero imports of `cuemsutils.xml`, `cuemsutils.create_script`, and `cuemsutils.timeoutloop`, and zero uses of `CuemsParser`, `XmlReaderWriter`, `create_script`, and `get_nodes_by_adoption` (FR-005, FR-006). Write the command output in `specs/001-cuems-utils-migration/evidence/census-zero.md` for the `cuems-utils` flow (FR-048, SC-002). This file is a source announcement, not a package. Do not start US4 or US8 before it exists, and do not cut a controller deploy from this checkpoint (spec clarification 2026-10-01)

---

## Phase 10: User Story 4 — The operator is told about a repair (Priority: P2, milestone 2)

**Goal**: A repaired load emits `document_load_report`. An unrepairable load emits `document_load_failed`. `project_save` is refused until that session acknowledges that report, and the original is in `trash/` before the first overwrite.

**Independent Test**: `tests/test_document_load_report.py` passes against a temporary library. A second session's acknowledgment does not unlock the first session's save.

Depends on T018 (`load_with_report` exists). Do not land this before T044. An unknown `type` may be emitted before the UI renders it (FR-050).

### Tests for User Story 4

- [ ] T045 [US4] Add `tests/test_document_load_report.py`. A repairable fixture emits `document_load_report` (never omitted, never `null`) with `file_differs_from_loaded` true when `outcome` is not `clean`, and the script checksum is unchanged. A second open reports the same repairs. An unrepairable fixture (dangling `action_target`, or a document newer than the library) emits `document_load_failed` with `document`, `cue_id`, `field`, the library `message`, and `next_steps` exactly `["restore_from_conversion_backup", "correct_field_by_hand", "remove_document"]`. A following `project_list` on the same connection succeeds (FR-019, FR-020, data-model.md)
- [ ] T046 [US4] In `tests/test_document_load_report.py`, assert `project_save` before `repair_acknowledge` returns `repair_save_refused` with `reason` `unacknowledged` and does not change the file; after that session acknowledges that `report_id`, `trash/` holds a byte-identical copy of the original and the saved file is the repaired document; if the copy fails, `reason` is `preserve_failed` and `CuemsScript.save` is not called; another session's acknowledgment does not unlock the save (FR-021, FR-021a)

### Implementation for User Story 4

- [ ] T047 [US4] On the session that issued `project_load`, store `project_uuid`, `report_id` (from `cuemsutils.helpers.new_uuid`), `outcome`, `file_differs_from_loaded`, and `acknowledged` (starts false) in `src/cuemseditor/CuemsWsUser.py` / the server session dict. Clear them on `project_unload`, session close, and any new load of the document. Another session must not read them (data-model.md, constitution II)
- [ ] T048 [US4] From `send_project` in `src/cuemseditor/CuemsWsUser.py`, emit `document_load_report` on every successful open, including `outcome` `clean`, and emit `document_load_failed` instead of `type: project` only when `load_with_report` raises `ValidationError`. `SchemaError`, `IngestError`, and `OSError` stay on the existing per-session error path and are not given `next_steps` (data-model.md). Shapes are in `specs/001-cuems-utils-migration/contracts/ws-messages.md`. Render `previous_value` and `substituted_value` as JSON-safe forms (string form of a `CTimecode`, `null` for `None`). Do not invent repairs the library did not return
- [ ] T049 [US4] In `received_project` (`project_save`) in `src/cuemseditor/CuemsWsUser.py`, refuse with `repair_save_refused` when this session's report for this project is not `clean` and `acknowledged` is false. Add inbound `repair_acknowledge` carrying `project_uuid` and `report_id`. When `file_differs_from_loaded` is true, `CopyMoveVersioned.move` the on-disk script into that project's `trash/` with a name that recovers the project and the date, then call `CuemsScript.save`. If the move fails, do not call `save` (FR-021, FR-021a)
- [ ] T050 [US4] Add `document_load_report`, `document_load_failed`, `repair_acknowledge`, and `repair_save_refused` to `tests/ws-command-responses.txt` (FR-022)
- [ ] T051 [US4] When `duplicate`'s source `outcome` is not `clean`, add an optional `report` key on the `project_duplicate` reply in `src/cuemseditor/CuemsWsUser.py`, same shape as `document_load_report`'s `value`. Do not overwrite the source and do not require acknowledgment (research R9). Note the optional key in `tests/ws-command-responses.txt` as a non-bump (FR-047a)

**Checkpoint**: A repair cannot reach disk unseen on `project_save`.

---

## Phase 11: User Story 8 — Schema forms and a separate node wire (Priority: P3, milestone 2)

**Goal**: Payload version 1 is the first frame. `initial_mappings` no longer carries nodes or `nodeconf_available`. The descriptor is served through `ConfigManager`. `initial_template` is retired.

**Independent Test**: `tests/test_payload_version.py` and `tests/test_schema_descriptor.py` pass. `nodeconf_available` is on `node_list` and on the `nodelist_get` reply, and absent from the project-mappings payload and from each node.

Depends on T044 and on T016 (the server connects). Do not remove keys from `initial_mappings` before T054 has sent `payload_version` (FR-050). T055 is the task that removes them.

### Tests for User Story 8

- [ ] T052 [US8] Add `tests/test_payload_version.py` asserting the first frame on connect is `{"type":"payload_version","value":1}` and that it arrives before any `initial_*` frame. The test fails if the integer changes without a matching bump row in `tests/ws-command-responses.txt` (FR-047, FR-047a). A connection that never sends this type is version 0
- [ ] T053 [P] [US8] Add `tests/test_schema_descriptor.py`. `schema_descriptor` returns `ConfigManager.get_schema_descriptor` types with `key`, `fields` (name, xsd type, `required`, `repeated`, order, kind, `enum_values`, default, repairability), and `instance`. `config_save` persists through `save_network_map`, `save_settings`, `save_project_mappings`, or `save_project_settings`. It rejects schema `script`, schema `hardware_outputs`, and any write of `default_mappings.xml` (FR-045, data-model.md)

### Implementation for User Story 8

- [ ] T054 [US8] Send `payload_version` as the first frame in the connect path in `src/cuemseditor/CuemsWsServer.py` (the path that today sends `initial_template` and `initial_mappings`), before those frames (FR-047). Record version 1 and the bump rules in `tests/ws-command-responses.txt`
- [ ] T055 [US8] After T054, split the wire in `src/cuemseditor/CuemsWsServer.py` and `src/cuemseditor/CuemsWsUser.py`: `initial_mappings` carries project output mappings only; new `node_list` carries `nodes`, `new_nodes`, and envelope `nodeconf_available` sampled when the frame is built. `watch_network_map` pushes `node_list` to all sessions. `nodelist_get` returns `node_list` to the caller. `nodeconf_available` is absent from the project-mappings payload and from each node, and it is not a schema field (FR-032 milestone 2, FR-046, research R14)
- [ ] T056 [US8] Add actions `schema_descriptor` and `config_save` in `src/cuemseditor/CuemsWsUser.py` per `specs/001-cuems-utils-migration/contracts/ws-messages.md`. Reach the descriptor only through `ConfigManager.get_schema_descriptor(SchemaName)`. A successful `network_map` save still refreshes all sessions the way `nodelist_modify` already does. Do not import `cuemsutils.xml.descriptor` (FR-045, D34)
- [ ] T057 [US8] Stop sending `initial_template` from `src/cuemseditor/CuemsWsServer.py`. Document in `tests/ws-command-responses.txt` that clients build from the descriptor's per-type `instance` instead (FR-008a). This removal is a payload-version bump already covered by version 1; do not ship it without T054
- [ ] T058 [US8] Write `specs/001-cuems-utils-migration/evidence/frontend-handover.md` naming `cuems-frontend` `src/app/services/projects/projects.service.ts:120`, `src/app/components/settings/settings.component.ts`, `src/app/components/projects/project-show/audio-mixer/audio-mixer.component.ts:80`, and `src/app/components/projects/project-show/video-mixer/video-mixer.component.ts:94`, including that the two mixers read `localStorage` key `initial_mappings` and need an eviction story (FR-018, FR-046). Do not edit the frontend here. Update the tag message from T043 so it stays unready until that frontend consumes the report and these families (FR-049)

**Checkpoint**: Milestone 2 is on the branch. The tag is still the maintainer's to cut.

---

## Phase 12: Polish

**Purpose**: Close the exit list. Do not fix carried constitution violations in passing.

- [ ] T059 Run `specs/001-cuems-utils-migration/quickstart.md`. For every step this environment cannot perform (live controller UI, applying `debian-consolidation.md` onto `debian/bookworm`, a frontend rendering the report), add a *not performed* row with the reason in `specs/001-cuems-utils-migration/evidence/not-performed.md` (FR-044). An omitted row is not a pass
- [ ] T060 [P] Confirm `CuemsDBProject.delete_from_trash`, the `ProjectMappings` import in `src/cuemseditor/cli.py`, and `script_file_name` were not changed. They stay carried in `specs/001-cuems-utils-migration/plan.md` Complexity Tracking (FR-043)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup. Blocks every story
- **US1 (Phase 3)**: depends on Foundational. Blocks US2, US3, US5, US6, US7
- **US2 (Phase 4)**: depends on US1. Blocks US6 (same `CuemsWsServer.py`) and the listening half of US1
- **US3 (Phase 5)**: depends on US1. Can run in parallel with US2 (different files: `CuemsDBProject.py` vs `CuemsWsServer.py`) after T009's captures exist
- **US5 (Phase 6)**: depends on US3 (shared duration comparison) and on T004's fixtures still matching the tool's fixture names
- **US6 (Phase 7)**: depends on US2 T013. Can run in parallel with US5
- **US7 (Phase 8)**: depends on US1. Can run in parallel with US5 and US6 (`pyproject.toml`, `debian/`, tag message)
- **Milestone 1 exit (Phase 9)**: depends on US2, US3, US5, US6, and US7. Blocks US4 and US8
- **US4 (Phase 10)**: depends on the exit and on US3's `load_with_report`
- **US8 (Phase 11)**: depends on the exit and on US6's node merge. `initial_mappings` must not lose keys before T054
- **Polish (Phase 12)**: depends on the stories in scope for the check being run. T059 after US8 if milestone 2 is in scope; the census file T044 is the earlier gate

### User Story Dependencies

- **US1 (P1)**: after Foundational. No other story. Scenario 2 (listening) completes at T016 in US2
- **US2 (P1)**: after US1. Template stand-in does not need US3
- **US3 (P1)**: after US1 and T009. Independent of the node merge
- **US5 (P2)**: after US3. Independent of US6 and US7
- **US6 (P2)**: after US2. Independent of US5 and US7
- **US7 (P3)**: after US1. Independent of US5 and US6
- **US4 (P2, milestone 2)**: after milestone 1 exit and US3
- **US8 (P3, milestone 2)**: after milestone 1 exit, US2, and US6

### Within Each User Story

- Failing-first tests run and are captured before the production edit they guard (T006, T017, T027, T031)
- A task that says "in one commit" (T034) is not split
- `tests/ws-command-responses.txt` is updated in the same story that changes the payload (T015, T026, T037, T050, T051, T054, T057)

### Parallel Opportunities

- T003 and T004 (different evidence files, no `src/` edit)
- T011 and T012 (test file vs upstream report)
- US3 in parallel with US2 after US1
- US5 in parallel with US6 and US7 after their own dependencies
- T039, T040, and T043 (pyproject, debian tree, tag message)
- T033 with T031 (different new test files) before the production node edits
- T052 and T053 (different test files) before the milestone 2 production edits
- T060 alongside T059

### Parallel Example: User Story 2

```bash
# Together, before the template edit:
Task: "T011 tests/test_public_surface.py"
Task: "T012 upstream-reports/UR-1-no-public-adoption-partition.md"

# Then, same file, not parallel:
Task: "T013 generate_example in src/cuemseditor/CuemsWsServer.py"
```

### Parallel Example: after User Story 1

```bash
# Different files:
Task: "T013–T016 US2 CuemsWsServer.py template"
Task: "T017–T026 US3 CuemsDBProject.py script I/O"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 and Phase 2
2. Phase 3 (US1)
3. Stop. Imports succeed, six test files collect, listening is still blocked and recorded

### Milestone 1 (census zero)

1. MVP
2. US2 so the process listens
3. US3, then US5; US6; US7 beside them where the dependencies allow
4. T044. Announce `evidence/census-zero.md` to the `cuems-utils` flow as source state only
5. Do not package or deploy this checkpoint. US4 ships in the same candidate tag, so the save-gate window never lands on its own

### Milestone 2 (coordinated tag, still not cut here)

1. US4 and US8
2. T059
3. Leave the tag message unready until `cuems-frontend` 05 consumes the report and the US8 families

### Task counts

| Phase | Tasks | IDs |
|---|---|---|
| Setup | 4 | T001–T004 |
| Foundational | 1 | T005 |
| US1 | 5 | T006–T010 |
| US2 | 6 | T011–T016 |
| US3 | 10 | T017–T026 |
| US5 | 4 | T027–T030 |
| US6 | 8 | T031–T038 |
| US7 | 5 | T039–T043 |
| Milestone 1 exit | 1 | T044 |
| US4 | 7 | T045–T051 |
| US8 | 7 | T052–T058 |
| Polish | 2 | T059–T060 |
| **Total** | **60** | T001–T060 |

---

## Notes

- Commits are GPG-signed. On `gpg failed to sign`, retry. Do not pass `--no-gpg-sign`
- Do not patch or vendor `../cuems-utils`. A missing public API is an upstream report
- Do not add a node-model test (FR-030). `tests/test_node_merge.py` pins the editor's merge and the wire form, not `NodeRole` or `Uuid` behaviour
- `tests/test_nodelist_actions.py` is edited only in T034
- Suggested MVP scope is User Story 1 only. The first deployable listening process is US1 plus US2
