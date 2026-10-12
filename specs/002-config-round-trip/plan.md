<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Implementation Plan: Config round trip, a durable repair gate, and the restated version 1 wire

**Branch**: `002-config-round-trip` (local only; never pushed, no upstream) | **Date**: 2026-10-12 |
**Spec**: [spec.md](spec.md)

**Input**: the feature specification, clarified 2026-10-08 (Q1–Q4).

## Summary

The editor gains a revision-checked configuration round trip:
- `config_load` serves a file's real values and its md5;
- `config_save` refuses a stale write, backs up the file it replaces, and announces the change;
- `network_map` stops being written here, and alias edits go to nodeconf as `node_set` over
  `/tmp/nodeconf.ipc`.

The repair gate moves from the connection to a per-project server table, with acknowledgments per
session. The editor re-derives the gate from the file on disk when it holds no state (a restart, a
stale tab), or when the file's md5 changed.

Payload version 1 is restated as the merge-candidate wire, with JSON booleans and the new
`config_save` reply, without a bump.

It also absorbs the save path of 869fat84r (`0b291d1`), ported onto objects (spec Q5–Q9, M9–M11,
research R11, R12):
- four `Media` columns, with a start-up migration;
- the upload probe;
- a fill that writes each cue's stored media values from the library rows, by cue identity and
  through the strict setters;
- a load-time comparison that puts present-but-stale media values into `document_load_report`'s
  new `media_repairs`, behind the same acknowledgment gate.

The rest of 869fat84r is deferred, with its collision surface recorded.

Four upstream gaps (G1–G4) are strict xfails that must flip before the tag. The approach comes from
[research.md](research.md) R1–R10.

## Technical Context

**Language/Version**: Python 3.11 (hatch environment interpreter 3.11.5; the bookworm target is
3.11)

**Primary Dependencies**:
- `cuemsutils 0.1.0rc16` (pin unchanged, S1), editable from `../cuems-utils` @ `b2ea09a`, `src/`
  clean. Public surface used:
  - `ConfigManager`: `to_wire`, `from_json`, `get_schema_descriptor`, `conf_path`, `project_path`,
    `load_network_map`, `load_net_and_node_mappings`, `load_project_mappings`;
  - `CuemsScript.load_with_report`;
  - `cuemsutils.tools.CommunicatorServices.Communicator`;
  - `cuemsutils.tools.coerce_identity`;
  - `cuemsutils.errors.{SchemaError, IngestError, ValidationError}`.
- `websockets`, `pynng` (through `Communicator`), `peewee`.
- `hashlib` from the standard library.

**Storage**: files, plus `project-manager.db` (SQLite through peewee), which gains four nullable
`media` columns through an additive `ALTER TABLE` (FR-036). Files: The config XML is under `CUEMS_CONF_PATH` and `<library>/projects/<uname>/`,
and the script XML under the library. In-memory server tables: `repair_gates` and `file_locks`. No
DB schema change.

**Testing**: `pytest` with the environment's interpreter (`$(hatch env find)/bin/python -m pytest`,
never `hatch run`, research R1). The tests use temporary libraries, `MagicMock` servers, and fake
`Communicator` peers, as in `tests/test_nodelist_actions.py` and `tests/test_schema_descriptor.py`.
Baseline: 160 passed, 3 skipped.

**Target Platform**: Debian 12 controller, `cuems-editor.service` (systemd). Development happens on
Debian 13.

**Project Type**: a single-package asyncio WebSocket middleware (`src/cuemseditor/`).

**Performance Goals**: none binding (the constitution's Governance admits no budget without a
baseline). Design constraint (Q4): a clean project's save adds no library load and no hash.

**Constraints**:
- Blocking work in the executor; shared state only on the loop (Principle II).
- No `cuemsutils.xml` import, and no access to private attributes (Principle V,
  `tests/test_public_surface.py`).
- Evidence under `specs/001-…/evidence/` is immutable.

**Scale/Scope**: a handful of operator sessions per controller; four config files plus one script
per project. Lock and gate tables are bounded by the project count.

## Constitution Check

*GATE: checked before Phase 0, and again after Phase 1 (below). Status: **PASS**, with one finding
fixed by a spec amendment (FR-015a) and one record carried in Complexity Tracking.*

**I. The Wire Is A Contract**

Wire deltas, each enumerated in [contracts/ws-messages.md](contracts/ws-messages.md):
- **Changed**:
  - `config_save`'s reply, from `"OK"` to an object;
  - `config_save`'s inbound value, which gains a required `base_revision`;
  - `network_map` is refused by `config_save`.

  The JSON booleans are already on the wire (`8f8b46e`). All of these fold into the restated
  version 1, which has not shipped.
