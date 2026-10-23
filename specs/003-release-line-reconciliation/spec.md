<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Feature Specification: Release-line reconciliation for cuems-editor 0.1.1-1

**Feature Branch**: `003-release-line-reconciliation`, branched from `feat/xml-refactor` @ `a2431f0`
(the `xml-refactor-merge-candidate` commit, version `0.1.1-1 UNRELEASED`). It is **local only**:
commit to it, never push it. It merges back into `feat/xml-refactor` with `--no-ff`. That merge, any
push, and the re-cut of the candidate tag are the maintainer's acts.

**Created**: 2026-10-22

**Status**: Clarified 2026-10-22 and 2026-10-23; planned; analysed 2026-10-23 (findings applied)

**Input**: the pre-spec `specs/planning/release-line-reconciliation-0.1.1.md` (commit `b8b9542`),
which holds the measurements, the decisions D1–D5, and the clarify list (its §12). That file is
temporary. The last task of this feature deletes it once this feature's artefacts carry its content
(FR-040). Section numbers (§) below refer to it.

**Purpose**: rule 4 of the coordinated release plan ("merge before bump") for this repository.
`0.1.1-1` is the first stable release. It must contain everything that shipped from the editor's
release line `origin/debian/bookworm` (`69d749e`, `0.1.0rc1-7`; it contains `origin/rc1`), and what
it absorbs must obey the xml-refactor contract. The release line is 43 commits ahead of the refactor
and 12 files conflict (38 hunks).

**Citation rule**: requirements from 001 and 002 are cited as `001 FR-<n>` and `002 FR-<n>`. A bare
`FR-<n>` is one of this feature's. Upstream reports are cited as `<repo> UR-<n>`.

---

## Clarifications

### Session 2026-10-22

- Q: Which parts of the released media check must US3 deliver? → A: **All four, as released**: the check at open, the re-probe before load, the re-probe at save, and the video-index rebuild. The frontend's reconciliation follows this feature, so the editor half must be complete when it starts.
- Q: What does the lint job check? → A: **The whole tree, and all existing findings are fixed in this feature**, in the final polish phase after all functionality is absorbed. The lint job is therefore part of the CI gate, and the cleanup phase ends with lint-only commits (no behaviour change, pass set unchanged).
- Q: Which dead or unclear files does the cleanup delete? → A: **Delete** the nine root-level packaging documents (folding any still-true build steps into the contributor guide) and the dead `db.py`. **Move** the manual upload page and its vendored assets to `dev/scripts/`. **Leave `CuemsLibraryMaintenance` in place**, unchanged and not wired in (it stays documented in `docs/`).
- Q: Who removes the `stop_project` expected-failure marker? → A: **This feature.** cuems-utils already carries the value on its head. A dedicated task first tests compatibility of the editor against that library (the save/reopen round trip and the leftover-target refusal on the library that will be re-cut) and only then drops the marker. If the candidate tag has not been re-cut by hand-off, the marker stays and the tag message records it as owed.
- Q (planning, 2026-10-23): Where do non-test data files live? → A: **`tests/data/`**, including `ws-command-responses.txt`; every citation of the old path is rewritten in the same commit.
- Q: Is a mixed-version setup supported? → A: **No.** The controller, engine and frontend upgrade together. The release notes and the tag message say so, and no old-client compatibility tests are added.

### Session 2026-10-23

