<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Evidence — 002-config-round-trip

Files in this directory are **immutable** once committed, as in
`specs/001-cuems-utils-migration/evidence/README.md:8-10`. They record what the code did at a
named commit. A file is not edited to make a test pass. A correction is a new file that names the
one it supersedes.

## Files

| File | Task | What it records |
|---|---|---|
| `environment.txt` | T002 | the interpreter, the `cuems-utils` and `cuems-nodeconf` commits, the baseline suite (FR-034) |
| `descriptor-instance-config.txt` | T003 | the four config root-type descriptor `instance`s refused by `from_json` + `.save` (gate G3's wider scope) |
| `repair-gate-failing-first.txt` | T009 | US1's reconnect test failing against the source at `22f9af4` (FR-005) |
| `protocol-doc-failing-first.txt` | T048 | `tests/test_protocol_doc.py` failing before the version-1 restatement |
| `media-values-failing-first.txt` | T055 | FR-042's six tests failing on their own assertions, after the columns and value functions and before the fill |
| `media-staleness-failing-first.txt` | T065 | US6's staleness tests failing before `media_staleness` |
| `project-frame-tip.json` | T073 | the `project` frame at the tip, from `capture_load_tip.py` (FR-030) |
| `t039-absorbed.md` | T078 | the note that closes `cuems-utils` T039 (FR-047) |
| `suite-final.txt` | T079 | the final suite run, with exactly the seven gate xfails |
| `environment-final.txt` | T079 | the final counts, appended as a new file because `environment.txt` is committed |
| `quickstart-run.txt` | T080 | each quickstart §3 scenario against the test that proves it |
