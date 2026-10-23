<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Implementation Plan: Release-line reconciliation for cuems-editor 0.1.1-1

**Branch**: `003-release-line-reconciliation` | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-release-line-reconciliation/spec.md`, with the
measurements in `specs/planning/release-line-reconciliation-0.1.1.md` (the pre-spec, temporary; § numbers
below refer to it).

## Summary

Merge the editor's release line (`origin/debian/bookworm` @ `69d749e`, 0.1.0rc1-7, containing `origin/rc1`)
into the refactor head `a2431f0` so that nothing shipped in 0.1.0rc1-4…-7 is lost. A plain mechanical merge
is not enough (measured: 12 files, 38 hunks, and a per-hunk resolution that does not even import), so the
work is: one merge commit that takes the refactor's side and deletes the clean-merged dict-era media-check
code; adaptation of the independent released fixes (save gate, media-name collisions, packaging); a
re-implementation of the deferred media check and report on `CuemsScript` objects (US3, all four released
parts); complete changelogs with a permanent completeness test; sibling reports; and a last phase that
cleans the repository, re-lays `tests/`, fixes every lint finding and adds a dispatchable `ci.yml`.
No new runtime dependency, no payload change, version stays `0.1.1-1`.

## Technical Context

**Language/Version**: Python 3.11 (`.python-version` 3.11.9; `requires-python >=3.11`). Bookworm packages
build with 3.11.

**Primary Dependencies**: `cuemsutils >=0.1.1,<0.1.2` (row 14), `peewee >=3.17`, `websockets >=14`. Dev:
`pytest`, `pytest-cov`, `pytest-xdist` (new, dev only, for `-n auto`), `ruff` (new, dev only). No runtime
addition.

**Storage**: SQLite `project-manager.db` (tables `project`, `media`, `projectmedia`) and the project XML
under `settings.xml <library_path>` (`/opt/cuems_library/`). The `media` table already has the four stored
columns (002, `ensure_media_columns`).

**Testing**: `pytest`. Baseline on `a2431f0` with `cuemsutils 0.1.1` @ `4b336cd`: **271 passed, 3 skipped**,
coverage **57 %** (2726 statements; measured 2026-10-23). The absorbed release-line tests add 136 tests.

**Target Platform**: Linux controller (Debian 12 bookworm package; Debian 13 development host).

**Project Type**: Python service (asyncio WebSocket server) with a Debian package built by
dh-virtualenv; repository-maintenance feature plus one re-implementation story.

**Performance Goals**: none new. One bound is kept from the release: the save-time re-measurement stops at a
fixed deadline (`REFRESH_DEADLINE_S = 20` seconds, the released value at `69d749e`) so a save never waits on a large file.

**Constraints**: constitution I–V (below); no second script reader; stored media values written through
setters; the report never gates a save; no `XmlReaderWriter`/`CuemsParser` in `src/`; GPG-signed commits;
no push, no tag.

**Scale/Scope**: 43 release-line commits, 12 conflicting files (38 hunks, 28 in 5 source files), about 700
lines of re-implemented source and 116 ported tests (US3), 25 existing test modules plus 4 absorbed and the new ones re-laid, 313 lint findings fixed.

## Constitution Check

*GATE: passes before Phase 0 and again after Phase 1.* (Constitution `1.0.0`; its Governance requires each
plan to name wire deltas, user-data write paths and `cuemsutils` imports.)

| Principle | Check | Result |
|---|---|---|
| I. Wire is a contract | **Wire deltas: none.** `media_check_report` is the *released* frame (0.1.0rc1-4); this feature restores it byte-for-byte (contract in [contracts/media-check-report.md](contracts/media-check-report.md)), so there is no old/new form. No existing frame changes. Payload version stays 1. Documentation-only correction: the protocol reference line for `project_status` says `none|running`; the engine has sent three states since rc6-4, and the reference is updated (no code delta). The released frame's consumer is `cuems-frontend` `origin/dev` `media-check.service.ts`; its reconciliation follows this feature. A test pins the exact key set and context values and fails against the pre-change behaviour (the frame is absent). **Verification is by golden payloads captured from the released producer at `69d749e`**, committed before any US3 source edit (`tests/data/golden/media_check_report_{open,ready,save}.json`), not by inspection. | PASS |
| II. Sessions isolated | Audiences declared: `context: "open"` → the requester only; `"ready"` and `"save"` → every session on the project (`send_to_project_sessions`, mutated on the event loop). Blocking work (DB, probe, hashing-free save path) runs in the server executor; the index rebuild is an asyncio subprocess, so no executor worker is held. In-flight de-duplication is keyed by project and lives outside the 002 `GateState`. | PASS |
| III. User data recovery | Write paths: (a) the check corrects **library rows** (derived values, re-measurable; the file is the source); (b) the script is **never rewritten at load**; a save keeps 002's backup-before-overwrite and gate; (c) media upload/delete/restore name handling keeps the released rollback of its own moves; (d) cleanup deletions are recoverable from git history. Atomic script writing is the library's (`CuemsScript.save`, verified at `4b336cd`), which closes the constitution's "atomic save unverified" ratification note. Tests run against a temporary library and assert the recovery path: a failed probe or a file still being copied leaves the row unchanged (`copy_in_progress`), the repair tool's dry run writes nothing and `--apply` backs up first. | PASS |
| IV. Tests gate risky paths | Gate 1: import smoke stays, plus a test that each media module imports alone (cycle). Gate 2: the frame test above. Gate 3: tests for row correction, rollback of media moves, and "nothing written before a refused save". Gate 4: `_engine_running` mapping and object-versus-dict walkers are hunted (research R9). Gate 5: each adaptation starts from a red test (TDD). The set of test files does not shrink without a recorded reason (disposition table in evidence). | PASS |
| V. Public surface | Imports **removed**: none present today; bookworm's `XmlReaderWriter`, `CuemsParser`, `xml.etree` script reading are *not* brought in. Imports **added**: none outside `cuemsutils`' public surface (`CuemsScript.load_with_report`, `CueList`, `AudioCue`, `VideoCue`, `CTimecode`). A grep test (`XmlReaderWriter|CuemsParser|CUE_TYPES|_clean_dangling`) keeps it so. The library is not patched. The range stays bounded `>=0.1.1,<0.1.2`. | PASS |

Operational constraints: nothing here edits topology; the restart note for `network_map.xml` is untouched.
The release follows the ecosystem order (the maintainer re-cuts the tag).

## Project Structure

### Documentation (this feature)

```text
specs/003-release-line-reconciliation/
├── plan.md
├── research.md          # decisions R1–R14
├── data-model.md        # inventory row, resolution record, manifest, comparison, report
├── quickstart.md        # validation scenarios
├── contracts/
│   ├── media-check-report.md   # the released frame, restored
│   ├── changelog-completeness.md
│   └── ci-workflow.md          # ci.yml inputs, jobs, gating
├── checklists/requirements.md
├── evidence/            # filled while implementing (environment, arms, disposition, builds, CI run)
├── upstream-reports/    # cuems-utils, cuems-frontend, cuems-engine
└── tasks.md             # /speckit-tasks
```

### Source code (repository root): current → target

```text
src/cuemseditor/
├── CuemsDBMedia.py            # + _free_filename, delete/restore collision handling (row 5)
├── CuemsDBProject.py          # + validate_media_cues_in_contents (row 4); duplicate() fill (6.2 f);
│                              #   media_staleness stays the one comparison
├── CuemsMediaRefresh.py       # NEW (re-implemented): open/ready checks, re-probe, index rebuild, report
├── media_values.py            # NEW leaf: _md5, _positive_int, _valid (breaks the import cycle)
├── CuemsWsUser.py             # + _error_text, _engine_running (4 cases), report hooks
├── CuemsWsServer.py           # + send_to_project_sessions
├── repair_durations.py        # + stored-value re-measurement as NEEDS_SAVE (still no script write)
└── db.py                      # DELETED (cleanup)

