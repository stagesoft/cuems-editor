<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# `project` frame capture (T004, FR-010)

The `{"type":"project","value": ...}` frame the editor sent before this feature, for one
fixture. `tests/test_project_payload.py` compares against these bytes. Do not regenerate them
to make a test pass (FR-040). See `../README.md` for the re-baseline rule.

| File | What |
|---|---|
| `script_minimal.frame.json` | the frame, exactly as `send_project` serialises it: `json.dumps({"type": "project", "value": CuemsDBProject.load_xml(...)})` |
| `script_minimal.capture-meta.json` | library version and path, and the fixture's sha256 before and after the read (equal: the read wrote nothing) |
| `capture_load.py` | the procedure. It copies the fixture into a temporary library and calls the unedited `CuemsDBProject.load_xml` |
| `rc16-legacy-reader-refusal.txt` | the same procedure against cuemsutils `0.1.0rc16` @ `6213b16`. It raises |

## Fixture

`tests/fixtures/script_minimal.xml`, sha256
`b06a8f6449626e3b276570340191ba39101e08e9e6560748fefcc4ca76bc7df5`. It is the only
fixture. Nothing from `../cuems-utils/tests/golden/xml` is included.

## Which library produced it, and why

Editor `src/` at `e05f4e7`, unedited. `cuemsutils` **0.1.0rc14**, the last tagged release
(`v0.1.0rc14`, `e4ad0ef`), installed from the index in the hatch environment. That is the
library a deployed editor runs, so this is the frame a deployed UI receives today.

The same unedited code against cuemsutils `0.1.0rc16` @ `6213b16` cannot produce a frame at all:
after cuems-utils 013, the deprecated `XmlReaderWriter` validates against the new `script.xsd`,
which has no `<AudioCue>` / `<VideoCue>` element, and raises
(`rc16-legacy-reader-refusal.txt`). There is no rc16 "before" to capture.

## How the new path reaches this fixture

`CuemsScript.load_with_report` refuses the pre-013 device shape with a `SchemaError` that names
`cuems-reshape-devices`. The editor does not reshape documents. The comparison therefore loads
`tests/fixtures/script_minimal_013.xml`, which is `cuems-reshape-devices` run over a copy of
this fixture (provenance in `tests/fixtures/README.md`). The operator runs the same tool over
the library before deploying. The reshape is delta (c).
