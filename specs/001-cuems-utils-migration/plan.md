<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Implementation Plan: cuemsutils public-surface migration

**Branch**: `feat/xml-refactor` (spec dir `specs/001-cuems-utils-migration/`; spec-kit scripts run with
`SPECIFY_FEATURE=001-cuems-utils-migration`) | **Date**: 2026-10-01 | **Spec**: [spec.md](spec.md)

**Input**: [spec.md](spec.md), constitution 1.0.0, the `specs/planning/xml-refactor/` bundle,
[research.md](research.md) (R1–R14)

## Summary

Move this repository onto the public surface `cuemsutils` 0.1.0rc16 actually ships, and close the
constitutional violation that the editor does not start. Two milestones on one branch:

1. **Milestone 1 — census zero.** The process imports. `src/` has no `cuemsutils.xml`,
   `create_script`, `CuemsParser`, or `XmlReaderWriter`. Scripts load and save through `CuemsScript`.
   The `project` payload differs from a pre-migration capture by exactly three enumerated deltas:
   (a) `schemaLocation` absent, (b) `Media.duration` wrapped, (c) hardware cues and outputs keyed
   `Cue` and `CueOutput` with `class`.
   Pass B of the duration tool is retired. The node merge follows `node_role` and the library's
   wire form, including `devices` / `device` / `class`. The pin is bounded and `debian/` is on this branch. This unblocks `cuems-utils` T049.
   It is not a controller deploy: `to_wire()` wraps `Media.duration` and emits `Cue`, and the old UI has no
   handshake yet. A pre-05 UI mis-reads `Cue`. Do not rewrite `AudioCue` back.
2. **Milestone 2 — the coordinated wire.** The repair report reaches the session, and a save of a
   repaired script is refused until that session acknowledges that report. The original is copied
   to `trash/` before the first overwrite. Payload version 1 is the first message on connect.
   `initial_mappings` loses the node domain. The schema descriptor is served and config-domain
   saves are accepted. The candidate tag waits on `cuems-frontend` 05.

Task zero is the import line alone. `create_script()`'s replacement is a later step. Until that
step, the constructor still cannot run.

**Where this plan departs from the pasted context block**, by recorded decision — the spec wins:

| Context block | Plan does | Why |
|---|---|---|
| `:470` becomes `partition_by_adoption` | `from cuemsutils.tools.NodeList import partition_by_adoption` once the 013 commit is pinned; both results are tuples of bare nodes | the function is internal on `0.1.0rc16`; 013 publishes it without a version bump (R5, FR-009) |
| Fold pass B into `cuems-convert-documents` | pass B is retired; the tool writes no script | that tool converts document *shape*, not DB-sourced durations (R7, spec Q5). No upstream change |
| `test_nodelist_actions.py` unedited (flow exit 9) | one recorded edit of the `NetworkMap` mock, assertions unchanged | removing the import makes `patch()` raise (spec F4, FR-041) |
| Payload spoken of as `project_load` | the frame the UI receives is `{"type":"project"}` | `send_project` already uses that type (R11) |

## Technical Context

**Language/Version**: Python ≥ 3.11 (packaged as `cuemseditor`; `hatch` / hatchling)

**Primary Dependencies**: `cuemsutils` 0.1.0rc16, resolved from sibling `../cuems-utils/src`
(`__version__` in `src/cuemsutils/__init__.py`) or an installed package at the same version.
`REMOVAL_RELEASE` is `v0.1.1` (`cuemsutils._deprecation`). **No new dependency. Do not patch or
vendor the library.**

**Storage**: `<library_path>/projects/<unix_name>/<script_file_name>` (`cli.py` default
`script.xml`; the name is configuration), `project-manager.db`, `trash/`. Config via
`ConfigManager` (`network_map.xml`). `default_mappings.xml` stays on the deferred 014 path.

**Testing**: `hatch test` (`testpaths = ["tests"]`, six files). The suite's colour means nothing
until FR-001: `import cuemseditor.CuemsWsServer` raises `ModuleNotFoundError` at
`src/cuemseditor/CuemsWsServer.py:27`.