- Q: Which branches count as release refs for the documentation deploy? → A: **`main`, `debian/bookworm` and `rc1`.** Pushes and dispatches on those deploy the docs; every other ref (including `feat/xml-refactor`, this feature's branch and `master`) does not.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Nothing that shipped is lost, and the release line is an ancestor (Priority: P1)

The maintainer prepares `0.1.1-1`. Operators in the field run `0.1.0rc1-4` to `-7`. After this story
the refactor branch contains the release line's history, its released changelog entries, and every
change independent of the media-check work, so upgrading to `0.1.1-1` removes no released fix.

**Why this priority**: it is the point of rule 4. Without it, the first stable release silently drops
shipped behaviour, and the behind-count stays above zero so every future release-line commit
re-conflicts.

**Independent Test**: after the merge, `git rev-list --count HEAD..origin/debian/bookworm` and
`HEAD..origin/rc1` are both 0, the suite equals the baseline, and each row of the inventory (§4) has a
named passing test or a recorded verdict.

**Acceptance Scenarios**:

1. **Given** the refactor head `a2431f0` and a freshly fetched release line, **When** the release line
   is merged, **Then** both behind-counts are 0 and the merge commit contains only the documented
   conflict resolutions and deletions (§5).
2. **Given** the merge commit, **When** the repository's tests run against the pinned `cuemsutils`,
   **Then** no test fails that fails on `a2431f0` under the same library and host, and the 271 baseline
   passes remain.
3. **Given** the release line moved after the pre-spec was measured, **When** the work starts and again
   before hand-off, **Then** the new commits are measured and merged the same way.
4. **Given** every remote branch and every tag, **When** they are swept for commits reachable from
   neither line, **Then** each has a recorded verdict (include, re-implement, changelog-only, exclude)
   with its reason, and the `0.1.0rc1-5+nodeadopt2` rig build is excluded.

---

### User Story 2 - The released save gate and media-name fixes work under the new contract (Priority: P1)

An operator saves a project whose media cue has no usable media block or names a file the library has
never seen. The save is refused, naming the cue, before anything is written. An operator uploads a file
named like one in the trash; it gets a versioned name instead of failing. Both shipped in `-5` and `-7`.

**Why this priority**: they are released fixes of data-loss and upload failures, independent of the
media-check work, and they are what a stable release must not regress.

**Independent Test**: the absorbed tests for these behaviours pass on the merged tree, with fixtures in
the version-2 device shape.

**Acceptance Scenarios**:

1. **Given** a save with a media cue lacking a media block, an empty file name, no id, or a file unknown
   to the library, **When** the save runs, **Then** it is refused before any row or file is written, the
   message names every offending cue, and the client sees it without a class-name prefix.
2. **Given** a media file in the media trash, **When** a cue references it, **Then** the save passes.
3. **Given** an upload, delete or restore whose name collides with a trashed or stray file, **When** it
   runs, **Then** it takes the versioned name, restore refuses an untracked live file with a clear
   error, and a rollback undoes its own moves.
4. **Given** the bypassed gate, **When** the library raises its own `ValueError` for a media block
   without a file, **Then** the text reaches the client unprefixed.

---

### User Story 3 - The media check and report is re-implemented on objects (Priority: P2)

An operator opens or loads a project whose media file was replaced by hand under the same name. The
editor measures what belongs to the library, and reports the stored values the project still holds that
no longer match, as a warning that persists in the UI. The project file is never rewritten at load.
This shipped in `0.1.0rc1-4` as dict-era code. Feature 002 deliberately deferred it.

**Why this priority**: rule 4 requires it, and the frontend's `dev` already consumes the
`media_check_report` frame. It is P2 because it is the largest piece, and the maintainer may cut it
from `0.1.1` (D1) without blocking US1, US2 and US4 to US6. If cut, the release notes and the tag
message must say so.

**Independent Test**: the ported acceptance set (the released media-refresh tests, ported test by test)
passes against the object API, and one comparison feeds both the load report's `media_repairs` and the
`media_check_report`.

**Acceptance Scenarios**:

1. **Given** a project with stale stored media values, **When** it is opened or loaded, **Then** a
   `media_check_report` is sent for the contexts the protocol text lists, `media_repairs` lists the same
   findings, and the report agrees with it.
2. **Given** a report, **When** the operator saves, **Then** the report never gates the save; only the
   002 gate does.
3. **Given** the engine answers `loaded` (a project loaded and stopped), **When** the check decides
   whether it may re-probe, **Then** `loaded` counts as "not running". `none` also does. Only `running`
   defers the check, and an unanswered query is distinct from all three.
4. **Given** a changed media file, **When** a save occurs within the deadline, **Then** the row is
   re-measured and the save writes the real values. Past the deadline the remaining rows are checked
   later.
5. **Given** the repair tool, **When** it finds a stored value differing from the library, **Then** it
   lists the project as needing a save and still writes no script (002 FR-027a).
6. **Given** the script, **When** the check reads it, **Then** it reads it through the library's object
   load, not a second reader.

---

### User Story 4 - Packaging, versions and changelogs are complete and verified (Priority: P1)

A packager builds `cuems-editor_0.1.1-1_all.deb` and a reader of the changelogs sees every build that
ever shipped.

**Why this priority**: an incomplete changelog hides a lost build, and a wrong relation makes `dpkg`
refuse the set.

**Independent Test**: the completeness check, the relation verdicts, and a bookworm-chroot build.

**Acceptance Scenarios**:

1. **Given** the merged `debian/changelog`, **When** its headers are compared with bookworm's and every
   release tag's, **Then** nothing is missing; the top is `0.1.1-1`; entries `-4` to `-7` are
   byte-identical to the released ones; the "not reconciled" bullet is replaced.
2. **Given** `CHANGELOG.md`, **When** audited build by build, **Then** `0.1.0rc1-1` to `-7` are each
   described and sourced, and the top header stays `0.1.1`.
3. **Given** a future release-line merge that drops a build, **When** the suite runs, **Then** a
   permanent test fails.
4. **Given** the merged control files, **When** the 016 relation verdicts run, **Then** all 121 pass
   with this repository's rows at their 016 values.
5. **Given** a bookworm-chroot build, **Then** `Version` is `0.1.1-1`, the venv's `home` is `/usr/bin`,
   and whether `CACHEDIR.TAG` is shipped is recorded (the strip is in `debian/rules`).

---

### User Story 5 - Sibling relations are verified and obligations written down (Priority: P1)

The maintainers of cuems-utils, cuems-frontend and cuems-engine know what this repository confirms and
what it needs, without this feature editing their files.

**Why this priority**: wire contracts added on the release line need both halves at the re-cut tags.

**Independent Test**: the upstream reports exist; the `stop_project` save-path tests exist.

**Acceptance Scenarios**:

1. **Given** a project holding a `stop_project` cue with no target, **When** it is saved and reopened,
   **Then** it round-trips. Until the library carries the value, this test is a strict expected failure
   whose reason names the upstream report. A leftover target is refused with the library's rule.
2. **Given** the three-state `project_status` of the engine, **When** the editor relays or reads it,
   **Then** the behaviour is covered by tests (US3 scenario 3).
3. **Given** this repository's conclusions, **Then** reports exist for cuems-utils (confirmations of its
   0.1.1 behaviours), cuems-frontend (the `media_check_report` contract and its consumer) and
   cuems-engine (acknowledgement), and the rewritten tag message names the reconciliation.

