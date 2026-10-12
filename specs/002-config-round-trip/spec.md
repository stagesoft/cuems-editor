<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Feature Specification: Config round trip, a durable repair gate, and the restated version 1 wire

**Feature Branch**: `002-config-round-trip`, branched from `feat/xml-refactor` @ `a3309ab`. It is
**local only**: commit to it, never push it, never give it an upstream. When the feature is done it
is merged into `feat/xml-refactor`. That merge, and any push of `feat/xml-refactor`, is the
maintainer's call.

**Created**: 2026-10-08

**Status**: Clarified 2026-10-08 (four questions) and amended 2026-10-12 to absorb part of
869fat84r (Q5–Q9; see [Clarifications](#clarifications)). The plan artifacts are updated to match.
Ready for `/speckit-tasks`.

**Input**: `specs/planning/xml-refactor/002-specify-prompt.md` (committed at `a3309ab`), which
takes up `specs/planning/xml-refactor/FROM-cuems-frontend-001.md` items 1 to 6. Line numbers below
are at `22093fd` unless another commit is named. The source files are unchanged between `22093fd`
and `a3309ab`.

**Purpose**: this feature collects the editor work that must land before the coordinated tag
`xml-refactor-merge-candidate` can be cut. Feature `001-cuems-utils-migration` is done except for
one task and stays closed. Its bookkeeping (T059 checked, T034 amended) was committed at `a3309ab`
and verified before this branch was created.

**Citation rule**: upstream reports are cited as `<repo> UR-<n>`, never as a bare number. Numbers
collide between repositories (`cuems-utils` `specs/planning/upcoming-feature-requirements-2026-10-02.md`
§4). Requirements from 001 are cited as `001 FR-<n>`. A bare `FR-<n>` in this file is one of
this feature's.

---

## Clarifications

### Session 2026-10-08

- Q: Should the repair gate be tracked per browser session or per project? (Q1) → A: **B.** The
  file-level facts (`report_id`, `outcome`, `file_differs_from_loaded`, `preserved`) are server
  state keyed by project UUID. Acknowledgments are recorded per `session_id` inside that state.
  Reconnects, second sessions and stale tabs are all covered, and 001 FR-021 ("another session's
  acknowledgment does not count") is kept (FR-006).
- Q: When should the editor check the script file on disk before saving? → A: **B.** It checks
  when it holds no record of the project (FR-009), and also when a record exists but the file's
  md5 differs from the md5 taken when the report was made. A changed file gets a fresh report, and
  the old acknowledgments are dropped. A clean, unchanged project gets no extra load (FR-009a).
- Q: Should `node_set` go straight to nodeconf or through the engine? (Q2) → A: **A, direct.** The
  editor opens `/tmp/nodeconf.ipc` itself. `cuems-engine` is not a party to the contract, and
  `nodelist_modify` keeps its engine route (FR-024).
- Q: Must every `config_save` carry `base_revision`? (Q3) → A: **A, required.** A request without
  the key is refused. `null` means "I expect no file" (FR-015).

### Session 2026-10-12

- Q: Which parts of the 869fat84r media-values branch (`origin/feat/869fat84r-media-dimensions` @
  `0b291d1`) does 002 take in? (Q5) → A: **C, the save path only.**
  - In: the four `Media` columns and their `ALTER TABLE`, the upload probe (size, pixel size,
    md5), and the `_fix_one_media` fill ported to objects (FR-036 to FR-042).
  - Deferred to a follow-on feature, with its collision surface recorded (spec M9): no probe at
    save time, no `media_check_report`, and no `CuemsMediaRefresh`.
- Q: May a media report ever refuse a `project_save` on its own? (Q6; the prompt's Q3) → A: **A,
  never.** But, in the maintainer's words, "repaired stale media should go to the script-repair
  report and be acknowledged by the operator". Follow-up → **B, already in 002.**
  - At load, the editor compares each cue's stored `Media` values with that file's library row, on
    the object already loaded. There is no probe and no second reader.
  - Present-but-different values become media entries in `document_load_report`, under the same
    `report_id` and acknowledgment as the script repairs. They gate the save the way a script
    repair does.
  - A value that is merely missing (a pre-rc15 project) is not stale. The save adds it without a
    report.
  - The deferred media check, when built, adds its findings to the same section. It never sends a
    frame of its own that gates a save (FR-043 to FR-046).
- Q: One report on the wire, or two? (the prompt's Q2) → **Settled by Q6, not asked separately:
  one frame.** `document_load_report` carries both parts, with one `report_id`, one acknowledgment
  and one lifecycle. The `report_id` re-use rule gains a second condition, a digest of the library
  rows the media comparison read (FR-045).
- Q: How does `document_load_report` say that a clean script has stale media values? (Q7) → A:
  **B.** `outcome` and `repairs[]` stay the library's verdict, verbatim.
  - The report gains `media_repairs[]` (items `{cue_id, file_name, field, stored, current}`).
  - It also gains `acknowledgment_required`, true when `outcome != "clean"` or `media_repairs` is
    non-empty.
  - `file_differs_from_loaded` is true when either part differs.
  - These are new optional keys, so there is no payload-version bump (FR-044).
- Q: One state store, or two? (Q8; the prompt's Q4) → **Moot under Q5 = C, not asked.** No
  in-flight registry (`_IN_PROGRESS`, `_OPEN_IN_PROGRESS`) comes into 002. If the follow-on
  brings them, they stay request de-duplication outside `GateState`, because `GateState` is the
  state that must survive a reconnect (M9).
- Q: `GateState.file_md5` and `Media.file_md5` share a name. Rename? (Q9; the prompt's Q5) →
  **Renamed, not asked.** The gate's field is `script_md5`. `file_md5` is a schema element name
  (`cms:Md5Type`, `cuems-utils` 014) and is fixed upstream.

---

## Settled inputs

These were decided before this spec. `/speckit-clarify` does not reopen them.

- **S1. The library version stays `cuemsutils 0.1.0rc16`.** That is the coordinated version of
  the merge candidate. `pyproject.toml` (`>=0.1.0rc16,<0.1.1`) and `debian/control` do not change.
  rc16 covers both the 013 and the 014 library, so the exact `cuems-utils` commit this feature is
  verified against is recorded in this feature's `evidence/`, as 001 did for 013.
- **S2. The payload version stays 1, and its definition is restated.** `8f8b46e` moved the
  booleans to JSON `true`/`false` without a bump. Version 1 never shipped, so it is redefined as
  the merge-candidate wire, real booleans included. This is the "rule restated" option the frontend
  offered. There is no bump. The protocol document must say so explicitly, so `cuems-frontend` can
  drop its `'True'` string branch.
- **S3. The UI reads values from the file, edits them, and writes them back.** It shows the file's
  real values, not descriptor defaults. The read projection is `ConfigManager.to_wire(section)` on a
  freshly loaded manager. A round trip was measured: fixtures → `to_wire` → JSON → `from_json` →
  `save` → reload. `settings` and `network_map` reload equal. The descriptor serves form metadata
  only. Its `instance` is the document only when no file exists yet.
- **S4. Every save sends the whole document.** The library replaces whole documents, and the round
  trip shows that untouched fields come back intact. There is no patch format.
- **S5. `network_map.xml` is written by `cuems-nodeconf`. The editor does not write it.** Measured
  in nodeconf's `CuemsNodeConf.py`:
  - `read_network_map()` runs only at startup;
  - `refresh_network_map` and `_save_network_map` write nodeconf's in-memory copy;
  - `CuemsNetworkMapType.refresh` decides whether to write by comparing in-memory signatures, never
    the file on disk.

  So nodeconf's next write silently reverts any outside write. That next write comes on a discovery
  change, an IP change, or any adopt or un-adopt. The fields have these owners:
  - `uuid`, `name`, `node_role`, `ip`, `online`: discovery, which overwrites them on every pass;
  - `adopted`: nodeconf, through `nodelist_modify` ADD/REMOVE;
  - `role_id` and `hostname`: nodeconf (`cuems-common` `docs/node-identity-contract.md:35-37`).
    **Not editable from the UI**, by any action (M7);
  - `alias`: the operator (UI), and the **only** node field the operator owns. Nothing publishes it
    over mDNS: nodeconf's alias publishing (`_ui_alias`) publishes a deployment constant
    (`../cuems-nodeconf/specs/planning/12-node-set-alias.md`, R3).

  So `config_save` stops accepting `network_map`. Reading it through `config_load` is fine. Alias
  edits go to nodeconf over IPC (US4).
- **S6. Every upstream gap is a strict xfail that flips when its owner fixes it.** No gap gets a
  hand-rolled workaround. The editor does not duplicate the `library_path/projects/<uname>/<file>`
  convention, and it does not read `ConfigManager._project_settings_document`
  (`tests/test_public_surface.py` forbids it).
- **S7. Exit criterion: no strict xfail remains when the tag is cut.** Every upstream gate in
  [Upstream gates](#upstream-gates) blocks the tag. None of them is a follow-up.

---

## Measured findings that shape this spec

Each finding was measured on `feat/xml-refactor` @ `a3309ab`, against `cuems-utils` @ `67c89bd`
(branch `014-xs-boolean-and-media-elements`).

**M1. `nodelist_modify` does not reach nodeconf from the editor. It goes through the engine.**
`CuemsWsUser.nodelist_modify` (`CuemsWsUser.py:526`) sends to the engine over `/tmp/editor.ipc`
(`comunicate_with_engine`). The engine forwards to `ipc:///tmp/nodeconf.ipc`
(`cuems-engine` `src/cuemsengine/tools/communicate.py:6`). The editor only checks whether
`/tmp/nodeconf.ipc` exists (`CuemsWsServer.nodeconf_available`, `:569`); it never opens it. The
nodeconf handler that answers `{"OK": false, "error": "unknown action: …"}` is
`CuemsNodeConf.engine_callback` on `cuems-nodeconf` `origin/feat/xml-refactor` @ `2045897`
(`cuemsnodeconf/CuemsNodeConf.py:368`, `:419`). "Shaped like `nodelist_modify`" therefore has two
readings: a direct editor → nodeconf hop, or a new verb on the engine route. They differ in whether
`cuems-engine` is a party to the contract. This was agenda item **Q2**, resolved as direct (Clarifications).

**M2. A repair gate held only in editor memory does not survive an editor restart.** The prompt's
risk is a stale tab or a dropped socket. A server-side gate keyed by project UUID covers both.
Neither covers this case: the editor restarts, the tab reconnects, and the tab sends `project_save`
for a project the new process never loaded. On that path today, as after a reconnect, the save is
accepted, nothing is moved to the trash, and the original is overwritten. A settings save now tells
the operator to restart services (FR-021), so an editor restart is a routine event, not a rare one.
FR-009 closes this case.

**M3. `config_save`'s reply is an existing message whose form changes.** Today it replies
`{"type": "config_save", "value": "OK"}` (`CuemsWsUser.py:636`). This feature puts the new revision
and, for `settings`, the restart notice into that reply. Under the bump rule
(`tests/ws-command-responses.txt:62-64`) a change of value form is a bump. Version 1 has not shipped,
so the change is folded into the restated version 1 together with the booleans (S2, FR-002). It is
named there explicitly, so nobody later mistakes it for an unrecorded bump.

**M4. `project_settings` has no public read projection. `project_mappings` has one.**
`_PROJECTABLE_SECTIONS` (`cuems-utils` `src/cuemsutils/tools/ConfigManager.py:166`) contains
`project_mappings` and not `project_settings`, and no public property exposes the loaded project
settings document. This is the gap that becomes **cuems-editor UR-7** (FR-018).

**M5. The UR-6 test is an error pin, not an xfail.**
`tests/test_schema_descriptor.py::test_config_save_of_project_settings_fails_before_the_file_exists_pending_ur6`
asserts today's error frame. Under S6 it becomes a strict-xfail round-trip assertion (gate G1, FR-032).

**M6. `capture_load.py` was correct for the code it ran against.** It records the procedure that
produced the rc14 `project` frame at editor `e05f4e7`
(`specs/001-cuems-utils-migration/evidence/project-capture/README.md`). It fails at the tip because
`load_xml` now returns `(CuemsScript, LoadReport)`. The evidence rule says files there are immutable
and that "a correction is a new file that names the one it supersedes"
(`evidence/README.md:8-10`). Editing the script would also falsify the record of what produced the
committed bytes. FR-030 decides accordingly.

**M7. `role_id` and `hostname` are nodeconf's, and are not editable — settled 2026-10-08.** The
prompt's S5 and CLAUDE.md said operators hand-populate `role_id`, `alias` and `hostname` during the
nodeconf transition. `cuems-common` `docs/node-identity-contract.md:35-37`, which is the contract,
gives `role_id` and `hostname` to **nodeconf** and only `alias` to the operator (UI). `cuems-utils`
requirements doc §0a G4 follows the contract, and S5 above has been corrected to match it. So:
- `node_set` carries `alias` only (FR-024);
- a request naming `role_id` or `hostname` is refused before anything is sent (US4 scenario 4);
- `config_save` cannot reach them either, because it refuses `network_map` (FR-019).

The hand-population note in CLAUDE.md describes how a manual transition is done on the file, not
who owns a field through the UI. This feature leaves it alone.

**M8. G4 has two owners.** `cuems-utils` §0a G4 (added 2026-10-08) asks the library for
`NodeIndex.set_alias(node_uuid, alias) -> bool`, an in-place setter, because nodeconf delegates
every map mutation to the library. Nodeconf's `node_set` handler is built on top of it. The gate
closes only when both have landed.

**M9. 869fat84r is absorbed in part, and the rest has a recorded collision surface.**
`origin/feat/869fat84r-media-dimensions` @ `0b291d1` has 9 commits off `d9e0a39`, 14 files,
+3132/−57. It is not an ancestor of this branch. It was written on the rc15 line: wire-dict walks,
`CuemsParser`, `XmlReaderWriter`.

**Comes in (Q5 = C)**, ported onto the object line, never merged textually:
- the four `Media` columns (`pixel_width`, `pixel_height`, `file_size`, `file_md5`), with
  `MEDIA_ADDED_COLUMNS`, `missing_media_columns` and `ensure_media_columns`, called at start-up
  (`CuemsProjectManager`) and by the repair tool;
- the upload probe: `probe_dimensions` and `media_file_size`, the upload-verified md5, and
  `Media.create(…)` storing them;
- the value logic: `PIXEL_KEYS`, `STORED_KEYS`, `_positive_int`, `_md5`, `_valid`,
  `dimensions_of_row`, `db_dimensions_resolver`;
- the fill: `_allowed_keys`, `_set_dimensions`, `_dimensions_snapshot`, `_fix_one_media` and the
  walk, re-expressed on cue identity and attribute setters (FR-038 to FR-040);
- the decision logic of `stale_changes`, re-expressed on objects for the load-time comparison
  (FR-043);
- `CuemsUpload`'s relink guard (a failed relink is logged, not fatal).

**Does not come in:**
- `pyproject.toml`'s `cuemsutils>=0.1.0rc15`, which S1 forbids. The SPDX header lines may come in.
- `CuemsMediaRefresh.py`: `refresh_media_before_load`, `check_media_on_open`, `_IN_PROGRESS`,
  `_OPEN_IN_PROGRESS`, the indexer.
- The save-time re-probe (`_save_resolvers` → `_verify_row_for_save`, `REFRESH_DEADLINE_S`).
  002's save resolvers only read the database.
- `media_report`, `plan_media_refresh`, `MediaFileCheck`, `_light_media_blocks`, `stale_by_file`,
  `cap_report_files`, the `_FAILED/_VERIFIED/_INDEX_FAILED` marks, `mark_index_failed`.
- `media_check_report` and `send_to_project_sessions`.
- `repair_durations`' stored-value re-measurement (`_check_stored`, `--no-md5`, `DIMS_CHANGED`,
  `MD5_CHANGED`). The repair tool takes only the column migration (FR-036).
- `tests/test_media_refresh.py`.
- The parts of `tests/test_media_dimensions.py` that exercise anything listed above.

**Collision surface for the follow-on feature.** It is bound by Q6:
- Its findings enter `document_load_report.media_repairs[]` (FR-046). It sends no frame of its own
  that gates a save.
- `GateState` is the only per-project report state. Any in-flight registry it brings is request
  de-duplication and lives outside `GateState` (Q8).
- Its re-probe changes library rows. That invalidates an outstanding report through FR-045's rows
  digest, not through a second identity.
- Its script reader must be the library's object load, not `_light_media_blocks` (M10).
- It lands in `CuemsDBProject.py` beside FR-038's object walk, and calls it rather than copying
  it.

**M10. `_light_media_blocks` reports an empty project on every 013 document.** It reads the script
with `xml.etree.ElementTree` and iterates elements named `AudioCue` and `VideoCue`
(`0b291d1:CuemsDBProject.py:380-393`). A 013 document has `<Cue class="audio">` and
`<Cue class="video">` (`tests/fixtures/script_minimal_013.xml`), so it finds no `Media` block, and
`media_report` says "nothing stale" for every project. No error is raised. This is the R2 defect in a
second reader, and porting the reader would also add a schema-less reader of script documents,
which 001 rejected. That is why 002's load-time comparison (FR-043) walks the loaded `CuemsScript`.

**M11. On the object line, `Media` is a `dict` subclass, and item assignment bypasses the setters.**
This was measured against the library at `b2ea09a`:
- the attribute setters raise as the prompt's R1 states (an uppercase or non-hex `file_md5`;
  `pixel_width` of `0`, `1.5` or `True`);
- assigning `None` removes the key;
- **`media['file_md5'] = 'ZZ'` stores `'ZZ'` without complaint.**

So a textual port that keeps `media[key] = value` and `del media[key]` does not raise. It stores
invalid values silently, and only the save's T1 validation, if anything, catches them. FR-040
requires attribute assignment and forbids item assignment and `del` on `Media`.

---

## User Scenarios & Testing *(mandatory)*

This feature has three groups of users:

- the **show operator**, who edits settings, project settings, project mappings and node aliases in
  the UI, and saves projects;
- the **UI team** (`cuems-frontend`), which builds against this repository's wire and has filed
  `FROM-cuems-frontend-001.md`;
- the **ecosystem maintainer**, who cuts `xml-refactor-merge-candidate` and needs every gate closed.

### User Story 1: A repaired script cannot overwrite its original unseen, after a reconnect or a restart (Priority: P1)

An operator opens a project that the library repaired or converted on load. Their WebSocket drops
and reconnects, or the editor restarts, or a second browser tab that never loaded the project sends
a save. In every one of these cases the save is refused until an operator who has seen the report
acknowledges it. The first save after acknowledgment still moves the original into the library
trash before writing.

**Why this priority**: today any dropped socket reaches the outcome that the load report exists to
prevent (frontend item 2): a repaired document silently overwrites the original with no copy in the
trash. This violates Principle III. It is the only item in this feature that can lose user data.

**Independent Test**: load a repaired fixture, reconnect with the same `session_id`, send
`project_save`, and expect `repair_save_refused`. This test is written first and fails against
`a3309ab`. Repeat with a second session that never loaded the project, and with a fresh server
process over the same library (the restart case).

**Acceptance Scenarios**:

1. **Given** a project loaded as `repaired` and not acknowledged, **When** the client reconnects with
   the same `session_id` and sends `project_save`, **Then** the reply is `repair_save_refused`
   (reason `unacknowledged`) and the file on disk is unchanged.
2. **Given** that reconnected session, **When** it re-sends `repair_acknowledge` with the report it
   was shown, **Then** it gets the echo, not the error frame. The next save moves the original into
   the trash and then writes.
3. **Given** a second session that never loaded the project, **When** it sends `project_save` for
   that project, **Then** the save is refused (Clarifications, Q1).
4. **Given** an editor restart, **When** a reconnecting tab sends `project_save` for a project whose
   file on disk the library would still repair or convert, **Then** the save is refused and the
   original stays in place (FR-009).
5. **Given** an acknowledged, saved project, **When** it is saved again, **Then** no second trash copy
   is made. There is one preserve per stale file.
6. **Given** a session that sends `project_unload`, **When** that session saves the same project
   later without loading it again, **Then** the save is treated as one from a session that never
   loaded it.
7. **Given** a clean load, **When** the project is saved after a reconnect, **Then** nothing is
   refused and nothing is moved. A clean project gains no new step.

---

### User Story 2: The operator edits the configuration as it really is, and does not overwrite a colleague's change (Priority: P1)

An operator opens Settings, Project settings or Project mappings. The form shows what the
controller's file actually holds. If no file exists yet, it shows the schema's starting document and
says that no file exists. The operator edits and saves the whole document. If someone else saved
the same file in the meantime, the save is refused, and the refusal carries the current document so
the UI can show what changed. If the library refuses the document, the refusal names the offending
field. After a settings save, the operator is told which services must restart for the change to
take effect.

**Why this priority**: without a read, `cuems-frontend` ships these views read-only (frontend item
3, `cuems-frontend` UR-2). An editing form built on descriptor defaults would overwrite a working
configuration with blanks, because `config_save` replaces the whole document (S4).

**Independent Test**: for each of `settings` and `project_mappings`, run `config_load` → edit one
value → `config_save` with the returned revision → `config_load` again. Assert that the edited value
is present, untouched values are unchanged, and the revision changed. Then save with the old
revision and expect `config_conflict` carrying the current document and revision.

**Acceptance Scenarios**:

1. **Given** an existing `settings.xml`, **When** a client sends `config_load` for `settings`,
   **Then** it receives `exists: true`, the md5 of the file's bytes as `revision`, and the document as
   `to_wire("settings")` projects a freshly loaded manager. The startup copy is never served.
2. **Given** a project with no `mappings.xml` yet, **When** `config_load` asks for `project_mappings`
   with that `project_uuid`, **Then** the reply is `exists: false`, `revision: null`, and the
   descriptor's `instance` as `document`, not the error frame.
3. **Given** `config_load` for a project domain without `project_uuid`, or with an unknown one,
   **Then** the reply is the error frame, as `config_save` answers today.
4. **Given** a client holding revision R, **When** it sends `config_save` with `base_revision: R`
   and the file still hashes to R, **Then** the document is written, the reply carries the new
   revision, and every other session receives `config_changed`.
5. **Given** a client holding revision R, **When** another session saved first, **Then** its
   `config_save` is refused with `config_conflict` carrying the current document and revision, and
   the file is not written.
6. **Given** two saves of the same file that arrive together with the same `base_revision`, **Then**
   exactly one is written and the other gets `config_conflict`.
7. **Given** a document the library refuses (`SchemaError` / `IngestError`), **When** it is saved,
   **Then** the reply is `config_save_refused`, which names the violation's location where the
   library gives one, and the file is unchanged.
8. **Given** a successful `settings` save, **When** the reply arrives, **Then** it says that
   `cuems-controller-engine` must restart, plus `cuems-node-engine` where it is active.
9. **Given** `config_save` for `network_map`, **Then** it is refused, and the refusal says that
   alias edits go through `node_set`. `script` and `hardware_outputs` stay refused as today.
10. **Given** `config_load` for `network_map`, **Then** it is served read-only, like `settings`.

---

### User Story 3: The UI team can act on one written statement of version 1 (Priority: P1)

The UI team reads `tests/ws-command-responses.txt` and finds one definition of payload version 1:
the merge-candidate wire, with real JSON booleans everywhere they were strings, and the new
`config_save` reply. Nothing in the document still describes `"True"` / `"False"`. The team can
delete its dual-read branches.

**Why this priority**: today two different wires both announce version 1 (frontend item 1), so the
consumer has to keep code for both. Fixing that costs one document and one test, and it unblocks
cleanup on the other side.

**Independent Test**: `tests/test_payload_version.py` passes with 1 and finds the restated row. A
test asserts that no description of the `project`, `node_list` or `initial_mappings` frames in the
protocol document mentions string booleans. Delta (e) of the `project` frame, which
`tests/test_project_payload.py` already pins, is listed in the document.

**Acceptance Scenarios**:

1. **Given** the protocol document, **When** read, **Then** the version-1 row says explicitly that
   version 1 is redefined as the merge-candidate wire, that this is not a bump, and that a client
   built for version 1 may drop string-boolean handling.
2. **Given** the `project` frame section, **When** read, **Then** it lists delta (e): `autoload`,
   `enabled` and `timecode` are JSON booleans. The sentence "'True' / 'False' strings, are unchanged"
   (`:139`) is gone.
3. **Given** the node section, **When** read, **Then** `adopted` / `online` are described as JSON
   booleans (`:208`). The `initial_template` history keeps its delta list as history, marked as the
   retired frame's (`:103`).
4. **Given** the advertised version, **When** the suite runs, **Then** it is still 1.

---

### User Story 4: The operator renames a node, and the name sticks (Priority: P2)

An operator gives a node an alias in Settings. The alias is sent to `cuems-nodeconf`, which owns the
file, and the new name reaches every open UI through the usual node list. Where nodeconf is not
running, the operator is told that renaming is unavailable on this controller, rather than seeing a
save that nodeconf will quietly revert.

**Why this priority**: an operator can rename a node only by hand-editing a file that the running
daemon overwrites (S5). It is P2 because the editor half cannot be finished without nodeconf's half,
which is an upstream gate.

**Independent Test**: against a fake nodeconf IPC peer (as `tests/test_nodelist_actions.py` does),
send `node_set` with a uuid and an alias. Assert the request the peer receives, the reply, and the
all-session `node_list` refresh. With no peer, assert the `unavailable` answer and that no file was
written.

**Acceptance Scenarios**:

1. **Given** nodeconf is available, **When** a client sends `node_set` with `node_uuid` and `alias`,
   **Then** the request is forwarded as `{"action": "node_set", "node_uuid": …, "alias": …}`. On
   success the client gets the confirmation, and every session gets a refreshed `node_list`.
2. **Given** `nodeconf_available` is false, **When** `node_set` is sent, **Then** the answer is
   `unavailable`, immediately and without a timeout. The editor writes no file.
3. **Given** nodeconf answers with an error, **When** it is relayed, **Then** the error text reaches
   the client unchanged, with no retry (as 001 FR-036 does for `nodelist_modify`).
4. **Given** a `node_set` that tries to change a field discovery or nodeconf owns (`name`,
   `node_role`, `ip`, `online`, `adopted`, `role_id`, `hostname`, or the uuid itself), **Then** the
   editor refuses it before sending anything, and the refusal names the field.

---

### User Story 5: The next consumer does not rediscover the frontend's findings (Priority: P3)

A developer reads this repository's protocol document and evidence. They learn that a descriptor
`instance` is not yet directly saveable, that `project_save` takes `{"CuemsScript": …}` and nothing
beside it, which library quirks a config save has, and how to reproduce the `project` frame capture
at the tip.

**Why this priority**: documentation only. The frontend has already found and worked around each of
these (frontend items 4, 5, 6). This story stops the next consumer from paying the same cost.

**Independent Test**: read each doc site listed in FR-028 to FR-031 and confirm the statement is
there. Run the tip capture script and confirm it produces a `project` frame.

**Acceptance Scenarios**:

1. **Given** `ws-command-responses.txt:69-70`, `:95` and `evidence/frontend-handover.md:44`, **When**
   read, **Then** the advice to build from `instance` is qualified: not directly usable until
   `cuems-frontend` UR-1 is fixed in `cuems-utils`.
2. **Given** the `project_save` row, **When** read, **Then** it says that `value` is
   `{"CuemsScript": …}` and nothing beside it.
3. **Given** the tip capture script, **When** run, **Then** it emits the tip's `project` frame.
   `capture_load.py` is byte-unchanged.

---

### User Story 6: A project stores its media files' real values, and the operator sees any correction before it is saved (Priority: P2)

An operator uploads a video. The library records its duration, pixel size, file size and md5. When
a project that uses the file is saved, its cues carry those values: a video cue carries all of them,
and an audio cue carries everything except the pixel size. A value the client sent that is not
valid is dropped, so it never fails the save. If a project on disk holds values that differ from
the library's (a file was re-uploaded, or the repair tool corrected a duration), opening the project
says so in the load report, and the operator acknowledges it before the save writes the corrected
values. Values that are merely missing, as in an older project, are added by the next save without
a report.

**Why this priority**: the engine relies on these values at playback (duration for Auto-follow
timing, pixel size instead of a probe at arm time). A silent rewrite of a cue's values is the same
class of change the repair gate exists to surface (Principle III). It is P2 because it adds no new
operator action. It reuses the acknowledgment from US1.

**Independent Test**: the six tests of FR-042, each failing first. Then load a project whose script
holds a duration different from its library row, and assert that `media_repairs` names it,
`acknowledgment_required` is true, and a save is refused until it is acknowledged.

**Acceptance Scenarios**:

1. **Given** an upload of a movie, **When** it completes, **Then** its row stores the pixel size,
   size and lowercase md5. A failed probe stores nothing for that value and does not fail the
   upload.
2. **Given** a database without the four columns, **When** the editor starts, **Then** they are
   added, existing rows keep their data, and a failure stops the start with a logged reason.
3. **Given** a save, **When** a video cue's `Media` arrives, **Then** it leaves with the row's
   values. An audio cue's `Media` carries no pixel size, and a bare `MediaCue` (unknown class) keeps
   its pixel size.
4. **Given** client values the setters would refuse (an uppercase md5, a non-hex md5, `0`, `1.5`,
   `True`), **When** saved, **Then** the md5 is lowercased or dropped, the rest are dropped, and the
   save succeeds.
5. **Given** a script whose stored duration differs from its row, **When** it is opened, **Then**
   the report lists it in `media_repairs` and requires acknowledgment. The save is refused until
   then, and the first save after acknowledgment preserves the original in the trash.
6. **Given** a pre-rc15 script with no stored sizes, **When** it is opened, **Then** the report is
   clean for media, and the next save adds the values.

---

### Edge Cases

- **A reconnect whose `session_id` the server no longer knows** (`CuemsWsServer.py:310-318` mints a
  new one): the repair gate must not depend on the client's id surviving. FR-008 and FR-009 cover
  it.
- **The file on disk changes between load and save** (another session saved it, or a hand edit):
  the report the operator acknowledged describes a document that no longer exists. The file's md5
  differs from the one recorded with the report, so the gate is re-derived from the file, and old
  acknowledgments are dropped (FR-009a).
- **A preserve that fails**: unchanged from 001 FR-021a. Nothing is saved (reason
  `preserve_failed`).
- **`config_save` with `base_revision` for a file that did not exist when loaded** (`revision: null`)
  and still does not exist: the save is accepted. If the file has appeared since, the save gets
  `config_conflict`. For project domains it is still blocked by `cuems-editor` UR-6 until that is
  fixed.
- **`config_save` with no `base_revision` key**: refused (Clarifications, Q3). An omitted revision
  is not a wildcard.
- **Two sessions saving different files**: locks are per target file, so these saves do not wait on
  each other. A project's `settings.xml` and the controller's `settings.xml` are different targets.
- **A hand edit, or a nodeconf write, that leaves the bytes unchanged**: the md5 is the same, so no
  conflict is raised. This is correct, because the content is the same.
- **nodeconf rewrites `network_map.xml` while a client holds a `network_map` revision**: there is no
  save to conflict with, because `network_map` is read-only (S5). The client sees the change through
  `node_list` (watcher push), and a fresh `config_load` returns the new revision.
- **`settings.xml` in the pre-013 device shape** (the development box's `/etc/cuems/settings.xml`,
  `cuems-utils` requirements doc §7): `config_load` returns the library's refusal as a structured
  failure, as `config_save_refused` does. It does not return the error frame with a stack trace.
- **A `settings` save on a controller whose engine is running a show**: the editor sends only the
  restart notice. It does not restart anything (out of scope).
- **`node_set` for a node that has just disappeared**: nodeconf answers. The editor relays the
  answer unchanged.
- **The save quirks**: a saved file is unindented XML, its `doc_version` is upgraded, and its
  `schemaLocation` is rewritten (FR-023). The next `config_load` therefore returns a different
  revision from the pre-save file's, even for an unchanged document. That is expected, and a client
  must take the revision from the save reply.
- **A library row changes while a media report is outstanding** (a re-upload of the same name, or
  the repair tool's pass A): the script's bytes are unchanged, but the rows digest is not. The
  report is re-derived with a new `report_id`, and acknowledgments are dropped (FR-045).
- **A cue whose media file has no library row** (an orphan): its values are left as they are, and
  it is not reported as stale.
- **A row whose value is itself invalid** (a pre-migration `file_size` of `0`): `dimensions_of_row`
  treats it as unknown, so the save removes the cue's value instead of writing `0`.
- **The editor and an older editor share a migrated database**: the added columns are additive, and
  peewee selects named columns, so an older editor still reads it (`0b291d1` `ensure_media_columns`
  docstring).

## Requirements *(mandatory)*

### Functional Requirements

**A. Payload version 1 restated (US3; frontend item 1)**

- **FR-001**: `tests/ws-command-responses.txt` MUST restate payload version 1 as the merge-candidate
  wire. It MUST say in so many words that version 1 never shipped, that the change from string
  booleans to JSON booleans (`8f8b46e`) is folded into version 1 rather than bumped, and that a
  client built for version 1 needs no string-boolean handling.
- **FR-002**: The restated row MUST enumerate everything folded into version 1 after its first
  statement: JSON booleans on `project` (`autoload`, `enabled`, `timecode`) and on `node_list` nodes
  (`adopted`, `online`), and the new `config_save` reply form (M3, FR-016). Delta (e) of the `project`
  frame MUST be listed in the `project` section, matching `tests/test_project_payload.py`.
- **FR-003**: Every description of a current frame that says booleans are strings MUST be corrected:
  `:139` (`project`) and `:208` (nodes). `:103` describes the retired `initial_template`. It MUST stay
  as history and be marked as the retired frame's. Its delta (a) MUST NOT be read as describing a
  live frame.
- **FR-004**: `CuemsWsServer.PAYLOAD_VERSION` MUST stay 1, and `tests/test_payload_version.py` MUST
  keep passing. A test MUST fail if a live-frame description in the protocol document says
  `"True"` / `"False"`.

**B. The repair gate outlives the connection (US1; frontend item 2)**

- **FR-005**: The failing test MUST come first. It loads a repaired fixture, reconnects with the same
  `session_id`, sends `project_save`, and expects `repair_save_refused`. Its failing run against
  `a3309ab` MUST be captured in this feature's `evidence/`.
- **FR-006**: Repair-gate state MUST be held where a reconnect does not drop it, and a stale or
  second session cannot bypass it (Clarifications, Q1). It is split in two:
  - the file-level facts (`report_id`, `outcome`, `file_differs_from_loaded`, `preserved`) are server
    state keyed by **project UUID**;
  - acknowledgment is recorded per `session_id` within that project's state.

  With this split, a reconnect that reuses its `session_id` keeps its acknowledgment, and a session
  that never acknowledged is refused. 001 FR-021's rule "another session's acknowledgment does not
  count" is kept.
- **FR-007**: The state MUST be read and written only on the event-loop thread (Principle II). The
  decision to preserve MUST still be claimed before the executor `await`, so that each stale file is
  moved at most once (as at `CuemsWsUser.py:918-920` today).
- **FR-008**: `repair_acknowledge` from a session that holds no state of its own for the project
  MUST be accepted when its `project_uuid` and `report_id` match the project's current outstanding
  report. It MUST NOT get the error frame "no load report to acknowledge on this session" in that
  case.
- **FR-009**: When `project_save` arrives for a project with no gate state in this process (an editor
  restart, or a save from a session that never loaded it), the editor MUST determine the gate from
  the file on disk before writing. Concretely, it loads the file with the library's report-returning
  load, in the executor, and runs the media comparison (FR-043). A report with
  `acknowledgment_required` is refused as `unacknowledged`, and the refusal names a report the
  session can obtain by loading the project. Otherwise the save goes ahead as today. The original
  MUST NOT be overwritten unpreserved on any path (Principle III).
- **FR-009a**: The project's gate state MUST record `script_md5`, the md5 of the script file's
  bytes as loaded for the report (Q9). On `project_save` of a project with non-clean gate state, the editor MUST re-hash
  the file in the executor before deciding.
  - If the hash differs, the state is re-derived from the file as in FR-009. That makes a new
    `report_id` and drops every acknowledgment. The save is refused as `unacknowledged` unless the
    new report has no `acknowledgment_required`. A changed `media_rows_digest` has the same effect
    (FR-045).
  - If the hash is the same, the recorded acknowledgments decide.

  Projects whose gate state is clean need no hash and no extra load (Clarifications).
- **FR-010**: `project_unload` (`CuemsWsUser.py:515-518`) MUST clear that session's acknowledgment
  for the project. When no session still references the project's state, that state MUST be dropped.
  A successful save that writes the repaired document MUST retire the outstanding report, because the
  file on disk now matches.
- **FR-011**: The protocol document's "Load reports and the save gate" section
  (`ws-command-responses.txt:169-175`) MUST be updated to say what survives a reconnect and a restart.
  It MUST also say that `cuems-frontend`'s reload-on-reconnect workaround
  (`load-report.service.ts`) is no longer needed.

**C. `config_load` and revision-checked `config_save` (US2; frontend item 3, `cuems-frontend` UR-2)**

- **FR-012**: A new action `config_load` with `{schema, project_uuid?}` MUST reply
  `{"type": "config_load", "value": {schema, project_uuid, exists, revision, document}}` to the
  caller only.
  - `document` is `ConfigManager.to_wire(section)` on a manager built for this request (never the
    startup `load_all=True` copy). The model is `_save_config_document`'s `load_all=False` pattern.
  - `revision` is the md5 of the file's bytes, computed by this repository. `cuems-utils` has no
    helper for it. It is never an mtime.
  - Domains: `settings`, `network_map` (read only), `project_mappings`, `project_settings`. Every
    other schema, and any other name, is refused as `config_save` refuses it.
  - Scalars are served as the library projects them. The editor does not normalise them.
    `network_map` is the only domain whose decode runs the adapter table.
- **FR-013**: When the target file does not exist, `config_load` MUST reply `exists: false`,
  `revision: null`, and the descriptor's `instance` for the domain's root type as `document`. It
  MUST NOT reply with the error frame.
- **FR-014**: For `project_mappings` and `project_settings`, `project_uuid` MUST be required, and it
  MUST be resolved with `CuemsDBProject.get_project_unix_name`, as `config_save` resolves it. A
  missing or unknown `project_uuid` is the error frame. The editor MUST NOT build the
  `projects/<uname>/<file>` path itself (S6).
- **FR-015**: `config_save` MUST require `base_revision`: the md5 from `config_load`, or `null` for
  "no file yet". A request without the key is refused with the error frame and writes nothing
  (Clarifications, Q3). Under one asyncio lock per resolved target file, the editor MUST re-hash the file:
  - if the hash does not match, it refuses with
    `{"type": "config_conflict", "value": {schema, project_uuid, revision, document}}`, carrying the
    current revision and document, and writes nothing;
  - otherwise it runs `from_json` → `save` → re-hash.

  The hash, the build and the write run in the executor. The lock is held on the loop across them.
- **FR-015a** *(added by the plan's Constitution Check, Principle III, 2026-10-12)*: Before a
  `config_save` overwrites an existing file, the editor MUST write the bytes it just hashed to
  `<library_path>/trash/config/<scope>_<file stem>_<YYYYmmddTHHMMSS>.xml`. `<scope>` is
  `controller` or the project's `unix_name`. If that write fails, nothing is saved, and the reply
  is the error frame. The live file is never moved away. A first save (no file) has nothing to
  back up. A test against a temporary library MUST assert that the backup exists and is
  byte-identical to the old file.
- **FR-016**: A successful `config_save` MUST reply
  `{"type": "config_save", "value": {schema, project_uuid, revision, restart}}`. `revision` is the
  new md5. `restart` lists the services that must restart for the change to take effect: for
  `settings`, `cuems-controller-engine`, plus `cuems-node-engine` where it is active; for the other
  domains, an empty list. This form replaces `"OK"`, and it is part of restated version 1 (M3,
  FR-002).
- **FR-017**: After a successful save, `{"type": "config_changed", "value": {schema, project_uuid,
  revision}}` MUST be broadcast to every **other** session. The saving session has the reply. Its
  audience MUST be recorded in the protocol document (Principle II).
- **FR-018**: `config_load('project_settings')` needs a public read projection that does not exist
  yet (M4). The editor MUST NOT read `ConfigManager._project_settings_document` and MUST NOT project
  the document itself. Until `cuems-utils` provides the projection, `config_load('project_settings')`
  MUST refuse with a message naming **cuems-editor UR-7**, and the round-trip test is a strict xfail
  (gate G2). UR-7 MUST be filed in this feature's `upstream-reports/` and indexed in the `cuems-utils`
  requirements document's terms (`<repo> UR-<n>`).
- **FR-019**: `config_save` MUST refuse `network_map`, and the refusal MUST name `node_set` as the
  path for alias edits (S5). It keeps the existing refusals of `script`, `hardware_outputs`, non-schema
  names and `default_mappings.xml`. The all-session node refresh after a `network_map` save is
  removed with the save.
- **FR-020**: A document the library refuses (`SchemaError`, `IngestError`, or a validation error
  carrying a violation) MUST be answered with
  `{"type": "config_save_refused", "value": {schema, project_uuid, field, location, message}}`,
  modelled on `load_failed_value` / `document_load_failed`. `location` is the violation's location
  when the library gives one, and `null` otherwise. `message` is the library's text. Other failures
  (I/O, an unknown project) stay the error frame. A refusal by `config_load` for a document the
  library cannot load (for example the pre-013 shape) uses the same shape under type
  `config_load_failed`.
- **FR-021**: The restart notice MUST be the only thing the editor does about restarting. The engine
  caches its configuration at startup (CLAUDE.md), and an engine-side reload is out of scope.
- **FR-022**: Every new frame type (`config_load`, `config_load_failed`, `config_conflict`,
  `config_changed`, `config_save_refused`, `node_set`) MUST get a row in
  `tests/ws-command-responses.txt`, with its audience. New types need no version bump.
- **FR-023**: The protocol document MUST record these measured quirks of a config save, without
  fixing them:
  - a save writes unindented XML (`settings` went from 2429 bytes / 44 lines to 1901 bytes / 1
    line);
  - a save upgrades `doc_version` (2 → 3 for `settings`) and rewrites `schemaLocation`;
  - `from_json('settings')` accepts by design the body that `to_wire('settings')` returns one level
    deeper.

  So a client MUST take the new revision from the save reply, not compute it.

**D. Alias editing through nodeconf (US4)**

- **FR-024**: A new action `node_set` with `{node_uuid, alias}` MUST forward
  `{"action": "node_set", "node_uuid": …, "alias": …}` directly to nodeconf on `/tmp/nodeconf.ipc`. The engine does not relay it (Clarifications, Q2).
  `nodelist_modify` keeps its engine route, because the engine must refuse adoption while a project
  is loaded.
  Only operator-owned fields are accepted, and `alias` is the only one (M7). A request carrying any
  field owned by discovery or by nodeconf, **`role_id` and `hostname` included**, is refused before
  anything is sent. The identity check
  uses `cuemsutils.tools.coerce_identity` (001 FR-035).
- **FR-025**: Where `nodeconf_available` is false, `node_set` MUST answer `unavailable` at once,
  without an IPC attempt or a timeout. The editor MUST NOT write `network_map.xml` as a fallback,
  on any path.
- **FR-026**: After a successful reply, every session MUST be refreshed as after `nodelist_modify`
  (`notify_all_node_list_update`). The `watch_network_map` push also covers it. An error reply from
  nodeconf MUST be relayed unchanged, with no retry.
- **FR-027**: The message shape is a cross-repository contract with `cuems-nodeconf`. The request
  MUST be written as an upstream report in this feature's `upstream-reports/`, addressed to
  `cuems-nodeconf`. The report gives the message, the reply, the field ownership from S5, and the
  "unknown action" answer that nodeconf's `engine_callback` gives today. It is gate G4. Tests run
  against a fake IPC peer, as `tests/test_nodelist_actions.py` does.

**E. Documentation fixes (US5; frontend items 4, 5, 6)**

- **FR-028**: The advice to build from the descriptor's `instance` (`ws-command-responses.txt:69-70`,
  `:95`) MUST be qualified: it is not directly usable until `cuems-frontend` UR-1 is fixed in
  `cuems-utils`. `evidence/frontend-handover.md:44` is immutable, so the qualification for it goes in
  a new file beside it that names it (`evidence/README.md:8-10`).
- **FR-029**: The `project_save` row MUST say that `value` is `{"CuemsScript": …}` and nothing beside
  it, because `CuemsScript.from_json` refuses any other top-level key.
- **FR-030**: `capture_load.py` MUST stay byte-unchanged (M6). A new script beside it,
  `project-capture/capture_load_tip.py`, MUST name `capture_load.py` as the procedure it supersedes
  at the tip, unpack `script, report = …`, and emit `script.to_wire()`. A run of it is recorded in
  this feature's `evidence/`. Nothing under `specs/001-cuems-utils-migration/evidence/` is edited.
- **FR-031**: The protocol document MUST say that the descriptor renders `network_map`'s node `uuid`
  as a one-value enumeration (the NOT PROVISIONED sentinel). This is a known `cuems-utils` gap
  (requirements doc §5), and a form must render the field as free text.

**Upstream gates (S6, S7)**

- **FR-032**: Each gate in [Upstream gates](#upstream-gates) MUST be a `strict=True` xfail test whose
  reason names the gate as `<repo> UR-<n>`, and which flips to XPASS, failing the suite, the day its
  owner fixes the gap. No gate is answered with a workaround in this repository.
- **FR-033**: The tag-readiness record (the tag message prepared under 001 FR-039) MUST list every
  strict xfail still standing. It MUST NOT be marked ready while any remain (S7).

**Bookkeeping**

- **FR-034**: The exact `cuems-utils` commit this feature is verified against MUST be recorded in
  `specs/002-config-round-trip/evidence/`, with the environment procedure. The local hatch
  environment cannot resolve rc16 from the index, so the procedure is to install
  `../cuems-utils` editable into the environment, as `001 evidence/environment.txt` records.
- **FR-035**: `CLAUDE.md` "Field notes" MUST gain these entries:
  - `network_map.xml` is nodeconf's, and the editor never writes it;
  - an alias is set through `node_set`;
  - a `settings` save requires restarting the engines, and the editor only says so;
  - the repair gate is keyed by project and survives a reconnect and an editor restart.
  - the media columns are added at start-up, a save writes each cue's media values from the
    library rows, and a stale value is reported at load and acknowledged before it is saved.

**F. Media values, absorbed from 869fat84r `0b291d1` (US6; Q5–Q9, M9–M11)**

- **FR-036**: `Media` MUST gain the nullable columns `pixel_width`, `pixel_height`, `file_size` and
  `file_md5`. They are added to an existing database by `ensure_media_columns`, which is additive
  and idempotent, at every editor start (`CuemsProjectManager`). A failure stops the start. The
  repair tool MUST run the same migration before it reads the database. Its dry run MUST NOT write
  the database: on a database without the columns, it reads a migrated temporary copy.
- **FR-037**: An upload MUST store, on its new row, a movie's pixel size (`probe_dimensions`, the
  first video stream), the file size (`media_file_size`), and the md5 the upload already verified,
  normalised with `_md5`. A value that cannot be read is stored as `NULL` and never fails the upload.
  The file is not hashed a second time.
- **FR-038**: The save path's media fill MUST be the object walk 002 already has (`isinstance(cue,
  MEDIA_CUES)`), extended to the stored values. The pure value functions `_positive_int`, `_md5`,
  `_valid`, `dimensions_of_row` and `db_dimensions_resolver` are ported unchanged, and `_md5` keeps
  returning `None` rather than raising. `fix_media_durations_in_contents` takes the walk's
  `dimensions_resolver`. The save's resolvers MUST only read the database, with no probe and no
  file read (Q5).
- **FR-039**: Which stored keys a cue may carry MUST be decided by cue identity, never by a wire key:
  ```python
  def _allowed_keys(cue):
      return STORED_KEYS[len(PIXEL_KEYS):] if isinstance(cue, AudioCue) else STORED_KEYS
  ```
  An `AudioCue` carries size and md5. Anything else, including a bare `MediaCue` (an unknown
  `class`), carries all four. `_fix_one_media` takes the cue object, not a type string.
- **FR-040**: On `Media`, every value MUST be normalised with `_valid` before it reaches a setter,
  and it MUST be written by **attribute assignment**. A key MUST be cleared by assigning `None`. Item
  assignment (`media[key] = …`), `del media[key]`, `media.pop(key)` and assigning `0` are forbidden
  for the stored keys (M11), and a test greps the source for them. No raw client value is ever
  assigned.
- **FR-041**: Media values the save writes MUST come from the library row, for the keys the cue may
  carry. A row value that is unknown or invalid removes the cue's value. An orphan cue (no row)
  keeps its values unchanged.
- **FR-042**: These six tests MUST exist and fail before FR-038 to FR-041 land. Their failing run is
  captured in `evidence/`. They close `cuems-utils` T039 (FR-047):
  1. an `AudioCue` whose `Media` arrives with `pixel_width` / `pixel_height` loses both, and a
     `VideoCue` keeps them (this fails against a port of `cue_type == 'AudioCue'`);
  2. a cue of unknown class (a bare `MediaCue`) keeps its pixel size;
  3. an uppercase client `file_md5` is stored lowercase, and the save succeeds;
  4. a non-hex or wrong-length `file_md5` is dropped, and the save succeeds;
  5. `file_size` of `0`, `1.5` and `True` from a client is dropped, not assigned;
  6. clearing a stored value leaves the key absent: not `0`, and not projected as `null` by
     `to_wire`.
- **FR-043**: At load (`CuemsDBProject.open` and `inspect`), the editor MUST compare each media
  cue's **present** stored values with its library row, on the loaded `CuemsScript` object. It uses
  the same decisions as the fill (FR-039 to FR-041): duration, pixel size (a cue that may not carry
  one but does is stale), file size, md5. The comparison runs no probe and parses no file. A value
  that is merely missing is not stale. An orphan is not stale.
- **FR-044**: `document_load_report` MUST gain two keys, and the payload version is not bumped
  (new optional keys):
  - `media_repairs[]`: items `{cue_id, file_name, field, stored, current}`. `field` is one of
    `duration`, `pixel_size` (`"WxH"`), `file_size` and `file_md5`. `current` is `null` when the
    save will remove the value.
  - `acknowledgment_required`: true when `outcome != "clean"` or `media_repairs` is non-empty.

  `outcome` and `repairs[]` stay the library's report verbatim. `file_differs_from_loaded` is true
  when the library says so or `media_repairs` is non-empty. The save gate (FR-006 to FR-010) and the
  preserve-to-trash step (001 FR-021a) key on `acknowledgment_required` and that combined flag.
- **FR-045**: `GateState` MUST record `media_rows_digest`: the md5 of the canonical JSON of the
  `(file_name, duration, pixel_width, pixel_height, file_size, file_md5)` rows the comparison read.
  A `report_id` is re-used only while both `script_md5` and `media_rows_digest` match. On
  `project_save` with non-clean state, a mismatch of either re-derives the state as FR-009a states.
- **FR-046**: The deferred media check (M9) is bound by Q6: its findings MUST enter
  `media_repairs[]`, and it MUST NOT send a frame that gates `project_save`. This repository's
  `ws-command-responses.txt` and CLAUDE.md say so, so the follow-on starts from it.
- **FR-047**: When FR-042's six tests pass, a short note MUST be written to this feature's
  `evidence/t039-absorbed.md`, naming the tests by node id, the 002 commit, and this spec's FR-036
  to FR-046. The maintainer then tells `cuems-utils` that
  `specs/planning/t039-editor-media-obligations.md` is absorbed, and T039 can close. This feature
  does not edit or delete anything in `cuems-utils`.
- **FR-048**: The commit that ports each piece MUST name `0b291d1` and the 869fat84r commit it
  comes from (`83d8460`, `cd37792`, `b29d40e` for the relink guard). The PR description lists what
  was deferred (M9).

### Upstream gates

Each gate is a strict xfail here. All must flip before the tag (S7).

| Gate | Owner | The editor test that flips |
|---|---|---|
| **G1**: `cuems-editor` UR-6. `conf_path`/`project_path` refuse a file not yet created. Wanted shape: `must_exist=False` | `cuems-utils` | today's error pin `test_config_save_of_project_settings_fails_before_the_file_exists_pending_ur6`, rewritten as a round-trip assertion (first `config_save` of a project's `settings.xml`, then `config_load`) |
| **G2**: `cuems-editor` UR-7 (filed by this feature). `project_settings` has no public read projection: it is missing from `_PROJECTABLE_SECTIONS` and has no public property | `cuems-utils` | `config_load('project_settings')` round trip |
| **G3**: `cuems-frontend` UR-1. The descriptor `instance` is not in `to_wire()` shape, and some required output fields have `null` defaults | `cuems-utils` | a cue built from `schema_descriptor('script')`'s `instance`, saved through `project_save`, and reloaded |
| **G4**: `node_set` IPC command (`cuems-editor` UR-8, filed by this feature) | `cuems-utils` (`NodeIndex.set_alias`, requirements doc §0a G4), then `cuems-nodeconf` (the handler) | the US4 test against a real-shaped reply from nodeconf's handler |

`cuems-utils` §0a also lists **G5**: 013's reshape defeats F3's `settings` 1 → 2 conversion
(`settings-reshape-defeats-f3-conversion-defect.md` there). It blocks the tag, but it is the
library's and has no editor test. The tag-readiness record (FR-033) lists it beside G1-G4 so that
the gate list is complete there as well.

### Key Entities

- **Config document**: one of `settings.xml` and `network_map.xml` (controller-wide), or a project's
  `settings.xml` and `mappings.xml`. It is always read and saved whole. Its wire form is
  `ConfigManager.to_wire`. It has an owner: `network_map` belongs to nodeconf; the other three belong
  to the operator through the editor.
- **Revision**: the md5 of a config document's bytes when they are read. It is opaque to clients.
  `null` means "no file". It is used only for the stale-write check, and it is not a version
  (neither `doc_version` nor the payload version).
- **Repair gate state**: per project, the outstanding load report (`report_id`, `outcome`, the
  `media_repairs`, whether the file differs, whether it has been preserved, `script_md5` and
  `media_rows_digest`) and the set of sessions that acknowledged it. It
  lives as long as the file it describes is stale. When the process restarts, the gate is
  re-derived from the file (FR-009).
- **Restart notice**: the list of services whose cached configuration a save has made stale.
- **Operator field (node)**: `alias`, the only node field the operator (UI) owns
  (`cuems-common` `docs/node-identity-contract.md`, M7). It is editable from the UI only through
  nodeconf.
- **Upstream gate**: a strict-xfail test, named by `<repo> UR-<n>`, that blocks the tag until it
  flips.
- **Stored media values**: the duration, pixel size (movies only), file size and md5 of a media file,
  held on its library row (source of truth) and copied into each cue's `Media` by the save. An
  `AudioCue` never carries a pixel size. Absent means unknown, and `0` is never a value.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In 100% of the tested paths (a reconnect with the same session, a reconnect with a new
  session, a second session, an editor restart, a stale tab), a repaired or converted script is never
  written over its original without an acknowledgment and a preserved copy. Today the reconnect path
  fails this every time.
- **SC-002**: The configuration that every editing form opens with is the file's content, byte for
  byte as the library projects it. In 0 cases is a defaults-only document shown for a file that
  exists.
- **SC-003**: A save based on an out-of-date read is refused 100% of the time, including two saves
  that arrive simultaneously, and 0 bytes of the newer file are lost.
- **SC-004**: A round trip with no edits (load → save → load) leaves every field of `settings` and
  `project_mappings` equal. The bytes differ only by the recorded save quirks.
- **SC-005**: The protocol document contains 0 descriptions of a live frame that uses string
  booleans. It has exactly one statement of version 1, and the advertised payload version is 1.
- **SC-006**: The editor writes `network_map.xml` in 0 code paths.
- **SC-007**: When nodeconf is unavailable, the operator learns that renaming is unavailable at once,
  not after an IPC timeout.
- **SC-008**: Every new frame type has a row in the protocol document, with its audience.
- **SC-009**: When the tag is cut, 0 strict xfails stand. Until then, every standing xfail is listed
  in the tag-readiness record by `<repo> UR-<n>`.
- **SC-010**: The `cuems-frontend` workarounds that this feature retires (the reload on reconnect and
  the `'True'` string branch) are each named in the handover, together with the requirement that
  retires them.
- **SC-011**: FR-042's six tests pass, each shown failing first. Item assignment on `Media`'s stored
  keys occurs 0 times in `src/`.
- **SC-012**: In 100% of the tested cases, a project whose script holds a media value that differs
  from its library row is never saved without an acknowledgment and a preserved original. A
  pre-rc15 project with merely missing values needs neither.

## Clarification agenda

All three were resolved on 2026-10-08, each taking its default (see [Clarifications](#clarifications)).

| # | Question | Default in this spec |
|---|---|---|
| **Q1** | Key the repair gate by `session_id` (fixes reconnects only) or by project UUID on the server (also covers a second session and a stale tab)? | **Resolved 2026-10-08 (B): by project UUID** (the prompt's recommendation, because the risk is to the file on disk), with acknowledgment recorded per `session_id` inside the project's state. This keeps 001 FR-021's "another session's acknowledgment does not count". Plus FR-009: with no state in this process (an editor restart), the gate is re-derived from the file before writing (M2). Neither keying alone covers a restart |
| **Q2** | `node_set` route: the editor opens `/tmp/nodeconf.ipc` directly, or the engine relays it as it relays `nodelist_modify` (M1)? | **Resolved 2026-10-08 (A): direct to `/tmp/nodeconf.ipc`**, as the prompt states. A direct hop keeps `cuems-engine` out of a contract that is about a file the engine never writes. `nodelist_modify` stays on its engine route, because the engine must refuse adoption while a project is loaded. An alias change has no such engine precondition |
| **Q3** | Is `base_revision` required on every `config_save`, or optional, meaning "last writer wins"? | **Resolved 2026-10-08 (A): required.** `config_save` has not shipped in any released UI (it is part of version 1), so requiring it breaks no deployed consumer. An optional revision would leave the overwrite this feature exists to prevent as the easy path |

## Out of scope

- **A configuration reload in `cuems-engine`.** The editor only sends the restart notice (FR-016,
  FR-021).
- **The union-type descriptor fix, the library's XML formatting, and the release-time rebind of
  `<< 0.1.1~` across siblings** (`cuems-utils` requirements doc §3). The rebind belongs to 0.1.1,
  not to this tag.
- **`hardware_outputs`** stays refused until `cuems-utils` gives it a model (planned for
  `cuems-utils` 015).
- **Frontend changes.** `cuems-frontend` consumes this feature's contract. The workarounds it can
  then delete are named in the handover (SC-010), not edited here.
- **Editing `role_id` / `hostname` through the UI.** They belong to nodeconf (M7).
- **Writing `network_map.xml` under any condition**, including as a fallback when nodeconf is down
  (S5, FR-025).
- **Feature 001's last open task.** 001 stays as it is.
- **The rest of 869fat84r** (M9): `CuemsMediaRefresh`, the save-time and pre-load re-probe, the
  video indexer, `media_check_report`, and the repair tool's stored-value re-measurement. These go
  to a follow-on feature bound by FR-046 and M9's collision surface.

## Assumptions

- The test environment resolves `cuemsutils` from the sibling `../cuems-utils` checkout, installed
  editable into the hatch environment. That checkout is at `67c89bd` on
  `014-xs-boolean-and-media-elements` when this spec is written. The commit actually verified
  against is recorded in `evidence/` (FR-034).
- md5 is used as a change detector, not as a security control. A deliberate collision attack on a
  controller's configuration is not in the threat model. The prompt names md5, and the library has
  just adopted `Md5Type` for `file_md5`.
- The concurrent-edit policy for **config documents** changes from "last writer wins, then notify" to
  "a stale write is refused, then notify". Under Principle II this is a contract change, and FR-015,
  FR-017 and FR-022 record it. The policy for **scripts** (`project_save`) is unchanged.
- A per-file asyncio lock is enough for exclusion because the editor is a single process. Other
  writers of the same files (an operator with a text editor) are covered by the re-hash, not by the
  lock.
- `cuems-node-engine` being "active" is something the editor cannot observe. The restart notice
  names it conditionally, and the operator decides.
- Commits are GPG-signed. If `gpg failed to sign`, the commit is retried, never bypassed.