**Target Platform**: Debian controller, systemd `cuems-editor.service`. Frontend WebSocket
`:9092`. Engine Unix IPC `/tmp/editor.ipc` (NNG).

**Project Type**: single Python package (`src/cuemseditor/`), plus the `cuems-editor-repair-durations`
console script.

**Performance Goals**: none. The constitution admits no budget until a measured baseline exists.
Save atomicity is a measured property of the library's `write_tree` (R4), not a budget.

**Constraints**: public `cuemsutils` surface only (Q14); two sanctioned `project` deltas and no
others; a load does not write; D21b is a session gate, not a comment; milestone 2 wire changes
do not land in a form a pre-05 UI misreads (FR-050); commits GPG-signed; this feature does not
cut or move the candidate tag.

**Scale/Scope**: `CuemsWsServer.py`, `CuemsWsUser.py`, `CuemsDBProject.py`, `repair_durations.py`;
tests `test_dangling_targets.py` (retire), `test_repair_durations.py` (split),
`test_nodelist_actions.py` (one mock edit), new smoke / public-surface / payload / node-merge
tests; `pyproject.toml`; `debian/` brought from `origin/debian/bookworm` @ `72f952a`;
`tests/ws-command-responses.txt`; `CLAUDE.md` field note for *needs a save*.

No NEEDS CLARIFICATION remains. Spec Q1–Q9 are resolved. R1–R14 are measurements.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution v1.0.0. Checked, **not amended**.

| Principle | Status | How |
|---|---|---|
| **I. The Wire Is A Contract** | ✅ | The `{"type":"project"}` frame stays byte-identical to a capture taken before the source change, except delta (a) `schemaLocation` absent, delta (b) `Media.duration` as `{"CTimecode": "..."}`, and delta (c) hardware cues and outputs keyed `Cue` and `CueOutput` with `class`. Key order otherwise and the string boolean form are unchanged. `doc_version` is not on the wire. New families are named in [contracts/ws-messages.md](contracts/ws-messages.md) with an audience, and land in `tests/ws-command-responses.txt`. Untangling waits on payload version 1 and `cuems-frontend` 05 (FR-050). The upstream golden corpus is compared and contradictions are recorded for `cuems-utils`; it is not an editor pass condition (Complexity Tracking) |
| **II. Sessions Are Isolated, The Event Loop Is Shared** | ✅ | Repair acknowledgment is keyed by session and by project. The refusal decision runs on the loop; `CopyMoveVersioned.move` and `CuemsScript.save` run on the executor. `network_map_error` is broadcast to all sessions. Today `reload_network_map_nodes` writes `self.mappings_dict` from the executor (`CuemsWsServer.notify_all_node_list_update`, `CuemsWsUser.nodelist_get`). The executor returns the loaded lists; the loop thread assigns them (R8) |
| **III. User Data Has A Recovery Story** | ✅ | Load does not write. The first save of a document whose report says the file differs copies the original into `trash/` with `CopyMoveVersioned` and refuses the save if the copy fails. Pass B stops writing scripts. Library `save` is atomic (R4). `delete_from_trash` is carried, not touched |
| **IV. Tests Gate The Risky Paths, Honestly** | ✅ | Import smoke fails before FR-001. The `node_type` merge, the timecode guard, the `initial_template` delta, and `network_map_error` each have a test that fails against the pre-change behaviour first. `test_dangling_targets.py` is retired with the library coverage named. No node-model test is added |
| **V. cuemsutils Is Consumed Through Its Public Surface** | ✅ | Census over `src/` goes to zero `cuemsutils.xml` imports. The adoption split is `partition_by_adoption` imported from `cuemsutils.tools.NodeList` on the pinned 013 commit. The version pin stays `>=0.1.0rc16,<0.1.1`. The `cli.py:29` `ProjectMappings` import is carried to `cuems-utils` 014 |

