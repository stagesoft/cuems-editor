<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Tasks: Release-line reconciliation for cuems-editor 0.1.1-1

**Input**: `specs/003-release-line-reconciliation/` (spec.md, plan.md, research.md, data-model.md, contracts/,
quickstart.md) and the temporary pre-spec `specs/planning/release-line-reconciliation-0.1.1.md` (§ numbers).

**Tests**: REQUESTED. The constitution (IV) and the spec require red-first tests for every adaptation and every
re-implementation. A task named "(red)" writes a test that must fail first; its "(green)" partner makes it pass.

**Phase numbering** (tasks.md phase ← plan.md phase): 1 ← 0, 2 ← 1, 3 ← 2, 4 ← 3, 5 ← 4, 6 ← 5, 7 ← 6 and 7, 8 ← 8, 9 ← 9, 10 ← 10, 11 ← 11.

**Organization**: by user story, but the **order of execution is the plan's phase order**, not priority order:
the merge (US1) comes first and the cleanup (US6) last, because moving files before the merge would turn clean
merges into rename conflicts. Each phase says what it depends on.

## Format: `[ID] [P?] [Story] Description`

- **[ID]**: `T###`, or `T###[a-z]` for a task inserted after the list was numbered (for example `T022a`, which runs after T022 and before T023); IDs are never renumbered

- **[P]**: can run in parallel (different files, no dependency on an incomplete task)
- **[Story]**: US1 merge and ancestry · US2 save gate and media names · US3 media check · US4 packaging and
  changelogs · US5 siblings · US6 cleanup and CI
- All commits are GPG-signed (retry on a gpg failure; never `--no-gpg-sign`), end with the attribution line
  from the session, and are never pushed. No tag is created or moved. No sibling file is edited.
- `$S` is the session scratchpad; evidence files live in `specs/003-release-line-reconciliation/evidence/`.

---

## Phase 1: Setup (measurement environment)

- [X] T001 `git fetch --all --tags`; re-measure the lines (`git rev-list --count HEAD..origin/debian/bookworm`, `..origin/rc1`, `origin/debian/bookworm..origin/rc1`), `git merge-tree --write-tree --name-only HEAD origin/debian/bookworm`, and the `comm -13` changelog recipe (contracts/changelog-completeness.md). If the release line moved, update the pre-spec §2/§4 numbers and note it in `evidence/lines-measured.md` (FR-001, FR-005)
- [X] T002 Build the pinned-library environment in `$S`: `git archive 4b336cd` of cuems-utils into `$S/utils-tag`, a Python 3.11 venv with `pytest pytest-cov pytest-xdist peewee websockets ruff`, and the `$S/cuems-utils` symlink the corpus test reads; write `evidence/environment.md` (host, Python, library commit and `cuemsutils.__version__`) (FR-006)
- [X] T003 Baseline arm A: a scratch worktree of `a2431f0`, run `pytest -q -p no:cacheprovider --cov=cuemseditor`; record the pass set and coverage in `evidence/arm-A.txt` (expect 271 passed, 3 skipped, 57 %). Repeat once against the cuems-utils head `387598e` and record the drift in `evidence/arm-A-utils-head.txt` (FR-006, SC-002)
- [X] T004 [P] Re-run the stray sweep of pre-spec §4.1 (`git rev-list --no-merges <ref> ^HEAD ^origin/debian/bookworm` for every `origin/*` branch; the union of `cuems-editor (...)` headers over all refs and tags) and write `evidence/stray-sweep.md` with a verdict and reason per ref; the `0.1.0rc1-5+nodeadopt2` rig build is excluded (FR-005)

**Checkpoint**: environment and baseline recorded; the branch `003-release-line-reconciliation` already exists.

---

## Phase 2: Foundational — the merge commit (US1, blocks everything)

**Goal**: `HEAD..origin/debian/bookworm` and `HEAD..origin/rc1` reach 0 with a green tree.
**Independent test**: after T008 the suite equals arm A (271 passed, 3 skipped) plus the independent absorbed tests; the two deferred test files are excluded from collection.