---

### User Story 6 - First-stable cleanup and a CI pre-publication gate (Priority: P2)

A new contributor finds one test layout, no dead files, accurate docs, and a CI workflow the maintainer
can dispatch against any ref before publishing.

**Why this priority**: the first stable release is the moment to clean; it runs last because moving
files earlier would turn clean merges into rename conflicts. It is P2 because it changes no behaviour.

**Independent Test**: after the moves the pass set equals the pre-cleanup set; the dispatched workflow
run is green and recorded.

**Acceptance Scenarios**:

1. **Given** the cleanup list (§14), **When** applied, **Then** each file has a recorded
   path-qualified usage check and a delete, move or keep verdict, and no tracked reference points at a
   removed path.
2. **Given** the new layout, **Then** every collected test is in exactly one of unit, integration or
   contract, marked from its directory, and the unit and contract passes need no network.
3. **Given** `ci.yml` landed on `main` by the maintainer, **When** dispatched on the feature head with
   the library input set to the cuems-utils candidate, **Then** all jobs are green and the run, the
   SHAs, the library commit and the strict-xfail list are recorded.
4. **Given** a dispatch on a non-release ref, **Then** no documentation is deployed.

---

### Edge Cases

- The release line gains a `0.1.0rc1-8` mid-work: re-measure and merge the delta; the loop is part of
  the order of work.
- The refactor's `0.1.0rc1-4` number was folded into `0.1.1-1` but was also released with different
  content: the released text is absorbed verbatim and the 001 text stays only in the `0.1.1-1` body.
- The merge brings dict-era code that depends on code the refactor side removed (an import cycle,
  missing helpers): it must be deleted in the merge commit, not left to fail later.
- The utils candidate tag lacks `stop_project` while the library head has it: the editor is
  re-validated on the re-cut tag.
- A client sends a media value that is absent versus `Unset` versus `None`: absent means missing, as
  measured on both library versions.