**Post-design re-check (2026-10-01)**: unchanged verdict, with the adoption path updated the same day. The split is the public `NodeList.partition_by_adoption` once the 013 commit is recorded. It returns two tuples of bare node objects. The editor does not re-implement the node model and does not define a local helper.

## Project Structure

### Documentation (this feature)

```text
specs/001-cuems-utils-migration/
├── spec.md, plan.md, research.md (R1–R14), data-model.md, quickstart.md
├── contracts/
│   ├── public-surface.md      # allowed imports + the census guard
│   ├── project-payload.md     # three deltas, one projection, load is a read
│   ├── ws-messages.md         # new families, audiences, payload version
│   ├── repair-tool.md         # pass A stays, pass B is gone
│   └── package-relations.md   # pin, debian/, tag message
├── checklists/requirements.md
├── upstream-reports/          # written during implementation: the UR-1 citation
└── debian-consolidation.md    # written when debian/ is imported (FR-038a)
```

`tasks.md` is `/speckit-tasks`, not this command. `../.xml-refactor-tag-messages/` receives the
tag message during implementation (FR-039); this command does not create the tag.

### Source Code (repository root)

```text
src/cuemseditor/
├── CuemsWsServer.py     # :27 import (task zero); :87 create_script → generate_example;
│                        # merge_node_data / reload_network_map_nodes; initial_* builders
├── CuemsWsUser.py       # project_load/save/duplicate; repair_acknowledge; schema_descriptor;
│                        # config_save; nodelist_*; node_status left as a cluster_status relay
├── CuemsDBProject.py    # four CuemsParser sites; load_xml/save_xml; duration fix on the object;
│                        # dangling walks deleted; fade check unchanged
├── repair_durations.py  # pass A stays; pass B deleted; TIMECODE_SHAPE deleted
└── cli.py               # ProjectMappings import carried (F7); script_file_name recorded only

tests/
├── test_import_smoke.py            # NEW — fails before FR-001
├── test_public_surface.py          # NEW — census guard
├── test_project_payload.py         # NEW — three deltas against the editor capture
├── test_node_merge.py              # NEW — node_role reaches the wire; fails against node_type first
├── test_dangling_targets.py        # RETIRED, reason recorded
├── test_repair_durations.py        # pass B tests retired; structured-duration test added
├── test_nodelist_actions.py        # one mock edit (FR-041), assertions unchanged
└── ws-command-responses.txt        # every payload this server sends

pyproject.toml                       # cuemsutils>=0.1.0rc16,<0.1.1
debian/                              # from origin/debian/bookworm @ 72f952a; bookworm branch kept
```

**Structure Decision**: single existing package. No new package. The adoption selection is a
method on `CuemsWsServer`, not a node model module. Session acknowledgment state lives on the
session dict the server already owns.

## Design

The measurements are in [research.md](research.md). The shapes are in [data-model.md](data-model.md)
and [contracts/](contracts/). This section is the ordering and the obligations those files assume.

### Task zero, then the constructor

FR-001 changes only `CuemsWsServer.py:27`: `new_uuid` comes from `cuemsutils.helpers`, and
`create_script` leaves that import. The smoke test is shown failing before this commit. The
seven F2 failures (`TestNetworkMapWatcher` 3, `TestNodeconfAvailableFlag` 4) are this import;
they are expected to pass with no edit to `test_nodelist_actions.py`.

`__init__` still calls `create_script()` until FR-008. The listening-state check (FR-003) is
ordered after FR-008. Milestone 1 fills `initial_template` with
`ConfigManager.generate_example(SchemaName.SCRIPT)` and keeps the message type and the
`{"CuemsScript": ...}` envelope. Every difference from the last `cuemsutils` release that still
shipped `create_script` is an enumerated delta (R10). Milestone 2 retires the message for the
descriptor's per-type empty instances, behind payload version 1.

### Script I/O

