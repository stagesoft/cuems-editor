<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Release-line reconciliation for `cuems-editor 0.1.1-1` — merge before release

**Written 2026-10-22** on `feat/xml-refactor` at `a2431f0` (the `xml-refactor-merge-candidate` tag
commit). **Status: pre-spec, decided, not started.** It is the input for the next SDD feature,
**`003-release-line-reconciliation`**. Run `/speckit-specify` with Appendix A, then the rest of the
suite.

**Lifetime: temporary.** This file is a pre-spec. Once `specs/003-release-line-reconciliation/` has
absorbed it (spec, plan, research, evidence and upstream reports), it is **deleted as the final task
of 003** (§11, last step). `specs/planning/` is not a home for it.

**What it discharges.** Rule 4 ("merge before bump") of
[`cuems-utils/specs/planning/coordinated-release-version-bump.md`](../../../cuems-utils/specs/planning/coordinated-release-version-bump.md)
for this repository, and the **NOT YET RECONCILED** section of
`../.xml-refactor-tag-messages/cuems-editor.txt`. The precedent is cuems-engine's
`specs/planning/release-line-reconciliation-0.1.1.md` (commit `945ccba`), already carried out as the
engine's feature 009. This file mirrors its structure.

**The finding that shapes everything.** The editor's merge is *not* the engine's. The engine merged
with 7 conflicting files and a mostly mechanical adaptation. Here 12 files conflict (38 hunks, 28 of
them in 5 source files), and the conflicts are **one decision wearing many hunks**: feature 002
deliberately *ported* half of 869fat84r onto the object API and *deferred* the other half
(`specs/002-config-round-trip/merge-notes.md`, "Deferred"). That deferred half shipped in
0.1.0rc1-4. The release line carries it as dict-era code. A textual merge cannot absorb it (§6).

## 0. Decisions already taken (maintainer, 2026-10-22)

| # | Decision |
|---|---|
| D1 | **The deferred half of 869fat84r is re-implemented in this feature**, on objects, as its own priority-2 story (§4 row 4, US3). Rule 4 therefore holds for it: nothing released in 0.1.0rc1-4 is lost, and the `media_check_report` wire has both halves at the re-cut tags (`cuems-frontend` `dev` already consumes it). The maintainer may cut the story from 0.1.1 without blocking the rest. If so, the release notes and the tag message must say so. |
| D2 | **The CI change is part of 003, and the pre-publication gate is a `workflow_dispatch` run.** `main` has no `.github/` at all (§14.4), so the maintainer lands **only `ci.yml`** on `main` in a tiny PR. That is one act outside this feature, listed in the hand-off. The file name is fixed: `ci.yml`. |
| D3 | **Feature branch `003-release-line-reconciliation` off `feat/xml-refactor`.** The release line merges in there and is adapted there. The branch merges back with `--no-ff`, and the **maintainer** re-cuts the candidate tag. Agents never move tags and never push. |
| D4 (inherited) | The version **stays `0.1.1-1`**. Rule 4 means the merge goes *under* the bump already made. The top changelog entry grows; it is not renumbered. |
| D5 | **The pre-spec is a planning file plus a `/speckit-specify` prompt.** This session wrote no code and no file other than this one. |

Housekeeping done in this session, recorded because it changes what "HEAD" meant: the local
`feat/xml-refactor` was **6 commits behind** `origin/feat/xml-refactor` (it stood at `2c100a4`, so it
lacked the bump `a2431f0`). It was fast-forwarded to `a2431f0` (`git merge --ff-only`, clean tree, no
data lost). Every number below is measured on `a2431f0`.

## 1. Goal, scope, non-goals

**Goal.** `0.1.1-1` must carry every fix and feature that shipped from the editor's release line
since the refactor branched, so that nothing released in `0.1.0rc1-4 … 0.1.0rc1-7` is lost. The
absorbed code must obey the xml-refactor contract: the public `cuemsutils` surface (constitution V),
version-2 scripts, `CuemsScript` objects not dicts, no second script reader, payload version 1, and
`xs:boolean` `true`/`false`.

**In scope.**
- All source, tests, docs, packaging and changelog content reachable from `origin/debian/bookworm`
  and not from `feat/xml-refactor`.
- The adaptation of that code to the contract, including the re-implementation of the deferred 869fat84r
  half (D1).
- Re-verifying this repository's rows of the 016 relation matrix, and the sibling halves of wire
  contracts the release line added.
- The first-stable-release cleanup (§14) and the CI gate (§14.4).
- The rewrite of the tag message, which only produces a text file.

**Not in scope.**
- Publishing anything (PyPI, the `.deb` archive).
- Any sibling's reconciliation, and any edit in a sibling repository. Obligations are written as
  upstream-report text (§8).
- Creating or moving tags, and pushing.
- New behaviour that no released build had.

**Moving target.** The release line can still release (`0.1.0rc1-8`…). §2 is a snapshot. The
implementation **re-measures at its start and again before hand-off** (§11, steps 1 and 9) and merges
anything newer the same way.

## 2. The lines, measured 2026-10-22 (after `git fetch --all --tags`)

| Ref | Commit | What it is |
|---|---|---|
| `feat/xml-refactor` = `xml-refactor-merge-candidate^{commit}` (local, remote and tag agree) | `a2431f0` | `0.1.1-1 UNRELEASED` |
| `origin/debian/bookworm` | `69d749e` | **the release line**, `0.1.0rc1-7`; tags `v0.1.0rc1-4` `faaa626`, `-5` `fc9f116`, `-6` `55ba6f7`, `-7` `69d749e` |
| `origin/rc1` | `fdba0bc` | the development line feeding it |
| `origin/main` = `origin/master` | `45e6cba` | **2021-05-20.** Not a line. Measuring against it is wrong in both directions. `git remote show origin` says `HEAD branch: main` |
| merge-base (bookworm, rc1) | `886f649` | the tip of `feat/nodelist-adoption-api`, which the refactor branched from |

Behind / ahead of the refactor head, by `git rev-list --count`:

| Line | Behind | Ahead |
|---|---|---|
| `origin/debian/bookworm` | **43** | 63 |
| `origin/rc1` | 16 | 63 |
| `origin/main` | 0 | 189 |

- **`rc1` ⊂ `debian/bookworm`**: `rev-list origin/debian/bookworm..origin/rc1` is **0**, and bookworm
  has 27 more commits (packaging). One merge of bookworm therefore brings rc1's ancestry too. There is
  no second merge to make, unlike the engine.