tests/                         # target layout (cleanup phase, last)
├── conftest.py                # markers from the directory; collect_ignore until US3 ports
├── support/                   # helpers, LibraryCtx, paths.py (DATA_DIR)
├── data/                      # every non-test data file: fixtures (was tests/fixtures), ws-command-responses.txt, released-builds.txt
│   └── golden/                # media_check_report_*.json captured at 69d749e (T022a)
├── unit/  integration/  contract/  packaging/
dev/scripts/                   # manual-ui (was tests/index.html + tests/static), README
docs/deploy/                   # apache-conf moved here
.github/workflows/ci.yml       # NEW (lint, unit, integration, coverage, summary)
pyproject.toml                 # + [tool.ruff], dev extras, pytest markers
```

**Structure Decision**: single Python package; no layout change to `src/` beyond the two new modules and one
deletion. `tests/ws-command-responses.txt` **moves to `tests/data/`**, with every other non-test data file (research R6).

## Implementation phases (the seed for tasks.md)

Order follows the pre-spec §11, adjusted for the clarifications (lint last, `stop_project` marker dropped by a
compatibility task, all four media-check parts).

| Phase | Content | Stories |
|---|---|---|
| 0 | Fetch and re-measure; create nothing new (branch exists); baseline arm A in the pinned environment; record environment | US1 |
| 1 | The merge commit: §5 resolutions, §5.2 deletions, `collect_ignore` for the two deferred test files; suite equals arm A | US1 |
| 2 | Independent fixes: save gate + `_error_text` + 013 fixtures; media-name collisions; `media_values.py` leaf and import-cycle tests | US2 |
| 3 | `stop_project` save-path tests (strict xfail) | US5 |
| 4 | Media check re-implementation (red then green, test file by test file): engine-state mapping → one comparison and the projection → `open` → `ready` (re-probe, index rebuild) → `save` re-probe → duplicate fill → repair tool re-measurement; protocol reference | US3 |
| 5 | Packaging and changelogs: `debian/changelog`, `CHANGELOG.md`, manifest and completeness test, `debian/control`/`rules`, bookworm build, verdicts | US4 |
| 6 | Docs (CLAUDE.md notes, protocol reference), upstream reports, `stop_project` compatibility task then marker removal (if the candidate tag is re-cut) | US5 |
| 7 | Re-fetch; merge any new release-line commits; three interleaved suite runs | US1 |
| 8 | Cleanup: deletes and moves, tests re-layout with directory markers, docs rewrites (pure moves; pass set unchanged after each commit) | US6 |
| 9 | Polish: ruff configuration and **all** findings fixed, as lint-only commits; coverage gate set from a fresh baseline | US6 |
| 10 | `ci.yml`; hand-off request to the maintainer to land it on `main`; dispatched green run recorded (blocked until then) | US6 |
| 11 | Tag-message rewrite; delete the pre-spec after traceability check | US1/US5 |

## Complexity Tracking

| Item | Why it is needed | Simpler alternative rejected |
|---|---|---|
| Merge commit deletes clean-merged code and ignores two test files temporarily | Measured: the mechanical hybrid does not import and fails 86 tests; deletion keeps the merge commit green and TDD intact | Fix forward on a red tree: breaks "red tests first" and hides which failures are real |
| A new leaf module `media_values.py` | The two media modules import each other (measured circular import) | Lazy imports inside functions: hides the cycle |
| Re-implementing instead of merging the media check | The released code uses a second script reader and retired surface (002 M10, constitution V) | Taking the released code wholesale |
| Dev-only additions (`pytest-xdist`, `ruff`) | CI parallel unit job and the chosen linter | Serial unit job, no lint (rejected by the clarification) |
| Coverage gate threshold set from a measurement (57 % today), not from CONTRIBUTORS' "80 %" | An unmeasured threshold would be red or meaningless | Invented 80 % |