- [X] T005 [US1] Write `evidence/conflict-resolutions.md`: the per-hunk table (file, hunk, side, reason) for the 12 files and 38 hunks from pre-spec §5.1, and the deletion list of §5.2 (FR-002)
- [X] T006 [US1] `git merge --no-ff --no-commit origin/debian/bookworm` on the feature branch; resolve every hunk per T005 (ours for `CuemsDBProject.py` hunks 1–7 and 9–12, `repair_durations.py`, `CuemsWsServer.py`, `pyproject.toml`; theirs for `_free_filename`; both for `.gitignore`, `CHANGELOG.md`, `tests/ws-command-responses.txt`; the combine rule for `CuemsDBProject.py` hunk 8 and the two-function rule for `CuemsWsUser.py` hunk 3). Never use `-X ours/theirs` (FR-002)
- [X] T007 [US1] In the same merge, delete the clean-merged dict-era media-check code of pre-spec §5.2: `src/cuemseditor/CuemsMediaRefresh.py`; `plan_media_refresh`, `_check_media_file`, `verify_media_files`, `_verify_media_row`, `media_report`, `_save_resolvers`, `_verify_row_for_save`, `reset_refresh_marks`, `cap_report_files` and the `CuemsDBMedia` import block in `src/cuemseditor/CuemsDBProject.py`; `MediaProbe`, `probe_media`, `PROBE_*` and the video-index helpers in `src/cuemseditor/CuemsDBMedia.py`; `_in_background`, `_report_on_open`, `_report_after_save`, `_engine_running` in `src/cuemseditor/CuemsWsUser.py` (FR-003). Keep the deleted text in the commit message body so US3 can read it from history
- [X] T008 [US1] In the same merge, add `collect_ignore = ["test_media_refresh.py", "test_media_dimensions.py"]` to `tests/conftest.py`, with a comment naming the stories that un-ignore them (FR-003). Make the one merge commit (signed); run the suite and record `evidence/arm-B-merge-commit.txt`; it must equal arm A plus the passing independent tests
- [X] T009 [US1] Verify ancestry: `git rev-list --count HEAD..origin/debian/bookworm` = 0 and `..origin/rc1` = 0; record in `evidence/ancestry.md` (SC-001)
- [X] T010 [US1] Write `evidence/test-disposition.md` skeleton: one row for each of the 136 tests the release line adds (`test_media_refresh` 71, `test_media_dimensions` 45, `test_validate_media_cues` 15, `test_media` +5) with disposition columns left to fill as the stories land (FR-006)

**Checkpoint**: green merge commit; US2–US5 can start. US2 and US4 can run in parallel with each other; US3 follows US2's leaf module.

---

## Phase 3: User Story 2 — save gate and media-name fixes (Priority: P1)

**Goal**: the released 869fej07m gate and the trash name-collision fix work under the 0.1.1 contract.
**Independent test**: `pytest tests/test_validate_media_cues.py tests/test_media.py` green; a refused save writes nothing.

