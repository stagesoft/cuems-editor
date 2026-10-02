<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Golden corpus against the XSD (T018, constitution I)

`../cuems-utils/tests/golden/xml` (last changed `23dd444`, 2026-10-01) compared with the XSD under
`../cuems-utils/src/cuemsutils/xml/schemas/` by loading each document through the library's
public load, `CuemsScript.load_with_report`, on cuemsutils `0.1.0rc16` @ `6213b16`. The public
load runs the XSD (T1) and the semantic rules (T2). All five goldens are script documents.

| Golden | `doc_version` | sha256 (first 12) | Public load |
|---|---|---|---|
| `cuems-editor__script_minimal.xml` | 2 | `8fda45467fe2` | loads, `clean`, no conversion, no repair |
| `cuems-engine__projects__complex_test__script.xml` | 2 | `c9a06c9df7cc` | loads, `clean`, no conversion, no repair |
| `cuems-engine__projects__empty_test__script.xml` | 2 | `9f4eacc776af` | loads, `clean`, no conversion, no repair |
| `cuems-utils__fade_showcase.xml` | 2 | `76ab5dee0d1f` | loads, `clean`, no conversion, no repair |
| `cuems-utils__unicode_showcase.xml` | 2 | `bf751a1f01e3` | loads, `clean`, no conversion, no repair |

**Contradictions found: none.** No golden carries a pre-013 `<AudioCue>` / `<VideoCue>` /
`<DmxCue>` element. Four carry `<Cue class=…>`; the empty project has no cues.

This comparison does not fail the editor suite, does not check `MANIFEST.sha256`, and does not
edit the golden. If a later regeneration in `cuems-utils` contradicts the XSD, that is reported
there. The editor's own comparison is against `project-capture/`, not this corpus.
