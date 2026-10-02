<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Not performed, and not passing (T062, FR-044)

`quickstart.md` was run on 2026-10-02 (`quickstart-run.txt`). Every step below was **not performed**
here, or **does not pass**. An omitted row would be read as a pass, so each one has its reason.

## Not performed

| Step | Reason |
|---|---|
| A live controller running this editor (quickstart §9, flow exit list) | no controller in this environment. Listening was checked on the dev host against a temporary library (`listening.txt`) |
| A UI rendering `document_load_report` / `document_load_failed`, sending `repair_acknowledge`, refusing payload version 1 (§7) | that is cuems-frontend 05, not written yet. The frames are pinned by `tests/test_document_load_report.py` and `tests/test_payload_version.py` against the real session handlers |
| Applying `debian-consolidation.md` onto `debian/bookworm` (§8) | the maintainer's action, as with tags. `origin/debian/bookworm` is still `72f952a` |
| Installing the built `.deb` on bookworm with a real `cuems-utils` package | no `cuems-utils` `.deb` at `>= 0.1.0rc16` exists to install against. The package was built in a bookworm chroot and its `Depends` read back (`bookworm-build.txt`); the install-order refusals were demonstrated for cuems-nodeconf with stubs, not repeated here |
| Cutting `xml-refactor-merge-candidate` | out of scope by contract. The message (`../.xml-refactor-tag-messages/editor-tag.msg`) says NOT READY |
| Running the duration tool on a production library (§6) | none available. Covered on the fixture library by `tests/test_repair_durations.py`, including the save round-trip |
| Re-running every pre-013 project through `cuems-reshape-devices` | operator step before deploy; no production library here. The class of refused sources is in `duplicate-refusals.md` |

## Does not pass

| Check | State | Owner |
|---|---|---|
| `tests/test_project_payload.py::test_open_frame_differs_from_the_capture_by_three_deltas_only` (SC-004) | **fails**: the `project` frame has a fourth difference, `"opacity": 100` on video cues whose document has none | `upstream-reports/UR-3`: cuems-utils stops emitting it, or the 001 spec sanctions it as a delta |
| T058 — `node_list` split out of `initial_mappings` (FR-032 milestone 2, FR-046) | **not landed** | needs a decision: it changes four assertions in `tests/test_nodelist_actions.py`, which the tasks allow to be edited only in T036 |
| T059 — `config_save` persisting `settings` / `network_map` / `project_mappings` / `project_settings` | **not implemented**; refusals are in place, the persisting test is `xfail(strict)` | `upstream-reports/UR-5`: no public JSON ingestion for config documents |