- `main` carries no workflows: the gate cannot be dispatched until the maintainer lands the file.
- The cleanup would delete something a rig operator uses (the manual upload page): the
  clarify step decides; the default keeps what is documented as used.

## Requirements *(mandatory)*

### Functional Requirements

**Merge and ancestry (US1)**

- **FR-001**: The refactor branch MUST contain `origin/debian/bookworm` by a real merge (`--no-ff`),
  not by cherry-pick or an ours-strategy merge, so that the behind-counts against `origin/debian/bookworm`
  and `origin/rc1` are 0 at hand-off.
- **FR-002**: The conflicts MUST be resolved per the pre-spec's table (§5.1), recorded as a per-hunk
  table in evidence, and the merge commit MUST contain only those resolutions and the deletions of §5.2.
- **FR-003**: The merge commit MUST delete the clean-merged dict-era code of the deferred media-check
  half, and the two released test files that exercise it MUST be excluded from collection until US3
  ports them, so that the merge commit is green.
- **FR-004**: Every inventory row (§4) MUST end present with a named test, or carry a recorded verdict
  and reason.
- **FR-005**: The branch-and-tag sweep (§4.1) MUST be run at the start and again before hand-off, every
  unmerged head merged by SHA (never cherry-picked), and the rig build and abandoned branches recorded as
  excluded.
- **FR-006**: The baseline (the refactor head under the pinned library) and the merged tree MUST be
  measured in the same environment, with each failure present only on the merged tree given a cause and
  an adaptation. The disposition of every absorbed test (ported, retired with a reason, passing as is)
  MUST be a table in evidence.

**Save gate and media names (US2)**

- **FR-007**: A save MUST be refused before any database row or file is written when a media cue has no
  media block, a null or empty one, an empty or missing file name, no id, or names a file the library has
  never seen; the error MUST name every offending cue. A file in the media trash MUST pass.
- **FR-008**: A refusal by a save-time gate MUST reach the client as its own text, without the class-name
  prefix, in project save and project new alike.
- **FR-009**: The library's own error for a media block without a file MUST reach the client unprefixed
  if the gate is bypassed.
- **FR-010**: Upload, delete and restore MUST handle name collisions with trashed or stray files as
  released in `-7`, including the rollback of the operation's own moves.
- **FR-011**: The absorbed tests MUST use the version-2 device shape. A fixture in the retired shape
  MUST be converted, not skipped.

**Media check and report (US3, D1)**

- **FR-012**: The editor MUST report, at open and before load, the stored media values that differ from
  the library, in a `media_check_report` for the contexts the protocol reference lists, and MUST NOT
  rewrite the project file at load.
- **FR-013**: The report MUST be a projection of the same comparison that produces the load report's
  `media_repairs`; there MUST be no second comparison and no second script reader.
- **FR-014**: The report MUST NOT gate a save and MUST NOT add per-project report state beside the 002
  gate state.
- **FR-015**: The check MUST treat the engine states `running`, `loaded`, `none` and "no answer" as four
  distinct cases; only `running` defers re-probing.
- **FR-016**: A save MUST re-measure a changed or legacy library row within the released deadline of 20 seconds (`REFRESH_DEADLINE_S = 20` at `69d749e`), never
  compute an MD5 on the save path, and leave unreached rows for a later save or load.
- **FR-016a**: The editor MUST rebuild the video index of a changed video during the pre-load check, so the nodes receive a valid index in the same load; a busy indexer is never waited for and no executor worker is held.
- **FR-016b**: A file whose size or modification time changes while it is being probed MUST be left unmeasured, listed in `unverified`, and reported with reason `copy_in_progress`; its row is not written.
- **FR-016c**: Every library-row write of the check (before load, at save, in the repair tool) MUST leave the row unchanged when the probe fails, and the repair tool MUST keep its backup before `--apply`, its dry run that writes nothing, and its report (constitution III).
- **FR-017**: The duplicate of a project MUST carry the library's stored values, as a save does.
- **FR-018**: The repair tool MUST list a project whose script holds a different stored value as needing a
  save, and MUST NOT write a script.
- **FR-019**: Stored media values MUST be written through the media attribute setters, never by item
  assignment; ids in the new frames MUST pass through the same helpers as the existing report.
