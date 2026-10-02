<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Tasks: cuemsutils public-surface migration

**Input**: Design documents from `/specs/001-cuems-utils-migration/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The spec and constitution IV require them (smoke, wire captures, failing-first silent-wrong tests, recovery-path tests). Write each test so it fails before the fix it guards, and keep the failing run when the task says to.

**Source still has the pre-013 keyed sites.** `src/cuemseditor/CuemsDBProject.py` still has `'AudioCue' in item` at line 79 and `CUE_TYPES` at line 385. `src/cuemseditor/CuemsWsServer.py:439` is still a comment on a merge that copies the existing node through. This session does not edit `src/`. T011, T023, T024, and T034 are what fail on that code.

**Organization**: Phases follow the user stories in spec.md. Milestone 1 is US1–US3 and US5–US7. Milestone 2 is US4 and US8. Census zero is the milestone 1 exit and does not wait for milestone 2. The cuems-utils 013 pin is `6213b1603d0a508b6ac7dfb5f46593ba4d870193` (`evidence/cuems-utils-013-landed.txt`). T036's precondition is that SHA in the pin file.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: User story for story phases only
- Every task names a file path

## Path Conventions

Single package: `src/cuemseditor/`, `tests/` at the repository root. Feature docs stay under `specs/001-cuems-utils-migration/`.

## Phase 1: Setup (evidence that must exist before `src/` changes)

**Purpose**: Record the broken import and the payloads the later tests compare against. No `src/` edit in this phase.

- [X] T001 Record `hatch run python -c "import cuemsutils; print(cuemsutils.__version__, cuemsutils.__file__)"` in `specs/001-cuems-utils-migration/evidence/environment.txt`. Expected version is `0.1.0rc16` from `../cuems-utils/src` or an install of that same version (quickstart.md §0)
- [X] T002 Run `hatch run python -c "import cuemseditor.CuemsWsServer"` and save the `ModuleNotFoundError: No module named 'cuemsutils.create_script'` traceback in `specs/001-cuems-utils-migration/evidence/import-failure.txt` (FR-004, research R1)
- [X] T003 [P] Reconstruct `create_script()` by running the last `cuemsutils` release that still ships `cuemsutils.create_script`. Save the payload, the release version, and a checksum in `specs/001-cuems-utils-migration/evidence/create-script-baseline.json` (FR-008, research R10). Do not edit `src/`
- [X] T004 [P] Capture the current `CuemsDBProject.load_xml` dict, before any edit to `src/cuemseditor/CuemsDBProject.py`, for `tests/fixtures/script_minimal.xml` only. Do not add documents from `../cuems-utils/tests/golden/xml`: that tree may hold a superseded state. Write the capture under `specs/001-cuems-utils-migration/evidence/project-capture/` and name the fixture in a sibling `README.md` (FR-010). Do not regenerate these bytes later to make a test pass (FR-040). Schema truth is `../cuems-utils/src/cuemsutils/xml/schemas/`, not `MANIFEST.sha256`

---

## Phase 2: Foundational (blocks every user story)

**Purpose**: Freeze what the captures mean so later tasks do not reinterpret them.

**⚠️ CRITICAL**: No user story work until T001–T005 are done.

- [X] T005 Write `specs/001-cuems-utils-migration/evidence/README.md` stating that files in this directory are immutable, that a re-baseline of the editor capture is a recorded diff and at most one, that `../cuems-utils/tests/golden/xml` is not frozen here because it may be superseded and is restated in `cuems-utils` after the system refactoring (the XSD under `../cuems-utils/src/cuemsutils/xml/schemas/` is the schema), that `doc_version` is the on-disk marker and is never a wire key, and that the payload version is a different integer (data-model.md, research R12)

**Checkpoint**: Baselines exist. User Story 1 can start.

---

## Phase 3: User Story 1 — The editor starts again (Priority: P1) 🎯 MVP

**Goal**: `cuemseditor` imports against `cuemsutils` 0.1.0rc16. The constructor still calls `create_script()` until US2.

**Independent Test**: `tests/test_import_smoke.py` passes. All six existing test files collect. The seven `TestNetworkMapWatcher` / `TestNodeconfAvailableFlag` failures are gone with no edit to `tests/test_nodelist_actions.py`. Constructing `CuemsWsServer` still fails, and that failure is recorded rather than called a listening success (FR-003).

### Tests for User Story 1

- [X] T006 [US1] Add `tests/test_import_smoke.py` that imports every module under `cuemseditor`. Run it before T007 and save the failure in `specs/001-cuems-utils-migration/evidence/smoke-failing-first.txt` (FR-002, constitution IV.1)

### Implementation for User Story 1

- [X] T007 [US1] In `src/cuemseditor/CuemsWsServer.py`, change only the `cuemsutils.create_script` import so `new_uuid` comes from `cuemsutils.helpers` and `create_script` is not imported (FR-001, research R1). Leave the `create_script()` call in `__init__`
- [X] T008 [US1] Run `hatch test` and save the output in `specs/001-cuems-utils-migration/evidence/suite-after-import.txt` (FR-004). Do not edit `tests/test_nodelist_actions.py`. `tests/test_media.py` and `tests/test_repair_durations.py` must collect
- [X] T009 [US1] After T007 and before any other `src/` edit, capture the `initial_template` envelope `{"type":"initial_template","value":{"CuemsScript": ...}}` from the T003 baseline, and capture `initial_mappings` without calling `CuemsWsServer.__init__` (it still names `create_script`), into `specs/001-cuems-utils-migration/evidence/initial-template.json` and `specs/001-cuems-utils-migration/evidence/initial-mappings.json` (FR-010, research R11). Take the mappings capture against cuems-utils `6213b1603d0a508b6ac7dfb5f46593ba4d870193`, not against `e9ed8af`. The procedure includes a node with `<device class>` (a `lighting` class included) and root `<default class direction>`. Name that SHA in `specs/001-cuems-utils-migration/evidence/README.md`
- [X] T010 [US1] Record in `specs/001-cuems-utils-migration/evidence/listening-blocked.txt` that `CuemsWsServer()` still raises because `__init__` calls `create_script()`. Do not claim FR-003 here

**Checkpoint**: The process imports. It does not listen yet.

---

## Phase 4: User Story 2 — Public surface, template stand-in (Priority: P1)

**Goal**: `initial_template` is `ConfigManager.generate_example(SchemaName.SCRIPT)`. The census test exists and stays red until the later stories delete the remaining `cuemsutils.xml` imports. The adoption report names the cuems-utils 013 commit; the call itself is T036.

**Independent Test**: The server listens on `:9092` (FR-003). `initial_template` differs from `evidence/create-script-baseline.json` only by the deltas named in `tests/ws-command-responses.txt`. `tests/test_public_surface.py` is present; it is not required to pass until the milestone 1 exit.

### Tests for User Story 2

- [X] T011 [P] [US2] Add `tests/test_public_surface.py` (FR-005, FR-006) scanning `src/` as text per `specs/001-cuems-utils-migration/contracts/public-surface.md`: no `cuemsutils.xml`, `cuemsutils.config`, `cuemsutils.create_script`, or `cuemsutils.timeoutloop`; no `CuemsParser`, `XmlReaderWriter`, `create_script`, `get_nodes_by_adoption`, `_select_adopted`, `def partition_by_adoption`, `CUE_TYPES`, `'AudioCue' in`, `'VideoCue' in`, `'DmxCue' in`, `node_type`, or `NodeType.`; `partition_by_adoption` is allowed only as `from cuemsutils.tools.NodeList import partition_by_adoption` and calls of that name; the single carried exception is `ProjectMappings` in `src/cuemseditor/cli.py`; the test fails if it scans zero files or finds zero `cuemsutils` imports. Run it once and keep the red output in `specs/001-cuems-utils-migration/evidence/public-surface-before.txt`
- [X] T012 [P] [US2] Write `specs/001-cuems-utils-migration/upstream-reports/UR-1-no-public-adoption-partition.md` citing `cuems-engine` `specs/008-cuems-utils-migration/upstream-reports/UR-1-no-public-adoption-partition.md` and naming cuems-utils `6213b1603d0a508b6ac7dfb5f46593ba4d870193` as the commit this editor pins (FR-009, research R5, `evidence/cuems-utils-013-landed.txt`). Copy that SHA and its subject into `specs/001-cuems-utils-migration/evidence/cuems-utils-013-pin.txt`. Do not carry an "if the import fails" branch. Do not import `cuemsutils.xml`. Do not add a local helper

### Tests for User Story 2, continued

- [X] T013 [US2] Add `tests/test_initial_template.py` asserting the served payload differs from `specs/001-cuems-utils-migration/evidence/create-script-baseline.json` only by the deltas the test lists (keys, key order, value types, placeholder values). One listed delta is (c): a hardware cue's key is `Cue` with `class`, and a hardware cue output's key is `CueOutput` with `class`. `generate_example` emits that. Do not strip it. Run it before T014 and save the failure in `specs/001-cuems-utils-migration/evidence/initial-template-failing-first.txt` (constitution IV.2). The constructor still calls `create_script()` here, so the red run is that failure, not a green delta list

### Implementation for User Story 2

- [X] T014 [US2] In `src/cuemseditor/CuemsWsServer.py`, replace the `create_script()` call with `ConfigManager.generate_example(SchemaName.SCRIPT)`. Keep the message type `initial_template` and the `{"CuemsScript": ...}` envelope (FR-008, research R10). Do not call `cuemsutils.xml.descriptor`. `ConfigManager.generate_example` is on cuemsutils `0.1.0rc16`; this does not wait on features 013 or 014. The example it serves includes delta (c). That is not a reason to wait, and not a reason to reshape the example locally
- [X] T015 [US2] Write those deltas, including delta (c), into `tests/ws-command-responses.txt` next to the `initial_template` line (FR-008, FR-042). Create `specs/001-cuems-utils-migration/evidence/frontend-handover.md` naming the consumer: `cuems-frontend` `src/app/services/projects/projects.service.ts:159` (reads `localStorage` key `initial_template`), `:240` (`type === 'initial_template'`), and `:243` (writes that key). Delta (a) of the `project` frame stays `projects.service.ts:120` and is added in the User Story 3 handover task. Do not omit the cue-key delta to keep the old envelope
- [X] T016 [US2] Start the server against a temporary library and record that it accepts a WebSocket connection on `:9092` in `specs/001-cuems-utils-migration/evidence/listening.txt` (FR-003). This closes User Story 1 scenario 2

**Checkpoint**: The service listens. The census is not zero yet.

---

## Phase 5: User Story 3 — Projects open and save with three deltas (Priority: P1)

**Goal**: Script I/O goes through `CuemsScript`. The `type: project` value matches the capture except for deltas (a), (b), and (c). A load writes nothing. Delta (c) is why milestone 1 is not a controller deploy: a pre-05 UI mis-reads `Cue`.

**Independent Test**: `tests/test_project_payload.py` passes against `evidence/project-capture/`. Opening a project changes zero bytes of its script file. `../cuems-utils/tests/golden/` is not a pass condition.

### Tests for User Story 3

- [X] T017 [US3] Add `tests/test_project_payload.py` before changing `src/cuemseditor/CuemsDBProject.py`. It must fail on today's `XmlReaderWriter` output. Assert the `{"type":"project"}` value differs from `specs/001-cuems-utils-migration/evidence/project-capture/` only by (a) `schemaLocation` absent, (b) `Media.duration` as `{"CTimecode": "HH:MM:SS.mmm"}`, and (c) a hardware cue keyed `Cue` with `class` and a hardware cue output keyed `CueOutput` with `class` (`ActionCue`, `FadeCue`, and `CueList` stay their own keys); key order otherwise unchanged; cue booleans stay `"True"` / `"False"`; `doc_version` is absent; the script file checksum is unchanged after open. Do not rewrite `AudioCue` back onto the wire. Do not assert `../cuems-utils/tests/golden/MANIFEST.sha256`. Do not edit a golden from this repository (FR-011, FR-014, FR-040, contracts/project-payload.md)
- [X] T018 [US3] Compare `../cuems-utils/tests/golden/xml` with the XSD under `../cuems-utils/src/cuemsutils/xml/schemas/` by loading each golden through the library's public load. Write every contradiction to `specs/001-cuems-utils-migration/evidence/golden-xsd-contradictions.md` for regeneration in `cuems-utils`. If the golden tree is absent, write that fact instead. This comparison does not fail the editor suite, and it does not change the golden (constitution I, plan Complexity Tracking). Do not treat `MANIFEST.sha256` as a pass condition

### Implementation for User Story 3

- [X] T019 [US3] In `src/cuemseditor/CuemsDBProject.py` `load` / `load_xml`, call `CuemsScript.load_with_report(path)` and return `script.to_wire()` once. Do not call `CuemsScript.load()` (it discards the report). Do not walk or edit that dict. Do not write the file (FR-012, FR-014, research R3)
- [X] T020 [US3] In `src/cuemseditor/CuemsDBProject.py`, replace `CuemsParser` in `update` and `new` with `CuemsScript.from_json` (this path does not repair). Replace `save_xml`'s `XmlReaderWriter.write_from_object` with `CuemsScript.save` (FR-013, research R3, R4)
- [X] T021 [US3] In `duplicate` in `src/cuemseditor/CuemsDBProject.py`, `load_with_report` the source and `save` under `new_unix_name` only. Do not overwrite the source path. Do not add `validate_fade_durations_in_contents` (research R9; `duplicate` stays unvalidated beyond library load). If the library load refuses a source that `duplicate()` used to copy, record that project in `specs/001-cuems-utils-migration/evidence/duplicate-refusals.md`. Do not add a second refusal in the editor
- [X] T022 [US3] In `update_projects_existed_media` in `src/cuemseditor/CuemsDBProject.py`, use the `CuemsScript` from `load_with_report`. Do not `to_wire()` and parse again (plan.md script I/O table)
- [X] T023 [US3] Rewrite `_fix_media_durations` and `fix_media_durations_in_contents` in `src/cuemseditor/CuemsDBProject.py` so they assign `CTimecode` on the loaded object from the media DB. Find media cues with `isinstance` against `AudioCue`, `VideoCue`, and `DmxCue`, and also visit a `MediaCue` whose `class` is none of those three. Do not read or write the wire dict. Do not implement the guide's `if 'Cue' in item` snippet (FR-012, FR-015). The library `media_duration` rule is unrepairable and has no DB (research R2). In `tests/test_project_payload.py`, assert a client payload whose cue key is `Cue`, whose `class` is `audio`, and whose media duration is the string `00:00:00.000` is accepted by `from_json` and then corrected from the database by this walker, not rejected. Add the same case for `class` `video` and for `class` `lighting`. A walker that still does `'AudioCue' in item` fails those (spec edge case; constitution I)
- [X] T024 [US3] Delete `_clean_dangling_targets`, `_nullify_dangling_refs`, and `_collect_cue_ids` from `src/cuemseditor/CuemsDBProject.py`. Do not port the `action_target` clear: `action_target_resolves` is `repairable=False` for `ActionCue` and for `FadeCue` via the MRO, and clearing it to `None` fails `action_target_required` (research R2, FR-015). Do not replace the walks with `CUE_TYPES = ['Cue', 'ActionCue', 'FadeCue', 'CueList']`. The library rule is by cue identity, so it already sees a `Cue` of any class. In `specs/001-cuems-utils-migration/evidence/test-retirements.md`, say the walks stay deleted and that the guide's collapsed list was not ported
- [X] T025 [US3] Replace `tests/test_dangling_targets.py` with a skipped module whose reason names `cuemsutils` `xml/validators.py` rules `target_resolves` (library repairs `Cue.target`) and `action_target_resolves` (library refuses). Record the same reason in `specs/001-cuems-utils-migration/evidence/test-retirements.md` (FR-017), and keep T024's note that the walks stay deleted and the guide's collapsed `CUE_TYPES` list was not ported. Do not re-assert those rules here
- [X] T026 [US3] Keep `validate_fade_durations_in_contents` on the raw client payload in `update` and `new` only, with the same `ValueError` text, in `src/cuemseditor/CuemsDBProject.py` (FR-016)
- [X] T027 [US3] Record deltas (a), (b), and (c) for the `type: project` frame in `tests/ws-command-responses.txt`, and append `cuems-frontend` `src/app/services/projects/projects.service.ts:120` (`schemaLocation: string`) to `specs/001-cuems-utils-migration/evidence/frontend-handover.md` (FR-018, FR-042). Delta (c) is part of payload version 1, not a bump to 2

**Checkpoint**: Open and save use the public script API. Dangling walks are gone.

---

## Phase 6: User Story 5 — Duration tool lists projects that need a save (Priority: P2)

**Goal**: Pass A still corrects the database. Pass B writes no script. The tool reports *needs a save*.

**Independent Test**: `hatch test tests/test_repair_durations.py` passes. After `--apply`, every `script.xml` checksum is unchanged and the *needs a save* list matches the fixture. Saving one listed project through the editor then removes it from that list.

Depends on T023: the duration comparison shares the object walker's `CTimecode` rules. `src/cuemseditor/repair_durations.py` is not edited by US3, so this phase can follow US3 immediately.

### Tests for User Story 5

- [ ] T028 [US5] In `tests/test_repair_durations.py`, add a test that a structured media duration (a `CTimecode`, or `{"CTimecode": "HH:MM:SS.mmm"}` on the wire) differing from the database value is reported. Add a second case: a fixture in the pre-013 cue shape (element `AudioCue`, no `class`) is reported `SKIPPED_INVALID` with the library's reason, the file checksum is unchanged, and `cuems-reshape-devices` is not invoked. Run the structured-duration case against the pre-change `TIMECODE_SHAPE.match` guard at `src/cuemseditor/repair_durations.py` and save the failure in `specs/001-cuems-utils-migration/evidence/timecode-guard-failing-first.txt` before T029 (FR-024, constitution IV.4)

### Implementation for User Story 5

- [ ] T029 [US5] In `src/cuemseditor/repair_durations.py`, delete pass B (`pass_b_xml`, the XML backup, `--xml-only`, and `--db-only`), `TIMECODE_SHAPE`, `CuemsParser`, and `XmlReaderWriter`. Read each script with `CuemsScript.load_with_report`. Compare durations with `CTimecode`. Print each mismatch as *needs a save* with the project, the media, the script value, and the database value. Outcomes remain corrected, unchanged, `SKIPPED_INVALID`, and *needs a save*. An un-migrated document (element `AudioCue`, no `class`) is `SKIPPED_INVALID` with the library's reason. Write no script, run no version conversion, and do not invoke `cuems-reshape-devices` (FR-023, FR-025, FR-025a, FR-027, contracts/repair-tool.md). Do not fold pass B back in. Do not extend `cuems-convert-documents`
- [ ] T030 [US5] Update `tests/test_repair_durations.py`: keep the pass A cases (dry-run, `--apply` plus database backup, idempotence, trash, missing database); assert every `script.xml` checksum is unchanged after `--apply`; assert the *needs a save* list; retire the pass B assertions in the file header with this contract as the reason; remove the `XmlReaderWriter` import (FR-007, FR-026)
- [ ] T031 [US5] In `tests/test_repair_durations.py`, save one project the tool listed as *needs a save* through `CuemsDBProject`'s save path, re-run the tool, and assert that project has left the list and that its script checksum changed only on that save (US5 acceptance scenario 4, quickstart.md §6)
- [ ] T032 [US5] State in the `repair_durations` module docstring, in `--help`, and in `CLAUDE.md` field notes that script files change only when an operator saves in the editor, and that until that save the engine plays the file on disk (FR-027, FR-027a). The help text also states that an old device shape is corrected by `cuems-reshape-devices` over the whole library, then a save in the editor, not by this tool

**Checkpoint**: This repository writes scripts only from the editor save path.

---

## Phase 7: User Story 6 — The node list stays correct (Priority: P2)

**Goal**: Merged nodes carry `node_role` and the library wire form. `NetworkMap` is gone. `node_status.alive` stays a different fact from `online`. A duplicate node identity is not retried.

**Independent Test**: `tests/test_node_merge.py` passes, including a run that failed while `basic_fields` still said `node_type`. `tests/test_nodelist_actions.py` stays green aside from the one mock edit in T035.

Depends on T014 (same file `src/cuemseditor/CuemsWsServer.py`). Not parallel with US2.

### Tests for User Story 6

- [ ] T033 [US6] Add `tests/test_node_merge.py` asserting a converted node whose `to_wire()` has `node_role` and no `node_type` still has `node_role` after `merge_node_data`. Run it before T036 and save the failure in `specs/001-cuems-utils-migration/evidence/node-type-failing-first.txt` (FR-028). Do not re-implement or re-test the node model: no assertion of `NodeRole` membership or `Uuid` parsing (FR-030)
- [ ] T034 [US6] Extend `tests/test_node_merge.py` so a merged `initial_mappings` node has string `uuid`, `adopted` and `online` as `"True"` or `"False"` (not JSON `true`/`false`), key `node_role`, and the mapping node's output blocks preserved (FR-031, research R6). The capture `evidence/initial-mappings.json` is taken against cuems-utils `6213b1603d0a508b6ac7dfb5f46593ba4d870193`, and that SHA is named in `specs/001-cuems-utils-migration/evidence/README.md`. The mappings half carries `devices` / `device` / `class` and `defaults` / `default` / `class` / `direction` as `to_wire()` emitted them. Any other difference from that capture is either an enumerated delta in the test or a bug. Add a case that feeds a post-013 mapping node, including `device class="lighting"`, and asserts `class` is still in the merged value. That case fails first against a merge that only copies `audio`, `video`, and `dmx`. Do not normalise a mix of `<audio>` and `<device class="audio">`
- [ ] T035 [P] [US6] Add `tests/test_node_status_distinct.py` asserting `node_status` still relays engine `cluster_status` (`alive` is the sub-second set) and that nothing copies `alive` onto a node's `online` (~30 s discovery). Assert `nodelist_modify` relays the engine error string unchanged, including `Node <uuid> not found`, with no retry (FR-033, FR-036). Do not edit `tests/test_nodelist_actions.py` in this task

### Implementation for User Story 6

- [ ] T036 [US6] Precondition: `specs/001-cuems-utils-migration/evidence/cuems-utils-013-pin.txt` names `6213b1603d0a508b6ac7dfb5f46593ba4d870193` (T012, `evidence/cuems-utils-013-landed.txt`). In one commit, in `src/cuemseditor/CuemsWsServer.py` delete `from cuemsutils.xml import NetworkMap` and replace `NetworkMap.get_nodes_by_adoption(network_map_dict)` with `adopted, unadopted = partition_by_adoption(network_map_dict)` imported from `cuemsutils.tools.NodeList`. Both names are tuples of bare node objects; an empty side is `()`. Pass those tuples on. Do not unwrap `{"node": <node>}`, do not re-wrap, do not read `adopted` to split, and do not define `_select_adopted`. The input list stays wrapped; the function unwraps it. Do not wait on feature 014. In that same commit, change only `TestNodeconfAvailableFlag._reload` in `tests/test_nodelist_actions.py` so it patches `partition_by_adoption` on `CuemsWsServer` and returns `(), ()`; leave every assertion unchanged and say so in the commit message (FR-009, FR-041, research R5)
- [ ] T037 [US6] Change `merge_node_data` in `src/cuemseditor/CuemsWsServer.py` so the library side is a tuple of bare node objects from `partition_by_adoption`. Status fields come from `node.to_wire()`. A library item is not skipped because `"node"` is absent. Output blocks stay from the existing mapping node, copied through: do not look up `audio`, `video`, or `dmx`. The comment at line 439 is not a keyed read, and this merge is not one of the fourteen deprecated-surface call sites. Compare a JSON identity with a map identity only through `cuemsutils.tools.coerce_identity` (FR-034, FR-035). The field list and the docstring that names `node_type` (`basic_fields` and the docstring above `merge_node_data`) name `node_role` instead. No in-memory comparison of a typed `adopted` or `online` against the string `"True"` (FR-029)
- [ ] T038 [US6] Make `reload_network_map_nodes` in `src/cuemseditor/CuemsWsServer.py` return the loaded lists and not assign `self.mappings_dict`. Assign those fields on the event-loop thread in `notify_all_node_list_update` and in `src/cuemseditor/CuemsWsUser.py` `nodelist_get` (research R8, constitution II). Leave the `__init__` call on the constructing thread. Both the refresh path and the serve path (`initial_setting_message`) still set `mappings_dict['nodeconf_available']` from a fresh `nodeconf_available()` call, not from a cached value (FR-032 milestone 1). Assert that in `tests/test_node_merge.py`
- [ ] T039 [US6] Extend `tests/test_node_merge.py` with a duplicate-identity map: no retry, last list retained, error broadcast, clear broadcast after a later good read (FR-036a). Run it before T040 and save the failure in `specs/001-cuems-utils-migration/evidence/network-map-error-failing-first.txt` (constitution IV.2). The pre-change watcher retries and does not broadcast `network_map_error`
- [ ] T040 [US6] In `src/cuemseditor/CuemsWsServer.py`, if `cuemsutils.errors.node_identity_collision_message(path, exc)` is not `None`, do not retry, log once per distinct identity, keep serving the last good node list, and broadcast `{"type":"network_map_error","value":{"kind":"duplicate_identity","identity":"<string>","file":"<path>"}}` to all sessions and to each session that connects while it stands. A later successful read broadcasts `{"type":"network_map_error","value":null}` and then the usual refresh. Other exceptions keep the existing retry. `identity` is the string form (FR-036a, research R13). Add the shape to `tests/ws-command-responses.txt`

**Checkpoint**: `node_type` is gone from `src/`. `nodeconf_available` is still injected into `mappings_dict` at both current sites and is still sampled live (FR-032 milestone 1). Do not move it yet.

---

## Phase 8: User Story 7 — The pin refuses a library that moved past this editor (Priority: P3)

**Goal**: `cuemsutils` is bounded on both sides, in `pyproject.toml` and in `debian/control`. The tag message exists and is not ready.

**Independent Test**: `grep cuemsutils pyproject.toml` shows `cuemsutils>=0.1.0rc16,<0.1.1`. `debian/control` has `python3-cuemsutils (>= 0.1.0rc16)` and `python3-cuemsutils (<< 0.1.1~)`. `debian/bookworm` was not deleted. The `.deb` was built inside a bookworm chroot, and its `pyvenv.cfg` says `home = /usr/bin`.

Can run beside US5 and US6 (different files) once US1 has landed. Do not lower the floor to make a test pass.

- [ ] T041 [P] [US7] Set the `cuemsutils` dependency in `pyproject.toml` to `cuemsutils>=0.1.0rc16,<0.1.1` (FR-037)
- [ ] T042 [P] [US7] Bring `debian/` onto `feat/xml-refactor` from `origin/debian/bookworm` at `72f952a` so the changelog history is carried (FR-038). Do not delete, rename, or force-update `debian/bookworm`
- [ ] T043 [US7] In `debian/control`, add `python3-cuemsutils (>= 0.1.0rc16), python3-cuemsutils (<< 0.1.1~)` beside `${python3:Depends}`. Add a `debian/changelog` entry for this migration (FR-038, contracts/package-relations.md)
- [ ] T044 [US7] Build the package for bookworm, not on the Debian 13 host. Measured 2026-10-01: `/usr/bin/python3` is 3.13.5, `PATH` `python3` is pyenv 3.11.9, `debuild` is absent, `mmdebstrap` is not installed but apt has `1.5.7-1+deb13u1`, unprivileged user namespaces are on, and this user has subuid/subgid. Install `mmdebstrap` if it is missing. Follow `cuems-nodeconf/tests/packaging/release-gate-demo.sh`: `mmdebstrap --mode=unshare --variant=apt` a bookworm chroot, install `dh-virtualenv` and the Python build dependencies inside it, and run `dpkg-buildpackage -b -us -uc -rfakeroot` there. Assert `pyvenv.cfg` says `home = /usr/bin` and the chroot `python3` is bookworm's 3.11. Save the log under `specs/001-cuems-utils-migration/evidence/bookworm-build.txt`. Do not run `debuild` on the trixie host. Leave `CLAUDE.md`'s `debuild` line as the bookworm-host instruction; add a field note that a trixie dev machine builds inside that chroot (FR-038, contracts/package-relations.md)
- [ ] T045 [US7] Write `specs/001-cuems-utils-migration/debian-consolidation.md` listing every `debian/` change on this branch by commit and file, plus anything on `debian/bookworm` not in `72f952a` (expected: none). Do not apply that list yourself (FR-038a)
- [ ] T046 [P] [US7] Write the candidate tag message under `../.xml-refactor-tag-messages/` naming `feat/nodelist-adoption-api` through `886f649`, `cuems-engine` `feat/nodelist-modify-dispatch`, and `cuems-nodeconf` `feat/nodelist-modify-hardening` (47 commits behind, largely superseded, not resolved here). In the same file, list the five commits on `feat/nodelist-adoption-api` up to `886f649` by hash and subject, for the PR description (FR-039a). Do not create, move, or push the tag. State that `cuems-frontend` 05 is outstanding so the message is not ready (FR-039, FR-039a, FR-049)

**Checkpoint**: The package metadata can refuse `0.1.1`. The bookworm chroot build produced a `.deb` whose `pyvenv.cfg` says `home = /usr/bin`.

---

## Phase 9: Milestone 1 exit (blocks milestone 2)

**Purpose**: Census zero is the T049 input for `cuems-utils`. It is not a controller deploy (`to_wire()` wraps duration and emits `Cue`; there is no payload-version handshake yet, so a pre-05 UI mis-reads both).

- [ ] T047 Run the census grep `cuemsutils\.(xml|timeoutloop|create_script)` over `src/`, the name grep `CuemsParser|XmlReaderWriter|create_script|get_nodes_by_adoption|_select_adopted` over `src/`, and confirm every `partition_by_adoption` hit in `src/` is the `cuemsutils.tools.NodeList` import or a call of that name (quickstart.md §3). Then `hatch test tests/test_public_surface.py`. All of these must be clean. Write the command output in `specs/001-cuems-utils-migration/evidence/census-zero.md` for the `cuems-utils` flow (FR-048, SC-002). This file is a source announcement, not a package. Do not start US4 or US8 before it exists, and do not cut a controller deploy from this checkpoint (spec clarification 2026-10-01)

---

## Phase 10: User Story 4 — The operator is told about a repair (Priority: P2, milestone 2)

**Goal**: A repaired load emits `document_load_report`. An unrepairable load emits `document_load_failed`. `project_save` is refused until that session acknowledges that report, and the original is in `trash/` before the first overwrite.

**Independent Test**: `tests/test_document_load_report.py` passes against a temporary library. A second session's acknowledgment does not unlock the first session's save.

Depends on T019 (`load_with_report` exists). Do not land this before T047. An unknown `type` may be emitted before the UI renders it (FR-050).

### Tests for User Story 4

- [ ] T048 [US4] Add `tests/test_document_load_report.py`. A repairable fixture emits `document_load_report` (never omitted, never `null`) with `file_differs_from_loaded` true when `outcome` is not `clean`, and the script checksum is unchanged. A second open reports the same repairs. An unrepairable fixture (dangling `action_target`, or a document newer than the library) emits `document_load_failed` with `document`, `cue_id`, `field`, the library `message`, and `next_steps` exactly `["restore_from_conversion_backup", "correct_field_by_hand", "remove_document"]`. A following `project_list` on the same connection succeeds (FR-019, FR-020, data-model.md)
- [ ] T049 [US4] In `tests/test_document_load_report.py`, assert `project_save` before `repair_acknowledge` returns `repair_save_refused` with `reason` `unacknowledged` and does not change the file; after that session acknowledges that `report_id`, `trash/` holds a byte-identical copy of the original and the saved file is the repaired document; if the copy fails, `reason` is `preserve_failed` and `CuemsScript.save` is not called; another session's acknowledgment does not unlock the save (FR-021, FR-021a)

### Implementation for User Story 4

- [ ] T050 [US4] On the session that issued `project_load`, store `project_uuid`, `report_id` (from `cuemsutils.helpers.new_uuid`), `outcome`, `file_differs_from_loaded`, and `acknowledged` (starts false) in `src/cuemseditor/CuemsWsUser.py` / the server session dict. Clear them on `project_unload`, session close, and any new load of the document. Another session must not read them (data-model.md, constitution II)
- [ ] T051 [US4] From `send_project` in `src/cuemseditor/CuemsWsUser.py`, emit `document_load_report` on every successful open, including `outcome` `clean`, and emit `document_load_failed` instead of `type: project` only when `load_with_report` raises `ValidationError`. `SchemaError`, `IngestError`, and `OSError` stay on the existing per-session error path and are not given `next_steps` (data-model.md). Shapes are in `specs/001-cuems-utils-migration/contracts/ws-messages.md`. Render `previous_value` and `substituted_value` as JSON-safe forms (string form of a `CTimecode`, `null` for `None`). Do not invent repairs the library did not return
- [ ] T052 [US4] In `received_project` (`project_save`) in `src/cuemseditor/CuemsWsUser.py`, refuse with `repair_save_refused` when this session's report for this project is not `clean` and `acknowledged` is false. That decision runs on the event-loop thread and does not touch the filesystem. Add inbound `repair_acknowledge` carrying `project_uuid` and `report_id`; set `acknowledged` on the loop thread. When `file_differs_from_loaded` is true, run `CopyMoveVersioned.move` and then `CuemsScript.save` on the server executor, the same way this handler already awaits `project.update`. Move the on-disk script into that project's `trash/` with a name that recovers the project and the date. If the move fails, do not call `save`. Do not call the move or the save from the async handler body (FR-021, FR-021a, constitution II)
- [ ] T053 [US4] Add `document_load_report`, `document_load_failed`, `repair_acknowledge`, and `repair_save_refused` to `tests/ws-command-responses.txt` (FR-022)
- [ ] T054 [US4] When `duplicate`'s source `outcome` is not `clean`, add an optional `report` key on the `project_duplicate` reply in `src/cuemseditor/CuemsWsUser.py`, same shape as `document_load_report`'s `value`. Do not overwrite the source and do not require acknowledgment (research R9). Note the optional key in `tests/ws-command-responses.txt` as a non-bump (FR-047a)

**Checkpoint**: A repair cannot reach disk unseen on `project_save`.

---

## Phase 11: User Story 8 — Schema forms and a separate node wire (Priority: P3, milestone 2)

**Goal**: Payload version 1 is the first frame. `initial_mappings` no longer carries nodes or `nodeconf_available`. The descriptor is served through `ConfigManager`. `initial_template` is retired.

**Independent Test**: `tests/test_payload_version.py` and `tests/test_schema_descriptor.py` pass. `nodeconf_available` is on `node_list` and on the `nodelist_get` reply, and absent from the project-mappings payload and from each node.

Depends on T047 and on T016 (the server connects). Do not remove keys from `initial_mappings` before T057 has sent `payload_version` (FR-050). T058 is the task that removes them.

### Tests for User Story 8

- [ ] T055 [US8] Add `tests/test_payload_version.py` asserting the first frame on connect is `{"type":"payload_version","value":1}` and that it arrives before any `initial_*` frame. The test fails if the integer changes without a matching bump row in `tests/ws-command-responses.txt` (FR-047, FR-047a). A connection that never sends this type is version 0
- [ ] T056 [P] [US8] Add `tests/test_schema_descriptor.py`. `schema_descriptor` returns `ConfigManager.get_schema_descriptor` types with `key`, `fields` (name, xsd type, `required`, `repeated`, order, kind, `enum_values`, default, repairability), and `instance`. `config_save` persists through `save_network_map`, `save_settings`, `save_project_mappings`, or `save_project_settings`. It rejects schema `script`, schema `hardware_outputs`, and any write of `default_mappings.xml` (FR-045, data-model.md)

### Implementation for User Story 8

- [ ] T057 [US8] Send `payload_version` as the first frame in the connect path in `src/cuemseditor/CuemsWsServer.py` (the path that today sends `initial_template` and `initial_mappings`), before those frames (FR-047). Record version 1 and the bump rules in `tests/ws-command-responses.txt`
- [ ] T058 [US8] After T057, split the wire in `src/cuemseditor/CuemsWsServer.py` and `src/cuemseditor/CuemsWsUser.py`: `initial_mappings` carries project output mappings only; new `node_list` carries `nodes`, `new_nodes`, and envelope `nodeconf_available` sampled when the frame is built. `watch_network_map` pushes `node_list` to all sessions. `nodelist_get` returns `node_list` to the caller. `nodeconf_available` is absent from the project-mappings payload and from each node, and it is not a schema field (FR-032 milestone 2, FR-046, research R14)
- [ ] T059 [US8] Add actions `schema_descriptor` and `config_save` in `src/cuemseditor/CuemsWsUser.py` per `specs/001-cuems-utils-migration/contracts/ws-messages.md`. Reach the descriptor only through `ConfigManager.get_schema_descriptor(SchemaName)`. A successful `network_map` save still refreshes all sessions the way `nodelist_modify` already does. Do not import `cuemsutils.xml.descriptor` (FR-045, D34)
- [ ] T060 [US8] Stop sending `initial_template` from `src/cuemseditor/CuemsWsServer.py`. Document in `tests/ws-command-responses.txt` that clients build from the descriptor's per-type `instance` instead (FR-008a). This removal is a payload-version bump already covered by version 1; do not ship it without T057
- [ ] T061 [US8] Extend `specs/001-cuems-utils-migration/evidence/frontend-handover.md` (created when the `initial_template` deltas are recorded) with `cuems-frontend` `src/app/services/projects/projects.service.ts:120`, plus `:159`, `:240`, and `:243` if they are not already there, `src/app/components/settings/settings.component.ts`, `src/app/components/projects/project-show/audio-mixer/audio-mixer.component.ts:80`, and `src/app/components/projects/project-show/video-mixer/video-mixer.component.ts:94`, including that the two mixers read `localStorage` key `initial_mappings` and need an eviction story (FR-018, FR-046, FR-008). Do not edit the frontend here. Update the tag message from T046 so it stays unready until that frontend consumes the report and these families (FR-049)

**Checkpoint**: Milestone 2 is on the branch. The tag is still the maintainer's to cut.

---

## Phase 12: Polish

**Purpose**: Close the exit list. Do not fix carried constitution violations in passing.

- [ ] T062 Run `specs/001-cuems-utils-migration/quickstart.md`. For every step this environment cannot perform (live controller UI, applying `debian-consolidation.md` onto `debian/bookworm`, a frontend rendering the report), add a *not performed* row with the reason in `specs/001-cuems-utils-migration/evidence/not-performed.md` (FR-044). An omitted row is not a pass
- [ ] T063 [P] Confirm `CuemsDBProject.delete_from_trash`, the `ProjectMappings` import in `src/cuemseditor/cli.py`, and `script_file_name` were not changed. They stay carried in `specs/001-cuems-utils-migration/plan.md` Complexity Tracking (FR-043)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies
- **Foundational (Phase 2)**: depends on Setup. Blocks every story
- **US1 (Phase 3)**: depends on Foundational. Blocks US2, US3, US5, US6, US7
- **US2 (Phase 4)**: depends on US1. Blocks US6 (same `CuemsWsServer.py`) and the listening half of US1
- **US3 (Phase 5)**: depends on US1. Can run in parallel with US2 (different files: `CuemsDBProject.py` vs `CuemsWsServer.py`) after T009's captures exist
- **US5 (Phase 6)**: depends on US3 (shared duration comparison) and on T004's fixtures still matching the tool's fixture names
- **US6 (Phase 7)**: depends on US2 T014. Can run in parallel with US5
- **US7 (Phase 8)**: depends on US1. Can run in parallel with US5 and US6 (`pyproject.toml`, `debian/`, tag message)
- **Milestone 1 exit (Phase 9)**: depends on US2, US3, US5, US6, and US7. Blocks US4 and US8
- **US4 (Phase 10)**: depends on the exit and on US3's `load_with_report`
- **US8 (Phase 11)**: depends on the exit and on US6's node merge. `initial_mappings` must not lose keys before T057
- **Polish (Phase 12)**: depends on the stories in scope for the check being run. T062 after US8 if milestone 2 is in scope; the census file T047 is the earlier gate

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

- Failing-first tests run and are captured before the production edit they guard (T006, T013, T017, T028, T033, T039)
- A task that says "in one commit" (T036) is not split
- `tests/ws-command-responses.txt` is updated in the same story that changes the payload (T015, T027, T040, T053, T054, T057, T060)

### Parallel Opportunities

- T003 and T004 (different evidence files, no `src/` edit)
- T011 and T012 (test file vs upstream report)
- US3 in parallel with US2 after US1
- US5 in parallel with US6 and US7 after their own dependencies
- T041, T042, and T046 (pyproject, debian tree, tag message)
- T035 with T033 (different new test files) before the production node edits
- T055 and T056 (different test files) before the milestone 2 production edits
- T063 alongside T062

### Parallel Example: User Story 2

```bash
# Together, before the template edit:
Task: "T011 tests/test_public_surface.py"
Task: "T012 upstream-reports/UR-1-no-public-adoption-partition.md"