- [X] T011 [US2] (red) Fix the absorbed fixtures in `tests/test_validate_media_cues.py` to the version-2 device shape (use `tests/fixtures/script_minimal_013.xml`); confirm the 4 failing cases still fail for the right reason (`_error_text` missing) before any source edit (FR-011, FR-007)
- [X] T012 [US2] (green) In `src/cuemseditor/CuemsWsUser.py` keep `_error_text` as a static method beside `repair_acknowledge` and use it in project save and project new, so a `ValueError` reaches the client unprefixed (FR-008)
- [X] T013 [US2] (green) In `src/cuemseditor/CuemsDBProject.py` `update()`/`new()`: call `validate_media_cues_in_contents(contents, media_exists=self._media_exists)` on the raw payload **before any write** and before fade validation (combine rule of hunk 8); keep `_media_exists`; a trashed file passes (FR-007)
- [X] T014 [P] [US2] (red then green) Add a test in `tests/test_validate_media_cues.py` that the library's `ValueError` for a media block without a file reaches the client unprefixed when the gate is bypassed (monkeypatch the gate off) (FR-009)
- [X] T015 [P] [US2] Confirm the media-name tests in `tests/test_media.py` (5 new) pass on the merged tree; add a rollback test if absent: upload, delete and restore undo their own moves on failure, and restore refuses an untracked live file with a clear error (FR-010, constitution III gate 3)
- [X] T016 [US2] (red) Add `tests/test_media_import_cycle.py`: `import cuemseditor.CuemsDBMedia` and `import cuemseditor.CuemsDBProject` each succeed in a fresh interpreter, and `media_values` imports neither (FR-021)
- [X] T017 [US2] (green) Create `src/cuemseditor/media_values.py` (leaf) holding `_md5`, `_positive_int`, `_valid`; import them from there in `CuemsDBMedia.py` and `CuemsDBProject.py`; keep the lowercase-before-assign rule (utils 014) (FR-021)
- [X] T018 [P] [US2] Add a grep test `tests/test_retired_surface.py`: `src/` contains none of `XmlReaderWriter`, `CuemsParser`, `CUE_TYPES`, `_clean_dangling_targets`, and no dict-walk `_walk_media_durations` signature (FR-022, FR-023, research R9)
- [X] T019 [US2] Fill the disposition rows for `test_validate_media_cues` and `test_media` in `evidence/test-disposition.md`

**Checkpoint**: US2 green on its own.

---

## Phase 4: User Story 5 — `stop_project` and sibling confirmations (Priority: P1)

**Goal**: the editor's `stop_project` save path is tested and the library behaviours of utils 017 are confirmed.
**Independent test**: the tests exist and are strict xfail against the current candidate tag.

- [X] T020 [US5] (red) Add `tests/test_stop_project_save.py`: a project holding a `stop_project` cue with no target saves through `CuemsDBProject.update` and reopens (round trip); a `stop_project` cue with a leftover `action_target` is refused with the rule name `project_action_takes_no_target`; both `@pytest.mark.xfail(strict=True, reason="cuems-utils 4b336cd lacks stop_project; see upstream-reports/cuems-utils.md")` (FR-032)
- [X] T021 [P] [US5] Add the X-4 assertion to `tests/test_media_staleness.py`: for a v2-loaded script with absent `pixel_width`/`file_size`, `key in media` is false and the attribute reads `None` (not `Unset`), asserted on the installed library (research R9, spec edge case)
- [X] T022 [US5] Compatibility task: run T020's tests against the library that will be re-cut (a venv with cuems-utils head), record XPASS/PASS in `evidence/stop-project-compat.md`; only if both pass **and** the candidate tag has been re-cut by hand-off, remove the markers; otherwise keep them and note the tag message as owing (FR-032, clarification)

**Checkpoint**: sibling-facing tests present.

---

## Phase 5: User Story 3 — media check and report on objects (Priority: P2, may be cut by the maintainer)

**Goal**: all four released parts re-implemented on `CuemsScript` objects; `media_check_report` restored byte-identically.
**Independent test**: the ported media-refresh tests (71) and media-dimensions tests (45) pass or have a recorded disposition; the frame matches contracts/media-check-report.md.
**Dependencies**: T017 (leaf module), Phase 2.

### Tests first (red)

