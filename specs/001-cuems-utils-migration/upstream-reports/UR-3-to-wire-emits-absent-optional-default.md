<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-3 — `to_wire()` emits a model default for an absent optional element

**From** cuems-editor 001, 2026-10-02. Measured on cuemsutils `0.1.0rc16` @ `6213b16`.

**Observed.** A video cue whose document has no `<opacity>` element (`script.xsd`:
`<xs:element name="opacity" type="cms:PercentType" minOccurs="0" />`) comes back from
`CuemsScript.load_with_report(...)[0].to_wire()` with `"opacity": 100`, placed before `class`.
`VideoCue`'s model default (`'opacity': 100`, `cues/VideoCue.py:8`) is filled on decode and then
projected as if the document carried it.

**Reproduction.**
```
python -c "from cuemsutils.cues import CuemsScript; \
s,_=CuemsScript.load_with_report('tests/fixtures/script_minimal_013.xml'); \
print(s.to_wire()['CuemsScript']['CueList']['contents'][1]['Cue'].get('opacity'))"
# 100     (grep -c opacity tests/fixtures/script_minimal_013.xml -> 0)
```

**Why it matters here.** Constitution I: the `project` frame may differ from the pre-migration
capture only by enumerated deltas, and 001 sanctions three: (a) `schemaLocation` absent, (b) wrapped
`Media.duration`, (c) `Cue` / `CueOutput` with `class`. `opacity` on every video cue that did not
carry it is a fourth. `tests/test_project_payload.py::test_open_frame_differs_from_the_capture_by_three_deltas_only`
fails on it, as the contract says it must. The editor does not strip the key (the open path is one
`to_wire()` call and nothing walks it), and it does not widen the delta list on its own.

**Expected, one of.**
1. The projection omits an optional element the document did not carry (round-trip fidelity), or
2. the ecosystem sanctions it: the editor spec adds a delta (d) "video cues carry `opacity`
   (default 100) when the document had none", with the `cuems-frontend` consumer named, and the
   test lists it.

Option 2 is a decision for the 001 spec owner, not a code change in this repository.

**Also seen.** `generate_example(SchemaName.SCRIPT)` emits `opacity` on its video cue too; that is
covered by the `initial_template` delta list (`ws-command-responses.txt`, which compares against a
baseline that already had `opacity`).
