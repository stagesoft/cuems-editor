<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Upstream report → `cuems-utils`: what `cuems-editor` found when it reconciled with its release line

**From:** `cuems-editor` feature 003 (`specs/003-release-line-reconciliation/`), 2026-10-23.
**Status:** answers to your 017 report, one new finding, and one thing to carry in the re-cut.
`cuems-editor` edits no file in your repository. Measured with `cuemsutils` exported with `git archive` at the
candidate tag `4b336cd` and at `feat/xml-refactor` `387598e`.

## 1. The re-cut must carry `stop_project` and the rc16 media guard (your 017 §1, §2)

Both are in `387598e`; neither is in `4b336cd`. The editor's tests pin it:

| Behaviour | `4b336cd` (the candidate tag) | `387598e` |
|---|---|---|
| `stop_project` in `script.xsd` | **absent** (0 matches); a project holding such a cue is refused at save | present (`script.xsd:321`); saves, reopens, a leftover target is refused with rule `project_action_takes_no_target` |
| `CueList.get_media` on a media block without a file | bare `KeyError('file_name')` | `ValueError` naming the cue ("cue … has no media file") |

The editor carries five **strict expected failures** for these (`tests/test_stop_project_save.py`, 4 cases;
`tests/test_validate_media_cues.py::test_the_librarys_media_error_reaches_the_client_unprefixed`). On the re-cut they turn
XPASS, which is red by design: the editor removes the markers then (its task T022). Please keep these five names in your
"still owed" list.

## 2. X-4, measured: absent stored media values

On a version-2 load of a script whose `Media` has no `pixel_width` / `pixel_height` / `file_size` / `file_md5`
(`script_minimal_013.xml`): `key in media` is false and the attribute reads `None`, **not** `Unset`, under both
`4b336cd` and `387598e`. The editor's comparison relies on "absent means missing" and asserts it
(`tests/test_media_staleness.py::test_an_absent_stored_value_reads_as_missing_not_as_unset`). Confirmation only.

## 3. New: `CuemsScript.save` no longer falls back to writing in place

The editor released (`0.1.0rc1-4`, 869fat84r D20) a save that wrote a temporary file in the project directory, renamed it
over the script and, **when it could not create a file in that directory, wrote the script in place**. The editor now
saves through `CuemsScript.save` (which is atomic, and which the editor trusts: it no longer carries its own writer).
Measured: in a directory the user cannot create files in (mode `0555`, a group-writable script), `CuemsScript.save`
**raises**; the released editor saved.

Whether the situation occurs in the field is unknown (project directories are normally owned by the service user). If it
does, `save` could fall back to an in-place write when the temporary file cannot be created. The editor does not work around
it (constitution V). The two released tests that pinned the fallback are retired with this reference
(`evidence/test-disposition.md`).

## 4. Libraries the editor was validated on

| | |
|---|---|
| Pinned environment | `cuemsutils 0.1.1` from `4b336cd`: 435 passed, 3 skipped, 5 strict xfails |
| Library head | `387598e`: the same suite, the 5 xfails turn XPASS (strict, red) and nothing else changes |

The editor re-validates on the re-cut tag (rule 5) with the dispatched CI run (`cuemsutils_ref`).