- **New types**: `config_load`, `config_load_failed`, `config_conflict`, `config_save_refused`,
  `config_changed`, `node_set`, `node_set_refused`. No bump.
- **Consumer**: `cuems-frontend` does not read `config_save` today. Its own gate fails on any use
  (frontend item 3). So no deployed component's reading changes before the UI.
- **Pre-change captures**: the existing tests pin `{"type":"config_save","value":"OK"}` and the
  `project` frame. The new tests assert the new shapes and fail against `a3309ab` (IV.2).
- **Wording**: Principle I's example "the **string** boolean form ("True")" describes the version-0
  wire. This feature changes no principle. A PATCH amendment that rewords the example is
  recommended, not required, and is left to the maintainer.

**II. Sessions Are Isolated, The Event Loop Is Shared**

Every new frame has a declared audience (contracts).
- `repair_gates` and `file_locks` are created and mutated on the loop thread only. Hashing,
  loading and saving run in the executor.
- The media comparison (FR-043) and the upload probe run in the executor. The comparison adds no
  file read beyond the load `open` already performs.
- **Concurrent-edit policy changes for config documents**, from last-writer-wins to refusing a
  stale write. This is recorded as a contract change (spec Assumptions; FR-015, FR-017). Scripts
  keep last-writer-wins.
- The gate's acknowledgments stay keyed by `session_id`, so one session's acknowledgment never
  unlocks another's save.

**III. User Data Has A Recovery Story**

| Write path | Recovery |
|---|---|
| `project_save` of a repaired script | trash-before-write (001 FR-021a), now also after a reconnect, a restart, or a stale tab (FR-009, FR-009a) |
| `config_save` | **Finding**: since 001 T059 it overwrote the file with no backup, and this feature makes it the operator's editing path. **Fixed** by FR-015a: under the lock, the bytes just hashed are written to `<library>/trash/config/…` before the save. If that fails, nothing is saved |
| `node_set` | the editor writes nothing; nodeconf owns the file |
| `project_save` writing corrected media values (FR-041) | a present-but-different value is reported and acknowledged first, and the original is preserved in the trash (FR-043, FR-044). A merely missing value is added without a report (Q6) |
| `ensure_media_columns` (`ALTER TABLE ADD COLUMN` on `project-manager.db`) | **No backup.** It is additive and idempotent, and an older editor still reads the result. Recorded in Complexity Tracking, not waived |

A write either completes or leaves the prior file: `.save` is a temp-file rename. Tests against a
temporary library assert both recovery paths (IV.3).

**IV. Tests Gate The Risky Paths, Honestly**
1. The import smoke test is unchanged.
2. Every wire change has a test that fails against `a3309ab`.
3. Both write paths have recovery tests.
4. Silent-wrong hunt: every caller of `self.repair_state` (only `CuemsWsUser.py`) moves to
   `server.repair_gates`, and a grep test asserts the name is gone. `config_save`'s
   `network_map` refresh branch is deleted together with its save.
5. Not applicable: this is not a bug fix, beyond US1's reconnect hole, whose failing test comes
   first (FR-005).

**V. cuemsutils Through Its Public Surface**

- **Imports added**: `cuemsutils.tools.CommunicatorServices.Communicator`, the module the server
  already imports from; `cuemsutils.errors.IngestError`. No `cuemsutils.xml` import.
  `_project_settings_document` is not read (G2 stays a gate).