- [X] T022a [US3] Capture golden payloads (constitution I, FR-020a): in a scratch worktree of `69d749e`, in a **separate venv with cuemsutils `0.1.0rc16`** (the floor the release line shipped against; the released code still uses `XmlReaderWriter` and `CuemsParser` and reads pre-013 device-shape scripts), with the engine-state callable stubbed to answer `loaded`, run the released producer (`check_media_on_open`, `refresh_media_before_load`, the save report) on a **pre-013** fixture library with one stale video, one stale audio file, one file mutated during its probe, and one clean project; commit the frames as `tests/data/golden/media_check_report_{open,ready,save,copy_in_progress,all_clear}.json` with a `README` naming the source commit, the library version, the stub and the fixture; normalise only volatile values (uuids, names, timestamps). This commit precedes every US3 source edit
- [X] T023 [US3] (red) Add `tests/test_engine_state.py` for the four-case engine mapping: `running` → defer (`engine_running`), `loaded` → proceed, `none` → proceed, no answer → `engine_silent` (FR-015, research R5)
- [X] T024 [US3] (red) Add `tests/test_media_report.py`: exact key set and `context` values of the frame; an all-clear; the 20-file cap with `total_files`; equality with the golden payloads of T022a after normalising uuids and names (key set and value types exact); `copy_in_progress` produced for a file whose `(st_size, st_mtime_ns)` changes during its probe; the report equals `media_repairs` grouped by file (field names `duration|pixel_size|file_size|file_md5`, `stored`, `current`); the report never changes `GateState` and a save is not refused because of it (FR-012, FR-013, FR-014, FR-020)
- [X] T025 [US3] (red) Un-ignore `tests/test_media_refresh.py` in `tests/conftest.py` and port it **test by test** onto the object API (fixtures build `CuemsScript` objects loaded through `load_with_report`; no `xml.etree`; no dict walkers); each ported test fails first; record the disposition of each of the 71 in `evidence/test-disposition.md` (FR-020)
- [X] T026 [US3] (red) Un-ignore `tests/test_media_dimensions.py` and port or retire each of its 45 tests: ported to the object walk (`_fix_one_media`, `_set_stored`, `media_staleness`), or retired **with the id of the 002 test already covering the assertion** (FR-006, FR-019)

### Implementation (green)

- [X] T027 [US3] (green) In `src/cuemseditor/CuemsWsUser.py` re-add `_engine_running` returning the four cases of T023 (never the released two-key `.get`) (FR-015)
- [X] T028 [US3] (green) Create `src/cuemseditor/CuemsMediaRefresh.py` (re-implemented): `media_report(script, repairs, unverified, complete, reason, context)` that projects `media_repairs` into the contracts/media-check-report.md shape; reading the script **only** through `CuemsDBProject.load_with_report` and `media_staleness` — no second reader (FR-013, 002 M10)
- [X] T029 [US3] (green) `check_media_on_open` in `CuemsMediaRefresh.py`: read-only (no engine query, no probe, no indexer, no DB write), shared by simultaneous opens of one project via the in-flight registry kept **outside** `GateState`; its database reads run in the server executor and the registry is mutated only on the event-loop thread; wire it in `CuemsWsUser.project_load` after the `project` frame, audience: the requester only; add a test that another session's frame is served while the check runs (FR-012, FR-019a, constitution II)
- [X] T030 [US3] (green) `refresh_media_before_load` in `CuemsMediaRefresh.py`: engine state check (T027), then re-probe of changed or legacy files and row correction within `REFRESH_DEADLINE_S = 20` (executor, never the event loop; marks and registry mutated on the loop thread only), the copy guard (a file whose size or mtime changes during its probe is `in_copy`, its row untouched, reason `copy_in_progress`), marks for failed or verified files, then the report with `complete`/`reason`; never raises; wire it into `project_ready`, audience: every session on the project. Red tests first, against a temporary library: a failed probe leaves the row byte-identical; a file being copied leaves it unchanged; recovery path named in the docstring (the file is the source; a later load re-measures) (FR-012, FR-016, FR-016b, FR-016c, FR-019a, constitution IV gate 3)
- [X] T031 [US3] (green) `CuemsWsServer.send_to_project_sessions(project_uuid, message, skip=None)` in `src/cuemseditor/CuemsWsServer.py` (mutates shared state only on the event loop) (FR-012)
- [X] T032 [US3] (green) Video-index rebuild of a changed video in `CuemsMediaRefresh.py` as an asyncio subprocess, with the busy-indexer flag (never waited for, no executor worker held); failure is recorded and does not block the load (FR-016a)
- [X] T033 [US3] (green) Save-time re-probe in `src/cuemseditor/CuemsDBProject.py`: a `save_resolvers(deadline)` that wraps `db_duration_resolver`/`db_dimensions_resolver`, re-measures a legacy or changed row first within the deadline, never computes an MD5, leaves unreached rows for later; stored values written through the `Media` attribute setters. Red test first: a probe failure during save leaves the row unchanged and the save still completes with the stored values (FR-016, FR-016c, FR-019)
- [X] T034 [US3] (green) After `project_save`, send the `save`-context report to every session on the project (`_report_after_save`) (FR-012)
- [X] T035 [US3] (green) `duplicate()` in `src/cuemseditor/CuemsDBProject.py`: call `_fix_media_durations(project_object)` on the copy so a legacy project's duplicate carries the stored values; red test first in `tests/test_media_values.py` (FR-017, research R9 f)
- [X] T036 [US3] (green) `src/cuemseditor/repair_durations.py`: the stored-value re-measurement lists a differing project as `NEEDS_SAVE`, flags `DIMS_CHANGED`/`MD5_CHANGED`, and still writes **no script**; red tests first in `tests/test_repair_durations.py`, against a temporary library: the dry run writes nothing (DB and files byte-identical), `--apply` writes its backup before any row, the report lists every change, a failed probe leaves its row unchanged (FR-018, FR-016c, constitution III, CLAUDE.md "never writes a script")
- [X] T037 [US3] Update the protocol reference `tests/ws-command-responses.txt` (moved to `tests/data/` in T057) for `media_check_report` and correct the `project_status` line to `running | loaded | none` plus `project_uuid`, `project_unix_name`; `tests/test_protocol_doc.py` must stay green (contracts/media-check-report.md)
- [X] T038 [US3] Confirm the AST guard `tests/test_media_values.py` (no item assignment on stored media keys) and `tests/test_public_surface.py` pass with the new modules; confirm `tests/test_payload_version.py` and `tests/test_protocol_doc.py` are green (payload version 1, no existing frame changed); run the full suite and diff against arm A (FR-024, SC-002, SC-006, SC-007)

