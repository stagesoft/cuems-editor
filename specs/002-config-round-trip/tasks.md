<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Tasks: Config round trip, a durable repair gate, and the restated version 1 wire

**Input**: Design documents in `specs/002-config-round-trip/`. Spec clarified on 2026-10-08 and
amended on 2026-10-12 (Q1–Q9).

**Prerequisites**: plan.md, spec.md, research.md (R1–R12), data-model.md, contracts/, quickstart.md

**Tests**: Included, as the spec and constitution IV require:
- failing-first tests for every wire change and every silent-wrong site;
- recovery-path tests for every write path;
- strict xfails for the upstream gates.

A task marked **(red first)** writes a test that must fail against the source at `22f9af4`.
`22f9af4` is the same source as `a3309ab`: this feature has not changed `src/`. The failing run is
saved under `specs/002-config-round-trip/evidence/`, as named in the task.

**How to run the suite** (research R1). Never use `hatch run`, which re-syncs dependencies and
replaces the editable `cuemsutils`:

```bash
E=$(hatch env find)
$E/bin/python -m pip install -e ../cuems-utils pytest pytest-asyncio
$E/bin/python -m pytest -q
```

Check that `cuemsutils.__file__` is under `../cuems-utils/src`. Baseline: 160 passed, 3 skipped.

**Test fixtures use `MagicMock` servers.** Every server attribute this feature adds is a **plain
dict**, set explicitly by each fixture: `server.repair_gates = {}` and `server.file_locks = {}`.
Logic lives in `CuemsWsUser` / `CuemsDBProject` functions that take those dicts. Nothing lives in
`CuemsWsServer` methods that a mock would silently replace.

**Commits**: GPG-signed; if signing fails, retry, never bypass. Commit on `002-config-round-trip`
only: never push it, never set an upstream. Each commit message ends with the repository's
attribution lines.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, and no dependency on an unfinished task)
- **[Story]**: the user story, in story phases only
- Every task names a file path

## Path Conventions

Single package: `src/cuemseditor/` and `tests/` at the repository root. Feature documents stay
under `specs/002-config-round-trip/`. Evidence goes in `specs/002-config-round-trip/evidence/`.
`specs/001-cuems-utils-migration/evidence/` is immutable: only new files are added there.

---

## Phase 1: Setup (environment and evidence)

**Purpose**: record what the feature is verified against, before any test is written for evidence.
This phase makes no `src/` edit.

- [X] T001 Create `specs/002-config-round-trip/evidence/README.md`. State that files in this directory are immutable once committed and that a correction is a new file naming the one it supersedes, mirroring `specs/001-cuems-utils-migration/evidence/README.md:8-10`. List each evidence file that the tasks below create.
- [X] T002 Record the environment in `specs/002-config-round-trip/evidence/environment.txt` (FR-034, research R1):
  - the commands from the header above, run as written;
  - `git -C ../cuems-utils rev-parse HEAD`, and whether `git -C ../cuems-utils status --short src/` is empty;
  - `cuemsutils.__version__` and `cuemsutils.__file__`;
  - the `python` version;
  - `git -C ../cuems-nodeconf rev-parse --abbrev-ref HEAD` and its SHA;
  - the full suite summary line;
  - a sentence saying that `hatch run` re-syncs and must not be used for recorded runs.

  If `../cuems-nodeconf` is not on a branch carrying `engine_callback` (`feat/xml-refactor`), write that down; it matters to T050.
- [X] T003 [P] Capture the four refused descriptor instances (research R4) in `specs/002-config-round-trip/evidence/descriptor-instance-config.txt`. For each of `settings`, `network_map`, `project_mappings` and `project_settings`:
  - take the root type, meaning `key.is_path` and no `/` in `key.name`;
  - run `ConfigManager(load_all=False).from_json(schema, instance)` followed by `.save(tmp)`;
  - record the exception type and message.

  Use a copy of `tests/fixtures/conf` as `CUEMS_CONF_PATH`, and put the probe script inline at the top of the file. This evidence backs gate G3's wider scope.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the shared tables, the lock helper, and `CuemsDBProject.open` / `inspect` returning
the script's md5. US1, US2 and US6 all build on these.

**⚠️ CRITICAL**: no user-story implementation begins until this phase is done.

- [ ] T004 In `src/cuemseditor/CuemsWsServer.py` `CuemsWsServer.__init__`, add `self.repair_gates = {}` and `self.file_locks = {}`, with a comment for each:
  - `repair_gates`: project uuid → `GateState` dict (data-model.md). Read and written only on the event-loop thread.
  - `file_locks`: `os.path.realpath(path)` → `asyncio.Lock`. Created lazily on the loop thread and never evicted.
- [ ] T005 In `src/cuemseditor/CuemsWsUser.py`, add the module function `file_lock(server, path)`. It returns `server.file_locks.setdefault(os.path.realpath(path), asyncio.Lock())`, and it is called only on the loop thread (research R6). Add the module function `bytes_md5(path)`, which returns `hashlib.md5(open(path,'rb').read()).hexdigest()`, or `None` when the file does not exist. `bytes_md5` runs in the executor.
- [ ] T006 Update the `server` fixtures in `tests/test_document_load_report.py` and `tests/test_schema_descriptor.py` (and the `user` fixture in `tests/test_nodelist_actions.py`, only if a later task needs it there) to set `server.repair_gates = {}` and `server.file_locks = {}`. Re-run the suite: still 160 passed, 3 skipped.
- [ ] T007 In `src/cuemseditor/CuemsDBProject.py`:
  - change `open(uuid)` to read the script's bytes once, compute their md5, then call `CuemsScript.load_with_report(path)`, and return `(value, report, script_md5)`;
  - add `inspect(uuid) -> (LoadReport, script_md5)`, which does the same read and load without building the wire value.

  Both raise exactly what `open` raises today (research R8.1, R8.2). The md5 is taken from one read and the library loads the path again, so a write between the two reads binds the report to the earlier bytes. That race is accepted: the next save re-hashes the file (FR-009a) and re-derives the gate on a mismatch. Update the one caller, `CuemsWsUser.send_project` (`src/cuemseditor/CuemsWsUser.py:809`), to unpack three values and ignore the md5 for now. US6's T066 later extends both return values with the media comparison.
- [ ] T008 Add `tests/test_db_project_inspect.py`, which asserts on a temporary library (the `lib` fixture pattern from `tests/test_document_load_report.py:79-99`):
  - `open` and `inspect` return the md5 of the file's exact bytes;
  - `inspect` writes nothing (sha256 is unchanged);
  - an unrepairable file raises `DocumentLoadFailed` from both.

**Checkpoint**: the suite is green, and the tables, the lock helper and the md5 are available.

---

## Phase 3: User Story 1 — A repaired script cannot overwrite its original unseen (Priority: P1) 🎯 MVP