- **FR-019a**: The check's database reads and probes MUST run in the server executor, never on the event loop; the in-flight registry and marks MUST be mutated only on the event-loop thread (constitution II).
- **FR-020**: The released media-check tests MUST be ported test by test as the acceptance set. The
  protocol reference MUST document the frame, and no frame defined here may change an existing one
  (constitution I).
- **FR-020a**: The restored frame MUST be compared with golden payloads captured from the released producer at `69d749e` (contexts `open`, `ready`, `save`), committed before any US3 source edit (constitution I).
- **FR-021**: The shared value normalisers MUST live where neither media module imports the other, and
  each module MUST import on its own.

**Contract conformance (all stories)**

- **FR-022**: `src/` MUST contain no use of the retired surface (no direct XML reader/writer, no
  `CuemsParser`, no dangling-target walk, no cue-type list); the public-surface test MUST stay green.
- **FR-023**: Atomic script writing MUST come from the library's save; the editor MUST NOT re-implement
  it.
- **FR-024**: Payload version stays 1 and no existing frame changes shape.

**Packaging and changelogs (US4)**

- **FR-025**: `debian/changelog` MUST contain every build in the union of bookworm, rc1 and every release
  tag, entries `0.1.0rc1-4` to `-7` verbatim, top `0.1.1-1`, the "not reconciled" bullet replaced by a
  "reconciled at <sha>" statement. Rig builds are excluded by an explicit, explained list.
- **FR-026**: `CHANGELOG.md` MUST describe each of `0.1.0rc1-1` to `-7`, each with a source marker; its
  top header MUST remain `0.1.1`; its lead MUST no longer say anything is unreconciled.
- **FR-027**: A permanent test MUST check the changelogs against a committed manifest of released builds
  (and, where release tags are present, byte-identity of the entries), and the project's version sites.
- **FR-028**: The merged control files MUST keep this repository's relation rows at their 016 values and
  the build rules MUST keep the `CACHEDIR.TAG` strip; the 016 verdict tool MUST report no failure, with
  new evidence in this feature's folder (016's never overwritten).
- **FR-029**: The package MUST be built in a bookworm chroot, never with `debuild` on the trixie host,
  and the evidence MUST show version, interpreter home and the `CACHEDIR.TAG` result.
- **FR-030**: The version stays `0.1.1-1`; no new runtime dependency is added.

**Siblings and tag message (US5)**

- **FR-031**: No file in a sibling repository MUST be edited. Obligations MUST be written as reports in
  `upstream-reports/` for cuems-utils, cuems-frontend and cuems-engine.
- **FR-032**: Saving and reopening a project with a `stop_project` cue MUST be tested; a leftover target
  MUST be refused with the library's rule; until the library carries the value the round trip is a
  strict expected failure naming its report. A dedicated task MUST first verify the editor against the
  library that carries the value, and only then remove the marker.
- **FR-032a**: The release notes and the tag message MUST state that the controller, engine and frontend upgrade together; no mixed-version support is provided.
- **FR-033**: The candidate tag message `../.xml-refactor-tag-messages/cuems-editor.txt` MUST be rewritten:
  new `Tag:` line, "reconciled with origin/debian/bookworm at <sha>", the carried work, an unchanged
  "pairs with" unless a sibling moved, and the pre-publication checklist line. No tag is created, moved
  or pushed.

**Cleanup and CI (US6)**

- **FR-034**: The cleanup MUST give each candidate file a path-qualified usage check and a verdict, delete
  the dead script, the nine root packaging documents and the generic prompt (subject to clarification),
  move the manual upload harness and the proxy example, and rewrite the stale test and contributor
  guides. Each cleanup commit is a pure move, delete or rewire; the pass set is unchanged.
- **FR-035**: The tests MUST be re-laid as unit, integration, contract, support and data, marked from the
  directory, with every non-test data file (fixtures and `ws-command-responses.txt`) under `tests/data/`, with the classification rule written down and a test asserting that every collected test
  carries exactly one such mark. Unit and contract passes MUST need no network.
- **FR-036**: A workflow named `ci.yml` MUST provide lint, parallel unit and integration jobs, combined
  coverage with a threshold taken from a measured baseline, and a summary job; a dispatch input MUST
  select the cuems-utils ref the library is installed from; push and pull-request triggers MUST include
  the integration branch and this feature's branch.
