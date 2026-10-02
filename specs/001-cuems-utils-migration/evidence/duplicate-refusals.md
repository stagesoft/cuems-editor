<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Sources `duplicate()` copied before 001 and the library load now refuses (T021)

`duplicate()` now opens the source with `CuemsScript.load_with_report`. Before 001 it copied the
directory and re-parsed the copy with the deprecated reader. The editor adds no refusal of its
own: whatever the library refuses is raised unchanged, the transaction rolls back, and nothing
is created (`tests/test_project_payload.py::test_duplicate_of_a_source_the_library_refuses_creates_nothing`).

| Project | Why it is refused | What the operator does |
|---|---|---|
| any script in the pre-013 device shape, e.g. `tests/fixtures/script_minimal.xml` | `SchemaError`: `script document … is in the pre-013 device shape (<AudioCue>/<VideoCue>/<DmxCue> …). Run \`cuems-reshape-devices\` to migrate it.` | run `cuems-reshape-devices` over the library, then duplicate |

This is the whole class, not a list of production projects: no production library was available
here. Every pre-013 script on a controller is in it until the reshape runs, and that is also why
milestone 1 is not a controller deploy.