**Goal**: a per-project repair gate that survives a reconnect, a second session, a stale tab and an
editor restart (spec FR-005 to FR-011; Q1, Q4).

**Independent Test**: load a repaired fixture, reconnect with the same `session_id`, and send
`project_save`. Expect `repair_save_refused`. Repeat for a second session and for a fresh server
object over the same library.

### Tests for User Story 1 (red first)

- [ ] T009 [US1] (red first, FR-005) Create `tests/test_repair_gate_durable.py`, reusing `tests/test_document_load_report.py`'s `lib`, `server`, `_session`, `_run`, `_drain` and `_write_variant` helpers. Import them, or copy them with a comment naming their source. Write `test_a_reconnect_with_the_same_session_id_keeps_the_gate`:
  - write the `repaired` variant;
  - open it with session A;
  - build a **new** `CuemsWsUser` with A's `session_id` (the reconnect);
  - send `project_save` from it;
  - expect `repair_save_refused` with reason `unacknowledged`, the file's sha256 unchanged, and no trash copy.

  Run it against the current source and save the failing output in `specs/002-config-round-trip/evidence/repair-gate-failing-first.txt`.
- [ ] T010 [P] [US1] In `tests/test_repair_gate_durable.py`, add `test_a_reacknowledge_after_reconnect_is_echoed_then_the_save_preserves`. After the reconnect from T009, `repair_acknowledge` with the original `report_id` answers `repair_acknowledge` (not the error frame). The next save moves the original into `trash/projects` and writes. A second save makes no second trash copy.
- [ ] T011 [P] [US1] In `tests/test_repair_gate_durable.py`, add `test_a_session_that_never_loaded_the_project_is_refused` (spec US1 #3).
- [ ] T012 [P] [US1] In `tests/test_repair_gate_durable.py`, add `test_after_an_editor_restart_the_gate_is_rederived_from_the_file` (FR-009). Use a fresh `server` with empty `repair_gates` over the same library, and a session that sends `project_save` without loading. Expect a refusal and the file unchanged.
- [ ] T013 [P] [US1] In `tests/test_repair_gate_durable.py`, add `test_a_file_changed_after_acknowledgment_gets_a_new_report` (FR-009a):
  - open, acknowledge, then overwrite the script file with another `repaired` variant whose bytes differ;
  - save;
  - expect a refusal naming a **new** `report_id`.
- [ ] T014 [P] [US1] In `tests/test_repair_gate_durable.py`, add `test_a_clean_project_save_adds_no_load` (Q4). Spy on `CuemsDBProject.inspect` and `bytes_md5` and assert that neither is called on a save after a clean open.
- [ ] T015 [P] [US1] In `tests/test_repair_gate_durable.py`, add these two tests:
  - `test_unload_drops_this_sessions_acknowledgment` (FR-010): after `project_unload` (patch `comunicate_with_engine`), a save from that session is refused;
  - `test_project_load_by_another_session_keeps_the_report_id`: R8.5, the file is unchanged.
- [ ] T016 [P] [US1] In `tests/test_public_surface.py` (or a new `tests/test_no_repair_state.py` if that file's structure forbids it), add a test asserting that the name `repair_state` no longer occurs in `src/cuemseditor/` (constitution IV.4).

### Implementation for User Story 1

- [ ] T017 [US1] In `src/cuemseditor/CuemsWsUser.py`, add module functions over `server.repair_gates` (data-model.md GateState):
  - `derive_gate(project_uuid, report, script_md5, prior)`. It builds the state dict with the fields `project_uuid`, `report_id`, `outcome`, `file_differs_from_loaded`, `script_md5`, `preserved`, `acknowledged_by` (a `set`) and `report`. It re-uses `prior['report_id']` and keeps `prior['acknowledged_by']` when `prior` exists and `prior['script_md5'] == script_md5`; otherwise it mints a new uuid4 and an empty set.
  - `gate_requires_ack(state)`, which returns `state['outcome'] != 'clean'`. US6's T067 extends it to `acknowledgment_required`.
- [ ] T018 [US1] Rewrite `send_project` in `src/cuemseditor/CuemsWsUser.py` (`:791-850`):
  - delete every `self.repair_state` use;
  - after `open` returns `(value, report, script_md5)`, set `self.server.repair_gates[project_uuid] = derive_gate(..., prior=self.server.repair_gates.get(project_uuid))`, on the loop thread;
  - send `document_load_report` with the state's `report_id`.
- [ ] T019 [US1] Rewrite `repair_acknowledge` in `src/cuemseditor/CuemsWsUser.py` (`:843-862`):
  - look the state up in `self.server.repair_gates.get(value['project_uuid'])`;
  - if it is missing, or `report_id` differs, answer `refuse_save(state_or_stub, 'unacknowledged')` as today;
  - if it matches, add `self.session_id` to `acknowledged_by` and echo.
  - Delete the error frame "no load report to acknowledge on this session" (FR-008).
- [ ] T020 [US1] Rewrite `received_project` in `src/cuemseditor/CuemsWsUser.py` (`:893-950`) per research R8.4. All of it holds `async with file_lock(self.server, self.server.db.project.script_path(unix_name))`; resolve `unix_name` in the executor with `get_project_unix_name`.
  - **No state**: `inspect` in the executor, then `derive_gate`.
  - **State that requires acknowledgment**: `bytes_md5` in the executor. A mismatch runs `inspect` and `derive_gate(prior=None)`, which mints a new id and clears the acknowledgments.
  - **Refuse** with `unacknowledged` when the state requires acknowledgment and `self.session_id not in acknowledged_by`.
  - **Claim `preserved`** before the executor `await`, as at `:918-920` today.
  - **After a successful `update` of a state that required acknowledgment**, replace it with a clean one carrying the new file's md5, from `bytes_md5` in the executor. A state that was already clean stays as it is, with no hash, so T014 holds (Q4).
  - **On `OriginalNotPreserved`**, set `preserved = False` and refuse with `preserve_failed`, as today.

  Delete `self.repair_state` from `__init__` (`:191-197`).
- [ ] T021 [US1] In `project_unload` (`src/cuemseditor/CuemsWsUser.py:499-523`), discard `self.session_id` from the loaded project's `acknowledged_by`. Then drop `repair_gates[uuid]` when no `server.sessions[*]['loaded_project']` equals it. In `request_delete_project` (`:954`), drop `repair_gates[project_uuid]` after a successful delete.
- [ ] T022 [US1] Run `tests/test_repair_gate_durable.py`, `tests/test_document_load_report.py` and `tests/test_db_project_inspect.py`. All of them pass. `test_another_sessions_acknowledgment_does_not_unlock_this_save` (`tests/test_document_load_report.py:272`) passes unedited, which is 001 FR-021 kept.
- [ ] T023 [US1] Replace `tests/ws-command-responses.txt:169-175` ("project_save of a project this session opened…") with the text of contracts/ws-messages.md's "Repair gate frames" section:
  - the gate is per project, and each session acknowledges for itself;
  - it survives a reconnect and an editor restart;
  - a changed file gets a new `report_id`;
  - `cuems-frontend`'s reload-on-reconnect (`src/app/services/projects/load-report.service.ts`) is no longer needed (FR-011).

**Checkpoint**: US1 is complete. Commit it, naming FR-005 to FR-011 and the evidence file.

---

## Phase 4: User Story 2 — Edit the configuration as it really is, without overwriting a colleague (Priority: P1)

**Goal**: `config_load`; `config_save` with `base_revision`, the per-file lock, a backup, structured
refusals, `config_changed` and the restart notice; `network_map` refused (spec FR-012 to FR-023,
FR-015a; Q3).

**Independent Test**: for `settings` and `project_mappings`, `config_load` → edit one value →
`config_save` with the revision → `config_load` again. Then a stale save gets `config_conflict`.

### Tests for User Story 2 (red first)

- [ ] T024 [US2] Create `tests/test_config_round_trip.py` with fixtures modelled on `tests/test_schema_descriptor.py:38-60`: a copied `tests/fixtures/conf` as `CUEMS_CONF_PATH`, with `settings.xml`'s `<library_path>` rewritten to a `tmp_path` library holding `projects/test_project/`. The server mock sets `users`, `sessions`, `repair_gates`, `file_locks` and `notify_others_config_changed = AsyncMock()`. Add `test_config_load_settings_serves_the_file`, asserting:
  - `exists: true`;
  - `revision` equals the md5 of `settings.xml`'s bytes;
  - `document == ConfigManager(load_all=False).to_wire('settings')`.

  It fails today: `unsupported action: config_load`.
- [ ] T025 [P] [US2] In `tests/test_config_round_trip.py`, add `test_config_load_network_map_is_read_only_and_loaded` (research R2: it needs `load_network_map()` first, and the document has key `node_list`). Add `test_config_load_project_mappings_with_its_uuid`: `get_project_unix_name` is mocked to `test_project`, and a `mappings.xml` is copied from `default_mappings.xml`. It needs `load_net_and_node_mappings()` first (R2).
- [ ] T026 [P] [US2] In `tests/test_config_round_trip.py`, add `test_config_load_without_a_file_is_exists_false_with_the_root_instance` (FR-013) for `project_mappings`:
  - `revision` is `None`;
  - `document` equals the descriptor `instance` of the root type `CuemsProjectMappings` (`key.is_path`, no `/` in `key.name`);
  - it is not the error frame.
- [ ] T027 [P] [US2] In `tests/test_config_round_trip.py`, add the error-frame cases for `config_load`: a project domain without `project_uuid`, an unknown `project_uuid` (`get_project_unix_name` raises `NonExistentItemError`), and an unknown schema.
- [ ] T028 [P] [US2] In `tests/test_config_round_trip.py`, add `test_round_trip_settings_and_project_mappings`:
  - load, change one scalar, save with `base_revision`;
  - the reply is `{"type":"config_save","value":{"schema","project_uuid","revision","restart"}}`, and `revision` is the new file's md5;
  - a reload shows the edit, every other field compares equal, and the revision changed (SC-004).
- [ ] T029 [P] [US2] In `tests/test_config_round_trip.py`, add `test_a_stale_base_revision_is_config_conflict_and_writes_nothing` (FR-015): the reply carries the current revision and document, and the file's sha256 is unchanged.
- [ ] T030 [P] [US2] In `tests/test_config_round_trip.py`, add `test_two_simultaneous_saves_write_once_and_conflict_once` (spec US2 #6). `asyncio.gather` two `config_save` coroutines with the same `base_revision` on the same loop and executor. Expect exactly one `config_save` reply and one `config_conflict`.
- [ ] T031 [P] [US2] In `tests/test_config_round_trip.py`, add these refusal tests:
  - `test_missing_base_revision_is_refused` (Q3);
  - `test_null_base_revision_with_an_existing_file_conflicts`;
  - `test_network_map_save_is_refused_and_names_node_set` (FR-019): the file is unchanged, and no `notify_all_node_list_update` is awaited;
  - `test_no_source_path_writes_network_map` (SC-006, FR-025): `'network_map'` is not a key of `CONFIG_SAVE_TARGETS`, and a grep of `src/cuemseditor/` finds no `save_network_map`.
- [ ] T032 [P] [US2] In `tests/test_config_round_trip.py`, add `test_a_library_refusal_is_config_save_refused_with_its_location` (FR-020, research R5). Use a `project_mappings` document with an invalid value, measuring first which field `.save()` refuses with a `Violation` (e.g. a `class` enumeration). Expect:
  - `field`, `location` as a list, `rule` and `message`, with `message` verbatim;
  - the file unchanged.

  Also add `test_an_unknown_top_level_key_is_config_save_refused_without_location` (`IngestError`, where `location` is `None`).
- [ ] T033 [P] [US2] In `tests/test_config_round_trip.py`, add `test_settings_save_names_the_engines_to_restart` (FR-016): `restart == [{"service": "cuems-controller-engine", "where_active": False}, {"service": "cuems-node-engine", "where_active": True}]`. For `project_mappings`, `restart == []`.
- [ ] T034 [P] [US2] In `tests/test_config_round_trip.py`, add `test_other_sessions_get_config_changed` (FR-017): `notify_others_config_changed` is awaited once with `{schema, project_uuid, revision}`, and the saver does not receive it.
- [ ] T035 [P] [US2] In `tests/test_config_round_trip.py`, add `test_the_replaced_file_is_backed_up_first` (FR-015a). After a save, `<library>/trash/config/` holds exactly one `controller_settings_<YYYYmmddTHHMMSS>.xml`, byte-identical to the pre-save `settings.xml`. Add `test_a_failed_backup_saves_nothing`: make `trash/config` a file so the write fails; expect the error frame and `settings.xml` unchanged.
- [ ] T036 [P] [US2] In `tests/test_config_round_trip.py`, add `test_a_pre_013_settings_is_config_load_failed`: write a `settings.xml` with a `<videoplayer>` under `<node>`, measuring the exact pre-013 shape from `../cuems-utils` tests first. Expect `config_load_failed` with the library's message.
- [ ] T037 [US2] Edit `tests/test_schema_descriptor.py`:
  - every `config_save` call gains `base_revision` (the file's md5, or `None`);
  - the `network_map` save test becomes a refusal assertion (FR-019);
  - the `{'type': 'config_save', 'value': 'OK'}` assertions become the object reply.

  Record in the commit message that these edits follow from M3 and Q3.
- [ ] T038 [US2] Rewrite `test_config_save_of_project_settings_fails_before_the_file_exists_pending_ur6` in `tests/test_schema_descriptor.py` as `test_first_config_save_of_project_settings_round_trips`: `config_save` with `base_revision: None` and no file, then `config_load`, and the value is present. Mark it `@pytest.mark.xfail(strict=True, reason="cuems-editor UR-6: ConfigManager.project_path refuses a file not yet created (gate G1)")`. This is gate G1 (FR-032).

### Implementation for User Story 2

- [ ] T039 [US2] In `src/cuemseditor/CuemsWsUser.py`, add `CONFIG_LOAD_STEPS` beside `CONFIG_SAVE_TARGETS` (`:121-126`), mapping each domain to its loader calls per research R2:
  - `settings`: none;
  - `network_map`: `load_network_map`;
  - `project_mappings`: `load_net_and_node_mappings`, `load_project_mappings(uname)`;
  - `project_settings`: refused, naming cuems-editor UR-7.

  Add `_load_config_document(name, project_uname)`, which runs in the executor and returns `(exists, revision, document)`:
  - resolve the path with `conf_path` / `project_path`, where `FileNotFoundError` means `exists: False` with the root `instance` from `get_schema_descriptor`;
  - otherwise `bytes_md5`, then the loader steps on a fresh `ConfigManager(load_all=False)`, then `to_wire`.
- [ ] T040 [US2] Add `async def config_load(self, value, action)` to `src/cuemseditor/CuemsWsUser.py` and register it in the action map (`:255-290`). It resolves `project_uuid` as `config_save` does (`:681-693`), maps `SchemaError` / `IngestError` / `ValidationError` to `config_load_failed`, and sends every other failure as the error frame.
- [ ] T041 [US2] Add `refusal_value(schema, project_uuid, error)` in `src/cuemseditor/CuemsWsUser.py`, modelled on `load_failed_value` (`:139-150`). It returns `{schema, project_uuid, field, location, rule, message}`:
  - `field` is `violation.location[1]`, or `None`;
  - `location` is `list(violation.location)`, or `None`;
  - `rule` is `violation.rule`, or `None`;
  - `message` is `str(error)`.

  Never parse the message (research R5).
- [ ] T042 [US2] Rewrite `config_save` and `_save_config_document` in `src/cuemseditor/CuemsWsUser.py` (`:129-135`, `:636-705`):
  - remove `network_map` from `CONFIG_SAVE_TARGETS` and add it to `CONFIG_SAVE_REFUSED` with the text "network_map.xml is written by cuems-nodeconf; set an alias with node_set";
  - require the `base_revision` key, sending the error frame if it is missing;
  - resolve the target path in the executor;
  - `async with file_lock(...)`: `bytes_md5` in the executor; a mismatch sends `config_conflict` with the current `_load_config_document`;
  - otherwise, in the executor: back up the hashed bytes to `<library_path>/trash/config/<scope>_<stem>_<YYYYmmddTHHMMSS>.xml`, where `<scope>` is `controller` or the `unix_name`. A failed backup raises, and nothing is saved (FR-015a). Then `from_json` → `.save(path)` → `bytes_md5`;
  - reply with the object, carrying `restart` per data-model.md ConfigTarget;
  - then `await self.server.notify_others_config_changed(self, {schema, project_uuid, revision})`;
  - map library refusals to `config_save_refused` via `refusal_value`.

  Delete the `network_map` node-refresh branch.
- [ ] T043 [US2] Add `async def notify_others_config_changed(self, calling_user, value)` to `src/cuemseditor/CuemsWsServer.py`, modelled on `notify_others_list_changes` (`:360`). It sends `{"type":"config_changed","value":value}` to every user except `calling_user`.
- [ ] T044 [US2] In `tests/ws-command-responses.txt`, **in the same commit as T042** (plan ordering 5):
  - add rows for `config_load`, `config_load_failed`, `config_conflict`, `config_save_refused` and `config_changed`, and the new `config_save` inbound and reply shapes, each with its audience (contracts/ws-messages.md);
  - rewrite the "schema_descriptor / config_save" section (`:73-90`) to match: `network_map` is refused, `base_revision` is required, the backup is written, the restart notice is given;
  - document the three save quirks of FR-023 verbatim.
- [ ] T045 [US2] Write `specs/002-config-round-trip/upstream-reports/UR-7-project-settings-has-no-read-projection.md`, in the style of `specs/001-cuems-utils-migration/upstream-reports/UR-6-*.md`, addressed to `cuems-utils` (spec M4, `cuems-utils` requirements doc §0a G2):
  - **Observed**: `_PROJECTABLE_SECTIONS` (`ConfigManager.py:166`) lacks `project_settings`, and `_project_settings_document` (`:531`) is private;
  - **Why**: `config_load` FR-018;
  - **Workaround**: none; `config_load` refuses, naming this report;
  - **Expected**: §0a G2's shape;
  - the editor test that flips.
- [ ] T046 [US2] Add `test_config_load_project_settings_round_trips` to `tests/test_upstream_gates.py` (create the file). Mark it `@pytest.mark.xfail(strict=True, raises=AssertionError, reason="cuems-editor UR-7: project_settings has no public read projection (gate G2)")`. It asserts `config_load` returns `exists: true` and the document that was written.
- [ ] T047 [US2] Run `tests/test_config_round_trip.py`, `tests/test_schema_descriptor.py` and `tests/test_upstream_gates.py`. Everything passes except the two expected xfails (G1, G2).

**Checkpoint**: US2 is complete. Commit T042, T043 and T044 together.

---

## Phase 5: User Story 3 — One written statement of version 1 (Priority: P1)

**Goal**: version 1 restated with JSON booleans and the `config_save` reply folded in, and no live
string booleans in the protocol document (spec FR-001 to FR-004).

**Independent Test**: `tests/test_payload_version.py` passes with 1, and `tests/test_protocol_doc.py`
finds no `"True"` / `"False"` in a live-frame section.

- [ ] T048 [US3] (red first) Create `tests/test_protocol_doc.py`. It splits `tests/ws-command-responses.txt` into sections at its unindented heading lines. It asserts that no section except `initial_template (retired at payload version 1)` contains `"True"`, `"False"`, `'True'` or `'False'`, and that the `payload_version 1:` paragraph contains the words "restated" and "JSON true / false". Save its failing run in `specs/002-config-round-trip/evidence/protocol-doc-failing-first.txt`.
- [ ] T049 [US3] Edit `tests/ws-command-responses.txt`:
  - replace `:68-71` with the restated row in contracts/ws-messages.md;
  - in the `project` section (`:124-147`), delete "and "True" / "False" strings," (`:139`) and add delta (e): `autoload`, `enabled` and `timecode` are JSON booleans, as pinned by `tests/test_project_payload.py`;
  - in the node section (`:206-209`), change "adopted / online "True" / "False" (not JSON true / false)" to "adopted / online JSON true / false";
  - head the `initial_template` section's delta list (`:103`) with "History, retired frame:".

  Run `tests/test_protocol_doc.py` and `tests/test_payload_version.py`; both pass. `CuemsWsServer.PAYLOAD_VERSION` stays `1`.

**Checkpoint**: US3 is complete.

---

## Phase 6: User Story 4 — Rename a node through nodeconf (Priority: P2)

**Goal**: `node_set` sent directly to `/tmp/nodeconf.ipc`; `unavailable` with no IPC; the
nodeconf error relayed verbatim; a `node_list` refresh (spec FR-024 to FR-027; Q2).

**Independent Test**: with a fake `Communicator`, assert the request, the reply and the refresh.
With no socket, assert `unavailable` and no `Communicator` built.

- [ ] T050 [US4] Create `tests/test_node_set.py`, with a `user` fixture modelled on `tests/test_nodelist_actions.py:34-60`. `server.nodeconf_available` is a `MagicMock(return_value=True)`, and `server.notify_all_node_list_update` is an `AsyncMock`. Patch `cuemseditor.CuemsWsUser.Communicator` with a fake whose `send_request` returns `{"OK": True}`. Add:
  - `test_node_set_sends_the_alias_and_refreshes_everyone`: the request equals `{"action":"node_set","node_uuid":NODE,"alias":"Stage left"}`, the reply is `{"type":"node_set","value":{"node_uuid":NODE,"alias":"Stage left"}}`, and the refresh is awaited once;
  - `test_unavailable_answers_at_once_and_builds_no_communicator` (`nodeconf_available` returns `False`; the patched class is never instantiated);
  - `test_nodeconf_error_is_relayed_verbatim_without_retry` (`{"OK": False, "error": "Node x not found"}`: `node_set_refused`, reason `nodeconf_error`, `send_request` called once);
  - `test_a_timeout_is_node_set_refused_timeout` (`send_request` sleeps past a patched `TIMEOUT`);
  - `test_a_sys_exit_from_communicator_is_unavailable` (the fake's constructor raises `SystemExit(1)`; the process survives);
  - `test_non_operator_fields_are_refused_before_ipc`: each of `uuid`, `name`, `node_role`, `ip`, `online`, `adopted`, `role_id`, `hostname` and `mac` gives `node_set_refused` with reason `not_operator_field`, and no instantiation (spec US4 #4);
  - `test_an_invalid_node_uuid_is_refused_before_ipc`: a `node_uuid` that `coerce_identity` rejects gives the refusal and no instantiation (FR-024);
  - `test_the_action_is_registered`.
- [ ] T051 [US4] Implement `async def node_set(self, value, action)` in `src/cuemseditor/CuemsWsUser.py` per research R7. Import `Communicator` from `cuemsutils.tools.CommunicatorServices`. Add `NODECONF_IPC = '/tmp/nodeconf.ipc'` reading `CuemsWsServer.NODECONF_IPC` (do not duplicate the string). The order is:
  1. validate the keys: only `node_uuid` and `alias`;
  2. validate `alias`: a non-empty string or `None`;
  3. `coerce_identity(node_uuid)`, sent as a string;
  4. check `nodeconf_available()`;
  5. build the `Communicator` inside `try/except (SystemExit, PermissionError)` → `unavailable`;
  6. `send_request` under `asyncio.timeout(TIMEOUT)`;
  7. on `OK`, reply, then `notify_all_node_list_update()`.

  Register the action in the map.
- [ ] T052 [US4] Add the `node_set` and `node_set_refused` rows to `tests/ws-command-responses.txt` (contracts/ws-messages.md), and one line in the "Nodes: adoption" section saying that the alias is set with `node_set` and never through `config_save`.
- [ ] T053 [US4] Write `specs/002-config-round-trip/upstream-reports/UR-8-node-set-ipc-command.md`, addressed to `cuems-nodeconf`. Quote `specs/002-config-round-trip/contracts/nodeconf-node_set.md` in full, give today's measured reply (`unknown action: node_set`, research R7), state its dependency on `cuems-utils` `NodeIndex.set_alias` (spec M8), and name the flipping test.
- [ ] T054 [US4] Add `test_nodeconf_engine_callback_accepts_node_set` to `tests/test_upstream_gates.py` (gate G4, research R7):
  - skip only if `../cuems-nodeconf` does not exist;
  - insert it into `sys.path`;
  - stub `netifaces`, `systemd`, `systemd.daemon`, `dbus` and `zeroconf` in `sys.modules` with `MagicMock`, via `monkeypatch.setitem`;
  - import `cuemsnodeconf.CuemsNodeConf`;
  - build it with `__new__`, set `_ready = True`, and give it a `communications_thread` whose `respond_to_engine` records the reply on its own running loop;
  - call `engine_callback` with the exact request T050 asserts;
  - assert `{"OK": True}`.

  Mark it `xfail(strict=True, raises=AssertionError, reason="cuems-editor UR-8: cuems-nodeconf has no node_set (gate G4); needs cuems-utils NodeIndex.set_alias")`. An `ImportError` must error, not xfail.

**Checkpoint**: US4 is complete, with G4 standing as an xfail.

---

## Phase 7: User Story 6 — Media files' real values, and stale values acknowledged (Priority: P2)

**Goal**: the save path of 869fat84r `0b291d1`, ported onto objects (spec FR-036 to FR-048; Q5–Q9;
M9–M11; research R11, R12). It depends on US1, because the comparison feeds `GateState`.

**Independent Test**: FR-042's six tests; then a project whose duration differs from its row gives
`media_repairs`, `acknowledgment_required: true`, and a refused save until it is acknowledged.

**Porting rule for every task in this phase**: copy from `git show 0b291d1:<path>` only what each
task names. Never merge `origin/feat/869fat84r-media-dimensions`, and never take its
`pyproject.toml` hunk (S1). Name the source commit in each commit message: `83d8460` for pixel and
file size, `cd37792` for size and md5, `b29d40e` for the relink guard (FR-048).

### Tests for User Story 6 (red first)

- [ ] T055 [US6] (red first, FR-042) Create `tests/test_media_values.py` with the six T039 tests. Each builds a `CuemsScript` from `tests/fixtures/script_minimal_013.xml`, sets `Media` values on its cues **through attribute assignment**, and runs `CuemsDBProject.update` against a temporary library whose `Media` rows carry known values. Build the library with the `lib` fixture pattern. A failure at the row insert is **not** red: record the red run only after T058 (columns) and T062 (value functions) land and before T063 (the fill), so each test fails on its own assertion.
  1. `test_an_audio_cue_loses_pixel_size_and_a_video_cue_keeps_it`;
  2. `test_an_unknown_class_media_cue_keeps_its_pixel_size` (a cue with `class="lighting"` decodes to a bare `MediaCue`);
  3. `test_an_uppercase_client_md5_is_stored_lowercase_and_the_save_succeeds`, built at the dict payload level (`data` passed to `update`), because a setter would refuse the uppercase value;
  4. `test_a_non_hex_or_wrong_length_md5_is_dropped_and_the_save_succeeds`;
  5. `test_zero_float_and_bool_file_sizes_are_dropped_not_assigned` (`0`, `1.5`, `True`, each in the payload dict);
  6. `test_a_cleared_value_is_absent_not_zero_not_null`. After the save, reload with `CuemsScript.load`: the key is not in the cue's `Media`, and `to_wire()` has no such key.

  Save that failing run (taken between T062 and T063) in `specs/002-config-round-trip/evidence/media-values-failing-first.txt`.
- [ ] T056 [P] [US6] In `tests/test_media_values.py`, add `test_no_item_assignment_on_stored_media_keys` (FR-040, M11). Grep `src/cuemseditor/` with a regex for `\[['"](pixel_width|pixel_height|file_size|file_md5)['"]\]\s*=`, `del \w+\[['"](pixel_width|pixel_height|file_size|file_md5)` and `\.pop\(['"](pixel_width|pixel_height|file_size|file_md5)`. Expect zero hits.
- [ ] T057 [P] [US6] Create `tests/test_media_migration.py`:
  - `test_start_up_adds_the_four_columns_and_keeps_rows`: a SQLite DB made with the **old** `media` schema (no new columns), opened through `CuemsProjectManager`;
  - `test_a_migration_failure_stops_the_start`: `ensure_media_columns` patched to raise;
  - `test_repair_tool_dry_run_never_writes_the_database`: the DB's sha256 is unchanged after `cuems-editor-repair-durations` runs without `--apply` on an old-schema DB;
  - `test_upload_stores_size_pixels_and_lowercase_md5`: `CuemsDBMedia.new` with `probe_dimensions` patched to `(1920, 1080)` and an uppercase md5;
  - `test_a_failed_probe_stores_null_and_does_not_fail_the_upload`.

### Implementation for User Story 6

- [ ] T058 [US6] Port into `src/cuemseditor/CuemsDBModel.py` from `0b291d1`:
  - the four `Media` fields `pixel_width = IntegerField(null=True)`, `pixel_height = IntegerField(null=True)`, `file_size = IntegerField(null=True)` and `file_md5 = CharField(null=True)`, with their docstring lines;
  - the extended `Media` select list;
  - `MEDIA_ADDED_COLUMNS = {'pixel_width': 'INTEGER', 'pixel_height': 'INTEGER', 'file_size': 'INTEGER', 'file_md5': 'VARCHAR(255)'}`;
  - `missing_media_columns` and `ensure_media_columns`, verbatim (FR-036).
- [ ] T059 [US6] Port into `src/cuemseditor/CuemsProjectManager.py` the start-up call `ensure_media_columns(database)`, which logs and re-raises on failure, verbatim from `0b291d1`. Port into `src/cuemseditor/repair_durations.py` **only** the `ensure_media_columns` / `missing_media_columns` use, and the dry run's migrated temporary copy. Do not port `_check_stored`, `--no-md5`, `DIMS_CHANGED` or `MD5_CHANGED` (deferred, spec M9).
- [ ] T060 [P] [US6] Port into `src/cuemseditor/CuemsDBMedia.py` from `0b291d1`:
  - `DIMENSIONS_PROBE_TIMEOUT`, `probe_dimensions` and `media_file_size`;
  - the `new()` changes that store `pixel_width` / `pixel_height` (MOVIE only), `file_size` and `file_md5`.

  Normalise `file_md5` with `CuemsDBProject._md5` rather than `md5.lower()` with a length check. Bring `MediaProbe` and `PROBE_*` only if `new()` uses them (research R11.2) (FR-037).
- [ ] T061 [P] [US6] Port into `src/cuemseditor/CuemsUpload.py` the relink guard from `b29d40e`: a failed `update_projects_existed_media` is logged with `could not relink …` and does not abort the upload. Also pass `received_md5` to `db.media.new` (`0b291d1:CuemsUpload.py:198`).
- [ ] T062 [US6] Port into `src/cuemseditor/CuemsDBProject.py`, verbatim from `0b291d1:CuemsDBProject.py:52-125`: `PIXEL_KEYS`, `STORED_KEYS`, `_positive_int`, `_md5`, `_valid`, `dimensions_of_row` and `db_dimensions_resolver`. `_md5` returns `None` and never raises (FR-038). Do not port `DIMENSION_KEYS`.
- [ ] T063 [US6] Write the object form of the fill in `src/cuemseditor/CuemsDBProject.py` (FR-039 to FR-041, data-model.md "Stored media values"):
  - `_allowed_keys(cue)`, exactly as FR-039 shows: `STORED_KEYS[len(PIXEL_KEYS):] if isinstance(cue, AudioCue) else STORED_KEYS`.
  - `_set_stored(media, values, cue)`: for each key in `STORED_KEYS`, `setattr(media, key, _valid(key, (values or {}).get(key)) if key in _allowed_keys(cue) else None)`. Clearing is assignment of `None`.
  - `_fix_one_media(cue, media, resolver, dimensions_resolver, stats)`:
    1. each present stored key is normalised with `_valid`, and `None` or not-allowed becomes `setattr(media, key, None)`;
    2. the duration is set from `resolver`, as today (an orphan stops here);
    3. `_set_stored(media, dimensions_resolver(file_name), cue)`, when a resolver is given and the file has a row.

    One block that fails is logged and skipped, and the walk goes on. Every client value that step 1 drops or normalises is logged at WARNING with the cue id, the file name and the key (FR-040: the stored keys are derived values owned by the row, so this is not save-time validation).
  - `_walk_media_durations` passes the cue.
  - `fix_media_durations_in_contents(contents, resolver, dimensions_resolver=None)`.
  - `_fix_media_durations` passes `db_dimensions_resolver`, with no probe (Q5).
  - The existing whole-walk `except Exception` in `_fix_media_durations` (`:463-469`) must not hide a per-block failure: per-block failures are counted in `stats.errors`, and a non-empty `stats.errors` is logged at WARNING with the file names.
- [ ] T064 [US6] Run `tests/test_media_values.py` and `tests/test_media_migration.py`. FR-042's six pass, the item-assignment grep is clean, and the migration tests pass.
- [ ] T065 [P] [US6] (red first) Create `tests/test_media_staleness.py`, reusing the `lib` / `server` / `_session` helpers from `tests/test_repair_gate_durable.py`:
  - `test_a_stale_duration_is_a_media_repair_and_requires_acknowledgment`: the script's `Media.duration` differs from the row. Expect `document_load_report.value.media_repairs == [{cue_id, file_name, field: "duration", stored, current}]`, `acknowledgment_required` true, `outcome` `"clean"` (verbatim), and `file_differs_from_loaded` true. The save is refused until acknowledged, then the original is preserved and written;
  - `test_pixel_size_on_an_audio_cue_is_a_media_repair_with_current_null`;
  - `test_missing_values_are_not_stale`: a pre-rc15 script with no stored sizes gives `media_repairs == []`, `acknowledgment_required` false, and the save adds the values;
  - `test_an_orphan_is_not_stale`;
  - `test_an_orphan_keeps_its_values_on_save` (FR-041): a cue whose file has no row keeps its valid stored values through `project_save`;
  - `test_an_invalid_row_value_is_a_media_repair_with_current_null` (spec Edge Cases, FR-044): the row's `file_size` is `0` and the cue holds a valid size. Expect the entry with `current: null`, and after acknowledgment the save removes the cue's value;
  - `test_a_row_change_after_acknowledgment_gets_a_new_report` (FR-045): update the `Media` row between the acknowledgment and the save;
  - `test_media_repairs_is_always_present`: `[]` on a clean load.

  Save the failing run in `specs/002-config-round-trip/evidence/media-staleness-failing-first.txt`.
- [ ] T066 [US6] In `src/cuemseditor/CuemsDBProject.py`, add `media_staleness(script) -> (media_repairs, media_rows_digest)` (FR-043). Walk `script.cuelist.contents` with the same `isinstance(cue, MEDIA_CUES)` walk. For each media cue with a `file_name` and a row, compare the **present** values with the decisions of `0b291d1:CuemsDBProject.py:396-427` `stale_changes`, re-expressed on the object:
  - `duration` (`CTimecode` equality with the row's);
  - `pixel_size`, rendered `"WxH"`, stale when not allowed on the cue or different;
  - `file_size`;
  - `file_md5`.

  `media_rows_digest` is `hashlib.md5(json.dumps(sorted(rows), separators=(',',':')).encode()).hexdigest()`, over the `(file_name, duration, pixel_width, pixel_height, file_size, file_md5)` tuples read. Extend `open` to return `(value, report, script_md5, media_repairs, media_rows_digest)` and `inspect` to return `(report, script_md5, media_repairs, media_rows_digest)`. Update their callers.
- [ ] T067 [US6] In `src/cuemseditor/CuemsWsUser.py`, extend the gate:
  - `derive_gate` takes `media_repairs` and `media_rows_digest`. It stores both, sets `acknowledgment_required = outcome != 'clean' or bool(media_repairs)`, and sets `file_differs_from_loaded = report.file_differs_from_loaded or bool(media_repairs)`. It re-uses the `report_id` only when `script_md5` **and** `media_rows_digest` match (FR-045).
  - `gate_requires_ack(state)` returns `state['acknowledgment_required']`.
  - `received_project` also recomputes the rows digest. It calls a new `CuemsDBProject.media_rows_digest(uuid)`, which reads the rows for the file names in the **on-disk** script via `inspect`'s walk, in the executor, when the state requires acknowledgment. A mismatch re-derives.
- [ ] T068 [US6] In `src/cuemseditor/CuemsWsUser.py` `load_report_value` (and its use by `request_duplicate_project`), add `media_repairs` (always a list) and `acknowledgment_required`, and OR `file_differs_from_loaded` (FR-044). `outcome`, `repairs` and `conversions` stay verbatim.
- [ ] T069 [US6] In `tests/ws-command-responses.txt`, extend the `document_load_report` row (`:20`) and the "Load reports and the save gate" text with `media_repairs` and `acknowledgment_required` (contracts/ws-messages.md). Add one paragraph: a later media check adds its findings to `media_repairs` and never sends a frame that gates a save (FR-046).
- [ ] T070 [US6] Run `tests/test_media_staleness.py`, `tests/test_repair_gate_durable.py`, `tests/test_document_load_report.py` and `tests/test_media_values.py`. All pass.

**Checkpoint**: US6 is complete. Commit per the porting rule, naming the source commits.

---

## Phase 8: User Story 5 — Documentation fixes and gate G3 (Priority: P3)

**Goal**: frontend items 4, 5 and 6 documented, and gate G3 standing (spec FR-028 to FR-031).

**Independent Test**: each named document site carries its statement, and the tip capture script
produces a `project` frame.

- [ ] T071 [P] [US5] In `tests/ws-command-responses.txt`:
  - qualify `:69-70` and `:95`: building from `instance` is not directly usable until `cuems-frontend` UR-1 is fixed in `cuems-utils`, and the config-schema instances are refused too (evidence `descriptor-instance-config.txt`);
  - add beside the `project_save` row (`:30`): "value is {"CuemsScript": …} and nothing beside it; CuemsScript.from_json refuses any other top-level key" (FR-029);
  - in the `schema_descriptor` section, state that `network_map`'s node `uuid` is rendered as a one-value enumeration (the NOT PROVISIONED sentinel), so render it as text (FR-031).
- [ ] T072 [P] [US5] Create `specs/001-cuems-utils-migration/evidence/frontend-handover-instance-caveat.md`, a new file. It names `frontend-handover.md:44` and states the same qualification as T071 (FR-028). Do not edit `frontend-handover.md`.
- [ ] T073 [P] [US5] Create `specs/001-cuems-utils-migration/evidence/project-capture/capture_load_tip.py`. Its docstring names `capture_load.py` as the procedure it supersedes at the tip. It mirrors `capture_load.py`'s temporary-library setup, calls `script, report = CuemsDBProject.load_xml(...)` on `tests/fixtures/script_minimal_013.xml`, and prints `json.dumps({"type": "project", "value": script.to_wire()})`. Run it as quickstart §5 shows, into `specs/002-config-round-trip/evidence/project-frame-tip.json`. Assert `git diff --exit-code specs/001-cuems-utils-migration/evidence/project-capture/capture_load.py` (FR-030).
- [ ] T074 [US5] Add `test_a_cue_built_from_the_descriptor_instance_saves_through_project_save` to `tests/test_upstream_gates.py` (gate G3). Take `schema_descriptor('script')`'s `Cue` and `CueOutput` instances, assemble a script with one audio cue, send it through `CuemsWsUser.received_project` against a temporary library, and assert the `project_save` reply. Mark it `xfail(strict=True, raises=AssertionError, reason="cuems-frontend UR-1: the descriptor instance is not in to_wire() shape and has null required defaults (gate G3)")`.

  Add `test_a_config_root_instance_saves_through_config_save`, parametrized over `settings`, `project_mappings` and `project_settings` (spec G3 (b)). For each, an existing file is in place (a copy from `tests/fixtures/conf`; for the project domains, under the temporary library's `projects/test_project/`). Send the root-type `instance` from `get_schema_descriptor` through `config_save` with the file's current md5 as `base_revision`, and assert the `config_save` reply. Same marker and reason. Using an existing file keeps G1 (UR-6) out of this test.

**Checkpoint**: US5 is complete, with G3 standing.

---

## Phase 9: Polish & Cross-Cutting

- [ ] T075 Add the field notes from FR-035 to `CLAUDE.md` "Field notes":
  - `network_map.xml` is nodeconf's, and the alias goes through `node_set`;
  - a `settings` save requires an engine restart, and the editor only says so;
  - `config_save` backs up into `<library>/trash/config/`, with no UI purge (plan Complexity Tracking);
  - the repair gate is per project, survives a reconnect and a restart, and is re-derived from the file;
  - the media columns are migrated at start-up, the save writes each cue's values from its row, a present-but-stale value is reported in `media_repairs` and acknowledged, and a later media check must add to that section, never gate on its own (FR-046).

  Cite reports as `<repo> UR-<n>`.
- [ ] T076 [P] Create `specs/002-config-round-trip/tag-readiness.md` (FR-033). `../.xml-refactor-tag-messages/` does not exist on this machine; say so, and say that the maintainer copies the text into the tag message. List:
  - each standing strict xfail by gate, `<repo> UR-<n>` and test node id: G1 cuems-editor UR-6, G2 cuems-editor UR-7, G3 cuems-frontend UR-1 (the script test and the three config-instance parameters), G4 cuems-editor UR-8 (cuems-utils `set_alias` + cuems-nodeconf);
  - G5 (cuems-utils' settings-reshape defect, no editor test);
  - the statement "not ready while any xfail stands" (S7).
- [ ] T077 [P] Create `specs/002-config-round-trip/merge-notes.md` (FR-048). Include:
  - the 869fat84r absorption: `0b291d1`, what came in (by file and function), and what was deferred, with spec M9's collision surface verbatim;
  - the `pyproject.toml` hunk not taken (S1);
  - the `cuems-frontend` handover: the workarounds this feature retires (reload-on-reconnect, the `'True'` branch) and the new frames, by contracts/ws-messages.md section (SC-010).

  This is the text for the merge into `feat/xml-refactor`, which the maintainer performs.
- [ ] T078 After T064 passes, write `specs/002-config-round-trip/evidence/t039-absorbed.md` (FR-047). Name:
  - the six FR-042 test node ids in `tests/test_media_values.py`;
  - the commit that made them pass;
  - spec FR-036 to FR-046;
  - the sentence "cuems-utils may delete specs/planning/t039-editor-media-obligations.md and close T039 against these tests".

  Do not edit anything in `../cuems-utils`.
- [ ] T079 Run the full suite as the header shows. Record in `specs/002-config-round-trip/evidence/suite-final.txt`:
  - the summary line: everything passes except exactly seven `xfailed` (G1, G2, G3 × 4, G4), with no `XPASS`. Each matches a node id in `tag-readiness.md`;
  - `cuemsutils.__file__`;
  - the `cuems-utils` SHA.

  Append the final counts to `evidence/environment.txt`'s run list, as a new file if the original is committed (T001's rule).
- [ ] T080 Walk `specs/002-config-round-trip/quickstart.md` §3 and tick each scenario against the test that proves it. Note any scenario without a test in `specs/002-config-round-trip/evidence/quickstart-run.txt`; there should be none.

---

## Dependencies & Execution Order

### Phase dependencies

- **Phase 1 (Setup)** comes first. T002 must exist before any **(red first)** run is recorded.
- **Phase 2 (Foundational)** depends on Phase 1 and blocks every story.
- **US1 (Phase 3)** depends on Phase 2.
- **US2 (Phase 4)** depends on Phase 2 (`file_lock`, `bytes_md5`). It is independent of US1.
- **US3 (Phase 5)** is independent. T049 edits the same file as T023, T044 and T052, so it runs sequentially with them, but in any order.
- **US4 (Phase 6)** depends on Phase 2 only.
- **US6 (Phase 7)** depends on **US1** (T017 to T020: `derive_gate`, `received_project`). T055 to T064 (values, migration, fill) can start right after Phase 2, but T055's red run is recorded between T062 and T063. T065 to T070 (staleness) need US1 done.
- **US5 (Phase 8)** is independent. T074 needs `tests/test_upstream_gates.py` from T046.
- **Polish** depends on every story it summarises. T078 depends on T064.

### Within each story

The red-first test is written, run and saved before the implementation it guards. Contract-document
edits land in the same commit as the payload change they describe (Principle I; plan ordering 5).

### Shared-file sequencing (not parallel)

- `tests/ws-command-responses.txt`: T023, T044, T049, T052, T069, T071.
- `src/cuemseditor/CuemsWsUser.py`: T005, T007, T017 to T021, T039 to T042, T051, T067, T068.
- `src/cuemseditor/CuemsDBProject.py`: T007, T062, T063, T066.
- `tests/test_upstream_gates.py`: T046, T054, T074.

### Parallel opportunities

- T003 with T002.
- In US1: T010 to T016 after T009 (same new file, independent tests; write them together).
- In US2: T025 to T036 are independent tests in one new file.
- In US6: T056 and T057 with T055; T060 and T061 with T058 and T059 (different files).
- US2, US3, US4 and US5 can proceed in parallel after Phase 2, apart from the shared-file lists.
- Polish: T076 and T077.

### Parallel example: after Phase 2

```text
US1: T009 → T010..T016 → T017..T023
US2: T024..T038 → T039..T047
US4: T050 → T051..T054
US6 values: T055..T057 → T058..T062 → (T055 red run) → T063..T064   (staleness T065..T070 waits for US1)
```

---

## Implementation Strategy

### MVP first (User Story 1)

Phases 1 and 2, then US1. That closes the only data-loss path (frontend item 2) and lets
`cuems-frontend` drop its reload-on-reconnect.

### Incremental delivery

1. US1, the gate: data safety.
2. US2 and US3, the config round trip and the restated version 1: the frontend's editing views.
3. US4, `node_set`: G4 stands until nodeconf lands.
4. US6, the media values: the gate already covers them.
5. US5, the documentation and G3.
6. Polish: the tag-readiness and merge notes.

### Exit criterion (S7, SC-009)

The tag is not cut while any of G1 to G4 is `xfailed`. Each flips to `XPASS(strict)` when its owner
lands the fix. Then remove the marker and keep the assertion.

### Task counts

| Phase | Tasks |
|---|---|
| Setup | 3 (T001–T003) |
| Foundational | 5 (T004–T008) |
| US1 (P1) | 15 (T009–T023) |
| US2 (P1) | 24 (T024–T047) |
| US3 (P1) | 2 (T048–T049) |
| US4 (P2) | 5 (T050–T054) |
| US6 (P2) | 16 (T055–T070) |
| US5 (P3) | 4 (T071–T074) |
| Polish | 6 (T075–T080) |
| **Total** | **80** |
