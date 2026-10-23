<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Upstream report → `cuems-engine`: acknowledgement of your 009 report to the editor

**From:** `cuems-editor` feature 003, 2026-10-23. Nothing is owed by the engine.

| Your row | Where the editor handles it | Test |
|---|---|---|
| W2 `project_status` = `running` / `loaded` / `none` (+ `project_unix_name`) | `CuemsWsUser.project_status` relays the answer unchanged. The media check reads it as four cases: `running` defers re-probing, `loaded` and `none` do not, no answer is distinct (the released editor read `loaded` as "no answer" and skipped the check whenever a project was loaded but stopped; fixed) | `tests/test_engine_state.py` (7 cases), `tests/test_media_report.py::test_a_loaded_but_stopped_engine_does_not_defer_the_probe` |
| W4 authored `stop_project` ActionCue, save path | the editor sends no target and saves through `CuemsScript.save`; it needs cuems-utils at or after the re-cut, which carries `stop_project` in `script.xsd` | `tests/test_stop_project_save.py` (strict xfail until the re-cut; passes on utils `387598e`) |

Unchanged and paired: `nodelist_modify`, `/engine/status/cluster_warning`.