- **Not re-implemented**: the path convention (the editor uses `conf_path` / `project_path`), the
  projection (`to_wire`), validation (`.save`'s T1).
- Not taken from 869fat84r: `cuemsutils.xml.*`, `CuemsParser`, `XmlReaderWriter`, and the
  `xml.etree` reader `_light_media_blocks` (M10). The ported walk uses `CuemsScript` objects and
  the `Media` setters.
- The md5 is the editor's own concern. The library declined a hash helper (`cuems-utils` §0a).

**Operational Constraints**

The restart notice implements "topology/config cached at startup". CLAUDE.md gains the field notes
(FR-035).

**Post-design re-check (after Phase 1): PASS.** The contracts, the data model and the quickstart
introduce no import, write path or audience beyond those listed.

## Project Structure

### Documentation (this feature)

```text
specs/002-config-round-trip/
├── spec.md
├── plan.md                    # this file
├── research.md                # Phase 0: R1–R10
├── data-model.md              # GateState, Revision, ConfigTarget, FileLocks
├── quickstart.md              # environment, suite, scenarios
├── contracts/
│   ├── ws-messages.md         # every frame added or changed, restated v1 row
│   └── nodeconf-node_set.md   # the IPC contract behind cuems-editor UR-8
├── checklists/requirements.md
├── upstream-reports/          # created by tasks: UR-7 (cuems-utils), UR-8 (cuems-nodeconf)
├── evidence/                  # created by tasks: environment.txt, failing-first runs, tip frame, instance refusals
└── tasks.md                   # /speckit-tasks
```

### Source Code (repository root)

```text
src/cuemseditor/
├── CuemsWsUser.py      # config_load, config_save (revision, lock, backup, refusals,
│                       #   broadcast), node_set, repair gate via server.repair_gates;
│                       #   repair_state deleted
├── CuemsWsServer.py    # repair_gates, file_locks, notify_others_config_changed;
│                       #   action registration
├── CuemsDBProject.py   # open() also returns script_md5 + media comparison; inspect(uuid);
│                       #   value functions, object fill (_allowed_keys(cue), setters only),
│                       #   media_staleness (FR-043)
├── CuemsDBModel.py     # 4 Media columns, ensure_media_columns (from 0b291d1)
├── CuemsDBMedia.py     # probe_dimensions, media_file_size, new() stores them (from 0b291d1)
├── CuemsProjectManager.py  # ensure_media_columns at start-up
├── CuemsUpload.py      # relink guard (from 0b291d1)
└── repair_durations.py # ensure_media_columns; dry run on a migrated temporary copy

tests/
├── test_repair_gate_durable.py     # US1 (FR-005 written first), FR-009, FR-009a, FR-010
├── test_config_round_trip.py       # US2: load, save, conflict, concurrency, backup, refusals, restart
├── test_node_set.py                # US4 with a fake Communicator; G4 against nodeconf's handler (xfail)
├── test_protocol_doc.py            # US3: no live string boolean; the restated row exists
├── test_media_values.py            # FR-042's six (red first), FR-036/037/041, item-assignment grep
├── test_media_staleness.py         # US6: media_repairs, acknowledgment_required, rows digest (FR-043 to FR-045)
├── test_upstream_gates.py          # G1–G3 strict xfails (G1 replaces the _pending_ur6 pin)
├── test_schema_descriptor.py       # edited: config_save cases gain base_revision; network_map now refused
├── test_document_load_report.py    # edited where it reached self.repair_state
└── ws-command-responses.txt        # restated v1, new rows, gate text, qualifications

specs/001-cuems-utils-migration/evidence/
├── project-capture/capture_load_tip.py           # new file (FR-030); capture_load.py untouched
└── frontend-handover-instance-caveat.md          # new file (FR-028)

CLAUDE.md                # field notes (FR-035)
```

**Structure Decision**: the existing single package. No new module. The work stays in the three
files that own sessions, the server and the project store. The tests split by user story, so each
story's failing-first run can be captured on its own.

## Ordering constraints for /speckit-tasks

1. **Environment and evidence first** (FR-034, research R1). Record the environment before any test
   is run for evidence.
2. **US1's failing test before any gate code** (FR-005). Capture it at `a3309ab`'s source.
3. **`CuemsDBProject.open` / `inspect`** before the gate rewrite. The gate needs the md5.
4. **`file_locks`** before both `config_save` and the gate's `project_save` path, which share it.
5. **The `config_save` reply change and the protocol-doc restatement land in the same commit**
   (Principle I: the document describes what is sent at every commit).
6. **The upstream reports** (UR-7 to `cuems-utils`, UR-8 to `cuems-nodeconf`) are written when their
   xfails are added, so each xfail's reason names a file that exists.
7. **869fat84r port**: FR-042's six tests first (captured red), then FR-036/037 (columns, upload),
   then the fill (FR-038 to FR-041), then the comparison (FR-043 to FR-045). The comparison lands
   after the gate rewrite (step 3), because it feeds `GateState`.
8. **Documentation-only items** (US5) can go in parallel with anything after step 1.

## Complexity Tracking

| Violation / carried record | Why now | Retired by |
|---|---|---|
| Strict xfails G1–G4 stand during the feature (S6) | Each is another repository's fix, and a workaround here is forbidden (Principle V) | each owner's fix. The tag is not cut while any stands (S7, FR-033) |
| Config backups in `<library>/trash/config/` accumulate, one per save, and have no UI purge | FR-015a's recovery path. Correctness first | a future trash-management feature. Recorded in the CLAUDE.md field note |
| `ensure_media_columns` alters `project-manager.db` without a backup (Principle III) | additive `ADD COLUMN`, idempotent, older editors still read the result; the same code runs on the rc15 line | a backup step for any later, non-additive migration. The editor has no migration framework |
| 869fat84r's re-probe, report and indexer are deferred (M9) | Q5 = C: keep the merge candidate's save path free of 20 s probes and of a reader that reports nothing on 013 | the follow-on feature, bound by FR-046 |
| Ratification records still open (`delete_from_trash` `rmtree` inside a transaction; `cli.py:29` `ProjectMappings`) | untouched by this feature | as recorded in 001's Complexity Tracking (`cuems-utils` 014/015 successors) |
