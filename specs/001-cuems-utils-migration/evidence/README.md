<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Evidence — 001-cuems-utils-migration

Files in this directory are **immutable** once committed. They record what the code did at a
named commit, and later tests compare against them. A file is not edited to make a test pass.
A correction is a new file that names the one it supersedes.

## Re-baselining the editor capture

`project-capture/` is the `project` frame the editor sent before this feature. It may be
re-baselined **at most once**, and only as a recorded diff: a new file beside the old one, the
diff between them, and the reason. The old bytes stay (FR-040).

## What is not frozen here

`../cuems-utils/tests/golden/xml` (and its `MANIFEST.sha256`) is **not** copied into or frozen by
this directory. That corpus may hold a superseded state while the system refactoring is in
progress, and it is restated in `cuems-utils` after that refactoring. The schema is the XSD under
`../cuems-utils/src/cuemsutils/xml/schemas/`, enforced by the library's public load and save.
Where a golden contradicts the XSD, the contradiction is written down for `cuems-utils`
(`golden-xsd-contradictions.md`); this repository does not edit the golden.

## Two numbers that are not one

- `doc_version` is the **on-disk** document marker, an XML attribute the library reads before
  decoding. It is never a key on a WebSocket payload and is never compared with the payload
  version.
- The **payload version** is the editor ↔ UI handshake integer, sent as
  `{"type":"payload_version","value": <int>}` (milestone 2). It is a different integer with its
  own bump rules (`tests/ws-command-responses.txt`).

## Libraries the captures were taken against

| Capture | cuemsutils |
|---|---|
| `create-script-baseline.json` | `0.1.0rc14` (`v0.1.0rc14`, `e4ad0ef`), the last release that ships `cuemsutils.create_script` |
| `project-capture/` | `0.1.0rc14`. rc16 @ `6213b16` cannot read the pre-013 fixture through the old reader (see that directory's README) |
| `initial-template.json` | derived from `create-script-baseline.json` (T009) |
| `initial-mappings.json` | `0.1.0rc16` @ **`6213b1603d0a508b6ac7dfb5f46593ba4d870193`** (cuems-utils 013), not `e9ed8af` |
| everything else | `0.1.0rc16` from `../cuems-utils/src` @ `6213b16` (`environment.txt`) |