| Call site today | After |
|---|---|
| `load` → `load_xml` → `XmlReaderWriter.read()` | `CuemsScript.load_with_report(path)`; return value of the open path is `script.to_wire()`, once |
| `update` / `new` `CuemsParser(data).parse()` | `CuemsScript.from_json(data)` — this path does not repair (R3) |
| `duplicate` load + parse + save | `load_with_report` of the source, then `save` of a **new** path (R9) |
| `update_projects_existed_media` `CuemsParser(self.load(...))` | `from_json` is wrong here: `load` will already return a wire dict. Use the object from `load_with_report` and do not project it just to parse it again |
| `save_xml` `XmlReaderWriter.write_from_object` | `script.save(path)` |

`_fix_media_durations` stays and walks the object, assigning `CTimecode` through the field. It
does not edit the wire dict. `_clean_dangling_targets` and `_nullify_dangling_refs` are deleted
(R2). `validate_fade_durations_in_contents` still runs on the raw payload in `update` and `new`
only, with the same `ValueError` text. `duplicate` is not given that check.

A load writes nothing. Unrepairable loads, including a document newer than the library, become
`document_load_failed` on the requesting session. The project stays listed.

### D21b, and when it is enforced

`cuemsutils` cannot order `load_with_report` before `save`. This repository does it in
`CuemsWsUser.received_project` (the `project_save` handler), which is the only path that
overwrites the file the session loaded:

- The session stores `report_id`, `outcome`, `file_differs_from_loaded`, and `acknowledged`
  for the project it loaded. A non-`CLEAN` report with `acknowledged == false` makes
  `project_save` return `repair_save_refused`. Another session's acknowledgment does not count.
  Unload, session close, or a new load of the document clears the flag. That decision reads
  session state on the event-loop thread.
- `repair_acknowledge` is a new inbound action carrying that `report_id`.
- When `file_differs_from_loaded` is true, the first overwrite moves the on-disk script into
  `trash/` with `CopyMoveVersioned.move` (project and date recoverable from the name). If the
  move fails, the save is refused and `CuemsScript.save` is not called. The move and the save
  run on the server executor, as `received_project` already does for `project.update`. They are
  not called from the async handler body.

This gate is milestone 2 on the branch. Until that phase, a checkout can save a repaired script
without the acknowledgment. That checkout is not a release. US1–US8 ship together under one
candidate tag, and census zero is only the source announcement to `cuems-utils` T049. The
unacknowledged-save window never lands on a controller by itself (spec clarification 2026-10-01).
The tag message stays unready until `cuems-frontend` 05 consumes the report (FR-049).

`duplicate` does not overwrite the source, so the gate and the trash copy do not apply to it.
The duplicate reply still carries the source report, as an optional key old readers ignore (R9).

### Nodes, without a second model

Milestone 1 keeps serving `initial_mappings` as the entangled payload, so nothing is removed
from a message the current UI reads. Inside it:

- `NetworkMap` is gone. `adopted, unadopted = partition_by_adoption(network_map)` with
  `from cuemsutils.tools.NodeList import partition_by_adoption`. Both results are tuples of bare
  node objects; an empty side is `()`. The input `node_list` stays a list of `{"node": <node>}`;
  the function unwraps it. The editor does not. This call starts only after
  `evidence/cuems-utils-013-pin.txt` records the cuems-utils commit on which the import succeeds.
  The version pin stays `>=0.1.0rc16,<0.1.1` because 013 does not cut a new version. Feature 014
  does not own this list. `get_nodes_by_adoption` and a local `_select_adopted` stay absent.
- `merge_node_data` copies status from `node.to_wire()` (`"True"` / `"False"`, string uuid,
  key `node_role`) and keeps output blocks from the existing mapping node. The library side is
  one of those tuples, so a missing `"node"` key is not a reason to skip the item. Identities are
  compared with `coerce_identity`. The `node_type` test fails against the old list first (R6).
- `node_status` stays a relay of the engine's `cluster_status`. `alive` is not `online`.
- `nodeconf_available` stays a live sample injected at both current sites. It is not a field of
  `project_mappings` or `network_map` (R14).
