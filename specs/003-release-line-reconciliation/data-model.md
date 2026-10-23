<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Data model: Release-line reconciliation

Few persistent entities: this is a maintenance feature. Most are evidence or test data. The one runtime
entity is the media check report.

## Inventory row (evidence table)

| Field | Meaning |
|---|---|
| `id` | row number in the pre-spec §4 (1–12) |
| `item` | the released change, with its ClickUp id |
| `commits` | bookworm commits (SHAs) |
| `released_in` | Debian build (`0.1.0rc1-N`) |
| `in_head` | `yes` / `partly` / `no` at `a2431f0` |
| `method` | `M` merge, `R` resolve, `A` adapt, `I` re-implement (never cherry-pick) |
| `proof` | the named test, or the recorded verdict |

Rule: every row ends with a `proof`. Stray branches and tags carry `verdict` ∈ include / re-implement /
changelog-only / exclude, plus `reason`.

## Conflict resolution record

`(file, hunk, side, reason)` with `side` ∈ ours / theirs / both / combine. 38 hunks in 12 files. The merge
commit's tree must equal the table (checked by a diff of the merge commit against `a2431f0` limited to the
listed paths).

## Test disposition record

For each of the 136 tests the release line adds: `(test_id, disposition, reason)` with `disposition` ∈
passing-as-is / ported / retired. `retired` requires the id of the test that already covers the assertion.

## Released-builds manifest (`tests/data/released-builds.txt`)

One Debian version per line: `0.1.0rc1-1` … `0.1.0rc1-7`. Lines starting with `#` are comments. The rig build
`0.1.0rc1-5+nodeadopt2` appears only in an `excluded:` block with its reason. Invariants (see
[contracts/changelog-completeness.md](contracts/changelog-completeness.md)).

## Stored media values (existing, 002)

Per media cue: `pixel_width`, `pixel_height` (not on audio cues), `file_size`, `file_md5` (32 lowercase hex),
plus `duration`. Absent means "missing" (attribute reads `None`; `key in media` is false), measured on
`cuemsutils` at `4b336cd` and `387598e`. Written only through the `Media` attribute setters.

## Library row (existing)

`media` table: `unix_name`, `duration`, `pixel_width`, `pixel_height`, `file_size`, `file_md5`, `in_trash`.
Derived from the file; the check may correct it (re-probe), the script is never touched at load.

## Comparison result (runtime, existing)

`media_staleness(script) → (media_repairs, rows_digest)`. `media_repairs[]` entries:
`{cue_id, file_name, field, stored, current}` with `field` ∈ `duration | pixel_size | file_size | file_md5`.
`rows_digest` changes when a row read by the comparison changes. It already feeds `GateState`
(`media_repairs`, `rows_digest`).

## Media check report (runtime, new projection)

Derived, never stored; not part of `GateState`.

| Field | Source |
|---|---|
| `project_uuid`, `project_name` | the loaded project |
| `context` | `open` / `ready` / `save` (the call site) |
| `files[]` (≤ 20) | `media_repairs` grouped by `file_name`: `cues` = number of distinct `cue_id`; `changes[]` = `{field, stored, current}` |
| `unverified[]` | files whose row is `legacy` or `changed` and was not measured (engine busy, deadline, probe failure) |
| `total_files` | all files with a finding, before the cap |
| `complete` / `reason` | `complete` false when part of the check did not run; `reason` ∈ `engine_running`, `engine_silent`, `deadline`, `probe_failed`, `copy_in_progress`, else null |

All-clear = `complete` ∧ no `files` ∧ no `unverified` (a client clears its warning only on that).

### In-flight state (not report state)

Per-project request de-duplication: a second request for a project whose check is running joins it; a flag
for a busy indexer; marks for files that failed or were verified in this process (so a failing file is not
re-probed until it changes). All in-process, outside `GateState`, reset by a test hook.

## Engine project state (existing input)

`running | loaded | none | (no answer)`. Mapping to the check: `running` → defer re-probing
(`engine_running`); `loaded`, `none` → proceed; no answer → `engine_silent`.

## State transitions: a media row in the check

`current` (matches the file) → `changed` (file replaced) → `measuring` → `current`; or `changed` →
`unverified` (deadline / engine running / probe failed) → measured by a later save or load. `legacy`
(no stored size yet) is measured the same way. The MD5 is never computed on the save path.