# Then, same file, not parallel:
Task: "T014 generate_example in src/cuemseditor/CuemsWsServer.py"
```

### Parallel Example: after User Story 1

```bash
# Different files:
Task: "T013–T016 US2 initial_template, red test first"
Task: "T017–T027 US3 project frame and script I/O"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Phase 1 and Phase 2
2. Phase 3 (US1)
3. Stop. Imports succeed, the six pre-feature test files collect, `tests/test_import_smoke.py` is the extra file, and listening is still blocked and recorded

### Milestone 1 (census zero)

1. MVP
2. US2 so the process listens
3. US3, then US5; US6; US7 beside them where the dependencies allow
4. T047. Announce `evidence/census-zero.md` to the `cuems-utils` flow as source state only
5. Do not package or deploy this checkpoint. US4 ships in the same candidate tag, so the save-gate window never lands on its own

### Milestone 2 (coordinated tag, still not cut here)

1. US4 and US8
2. T062
3. Leave the tag message unready until `cuems-frontend` 05 consumes the report and the US8 families

### Task counts

| Phase | Tasks | IDs |
|---|---|---|
| Setup | 4 | T001–T004 |
| Foundational | 1 | T005 |
| US1 | 5 | T006–T010 |
| US2 | 6 | T011–T016 |
| US3 | 11 | T017–T027 |
| US5 | 5 | T028–T032 |
| US6 | 8 | T033–T040 |
| US7 | 6 | T041–T046 |
| Milestone 1 exit | 1 | T047 |
| US4 | 7 | T048–T054 |
| US8 | 7 | T055–T061 |
| Polish | 2 | T062–T063 |
| **Total** | **63** | T001–T063 |

---

## Notes

- Commits are GPG-signed. On `gpg failed to sign`, retry. Do not pass `--no-gpg-sign`
- Do not patch or vendor `../cuems-utils`. A missing public API is an upstream report
- Do not add a node-model test (FR-030). `tests/test_node_merge.py` pins the editor's merge and the wire form, not `NodeRole` or `Uuid` behaviour
- `tests/test_nodelist_actions.py` is edited only in T036
- Suggested MVP scope is User Story 1 only. The first deployable listening process is US1 plus US2