**Checkpoint**: US3 complete, or cut by the maintainer: if cut, delete `CuemsMediaRefresh` tasks T028–T034/T036, keep the exclusions in `tests/conftest.py`, and add the loss to the changelog and tag message (spec US3 note).

---

## Phase 6: User Story 4 — packaging, versions, changelogs (Priority: P1)

**Goal**: complete changelogs, a permanent completeness test, verified relations, a bookworm build.
**Independent test**: `pytest tests/contract/test_changelog_complete.py` (or its pre-move path), `verdicts.sh`, `tests/packaging/bookworm-build.sh`.

- [ ] T039 [US4] (red) Create `tests/data/released-builds.txt` (`0.1.0rc1-1` … `-7`, with an `excluded:` block naming `0.1.0rc1-5+nodeadopt2` and its reason) and `tests/test_changelog_complete.py` implementing the six invariants of contracts/changelog-completeness.md; it must fail now (FR-027, FR-025)
- [ ] T040 [US4] (green) Resolve `debian/changelog`: absorb the released `0.1.0rc1-4` … `-7` entries **verbatim** from `origin/debian/bookworm` in dpkg order beneath `0.1.1-1`; replace the "NOT YET RECONCILED" bullet with "Reconciled with debian/bookworm at <sha> (0.1.0rc1-7)" listing rows 1–6 and the D1 outcome and the "upgrade together" statement; verify `dpkg-parsechangelog -l debian/changelog -S Version` prints `0.1.1-1` (FR-025, FR-032a)
- [ ] T041 [US4] (green) `CHANGELOG.md`: keep `## 0.1.1` on top, rewrite its lead (nothing unreconciled), fold the bookworm `## Unreleased` into the `-5` sub-entry, and add one sub-entry per build `-1…-7` under `## 0.1.0rc1`, each with `<!-- source: debian/bookworm 0.1.0rc1-N (<sha>) -->` (FR-026, research R1)
- [X] T042 [P] [US4] `debian/control`, `debian/rules`, `pyproject.toml`: confirm the merged files carry exactly rows 11–14 of the 016 matrix and the `CACHEDIR.TAG` strip plus the SPDX headers; no new runtime dependency (FR-028, FR-030)
- [X] T043 [US4] Run `sh ../cuems-utils/specs/016-coordinated-minor-bump/tools/verdicts.sh`; record `evidence/relation-verdicts.txt` (expect 121 verdicts, 0 FAIL); never overwrite 016's files (FR-028, SC-004)
- [X] T044 [US4] Build in the bookworm chroot with `tests/packaging/bookworm-build.sh` (never `debuild` on trixie); record `evidence/bookworm-build.md`: `Version: 0.1.1-1`, `home = /usr/bin`, `Depends`, and the result of `dpkg -c … | grep CACHEDIR` (FR-029, research R7)
- [X] T045 [US4] Fill the remaining disposition rows and the inventory proof table (pre-spec §4 rows 1–12, each with its named test) in `evidence/inventory-proofs.md` (FR-004)