- A `ValidationError` whose message contains `node identities are not unique` is not retried.
  The last good list keeps being served. `network_map_error` is broadcast to all sessions and
  to each session that connects while it stands, then cleared on the next successful read (R13).
- `nodelist_modify` error strings, including nodeconf's readiness-window `"Node … not found"`,
  are relayed unchanged.

Milestone 2, only after `payload_version` is the first frame: `initial_mappings` is project
outputs only; a `node_list` message carries the adopted and unadopted arrays with
`nodeconf_available` beside them, pushed by `watch_network_map` and pulled by `nodelist_get`.
The frontend hand-over names `settings.component.ts`, `audio-mixer.component.ts:80`,
`video-mixer.component.ts:94`, `projects.service.ts:120` (`schemaLocation`), and
`projects.service.ts:159`, `:240`, and `:243` (`initial_template`, including the
`localStorage` key).

`schema_descriptor` returns `ConfigManager.get_schema_descriptor(SchemaName)`. `config_save`
writes through `save_network_map`, `save_settings`, `save_project_mappings`, or
`save_project_settings`. Not `hardware_outputs` (reserved, no model bindings) and not
`default_mappings.xml` (014).

### Repair tool

Pass A (ffprobe, database, backup, dry-run) stays. Pass B is deleted, including its XML backup
and `--xml-only` writes. The tool reads scripts with the public load, compares durations with
`CTimecode`, and lists mismatches as *needs a save*. It writes no script. `TIMECODE_SHAPE` is
deleted. The guard test fails on a structured duration before the fix. `CLAUDE.md` records that
an unsaved project keeps short durations on disk and that the engine plays from disk.
`tests/test_repair_durations.py`'s `XmlReaderWriter` import goes away with pass B.

### Release

`pyproject.toml` declares `cuemsutils>=0.1.0rc16,<0.1.1`. `debian/` comes from
`origin/debian/bookworm` at `72f952a`, with `Depends: python3-cuemsutils (>= 0.1.0rc16),
python3-cuemsutils (<< 0.1.1~)`. The package is built inside an unprivileged bookworm
chroot (`mmdebstrap --mode=unshare`), not with `debuild` on the Debian 13 development
host. `debian/bookworm` is not deleted. Every `debian/` change is
listed in `debian-consolidation.md` for the maintainer to apply there. The tag message names
`feat/nodelist-adoption-api` @ `886f649`, `cuems-engine`'s `feat/nodelist-modify-dispatch`, and
`cuems-nodeconf`'s `feat/nodelist-modify-hardening`. This feature does not create the tag.

## Phasing

Phase numbers match `tasks.md`. Census zero is phase 9. It follows the pin (phase 8) and is not part of the coordinated wire (phases 10 and 11).