- **FR-036a**: The lint job MUST cover the whole tree. All existing findings MUST be fixed in a final polish phase, after every functionality story is absorbed, as lint-only commits that change no behaviour and keep the pass set unchanged. The tool and its configuration MUST be committed in the repository.
- **FR-037**: The documentation deploy MUST run only from the release refs `main`, `debian/bookworm` and `rc1`; a push or dispatch on any other ref MUST NOT deploy.
- **FR-038**: One dispatched run on the feature head, with the library input at the current utils
  candidate, MUST be green and recorded in evidence. It depends on the maintainer landing the file on
  `main`; until then the requirement is blocked, not waived.
- **FR-039**: Docs and rules that name moved paths (README, contributor guide, CLAUDE.md, the
  constitution by a patch amendment) MUST name the new paths, and a repository search for the old paths,
  excluding frozen specs, MUST return nothing.
- **FR-040**: The final task MUST delete the pre-spec only after every one of its sections is traceable
  to this feature's artefacts, and a repository search for its name outside this feature's folder MUST
  return nothing.

### Key Entities

- **Release line**: the branch holding the released changelog entries and tags; its content must be an
  ancestor of the refactor head.
- **Inventory row**: one released change, with its source commits, the build that shipped it, whether the
  refactor already has it, the method, and its seam.
- **Conflict resolution record**: per file and hunk, the chosen side, and the reason.
- **Media check report**: the informational projection of the comparison between a project's stored media
  values and the library; never a gate.
- **Released-builds manifest**: the committed list of Debian versions that shipped, with explained
  exclusions, used by the completeness check.
- **Upstream report**: a text for a sibling's maintainers, never an edit in their repository.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At hand-off, 0 commits of the release line (and of `origin/rc1`) are missing from the
  feature head, measured against freshly fetched refs.
- **SC-002**: 0 tests fail on the feature head that do not also fail on `a2431f0` under the same library
  and host; the 271-test baseline is intact, and every released test absorbed has a recorded disposition
  (100 % covered, none silently skipped). Three interleaved runs give identical sets.
- **SC-003**: 100 % of the builds `0.1.0rc1-1` to `-7` appear in both changelogs, and the permanent check
  fails when any one is removed.
- **SC-004**: All 121 relation verdicts report no failure, and the package builds in a bookworm chroot
  with the expected version.
- **SC-005**: An operator saving a malformed media cue gets a refusal naming the cue in one step, with no
  row or file written (0 writes before refusal).
- **SC-006**: A project with stale stored media values is reported on open and load with the same findings
  as the load report (0 discrepancies in the ported acceptance set), and the report never blocks a save.
- **SC-007**: 0 occurrences of the retired surface in `src/`; the public-surface and import tests pass.
- **SC-008**: After the cleanup, 0 tracked references to removed or moved paths outside frozen specs, 0
  collected tests outside the three marked directories, and an unchanged pass set apart from listed
  retirements.
- **SC-009**: One dispatched CI run on the feature head is green and recorded with its run link, SHAs,
  library commit and strict-xfail list.
- **SC-010**: The three upstream reports and the rewritten tag message exist; no sibling file and no tag
  was changed.

## Assumptions

- The release line may still move; the measurements are a snapshot and are repeated at the start and
  before hand-off.
- The library under test is the cuems-utils candidate tag, re-validated on its re-cut (rule 5); at the
  time of writing the library head already carries `stop_project` and the candidate tag does not.
- Feature 002's constraints on the deferred work (findings enter `media_repairs`, no frame of its own
  gates a save, one per-project report state, one script reader) bind US3.
- The 12 conflicting files and 38 hunks are as measured on `a2431f0`; the hybrid-tree failure count (86)
  is indicative and is re-measured on the real merge commit.
- The maintainer lands `ci.yml` on `main` and re-cuts the tag; this feature neither pushes nor tags.
- No lock file exists, so there is no lock-staleness item.
- Five of the pre-spec's open questions (§12) were settled in the Clarifications section. The rest keep the defaults stated there and are decided in the plan.
- Out of scope: publishing, sibling edits, tag moves, pushes, new behaviour, the cuems-frontend
  reconciliation itself.