---

## Phase 7: Docs, upstream reports, re-merge (US5, US1)

- [X] T046 [P] [US5] Write `upstream-reports/cuems-utils.md`: X-1 status (candidate tag lacks `stop_project`, head has it), X-4 measurement, answers to utils 017 §1 and §2, the strict-xfail name (FR-031)
- [X] T047 [P] [US5] Write `upstream-reports/cuems-frontend.md`: the `media_check_report` contract, the consumer file and line on `origin/dev` (`media-check.service.ts`, `app.component.ts:54`), and the request that its reconciliation confirm both halves. Before writing it, check read-only how the frontend's `feat/xml-refactor` dispatches an unknown WebSocket frame type (ignored, logged, or an error) and record the answer and its file and line in the report; if it errors, say so as a blocker for landing the editor before the frontend (FR-031, constitution I)
- [X] T048 [P] [US5] Write `upstream-reports/cuems-engine.md`: acknowledge W2 (`project_status` three states, where tested: T023) and W4 (`stop_project` save path: T020) (FR-031)
- [X] T049 [US5] Update `CLAUDE.md` field notes: the media check is a projection of `media_staleness`; `loaded` is not "no answer"; atomic script writes belong to the library; `stop_project` needs the re-cut utils; the constitution "atomic save unverified" note is closed (plan Constitution III)
- [X] T050 [US1] Re-fetch (`git fetch --all --tags`); if the release line moved, merge the new commits the same way and loop through the affected phases; re-run the stray sweep (T004); run the suite as arms A and B, three interleaved runs, and record identical sets in `evidence/suite-final-runs.txt` (FR-005, SC-002)

---

## Phase 8: User Story 6 — cleanup (Priority: P2; runs after Phase 7)

**Goal**: the repository is clean for the first stable release. Pure moves, deletes and rewires; the pass set stays the same after each commit.
**Independent test**: `git grep` of old paths returns nothing; the pass set is unchanged.

- [X] T051 [US6] Write `evidence/cleanup-usage-checks.md`: for every candidate (pre-spec §14.1) a path-qualified usage check and a verdict (FR-034)
- [X] T052 [P] [US6] Delete `src/cuemseditor/db.py` and its `NOT_IMPORTED` entry in `tests/test_import_smoke.py`; keep the smoke test's exclusion check meaningful (FR-034)
- [X] T053 [P] [US6] Delete the nine root packaging documents (`.packaging-summary.txt`, `BUILD-PACKAGE.md`, `DEBIAN-PACKAGING.md`, `MANIFEST.in`, `MIGRATION-SUMMARY.md`, `PACKAGING-TEMPLATE.md`, `QUICK-REFERENCE.md`, `STRUCTURE.md`, `USAGE.md`) and `planning/documentation-prompt.md`; first fold any still-true build step of `BUILD-PACKAGE.md` into `CONTRIBUTORS.md` (FR-034)
- [X] T054 [P] [US6] Move `tests/index.html` and `tests/static/` to `dev/scripts/manual-ui/` with a short `README.md` (nothing here is packaged or run by CI) and move `apache-conf/000-default-le-ssl.conf` to `docs/deploy/`; fix the references (FR-034)
- [X] T055 [US6] Leave `src/cuemseditor/CuemsLibraryMaintenance.py` untouched and still documented (clarification); record the decision in `evidence/cleanup-usage-checks.md`
- [X] T056 [US6] (red) Add `tests/contract/test_layout.py`: no `tests/test_*.py` at the root; every collected test carries exactly one of `unit`, `integration`, `contract`; non-test data lives only under `tests/data/`; fails until the move (FR-035)
- [X] T057 [US6] Re-lay `tests/`: `git mv` the modules into `unit/`, `integration/`, `contract/` per plan research R13; create `tests/support/` with the shared helpers and `paths.py` (`DATA_DIR`); move `tests/fixtures/*` and `tests/ws-command-responses.txt` and `tests/data/released-builds.txt` under `tests/data/`; add the directory markers hook to `tests/conftest.py`; keep `--strict-markers`; keep `tests/packaging/` (FR-035)
- [X] T058 [US6] Rewrite every citation of the moved paths in the same commit: `.specify/memory/constitution.md` (PATCH amendment via `/speckit-constitution`), `CLAUDE.md`, the comment in `src/cuemseditor/CuemsWsServer.py`, `test_protocol_doc`, `test_payload_version`, `test_initial_template`, `tests/README.md` and `README.md` (FR-039)
- [X] T059 [P] [US6] Rewrite `tests/README.md` (classification rule, layout, how to run) and `CONTRIBUTORS.md` (testing, lint, release checklist including the pre-publication dispatch line; remove `cd src && pytest`, the unmeasured "80 %" and the stale CI claims) (FR-034, FR-039)
- [X] T060 [US6] Verify: `git grep -nE "tests/ws-command-responses|tests/fixtures|tests/static|apache-conf|planning/documentation-prompt|cuemseditor\.db\b|scripts/dev" -- . ':!specs'` returns nothing; T056 is green; the pass set equals T050's (SC-008)