| Phase | Content | Milestone |
|---|---|---|
| 1 — Setup | import-failure record; capture the `project` frame, `initial_mappings`, and `initial_template` before any source change after the import line; reconstruct `create_script()` from the last release that shipped it | 1 |
| 2 — Foundational | evidence README: captures are immutable, `doc_version` is not a wire key | 1 |
| 3 — User Story 1 | FR-001 only; smoke test shown failing first; suite baseline whose colour means something. Listening is still blocked | 1 |
| 4 — User Story 2 | `initial_template` test failing first; `generate_example(SchemaName.SCRIPT)`; enumerated deltas, including the frontend file and line; listening-state check | 1 |
| 5 — User Story 3 | four `CuemsParser` sites plus load and save; `load_with_report` / `save` / one `to_wire()`; object duration fix, including a `MediaCue` whose class is not `audio`, `video`, or `dmx`; delete dangling walks and do not port a collapsed `CUE_TYPES`; retire `test_dangling_targets.py`; three-delta test against the editor capture; golden-versus-XSD contradictions recorded, not asserted | 1 |
| 6 — User Story 5 | retire pass B; structured-duration test failing first; `CLAUDE.md` note; save one listed project and confirm the tool drops it | 1 |
| 7 — User Story 6 | `node_role`; `partition_by_adoption` from `cuemsutils.tools.NodeList` after the 013 commit is pinned; two tuples of bare nodes; `to_wire()` merge; collision test failing first, then the handler; executor assignment moved to the loop; the one `test_nodelist_actions.py` edit in the same commit as the `NetworkMap` removal | 1 |
| 8 — User Story 7 | `pyproject.toml`; import `debian/`; bookworm chroot build; consolidation record; tag message drafted, not ready, and the five adoption commits named for the PR | 1 |
| 9 — Milestone 1 exit | census zero announced to the `cuems-utils` flow. Not a controller deploy | 1 |
| 10 — User Story 4 | ack gate and trash copy on the executor; report and failure messages | 2 |
| 11 — User Story 8 | payload version first; untangle `node_list`; descriptor and `config_save`; retire `initial_template`; frontend hand-over by file and line | 2 |
| 12 — Polish | quickstart exit list, including *not performed* rows; carried constitution violations left untouched | 1 and 2 |

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Principle III: `CuemsDBProject.delete_from_trash` calls `shutil.rmtree` inside a DB transaction. A rollback restores the row and not the directory | Pre-existing. This feature does not call that function. Successor is a later feature, named here so the ratification list is not dropped | Fixing it inside this migration mixes an unrelated data-loss bug into the census |
| Principle V: `cli.py:29` imports `ProjectMappings` from `cuemsutils.tools.ConfigManager`'s module namespace. The class is defined under `cuemsutils.xml` and is not in `tools.__all__`. Its only use is `get_mappings()` reading `default_mappings.xml` (F7) | The read is the one `cuems-utils` 014 moves. Migrating it now means migrating it again. It is outside the T049 grep, so it does not block milestone 1 | A local replacement reader would be a second consumer of a file 014 deletes |
| Principle V: adoption split | On `0.1.0rc16` the function is only `NetworkMap.partition_by_adoption` inside `cuemsutils.xml`. Feature 013 publishes `from cuemsutils.tools.NodeList import partition_by_adoption` without a version bump. T036 waits for that commit SHA in `evidence/cuems-utils-013-pin.txt` and calls it. Both results are tuples of bare nodes. No local helper is added | Importing `cuemsutils.xml.settings.NetworkMap` (Q14). Defining `_select_adopted` after the public import exists |
| Principle I: `cuems-utils` `tests/golden/xml` is not an editor pass condition | The corpus may hold a superseded state. Schema truth is the XSD under `cuems-utils/src/cuemsutils/xml/schemas/`. Principle I still requires the corpus to be compared: contradictions are recorded for regeneration in `cuems-utils`. This repository does not edit the golden and does not assert `MANIFEST.sha256` | Treating a superseded golden checksum as a gate (a claim that cannot be true). Skipping the comparison entirely |
| `script_file_name` (`cli.py` `'script.xml'`) vs `CuemsProjectManager`'s docstring example `'cue_script.xml'`, and vs the engine's hardcoded `"script.xml"` | Recorded only. A library walker that hardcodes the name is `cuems-utils` 012's trap, not this feature's | "Fixing" the name here would desynchronise the editor from libraries it already opens |

## Complexity Tracking — resolved, so they are not carried

- Principle III, "whether `XmlReaderWriter.write_from_object` is atomic": the replacement
  `CuemsScript.save` writes a temp file in the target directory and `os.replace`s it (R4).
- Principle IV, "the import smoke test does not exist yet": phase 2 adds it, failing first.
- Principle V, the six shipped imports of `cuemsutils.xml` / `create_script`: phases 2–6 remove
  them. The census is the milestone-1 exit.
- Principle III, the branch window before the save gate: a checkout between milestone 1 and US4
  can overwrite a repaired script with no acknowledgment. It does not ship. US1–US8 land under
  one candidate tag, and census zero is a source announcement, not a package (spec clarification
  2026-10-01). The gate is in the same release as the wire change that makes a repair observable.
