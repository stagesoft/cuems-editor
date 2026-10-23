<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Test data

Every non-test data file lives here (`tests/support/paths.py:DATA_DIR`). Besides the fixtures below: `ws-command-responses.txt`
(the protocol reference, cited by the constitution), `released-builds.txt` (the manifest of shipped Debian builds), and
`golden/` (the released `media_check_report` frames; its README names the source).

## Fixtures

| File | sha256 | Provenance |
|---|---|---|
| `script_minimal.xml` | `b06a8f64…bc7df5` | pre-013 device shape (`<AudioCue>`, `<VideoCue>`). Source of the pre-migration `project` capture (`specs/001-cuems-utils-migration/evidence/project-capture/`). The current library refuses to load it |
| `script_minimal_013.xml` | `df367383…6e5ed0b` | `cuems-reshape-devices` (cuemsutils `0.1.0rc16` @ `6213b16`) run over a copy of `script_minimal.xml`. The only change is each `<AudioCue>` / `<VideoCue>` element becoming `<Cue class="audio">` / `<Cue class="video">`. No `doc_version`, so the library still converts it 1 → 2 in memory on load |

Do not hand-edit either file. A new shape is a new fixture with its provenance in this table.

## `conf/`

A `CUEMS_CONF_PATH` for tests that construct `ConfigManager` or `CuemsWsServer`. Same bytes as
`specs/001-cuems-utils-migration/evidence/mappings-capture/` (cuemsutils `6213b16`):
`settings.xml` and `network_map.xml` from `../cuems-utils/tests/data/`, and that directory's
`default_mappings.xml` plus one `<device class="lighting">` on node `…0001`.