---

## Phase 9: Polish — lint (US6, after all functionality)

- [X] T061 [US6] Add `[tool.ruff]` to `pyproject.toml` (`select = ["E","F","I","W"]`, `line-length = 120`) and `ruff` plus `pytest-xdist` to the dev extras; record the baseline (expect 269 in `src/`, 44 in `tests/`) in `evidence/lint-baseline.txt` (FR-036a, research R11)
- [X] T062 [US6] Apply `ruff check --fix` for the safe fixes in one lint-only commit, run the suite, confirm the pass set is unchanged (FR-036a)
- [X] T063 [US6] Fix the remaining findings by hand in lint-only commits, one per module group (`CuemsDB*`, `CuemsWs*`, the rest, `tests/`); no behaviour change; run the suite after each; finish with `ruff check .` reporting zero findings (FR-036a, SC-008)
- [X] T064 [P] [US6] Fix `.github/workflows/pypi-publish.yml` `environment.url` to name `cuemseditor` (research R8)

---

## Phase 10: CI gate (US6)

- [ ] T065 [US6] Write `.github/workflows/ci.yml` per contracts/ci-workflow.md: `workflow_dispatch` input `cuemsutils_ref`, push/PR triggers on `feat/xml-refactor` and `003-release-line-reconciliation`, jobs `lint`, `unit` (`pytest tests/unit tests/contract -n auto --cov`), `integration`, `coverage` (`--fail-under` set from a fresh baseline; 55 if unchanged), `gate-summary`; install cuemsutils from the cuems-utils git ref and check cuems-utils out beside the repository for the corpus test (FR-036)
- [ ] T066 [US6] Restrict `.github/workflows/gh-pages.yml` so pushes and dispatches deploy only from `main`, `debian/bookworm` and `rc1` (FR-037)
- [ ] T067 [US6] Validate both workflow files locally (YAML parse; `actionlint` if available) and re-measure combined coverage to set the threshold; record in `evidence/ci-local-validation.md` (SC-009)
- [ ] T068 [US6] **Maintainer act (blocking)**: ask the maintainer to land `.github/workflows/ci.yml` alone on `main`; record the request in `evidence/ci-gate.md`. Until it is landed FR-038 is blocked, not waived
- [ ] T069 [US6] After T068, `gh workflow run ci.yml --ref 003-release-line-reconciliation -f cuemsutils_ref=xml-refactor-merge-candidate`; wait for a green run; record the run URL, the editor SHA, the cuemsutils ref and resolved commit, the summary and the strict-xfail list in `evidence/ci-gate.md` (FR-038, SC-009)

