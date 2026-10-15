<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Tag readiness — `xml-refactor-merge-candidate`, cuems-editor's part

002 FR-033, S7, SC-009. Written 2026-10-12 at the end of 002's implementation.

**Status: READY** (2026-10-15). No xfail stands: all seven gate tests pass without markers, and G5 is
closed in `cuems-utils` (`b43bc50`). The run is `evidence/suite-tag-ready.txt`, which supersedes
`evidence/suite-final.txt`: 271 passed, 3 skipped, at editor `2360936` on cuems-utils `0b3690e` and
cuems-nodeconf `82b0a69`. *Ready* is this repository's half only. **Cutting or moving the tag is the
maintainer's**, never an agent's, and the commits it rests on were local and unpushed when this was
written. Was **NOT READY**, with seven strict xfails, from 2026-10-12.

**Where this text goes.** 001 FR-039 prepared the tag message under
`../.xml-refactor-tag-messages/`. That directory does not exist on this machine (checked
2026-10-12). The maintainer copies this record into the tag message when cutting the tag.

First verified against cuemsutils `0.1.0rc16` from `../cuems-utils` @ `cdb3bef`
(`014-xs-boolean-and-media-elements`, `src/` clean) and `../cuems-nodeconf` @ `65605de`
(`feat/xml-refactor`), in `evidence/suite-final.txt`. Re-verified READY in
`evidence/suite-tag-ready.txt` (see the status line).

## The strict xfails, all closed

Each one failed the suite with `XPASS(strict)` the day it passed; then its marker came off and the
assertion stayed (S6). The *What flips it* column is kept as written; *Closed* says what did.

| Gate | Closed | By |
|---|---|---|
| **G1** | 2026-10-15 | editor `6de91fb`: `_config_path` passes `must_exist=False` on the write side; a first save creates the file with no backup |
| **G2** | 2026-10-15 | editor `35a79d1`: `project_settings` loads through `load_project_settings`. The measured projection keys each item by `SettingType`; the test asserts that and C2's round trip |
| **G3** cue | 2026-10-15 | editor `fc025a7`: the test's own double wrap removed (the output instance already carries `CueOutput` and `class`); no library change was needed |
| **G3** config roots ×3 | 2026-10-14 | editor `9728daf`, on cuems-utils 015 |
| **G4** | 2026-10-14 | editor `2c100a4`, on cuems-nodeconf `3d3601d` |

The original table:

| Gate | Report | Owner | Test node id | What flips it |
|---|---|---|---|---|
| **G1** | `cuems-editor` UR-6 (`specs/001-cuems-utils-migration/upstream-reports/UR-6-config-path-helpers-require-existence.md`) | `cuems-utils` | `tests/test_schema_descriptor.py::test_first_config_save_of_project_settings_round_trips` | `conf_path`/`project_path` gain the wanted `must_exist=False`, **and** the editor's `_config_path` (`src/cuemseditor/CuemsWsUser.py`) passes it on the write side. A library change alone does not flip it |
| **G2** | `cuems-editor` UR-7 (`upstream-reports/UR-7-project-settings-has-no-read-projection.md`) | `cuems-utils` | `tests/test_upstream_gates.py::test_config_load_project_settings_round_trips` | a public `project_settings` projection for `to_wire`, **and** the editor removing `project_settings` from `CONFIG_LOAD_REFUSED` and giving it a `CONFIG_LOAD_STEPS` entry (`load_project_settings(uname)`) |
| **G3** | `cuems-frontend` UR-1 (`../cuems-frontend/specs/001-schema-descriptor-migration/upstream-reports/UR-1-descriptor-instance-not-wire-shaped.md`); the config scope is evidence `evidence/descriptor-instance-config.txt` | `cuems-utils` | `tests/test_upstream_gates.py::test_a_cue_built_from_the_descriptor_instance_saves_through_project_save` | the script descriptor's `AudioCueType` / `AudioCueOutputsType` instances in `to_wire()` shape with usable defaults (today refused at `output_vol`) |
| **G3** | as above | `cuems-utils` | `tests/test_upstream_gates.py::test_a_config_root_instance_saves_through_config_save[settings]` | the `CuemsSettings` root instance saveable (today `{"Settings": null}`, refused) |
| **G3** | as above | `cuems-utils` | `tests/test_upstream_gates.py::test_a_config_root_instance_saves_through_config_save[project_mappings]` | the `CuemsProjectMappings` root instance saveable (today refused at `number_of_nodes`) |
| **G3** | as above | `cuems-utils` | `tests/test_upstream_gates.py::test_a_config_root_instance_saves_through_config_save[project_settings]` | the `CuemsProjectSettings` root instance saveable (today refused at `setting/name`) |
| **G4** | `cuems-editor` UR-8 (`upstream-reports/UR-8-node-set-ipc-command.md`) | `cuems-utils` (`NodeIndex.set_alias`, requirements doc §0a G4), then `cuems-nodeconf` (the handler) | `tests/test_upstream_gates.py::test_nodeconf_engine_callback_accepts_node_set` | **Closed 2026-10-14**: cuems-nodeconf `3d3601d` on cuems-utils `38d2ede`. The marker is off, and the test seeds a map that holds the node and checks the alias on disk |

## G5: no editor test

**G5** — `cuems-utils` §0a: 013's reshape defeats F3's `settings` 1 → 2 conversion
(`settings-reshape-defeats-f3-conversion-defect.md` in `cuems-utils`). It blocks the tag. It is the
library's, and the editor has no test for it; it is listed here so that the gate list is complete.

**Closed** in `cuems-utils` `b43bc50`, verified to be an ancestor of the cuems-utils commit the
READY run used.

## Ready when

No `xfailed` remains in the editor's suite, G5 is closed in `cuems-utils`, and the run that shows it
is recorded as a new evidence file naming `evidence/suite-final.txt` as the one it supersedes.
**All three met 2026-10-15** (`evidence/suite-tag-ready.txt`).