- The 43 commits are 15 merge commits and 28 others: **12 code**, **16 packaging or release**.
- The refactor already holds node adoption (869ebkkme, PR #7): the merge-base *is* that branch's tip.
- The released tags `v0.1.0rc1-4 … -7` are all ancestors of bookworm and of no other ref. There is
  **no hotfix line** like the engine's `hotfix/rc5-*`.
- `debian/` reached the refactor by *copy* (`0834e99`, "bring debian/ from debian/bookworm @ 72f952a"),
  not by merge. The Dec 2025 – Mar 2026 packaging commits are therefore content-present but
  ancestry-absent.
- Open PRs on the repository: none (`gh pr list --state open`). All 11 historic PRs are merged.

## 3. Strategy: one real merge, then adaptation commits

**Method choice, per item (the table in §4 assigns one to each).**

| Method | Used for | Why |
|---|---|---|
| **M — merge** (`git merge --no-ff origin/debian/bookworm`) | everything, as the vehicle | It is the only method that makes `git rev-list --count HEAD..origin/debian/bookworm` reach **0** (and `..origin/rc1`, as bookworm contains it). It keeps the released changelog entries verbatim and lets the next release-line commit merge without re-conflicting. |
| **R — conflict resolution** | the 12 files, 38 hunks | Rules in §5. |
| **A — adaptation** (TDD, separate commits *after* the merge) | code that merged cleanly but breaks the contract; tests that encode a pre-013 or dict-era assumption | The fix belongs to neither parent. |
| **I — re-implementation** | the deferred 869fat84r half (D1) | The code moved to objects in the refactor; the released version is dict-era and uses retired surface (§6.2). The same rule as planning §10.4: a merge brings the changelog entry, not a working fix. |
| **C — cherry-pick** | **nothing** | It would lose ancestry; the next sweep would flag the same commits again. |

**Why the merge commit cannot be a plain mechanical resolution** (measured, §6.1). Resolving every
conflicting hunk with the refactor's side leaves a *hybrid*: bookworm's non-conflicting hunks still
merge in, and they call code that the refactor side removed. The tree does not import (a circular
import between `CuemsDBMedia` and `CuemsDBProject`), and once that is stubbed, 86 tests fail. So the
**merge commit takes the refactor's side for every hunk and also deletes the clean-merged
dict-era code of the deferred half** (the deletion list is §5.2). Its tree is then *a2431f0 plus the
items that are independent of the deferred half* (§4 rows 5–9). The deferred half's own test files
are collected-out (`collect_ignore` in `tests/conftest.py`, one line per file) in that commit, and each
is un-ignored by the story that ports it. This keeps the merge commit green, and keeps TDD: no
production line comes back before its test is red.

**Commit shape** (all GPG-signed; on a gpg failure, retry; never `--no-gpg-sign`):

1. The merge commit of `origin/debian/bookworm`: the §5 resolutions and the §5.2 deletions, nothing else.
2. Adaptations A-1…, one commit each, each fixing a test that is red on the merge commit or adding
   the missing red test first.
3. The re-implementation story (US3), as red-then-green pairs.
4. The packaging and changelog commit (§7).
5. The docs commit (§9).
6. The cleanup commits (§14), one per sub-section.
7. The suite, relations and CI evidence record.

Do **not** use `git merge -X ours/theirs`. It drops hunks of absorbed fixes silently. `git merge -s
ours` is also wrong here: it would discard §4 rows 5–7.

## 4. Inventory: what the merge brings, and the method for each item

ClickUp ids in parentheses. "Released in" is the bookworm changelog entry that shipped it.
"In HEAD?" says whether `a2431f0` already holds the behaviour (measured by `git grep` of the symbol).

| # | Item | Commits (bookworm) | Released in | In HEAD? | Method | Seam |
|---|---|---|---|---|---|---|
| 1 | Media pixel size, file size, MD5 stored at upload and written into every cue on save (new, update, duplicate); utils floor `>= 0.1.0rc15` (869fat84r, D18) | `bba37df` `83d8460` `b7e304f` `cd37792` `2541424` | rc1-4 | **ported** by 002 (`1502d64`, onto objects; verbatim for the DB parts) | M, resolve to ours | A-1: 45 absorbed tests in `test_media_dimensions.py` assert the dict walk; each is ported or retired with a reason (§6.1) |
| 2 | Correct a project's media values before load; relink cleanup, export and relink warning for files deleted for good (869fat84r D20) | `dd8897c` `b29d40e` `9b6eb13` | rc1-4 | **partly**: the relink guard in `CuemsUpload` is ported; the rest is the deferred half | M + I | §6.2 (e), (d) |
| 3 | Check and report at load, never rewrite (869fat84r D20 rev 2): `CuemsMediaRefresh.py` (223 lines), `media_check_report`, `send_to_project_sessions`, `media_report`, `plan_media_refresh`, `verify_media_files`, the save-time re-probe (`_save_resolvers`), the repair tool's stored-value re-measurement | `199606e` `0b291d1` | rc1-4 | **no** (deferred by 002 M9) | **I** (D1) | §6.1, §6.2 (a)(d)(e)(f)(i) |
| 4 | Save gate: a media cue without a usable media block, or naming a file the library never saw, is refused before anything is written; `ValueError` text reaches the client without the `<class …>` prefix (869fej07m) | `9fa603a` = `f8ed35e` (two routes to the same change) | rc1-5 | **no** | M + **A** | A-2, A-3 |
| 5 | Media name collisions with trashed or stray files on upload, delete and restore (`_free_filename`) | `3cf3a7e` (PR #10) | rc1-7 | **no** | M (clean; passes) | none |
| 6 | Stop shipping `/usr/lib/cuems/CACHEDIR.TAG` (`debian/rules`) | `cb39846` (PR #9) | rc1-6 | **no** (`debian/rules` lacks it) | M + R (`debian/rules`) | §7.3: build and check `dpkg -c` |
| 7 | Node adoption over the WebSocket (`nodelist_get`, `nodelist_modify`, `node_status`) | `943c5e4`, PR #7 | rc1-7 (text only) | **yes** (merge-base is its tip) | none; changelog text only | none |
| 8 | Dec 2025 – Mar 2026 packaging (dh-virtualenv, `pyproject`, postinst), and `72f952a` (rc1-3: the removed `cuemsutils.daemon` import) | `9990926` `77d490c` `6c85404` `ae32d3d` `c0a199b` `9b1893c` `5440908` `e922cb2` `886275f` `349d278` `72f952a` | rc1-1…-3 | **content yes** (`0834e99` copied `debian/` @ `72f952a`) | M (ancestry only) | the root-level packaging documents are new files (row 9) |
| 9 | Nine root-level packaging documents: `.packaging-summary.txt`, `BUILD-PACKAGE.md`, `DEBIAN-PACKAGING.md`, `MANIFEST.in`, `MIGRATION-SUMMARY.md`, `PACKAGING-TEMPLATE.md`, `QUICK-REFERENCE.md`, `STRUCTURE.md`, `USAGE.md` | `9990926` | — | **no** | M, then **delete** in §14 | stale (§14.4) |
| 10 | Released changelog entries `0.1.0rc1-4`, `-5`, `-6`, `-7` | the release commits | — | **no** | M + R (`debian/changelog`) | §7.1 |
| 11 | `CHANGELOG.md` `## Unreleased` (869fej07m) | `9fa603a` | — | **no** | M + R | §7.2 |
| 12 | `cuems-utils (>= 0.1.0rc15)` in `debian/control` and the bookworm `pyproject.toml` pin | `2541424` | rc1-4 | superseded | **R → ours** | relation rows 11, 12, 14 |

### 4.1 Outside both lines: stray branch heads and tags (swept 2026-10-22)

Every `origin/*` branch and every tag was checked: `git rev-list --no-merges <ref> ^HEAD
^origin/debian/bookworm`.

| Ref | Unique commits | Verdict and reason |
|---|---|---|
| `integ/rc1-5-node-adoption` | 1 (`faefa5e`, 2026-10-08) | **Exclude.** A changelog entry for `0.1.0rc1-5+nodeadopt2`, "test-rig integration build … not a release". Its content shipped in rc1-7 (row 7). The exclusion is recorded in evidence and in the completeness test's explicit exclusion list. |
| `media_duration_hack` | 1 (`f67351b`, 2025-09-11, root-level `CuemsDBProject.py`) | **Exclude.** Pre-`src/` layout; the duration work is `fix/media-duration-extraction`, already an ancestor. |
| `docker`, `old-docker` | 10 and 12 (2025-03) | **Exclude.** Abandoned container experiments (SSL, Dockerfile), unrelated to the package. |
| `engine` | 2 (2020) | **Exclude.** Historic. |
| `gh-pages` | 1 | **Exclude.** MkDocs deploy output, not source. |
| `fix/media-upload-trash-name-collision` `3cf3a7e` | 0 | Already inside bookworm (PR #10). |
| `feat/869fat84r-media-dimensions` `0b291d1`, `debian/869fat84r-utils-floor` `2541424`, `release/0.1.0rc1-{4,5,7}`, `feat/nodelist-adoption-api` | 0 each | Inside bookworm or the refactor. |
| 14 further branches (`export`, `feature/*`, `fix/*`, `proto-node`, `server`, `sessions`, `subprocess`, `thread`, …) | 0 each | Inside the refactor or bookworm. |
| Tags `img_a1`, `post_mtc_fix`, `pre_mtc_fix`, `pre-*-merge` (5) | — | Rollback markers of earlier merges. Not releases. |

**No branch has a *released* changelog entry that is on neither line.** The union of `cuems-editor
(<version>)` headers over every branch and tag is: `0.1.0rc1-1 … -7`, `0.1.0rc1-5+nodeadopt2` (rig,
excluded) and `0.1.1-1`. So, unlike the engine, there is no changelog-only hotfix to copy.

Nothing needs `git merge -s ours` for ancestry. The re-sweep at hand-off (§11 step 9) re-runs this
table; a new unmerged head merges by SHA, never by cherry-pick.

## 5. Conflict resolutions (method R)

Measured by `git merge-tree --write-tree` and a trial merge in a scratch worktree.

### 5.1 Per file

| File (hunks) | Resolution | Reason |
|---|---|---|
| `.gitignore` (1) | **Both**: keep ours, add bookworm's `debian/` build-output lines if absent | Both sides ignore different things; the refactor's lines are a superset of the needed ones. |
| `CHANGELOG.md` (1) | **Both**, then §7.2 | Ours is the `0.1.1` section; theirs is `## Unreleased` (869fej07m). Theirs becomes released history. |
| `debian/changelog` (1) | §7.1 | Not a hunk choice. |
| `debian/control` (2) | **Ours** for every versioned `Depends` (rows 11–13); **theirs** for the SPDX header | Rule 4 plus relation rows. Theirs' `cuems-utils (>= 0.1.0rc15)` is the value row 11 replaced. |
| `debian/rules` (2) | **Both**: theirs' SPDX header and the `CACHEDIR.TAG` strip, ours for everything 016 changed | Row 6. |
| `pyproject.toml` (1) | **Ours** (`version = "0.1.1"`, `cuemsutils>=0.1.1,<0.1.2`) | Row 14. |
| `src/cuemseditor/CuemsDBMedia.py` (4) | Hunk 1 (imports): **theirs'** `asyncio`, `json` only if the surviving code uses them; hunk 2 (`_free_filename`): **theirs**; hunks 3, 4 (`md5` docstring, `_md5(md5)`): **ours** | Row 5 is independent of the deferred half; `_md5` is the shared normaliser (see §6.2 g). |
| `src/cuemseditor/CuemsDBProject.py` (12) | **Ours** for hunks 1–7 and 9–12; hunk 8: **combine**: ours' raw-payload comment and fade validation, plus theirs' `validate_media_cues_in_contents(...)` call placed *before* any write | Hunks 3–7: the object walk (`_fix_one_media`, `_set_stored`, `media_staleness`) replaced the dict walk. Hunk 9: theirs re-introduces `_clean_dangling_targets` and `CUE_TYPES`, which CLAUDE.md forbids. Hunk 11: theirs uses `CuemsParser`. Hunk 12: theirs writes the script by hand with `XmlReaderWriter` (see §6.2 b). |
| `src/cuemseditor/CuemsWsServer.py` (1) | **Ours** (`notify_others_config_changed`); `send_to_project_sessions` comes back with US3 | The two functions interleave in one hunk; keeping both textually yields a broken function. |
| `src/cuemseditor/CuemsWsUser.py` (4) | Hunk 1 (imports): **ours**, plus theirs' `check_media_on_open`, `refresh_media_before_load` only with US3; hunk 2 (`project_ready` tail): **ours**; hunk 3 (`repair_acknowledge` vs `_error_text`): **both, as two functions**; hunk 4 (`_report_after_save` vs `OriginalNotPreserved`): **ours**, US3 re-adds the report | Row 4 needs `_error_text`. The 002 gate (`derive_gate`, `repair_acknowledge`) is the load-report path; `media_check_report` is added beside it, not in place of it. |
| `src/cuemseditor/repair_durations.py` (7) | **Ours** for all 7 | The tool writes no script (CLAUDE.md, FR-027a). Theirs' stored-value re-measurement returns with US3 under the `NEEDS_SAVE` rule. |
| `tests/ws-command-responses.txt` (2) | **Both** | It is the protocol reference: the `media_check_report` section (theirs) and the 002 sections (ours) coexist. `test_protocol_doc` and `test_payload_version` read it. |

### 5.2 Clean-merged bookworm code that the merge commit deletes (the hybrid problem)

These merge without a conflict and must not stay, because they depend on removed dict-era code.
Each returns, rewritten for objects, in US3:

- `src/cuemseditor/CuemsMediaRefresh.py` (whole file; it imports `xml.etree` and parses the script
  itself, which is the second reader 002 M10 forbids);
- in `CuemsDBProject.py`: `plan_media_refresh`, `_check_media_file`, `verify_media_files`,
  `_verify_media_row`, `media_report`, `_save_resolvers`, `_verify_row_for_save`,
  `reset_refresh_marks`, `cap_report_files`, and the `from cuemseditor.CuemsDBMedia import (INDEX_STALE
  …)` import;
- in `CuemsDBMedia.py`: `MediaProbe`, `probe_media`, `PROBE_*`, the video-index helpers (002's list);
- in `CuemsWsUser.py`: `_in_background`, `_report_on_open`, `_report_after_save`, `_engine_running`.

`tests/test_media_refresh.py` (71 tests) and `tests/test_media_dimensions.py` (45) are added by the
merge and listed in `collect_ignore` until US3 and A-1 port them.

## 6. Semantic seams (measured)

### 6.1 Measured: the merged tree versus `a2431f0`

**Environment, and why it is indicative.** pyenv 3.11.9, a venv built from `cuemsutils` **at the
candidate tag `4b336cd`** (exported with `git archive`, so no sibling repository was touched), plus
`pytest`, `peewee`, `websockets`. `tests/test_config_round_trip.py` reads
`../cuems-utils/tests/data/corpus/`, so a symlink named `cuems-utils` to the same export sits beside the
worktree. Two worktrees under the session scratchpad; both removed afterwards. No native library is
stubbed (the editor has none). The merged arm is a **hybrid** (per-hunk "ours" for the 5 source files
and a stub that breaks the import cycle, see below), so its failure *count* is a measure of how far
a mechanical merge is from a working tree, not a validation. The arm-A figures are validation-grade:
they equal 016's record (271 passed, 3 skipped).

| Arm | Result |
|---|---|
| A: `a2431f0` alone, `cuemsutils 0.1.1` @ `4b336cd` | **271 passed, 3 skipped, 0 failed** (7.2 s) |
| A: same, `cuemsutils` @ `387598e` (utils `feat/xml-refactor` head, 142 commits past the tag) | 271 passed, 3 skipped, 0 failed (library drift: none) |
| B: merge, every conflicting hunk to ours, `_md5` import stubbed to break a cycle | 411 collected: **322 passed, 3 skipped, 86 failed** (14.7 s) |

**Before the stub, arm B did not import at all**: `CuemsDBMedia` imports `_md5` from `CuemsDBProject`
(the refactor's port), while the clean-merged `CuemsDBProject` imports `INDEX_STALE` and four more
names from `CuemsDBMedia` (bookworm). 17 test modules failed at collection. Common to both arms:
nothing; arm A has no failure, so no failure is environmental.

The 86 failures, by file (all **only** on the merged tree):

| Failing | n | Cause | Adaptation |
|---|---|---|---|
| `test_media_refresh.py` (bookworm, 71 tests) | 44 | The deferred half is missing in the ours-resolved tree. The clean-merged module reaches for `ET`, `refresh_media_before_load` and others that the ours rule removed. | **US3**: re-implement on objects; port the 71 tests as the acceptance set. |
| `test_media_dimensions.py` (bookworm, 45) | 26 | The tests drive the dict walk (`_fix_one_media(cue_type, media: dict, …)`, `DIMENSION_KEYS`). The refactor's equivalents are `test_media_values.py` and `test_media_staleness.py`. | **A-1**: for each test, port its assertion onto the object walk, or retire it with a reason (the assertion is already covered by test X). The disposition table goes to evidence. |
| `test_repair_durations.py` (002) | 10 | The clean-merged tool code calls `_check_stored`, which sits in an ours-dropped hunk. | Disappears once §5.2's deletions are made; the stored-value re-measurement returns in US3 as `NEEDS_SAVE`. |
| `test_validate_media_cues.py` (bookworm, 15) | 4 | Their fixtures write a **pre-013 device-shape** `script.xml`; `CuemsScript.load` raises `SchemaError … run cuems-reshape-devices`. One also needs `CuemsWsUser._error_text` (an ours-dropped hunk). | **A-2**: move the fixtures to the 013 shape (`tests/fixtures/script_minimal_013.xml` exists); **A-3**: keep `_error_text` (§5.1). |
| `test_media_values.py` (002) | 1 | The AST guard "no item assignment on stored media keys" flags `update['file_md5'] = None` at `CuemsDBProject.py:1449`, in clean-merged `_verify_media_row`. | Goes with §5.2's deletion; the rule binds US3 (see M11 in 002). |
| `test_media_migration.py` (002) | 1 | The dry-run test reaches the same `_check_stored`. | Same as `test_repair_durations.py`. |

Passing on the merged tree, i.e. independent of the deferred half: `test_media.py` (5 new tests, row 5),
the 11 of 15 tests in `test_validate_media_cues.py` that do not hit the fixture shape, all 271 baseline
tests except the 12 above, and the 002 suite.

### 6.2 Found by reading, not by a failing test: conformance and risk

| Id | Where | Rule | Required |
|---|---|---|---|
| (a) | bookworm `CuemsWsUser._engine_running`: `{'running': True, 'none': False}.get(status)` | The engine's `project_status` is three-state since cuems-engine rc6-4: `running` / `loaded` / `none` (`../cuems-engine/specs/009…/upstream-reports/cuems-editor-engine-contracts.md`, W2). `loaded` maps to `None`, "the engine does not answer", so the media check is **skipped whenever a project is loaded but stopped**. | Map `loaded` to `False`; the red test uses all three values and an unanswered query. |
| (b) | bookworm `CuemsDBProject.save_xml` hunk 12: temp file, `XmlReaderWriter.write_from_object`, `os.replace` | Constitution V: no `XmlReaderWriter`, no `CuemsParser`. The reason for it, atomic writes, is met by the library: `CuemsScript.save` "answers atomically" (utils `CuemsScript.py:478`, `:517`, `:523`, verified at `4b336cd`). | Take ours. Do **not** re-implement atomic writing. Record that constitution III's "atomic save unverified" ratification note is closed by this. |
| (c) | bookworm `update()` hunk 8, `_clean_dangling_targets`, `CUE_TYPES` | CLAUDE.md: "Do not reintroduce a walk keyed on cue names." | Ours. A regression test that no `CUE_TYPES` exists in `src/`. |
| (d) | bookworm `_relink_existed_media`: `CuemsParser(self.load(project_uuid)).parse()` | Public surface only. | Re-implement through `load_with_report(project_uuid, include_trash=True)` (ours already does). `test_public_surface.py` must stay green. |
| (e) | `CuemsMediaRefresh._light_media_blocks`: `ET.parse(script.xml)` | 002 M10: the script reader must be the library's object load; one reader. | US3 reads cues through `load_with_report`, reusing `media_staleness`. |
| (f) | bookworm `duplicate()` hunk 10 fills durations from the DB on the copy | `duplicate()` is deliberately not validated (CLAUDE.md), but filling is allowed. | Add `_fix_media_durations(project_object)` to ours' `duplicate()` on the object; red test: a legacy project's copy carries the stored values. |
| (g) | `_md5` lives in `CuemsDBProject`, imported by `CuemsDBMedia`; bookworm's `CuemsDBProject` imports from `CuemsDBMedia` | A circular import is the trial's first failure. | Move the normalisers (`_md5`, `_positive_int`, `_valid`) to a leaf module that imports neither; test that `import cuemseditor.CuemsDBMedia` and `…CuemsDBProject` each work first (`test_import_smoke` covers it). utils 014: lowercase before assigning (already done in 002). |
| (h) | ids in the new report frames | Same id helpers as `media_repairs` (`str(cue.get('id'))` as in `_stale_entries`). | Reuse; one test per wire-leaving id. |
| (i) | Two reports about one fact: `document_load_report.media_repairs` (002, gating) and `media_check_report` (869fat84r, informational) | 002 M9/Q6: findings enter `media_repairs`; **no frame of its own may gate a save**; `GateState` is the only per-project report state. | Clarify Q3: should `media_check_report` be derived from the same comparison, never from a second one? Recommended: yes, one comparison, two projections. |
| (j) | **`stop_project` save path.** The editor has **zero** references to `stop_project` in `src/` and `tests/`. | utils 017 report §2: send no target; clear a leftover target when a cue is retyped. The candidate tag `4b336cd` has **no** `stop_project` in `script.xsd` (0 matches); utils `387598e` has it. | A test that saves and reopens a project holding a `stop_project` cue, and one that a leftover `action_target` is refused with rule `project_action_takes_no_target`. Strict xfail against the current tag until utils re-cuts (§8.1, X-1). |
| (k) | utils 017 §1: `CueList.get_media` raises `ValueError` naming the cue for a media block without a file | The editor calls `project_object.get_media()` on both lines (`CuemsDBProject.py:1097` on the refactor). | Row 4's gate runs first and refuses with a plain message; add a test that `get_media`'s `ValueError` reaches the client unprefixed if the gate is bypassed. |
| (l) | X-4, `Media` values on a v2 load, measured | `key in media` and `media.get(key)` are `False`/absent, and the attribute is `None` (not `Unset`), for absent `pixel_width`/`file_size` on `script_minimal_013.xml`, under `cuemsutils` at **both** `4b336cd` and `387598e`. The fixture is the only script measured. | Keep the "absent means missing" reading; add the assertion to `test_media_staleness`. Report to utils as confirmation. |

## 7. Packaging, versions, changelogs

### 7.1 `debian/changelog`

Planning §10.1 shape, ordered by dpkg version, highest first:

```
cuems-editor (0.1.1-1) UNRELEASED        ← kept; body extended (below)
cuems-editor (0.1.0rc1-7) bookworm       ← verbatim from origin/debian/bookworm
cuems-editor (0.1.0rc1-6) bookworm       ← verbatim
cuems-editor (0.1.0rc1-5) bookworm       ← verbatim
cuems-editor (0.1.0rc1-4) bookworm       ← verbatim; the RELEASED text (869fat84r), not the folded 001 body
cuems-editor (0.1.0rc1-3) bookworm       ← already present
cuems-editor (0.1.0rc1-2) UNRELEASED, (0.1.0rc1-1) bookworm   ← already present
```

- **Collision to resolve explicitly.** The refactor's `0.1.0rc1-4 UNRELEASED` was folded into `0.1.1-1`
  by the bump and its header is gone, but its number *was* released from bookworm with different content.
  The released `-4` text goes in verbatim; the 001 text stays only in the `0.1.1-1` body.
- Replace the "NOT YET RECONCILED" bullet with "Reconciled with debian/bookworm at `<sha>`
  (0.1.0rc1-7): absorbs 0.1.0rc1-4 … -7", one line per row 1–6, and the D1 outcome.
- `0.1.0rc1-5+nodeadopt2` is a rig build: **not** in the changelog (§4.1).
- `dpkg-parsechangelog -l debian/changelog -S Version` must still print `0.1.1-1`.

### 7.2 `CHANGELOG.md`: every released build present

Two documents carry the history and both must be complete. Today `CHANGELOG.md` has `## 0.1.1 —
Unreleased` and a single `## 0.1.0rc1 — 2026-05-26` (the CTimecode migration only). **Builds
`0.1.0rc1-1 … -7` are not described there beyond that one change.** The audit, one build per row:

| Build | Date | Covered in `CHANGELOG.md`? | Source |
|---|---|---|---|
| `0.1.0rc1-1` (initial package) | 2025-12-11 | no | `debian/changelog` |
| `0.1.0rc1-2` (dev build) | 2026-03-10 | no | `debian/changelog` |
| `0.1.0rc1-3` (daemon import fix, FadeCue validation) | 2026-08-05 | no | `debian/changelog` |
| `0.1.0rc1-4` (869fat84r) | 2026-10-06 | no | bookworm `debian/changelog` |
| `0.1.0rc1-5` (869fej07m gate) | 2026-10-08 | only as bookworm's `## Unreleased` | bookworm |
| `0.1.0rc1-6` (CACHEDIR.TAG) | 2026-10-09 | no | bookworm |
| `0.1.0rc1-7` (node adoption, trash collisions) | 2026-10-09 | no | bookworm |

Required: keep `## 0.1.1` as the top header; fold bookworm's `## Unreleased` into the released section;
extend `## 0.1.0rc1` with one sub-entry per build, each marked `<!-- source: debian/bookworm
0.1.0rc1-N (<sha>) -->` (the engine's convention), under `Added` / `Changed` / `Fixed`; rewrite the
`0.1.1` lead so it no longer says anything is unreconciled.

**Permanent check (recommended, Q1):** `tests/contract/test_changelog_complete.py`. It reads a
committed manifest of released Debian versions (`tests/data/released-builds.txt`: `0.1.0rc1-1 … -7`,
with the excluded rig build named and explained), and asserts: every version is a header in
`debian/changelog`; every version is named in `CHANGELOG.md`; `dpkg-parsechangelog` top equals
`pyproject`'s version plus `-1`. Where the release tags are present (CI fetches them), it also asserts
each entry is byte-identical to the one at its tag; absent tags, that part skips with a reason. The
mechanical equivalent for review is planning §10.1's `comm -13` recipe, which must print nothing.

### 7.3 `debian/control`, `debian/rules`

- Relations, after the merge, are exactly rows 11–14 of the 016 matrix: `cuems-utils (>= 0.1.1)`,
  `(<< 0.1.2~)`, `cuems-common (>= 1.3.1~)`, `pyproject "cuemsutils>=0.1.1,<0.1.2"`. Re-run
  `cuems-utils/specs/016-coordinated-minor-bump/tools/verdicts.sh`: it reports **121 verdicts, 0 FAIL**
  today (this repo's 21 included). It must report the same after the merge. New evidence goes in
  `specs/003-…/evidence/`; never overwrite 016's.
- `debian/rules` must carry the `CACHEDIR.TAG` strip (row 6) **and** 016's changes. cuems-utils stopped
  shipping the file in `0.1.0rc16+1`, so the strip matters only against an older utils, but it keeps
  every package agreeing that nobody ships it. Build in a bookworm chroot
  (`tests/packaging/bookworm-build.sh`; the CLAUDE.md warning applies: never `debuild` on trixie), run
  `dpkg -c … | grep CACHEDIR`, and record the result either way. The same build checks `Version:
  0.1.1-1` and that the venv's `pyvenv.cfg` says `home = /usr/bin`.
- SPDX headers on `debian/control` and `debian/rules` come from bookworm (clean).

### 7.4 Things that do not move

`poetry.lock` does not exist here (hatch backend), so there is no lock-staleness item. The version
single source stays `src/cuemseditor/__init__.py` (hatch). `debian/postinst`, `prerm`, `postrm`:
identical on both sides.

## 8. Sibling relations, from the `xml-refactor-merge-candidate` perspective

The engine and cuems-utils (its feature 017) have reconciled already; this repository is among the last.
So most lines below are **to confirm**, not to request.

### 8.1 cuems-utils

| Id | Obligation | Measured |
|---|---|---|
| X-1 | `stop_project` in the version-2 `script.xsd` `ActionType`, so the editor can save such a cue. | **Not in the candidate tag** `4b336cd` (0 matches). **In utils `387598e`** (`script.xsd:321`, `ActionCue.py:18`). The editor's test (§6.2 j) is a strict xfail until the re-cut; the re-cut turns it XPASS, which is the signal to drop it. |
| X-4 | `Media.pixel_width/pixel_height/file_size` read semantics, v2 load. | Measured (§6.2 l): absent means absent; attribute `None`; not `Unset`. Confirmation only. |
| 017 §1, §2 | `get_media` `ValueError`; clear a leftover `stop_project` target. | The editor confirms both (§6.2 j, k). |
| Re-cut | The editor's evidence ran against `4b336cd`, and `387598e` gave the same arm-A result (271/3). The editor must be **re-validated on the re-cut tag** (rule 5). | The CI gate input `cuemsutils_ref` (§14.4) is how. |

### 8.2 The other siblings

| Contract | Producer | Consumer and where its half lives | Note |
|---|---|---|---|
| `media_check_report` (US3) | this repo | `cuems-frontend` `origin/dev` (`media-check.service.ts`; absent from the frontend's `feat/xml-refactor`) | **Both halves must exist at the re-cut tags.** The frontend's reconciliation (31 behind `dev`) absorbs its half; this feature produces the editor half and the wire text (`tests/ws-command-responses.txt`, the section "media_check_report (869fat84r D20 …)"). |
| `document_load_report.media_repairs`, `repair_*`, `config_*`, `node_set` | this repo (002) | `cuems-frontend` (adopted in `a3ef0c8`) | Unchanged by this merge. |
| `project_status` `running`/`loaded`/`none` | cuems-engine | this repo (`CuemsWsUser.project_status` relays it; `_engine_running` reads it) | W2 of the engine's report; §6.2 (a). |
| `nodelist_modify`, `node_set` | this repo | cuems-engine, cuems-nodeconf | Already paired; no change. |
| `cuems-common (>= 1.3.1~)` | — | — | Nothing in rc1-4…-7 touches units or `/etc/cuems`. |
| `CACHEDIR.TAG` | utils (stopped), this repo (strips) | — | Cross-package overwrite class; row 6. |

**This feature edits no sibling.** It produces, under `specs/003-…/upstream-reports/`:

1. **to cuems-utils**: the confirmations of §8.1 (X-1 status, X-4 measurement, 017 §1 and §2 answered);
   ask that the editor's strict xfail be named in its list of "still owed".
2. **to cuems-frontend**: the `media_check_report` contract and shape, the line numbers of its
   consumer on `dev`, and a request that its reconciliation confirm both halves.
3. **to cuems-engine**: nothing owed; acknowledge W2 and W4 and say where each is tested.
4. the rewritten `../.xml-refactor-tag-messages/cuems-editor.txt` (§10).

What the engine's pre-spec §8 places on this repository: the `project_status` three-state (W2,
handled by §6.2 a) and the `stop_project` save path (W4, by §6.2 j). Nothing else targets the editor.

## 9. Docs touched by the merge

- **`CLAUDE.md`**: no merge conflict (bookworm does not touch it). Add field notes for what 003 settles:
  the media check is a projection of `media_staleness` (not a second reader); `loaded` is not "not
  answering"; `stop_project` needs utils at or after the re-cut. Remove or correct anything stale after
  the cleanup (paths).
- **`tests/ws-command-responses.txt`**: the merged protocol reference; it carries both sets of frames.
- **`CONTRIBUTORS.md`**: wrong today (`cd src && pytest`; `ruff check .` and "Coverage ≥ 80% / CI green"
  name a CI that does not exist; §14.3). Rewrite its testing and release sections.
- **`tests/README.md`**: describes `test.py`, `test_db.py`, `test_nng.py` and a `legacy/` directory, none of
  which exists. Rewrite (§14.2).
- `specs/001-…` and `specs/002-…` are frozen history; do not rewrite them. Record decisions in 003's
  evidence.

## 10. Acceptance criteria (for spec.md's success criteria)

1. `git rev-list --count HEAD..origin/debian/bookworm` = **0** and `..origin/rc1` = **0**, measured at
   hand-off against freshly fetched refs. The §4.1 sweep is re-run and every row has a verdict.
2. Every row of §4 is present or has a recorded verdict. For rows 4–6, one named test per row passes.
3. The suite (the repository's own CI commands, §14.4) has **no failure that `a2431f0` does not also
   have**, on the same host and with the same `cuemsutils`. Baseline: **271 passed, 3 skipped**. The
   disposition of every bookworm test (ported, retired with reason, passing as-is) is a table in evidence;
   none is silently skipped. Run three times, interleaved, as 016 did.
4. Strict xfails are exactly the §6.2 (j) rows, each with its upstream-report path in the reason, plus the
   existing UR-1/UR-6/UR-7 markers that are still open.
5. `import cuemseditor.CuemsDBMedia` and `…CuemsDBProject` succeed independently; `test_public_surface`
   and `test_import_smoke` stay green; `git grep -nE
   "XmlReaderWriter|CuemsParser|CUE_TYPES|_clean_dangling" -- src` returns nothing.
6. US3: `media_check_report` is sent for the contexts the protocol text lists (open, load, save); it never
   gates a save; it agrees with `media_repairs` for the same project and state (one comparison, two
   projections); `_engine_running` treats `loaded` as not running; the 71 ported tests pass.
7. Relation verdicts: **121 / 0 FAIL** (this repo's 21 rows included), run after the merge. The `.deb`
   builds in the bookworm chroot with `Version: 0.1.1-1`, `home = /usr/bin`, and the `CACHEDIR.TAG` check
   is recorded.
8. **Every released build is in the stable changelogs**, checked mechanically (§7.2): the `comm -13`
   recipe over `debian/changelog` against bookworm ∪ every `v0.1.0*` tag prints nothing; entries `-4 … -7`
   are byte-identical to bookworm's; every build is named in `CHANGELOG.md`; the permanent test exists and
   is part of the suite; `CHANGELOG.md`'s top is `0.1.1`.
9. `../.xml-refactor-tag-messages/cuems-editor.txt` is rewritten: `Tag:` is the new `feat/xml-refactor`
   head after the 003 `--no-ff` merge; "NOT YET RECONCILED" becomes "Reconciled with origin/debian/bookworm
   at `<sha>` (0.1.0rc1-7)"; "Carries" gains 003 and rows 1–6; "Pairs with" is unchanged unless a sibling
   moved. The maintainer re-cuts the tag; this feature does not. (The remote already holds the tag at
   `a2431f0`: it is a move, hence maintainer-only.)
10. The upstream reports of §8.2 exist.
11. The cleanup phase's acceptance (§14.5) holds, and a **dispatched CI run on the 003 head is green**
    (§14.4), recorded in `evidence/ci-gate.md`.

## 11. Execution order (seed for tasks.md)

1. Fetch. Re-measure §2 (counts, new release-line entries, the §7.1 `comm` recipe, `gh pr list`). Update
   the tables if the line moved. Fast-forward `feat/xml-refactor` if the maintainer pushed.
2. Create `003-release-line-reconciliation` off `feat/xml-refactor`. Run the baseline (arm A) with
   `cuemsutils` at the candidate tag; record the environment.
3. Merge `origin/debian/bookworm` with the §5 resolutions and §5.2 deletions, and the `collect_ignore`
   lines. Commit. Run the suite; expect arm A's set.
4. Row 4 (the save gate): A-2, A-3, then §6.2 (c), (k).
5. Row 5 and the shared normalisers (§6.2 g), with the import-cycle red test first.
6. The `stop_project` save-path tests (§6.2 j) and the X-4 assertion (l).
7. **US3** (D1): `_engine_running` (a); the one comparison feeding `media_repairs` and
   `media_check_report`; the check at open and before load; the save-time re-probe within its deadline;
   the repair tool's re-measurement as `NEEDS_SAVE`; port `test_media_refresh.py` and
   `test_media_dimensions.py` test by test, un-ignoring each file as it goes green. Red before green,
   always. Update `tests/ws-command-responses.txt`.
8. Packaging: changelogs (§7.1, §7.2, the permanent test), the rules audit, the bookworm build and the
   `CACHEDIR.TAG` check, the verdicts.
9. Docs (§9). Upstream reports (§8.2).
10. Re-fetch. If the line moved, merge again and loop to step 3 for the delta. Run the full suite (arms
    A and B, three interleaved runs).
11. **Cleanup phase** (§14), one commit per sub-section. Pure moves and deletes; the pass set stays
    unchanged after each.
12. CI (§14.4): `ci.yml`, then the dispatched run once the maintainer has landed the file on `main`.
13. Rewrite the tag message. Hand off: the `--no-ff` merge into `feat/xml-refactor`, landing `ci.yml` on
    `main`, and the tag re-cut are maintainer acts.
14. **Final task: delete this planning file** (`git rm specs/planning/release-line-reconciliation-0.1.1.md`).
    First verify that every section is traceable from `specs/003-release-line-reconciliation/`: FRs or SCs
    for §4–§10 and §14, research for the open items, evidence for §6.1 and §13. Then `git grep -n
    release-line-reconciliation-0.1.1 -- . ':!specs/003-*'` must return nothing. 003 links to the file's last
    commit, so the history stays reachable.

## 12. Open questions for `/speckit-clarify`

1. `CHANGELOG.md` layout (§7.2): sub-entries per build under `## 0.1.0rc1`, as the engine did? And the
   permanent completeness test (recommended) or a one-off evidence script?
2. The merge commit's shape (§3, §5.2): delete the dict-era code in the merge commit and ignore the two
   test files until ported (recommended), or let the merge commit carry the hybrid and fix forward?
3. §6.2 (i): is `media_check_report` derived from the single comparison that feeds `media_repairs`
   (recommended), or does it keep its own plan (`plan_media_refresh`) as released?
4. US3's scope within 0.1.1 (D1 allows cutting it): which of the check at open, the re-probe before load,
   the save-time re-probe and the indexer rebuild are needed for the frontend's warning to be useful?
5. §6.2 (j): once utils re-cuts with `stop_project`, drop the strict xfail inside 003 or leave it to a
   follow-up?
6. Is a mixed-version cluster during a rolling upgrade expected for the editor? (It is not on the engine's
   side; the editor serves one controller.)
7. Cleanup (§14.1): which of the nine root-level packaging documents does anyone still use? Default: all
   deleted, with `BUILD-PACKAGE.md`'s still-true content folded into `CONTRIBUTORS.md`.
8. Cleanup (§14.1): `CuemsLibraryMaintenance` is referenced only by `docs/` and a docstring (nothing
   instantiates it). Delete it, or is the library tree created elsewhere and this should be wired in?
9. Lint (§14.4): there is no lint config. Pick the tool and the baseline (ruff reports 369 findings, black
   would reformat 14 of 16 files, flake8 reports 946 at its defaults). Gate only on the files 003 touches?
10. `tests/index.html` + `tests/static/` (680 K of vendored crypto-js): keep as a manual upload harness
    under `scripts/dev/`, or delete?
11. Should `pypi-publish.yml`'s `environment.url` (`…/project/cuemsutils/…`, a copy-paste from another
    repository) be corrected in 003? It is a publication hazard, not a publication.

## 13. How this was measured (reproducible)

```bash
git fetch --all --tags
git rev-list --count HEAD..origin/debian/bookworm        # 43
git rev-list --count HEAD..origin/rc1                    # 16
git rev-list --count origin/debian/bookworm..origin/rc1  # 0  (rc1 is inside bookworm)
git merge-tree --write-tree --name-only HEAD origin/debian/bookworm   # 12 conflicted files
for r in <every origin/* branch>; do git rev-list --no-merges $r ^HEAD ^origin/debian/bookworm; done
for r in <branches, tags>; do git show $r:debian/changelog | grep -oE '^cuems-editor \([^)]+\)'; done | sort -u
gh pr list --state all ; gh api repos/stagesoft/cuems-editor/contents/.github/workflows?ref=main   # 404
# trial: git worktree add (x2) in the session scratchpad; cuemsutils from `git archive 4b336cd`
# (and 387598e); `git merge --no-commit origin/debian/bookworm`; per-hunk resolver (default ours,
# DBMedia hunks 1-2 theirs); `_md5` import stubbed; `pytest -q -p no:cacheprovider`
sh ../cuems-utils/specs/016-coordinated-minor-bump/tools/verdicts.sh   # 121 verdicts, 0 FAIL
```

Environment: Debian 13 host, pyenv 3.11.9, `cuemsutils 0.1.1` from `git archive` of cuems-utils `4b336cd`
(arm A also at `387598e`). Arm A figures are validation-grade (they equal 016's record). The hybrid arm B
and the lint counts are **indicative**: they depend on the resolution policy and on the ruff/black/flake8
defaults of this host. The worktrees were removed. The `hybrid` count (86) should be re-measured on the real
merge commit in step 3.

## 14. Final phase: repository cleanup for the first stable release

0.1.1-1 is the first real stable release. 003 ends with a cleanup phase that deletes, relocates or rewrites
what lost its meaning. **It runs last, after the final re-merge** (§11 step 10), because moving files before
the merge would turn clean merges into rename conflicts. No behaviour change: each commit is a pure move,
delete or rewire, and the pass set stays the same. A "live reference" is a path-qualified hit in `src/`,
`tests/`, `debian/`, `.github/`, `pyproject.toml` or `docs/`; `specs/` is frozen history.

### 14.1 Files and directories

| Path | What it is | Live references | Verdict |
|---|---|---|---|
| `src/cuemseditor/db.py` (189 lines) | A pre-`src/` scratch script that creates `./project-manager.db` and `.get()`s two hardcoded project UUIDs at import | `tests/test_import_smoke.py` lists it as *excluded from import* and asserts nothing imports it | **delete**, together with its `NOT_IMPORTED` entry |
| `src/cuemseditor/CuemsLibraryMaintenance.py` (59 lines) | Creates the library directory tree | none in `src/` (a docstring in `CuemsProjectManager` and `docs/api.md`, `docs/index.md`) | **decide** (Q8): wire in or delete with its docs |
| Nine root-level packaging documents from bookworm (§4 row 9) | AI-era scaffolding for the dh-virtualenv migration; `MANIFEST.in` names a `setup.py` and a `static/` that do not exist and is ignored by hatch | `.packaging-summary.txt` 0, `QUICK-REFERENCE.md` 0, `STRUCTURE.md` 0, others 1–5 hits, all among themselves | **delete**, folding `BUILD-PACKAGE.md`'s still-true build steps into `CONTRIBUTORS.md` (Q7) |
| `planning/documentation-prompt.md` | A generic doc-generation prompt for "any repository in the family", including "CI test + coverage workflow" | none | **delete** (outside `specs/`, not about this repo) |
| `apache-conf/000-default-le-ssl.conf` | A reverse-proxy example | `tests/README.md` only | **move** to `docs/` (deployment reference) and fix the two references |
| `tests/index.html`, `tests/static/` (90 files, 680 K, vendored crypto-js) | A manual upload harness, not a test | `tests/README.md` only | **move** to `scripts/dev/manual-ui/` or delete (Q10); a vendored library has no business under `tests/` |
| `tests/README.md` | Describes `test.py`, `test_db.py`, `test_nng.py`, `legacy/`: none exists | — | **rewrite** |
| `tests/fixtures/` (`script_minimal.xml`, `script_minimal_013.xml`, `conf/`) | Live fixtures | `tests/conftest.py` and tests | **move** to `tests/data/` behind one `DATA_DIR` |
| `.github/workflows/pypi-publish.yml` | Publishes on a release | its `environment.url` names `cuemsutils` | **keep**; fix the URL (Q11) |
| `.github/workflows/gh-pages.yml` | MkDocs deploy | triggers include `rc1`, `feature/gh-pages` | **keep**; restrict to release refs (§14.4) |
| `mkdocs.yml`, `docs/` | MkDocs site source | `gh-pages.yml` | **keep** |
| `.claude/skills/`, `.specify/` | SDD tooling | — | **keep** |
| `site/`, `.pytest_cache` | Ignored build output | `.gitignore` | none tracked; nothing to do |

Not found, checked: no tracked venv, `__pycache__` or `.pyc` files; no `poetry.lock`; no `dev/` directory;
every `tests/test_*.py` is collected (`testpaths = ["tests"]`, 25 modules, no `testdev_*`).

### 14.2 `tests/` layout, matching cuems-utils

```
tests/
  conftest.py       # fixtures; sets unit / integration / contract from the directory
  support/          # shared helpers (LibraryCtx, fake sockets), paths.py: DATA_DIR
  data/             # fixtures, ws-command-responses.txt, released-builds.txt
  unit/  integration/  contract/  packaging/
```

Initial split (verify at move time; the sweep found **no** real socket, subprocess or JACK use):
`contract/`: `test_public_surface`, `test_import_smoke`, `test_protocol_doc`, `test_payload_version`,
`test_upstream_gates`, `test_schema_descriptor`, and the new `test_changelog_complete`;
`integration/`: `test_probe_duration` (the only module with `ffprobe`/subprocess signals: confirm it is
patched, otherwise it is integration) and any US3 test that needs a real indexer; `unit/`: everything
else. `packaging/` stays. Markers come from the directory via `pytest_collection_modifyitems`;
`--strict-markers` on; the classification rule goes in `tests/README.md` and `CONTRIBUTORS.md`.
`tests/ws-command-responses.txt` is cited by path in the constitution, CLAUDE.md and four tests: move it
once and fix all of them, or leave it (decide in plan; the grep in §14.5 guards both).

**Not applicable here:** frontend tooling, the `slow` marker (no slow tests), `golden/`.

### 14.3 Other stale items

- `CONTRIBUTORS.md`: `cd src && pytest` (tests are at the root), `ruff check .` (no config), "Coverage ≥ 80%"
  and "CI green" (no CI). Rewrite.
- `CLAUDE.md`: re-check the paths it names after the moves.
- `.gitignore`: add `.venv-*/` and `.ruff_cache/`; keep `debian/` build-output lines.
- `README.md`: check every path and command it gives against the new layout.

### 14.4 CI: the pre-publication gate, run manually in the cloud (D2)

**Measured constraints.**
- **There is no test workflow.** The repository has `gh-pages.yml` and `pypi-publish.yml` only.
- **`main` is the default branch and holds no `.github/` directory**: `gh api …/contents/.github/workflows?ref=main`
  returns 404, `main` is `45e6cba` (2021-05-20), and it is unprotected. `workflow_dispatch` runs only workflows
  that exist on the default branch, so the maintainer must land `ci.yml` there. It is the only file that goes to
  `main`.
- **Triggers.** `push` and `pull_request` on `feat/xml-refactor` and `003-release-line-reconciliation`
  (and `main`, after the landing); dispatch is the release gate.
- **`cuemsutils` cannot come from PyPI** (0.1.1 is unpublished; rule 5). Dispatch input `cuemsutils_ref`
  (default `xml-refactor-merge-candidate` of cuems-utils); `pip install "cuemsutils @
  git+https://github.com/stagesoft/cuems-utils@${ref}"`. The job logs the resolved commit
  (`git ls-remote`) and `cuemsutils.__version__`. Push and PR runs use the same default.
- **No lock file**, so there is no staleness question; dependencies resolve from `pyproject.toml`.
- **The X-1 interaction.** Until utils re-cuts with `stop_project`, the strict xfails make the run green and
  honest; re-dispatching after the re-cut turns them XPASS-strict, i.e. red, which says "drop them".
- The release-gate demo that builds the `.deb` (`tests/packaging/bookworm-build.sh`) needs `mmdebstrap`
  user namespaces and is **not** a hosted-runner job: it stays a local, recorded step.

**Job layout** (inside `ci.yml`): `lint` (the tool and scope from Q9; may start as the touched files only),
`unit` (`pytest tests/unit tests/contract -n auto --cov`, no network), `integration`
(`pytest tests/integration --cov`, in parallel), `coverage` (combine, `--fail-under` set from a measured
baseline, not invented), `gate-summary` (editor SHA, `cuemsutils` ref and commit, pass/xfail counts, the
strict-xfail list). The coverage threshold is **measured in plan**; CONTRIBUTORS' "≥ 80 %" is aspirational.

**Docs deploy.** `gh-pages.yml` currently deploys on a push to `main`, `master`, `rc1` and
`feature/gh-pages`. Keep a dispatch or release-ref trigger only; a dispatch on a non-release ref must not
deploy.

**The gate itself.** Before 003 hands off: one dispatched run on the 003 head SHA, green, with
`cuemsutils_ref` at the current utils candidate. Record URL, SHA and summary in `evidence/ci-gate.md`.
Before publication (maintainer): another run on the post-merge `feat/xml-refactor` head with utils' *re-cut*
tag; it gates `pypi-publish.yml` and the `.deb` upload. Write that checklist line into the tag message and
`CONTRIBUTORS.md`.

### 14.5 Acceptance for the cleanup phase

- `git grep -nE "tests/fixtures|tests/static|apache-conf|planning/documentation-prompt|cuemseditor\.db\b" --
  . ':!specs'` returns only the new paths (or nothing).
- No `tests/test_*.py` remains at the root of `tests/`; every collected test carries exactly one of `unit`,
  `integration`, `contract` (a small contract test over the collection asserts it).
- `pytest tests/unit tests/contract -n auto` passes without network. The pass set before and after the
  cleanup is identical, apart from retired tests, each listed in evidence with its reason.
- `ci.yml` exists with the §14.4 jobs and the `cuemsutils_ref` input; the dispatched run is green and
  recorded; a dispatch on a non-release ref does not deploy docs.
- README, CONTRIBUTORS, CLAUDE.md and the constitution (a PATCH amendment through `/speckit-constitution`, if
  it names a moved path) name the new paths.

---

## Appendix A — paste-ready `/speckit-specify` prompt

> Feature `003-release-line-reconciliation` for cuems-editor. Branch off `feat/xml-refactor` (`a2431f0`,
> the `xml-refactor-merge-candidate` commit, version 0.1.1-1 UNRELEASED). Absorb the editor's release line
> `origin/debian/bookworm` (`69d749e`, 0.1.0rc1-7; it contains `origin/rc1`) into the refactor before 0.1.1-1
> is published ("merge before bump", rule 4 of cuems-utils
> `specs/planning/coordinated-release-version-bump.md`), so that nothing shipped in 0.1.0rc1-4…-7 is lost and
> the absorbed code obeys the xml-refactor contract (public `cuemsutils` surface, `CuemsScript` objects, no
> second script reader, version-2 scripts, payload version 1). The work order is
> `specs/planning/release-line-reconciliation-0.1.1.md`. Use its decisions D1–D5 (D1: the deferred half of
> 869fat84r is re-implemented in this feature on objects, as a priority-2 story the maintainer may cut; D2: the
> CI gate is a `workflow_dispatch` run of `ci.yml`, which the maintainer lands on `main` because `main` has no
> `.github/`), its inventory (§4: 12 rows; save gate 869fej07m, media trash name collisions, the
> `CACHEDIR.TAG` strip, the released changelog entries 0.1.0rc1-4…-7, the deferred check-and-report half),
> its stray sweep (§4.1: no hotfix line; the `0.1.0rc1-5+nodeadopt2` rig build and old branches excluded),
> its conflict rules (§5: 12 files, 38 hunks; the merge commit takes the refactor's side and deletes the
> clean-merged dict-era code listed in §5.2), its measured seams (§6: arm A 271 passed / 3 skipped, the
> hybrid arm 86 failures, adaptations A-1…A-3 and the conformance list §6.2 a–l, including the engine's
> three-state `project_status` and the `stop_project` save path), its packaging and changelog shape (§7,
> with a permanent completeness test), its sibling obligations (§8: no sibling edited; upstream reports to
> cuems-utils and cuems-frontend), its acceptance criteria (§10, including §14.5) and its execution order
> (§11). Its final phase is the first-stable-release cleanup (§14): delete `src/cuemseditor/db.py`, the nine
> root-level packaging documents and `planning/documentation-prompt.md`; move the manual upload harness and
> `apache-conf/`; rewrite `tests/README.md` and `CONTRIBUTORS.md`; re-lay `tests/` as cuems-utils does
> (`unit/`, `integration/`, `contract/`, `support/`, `data/`), marked by directory. Pure moves; the pass set is
> unchanged. Add `ci.yml` (lint, parallel unit and integration jobs, combined coverage, a `cuemsutils_ref`
> dispatch input installing cuemsutils from the cuems-utils candidate tag, no docs deploy from non-release
> refs) and record a green dispatched run as evidence. The final task of tasks.md deletes the planning file
> once the 003 artefacts carry all of its content (§11 step 14). Treat §12 as the clarify list. Out of scope:
> publishing, any sibling edit, tag creation or moves, pushes, new behaviour. The version stays 0.1.1-1.
> Constitution: wire is a contract (I), user data has a recovery story (III), tests gate the risky paths (IV),
> cuemsutils through its public surface (V); TDD, YAGNI, no new runtime dependency. Planning artefacts go
> under `specs/003-release-line-reconciliation/`, evidence under its `evidence/`, upstream reports under its
> `upstream-reports/`.