---

## Phase 11: Hand-off

- [ ] T070 Rewrite `../.xml-refactor-tag-messages/cuems-editor.txt`: new `Tag:` line (the `feat/xml-refactor` head after the maintainer's `--no-ff` merge, marked `<MAINTAINER: fill at re-cut>` until then), "Reconciled with origin/debian/bookworm at <sha> (0.1.0rc1-7)", the carried work (003 and rows 1–6), unchanged "Pairs with" unless a sibling moved, the pre-publication dispatch checklist line, the "upgrade together" statement, and any owed `stop_project` marker. This is a text file outside the repository: write it, do not tag (FR-033, FR-032a)
- [ ] T071 Final acceptance sweep against spec SC-001…SC-010; write `evidence/acceptance.md` with one line per criterion and its proof. First re-fetch: if the release line moved after T050, merge the delta before the tag-message rewrite, re-filing any new test file into the new layout and reformatting it to the lint rules (the rules are in `CONTRIBUTORS.md`, T059), and re-run the suite; record whether the line moved
- [ ] T072 **Final task**: verify every section of the pre-spec is traceable (§4–§10 and §14 to FRs/SCs, §6.1 and §13 to evidence); `git rm specs/planning/release-line-reconciliation-0.1.1.md`; `git grep -n release-line-reconciliation-0.1.1 -- . ':!specs/003-*'` must return nothing; link the file's last commit in `evidence/acceptance.md` (FR-040)

---

## Dependencies and order

```text
Phase 1 (T001–T004)
  └─ Phase 2 merge commit (T005–T010)
       ├─ Phase 3 US2 (T011–T019) ──┐
       ├─ Phase 4 US5 tests (T020–T022)
       ├─ Phase 6 US4 packaging (T039–T045)      (parallel with Phases 3–5 after T010)
       └─ Phase 5 US3 (T022a–T038)  needs T017 from Phase 3; T022a before any US3 source edit
Phase 7 docs, reports, re-merge (T046–T050)       after Phases 3–6
Phase 8 cleanup (T051–T060)                        after Phase 7
Phase 9 lint (T061–T064)                           after Phase 8
Phase 10 CI (T065–T069)                            after Phase 9; T069 blocked on T068 (maintainer)
Phase 11 hand-off (T070–T072)                      last; T072 is the final task
```

Within a story: red test, then green; `[P]` tasks touch different files. The cleanup (Phase 8) and the lint
(Phase 9) must not start before T050's final re-merge, or they cause rename conflicts.

## Parallel examples

- After T010: T011–T019 (US2), T039–T045 (US4), T020–T021 (US5) touch different files and can proceed together.
- Phase 7: T046, T047, T048 are independent reports.
- Phase 8: T052, T053, T054 are independent deletes and moves; T057 follows them.
- Phase 9: T064 is independent of T062/T063.

## Implementation strategy

1. **MVP = Phases 1–2 (US1)**: a green merge that makes the release line an ancestor. Stop here and the
   refactor already contains every independent released fix except the media check.
2. Add US2, US4 and US5 (all P1): the data-loss gate, complete changelogs and relations, the sibling tests.
3. Add US3 (P2): the media check. The maintainer may cut it; the cut procedure is under Phase 5's checkpoint.
4. Re-merge, then clean up, lint and the CI gate (US6, P2), in that order.
5. Hand off: the maintainer lands `ci.yml` on `main`, merges the branch with `--no-ff` and re-cuts the tag.

## Summary counts

| Story / phase | Tasks |
|---|---|
| Setup (no story) | 4 (T001–T004) |
| US1 merge and ancestry | 6 + 1 (T005–T010, T050) |
| US2 save gate and media names | 9 (T011–T019) |
| US5 siblings | 3 + 4 (T020–T022, T046–T049) |
| US3 media check | 17 (T022a, T023–T038) |
| US4 packaging and changelogs | 7 (T039–T045) |
| US6 cleanup, lint, CI | 10 + 4 + 5 (T051–T060, T061–T064, T065–T069) |
| Hand-off (no story) | 3 (T070–T072) |
| **Total** | **73** |
