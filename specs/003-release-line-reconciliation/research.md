<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Research: Release-line reconciliation for cuems-editor 0.1.1-1

Resolves the open items of the pre-spec §12 and the technical unknowns of the plan. Measurements dated
2026-10-22/23 on `a2431f0`, Debian 13 host, pyenv 3.11.9, `cuemsutils 0.1.1` exported from cuems-utils
`4b336cd` (and `387598e` where stated). Figures labelled *indicative* depend on host defaults.

## R1 — `CHANGELOG.md` layout and the completeness check (§12 Q1)

- **Decision**: keep one `## 0.1.0rc1` section and add one sub-entry per Debian build `-1…-7`, each introduced
  by `<!-- source: debian/bookworm 0.1.0rc1-N (<sha>) -->` (the engine's convention), under `Added` /
  `Changed` / `Fixed`. Fold bookworm's `## Unreleased` (869fej07m) into `-5`. `## 0.1.1` stays on top. The
  completeness check is a permanent contract test over a committed manifest.
- **Rationale**: there is one header per upstream version and `-N` revisions do not get headers; the version
  test reads the top header. A permanent test stops a future release-line merge dropping a build silently.
- **Alternatives**: one-off script (forgotten); a header per build (breaks the version test).

## R2 — Merge commit shape (§12 Q2)

- **Decision**: the merge commit takes the refactor's side for all 38 hunks (with the §5.1 exceptions), deletes
  the §5.2 clean-merged dict-era code, and lists the two deferred test files in `collect_ignore`.
- **Rationale**: measured — the per-hunk "ours" hybrid failed to import (circular), and with that stubbed it
  failed 86 of 411 tests. The merge commit must be green and a later story un-ignores each test file.
- **Alternatives**: carry the hybrid and fix forward (a red merge commit; unclear which failures are real).

## R3 — One comparison, two projections (§12 Q3)

- **Decision**: `media_check_report` is computed from the same comparison that feeds `media_repairs`
  (`media_staleness`, which reads library rows and compares against the object-loaded script). The report
  groups `media_repairs` by file name (counting cues, dropping cue ids) and adds the file-level facts the
  repair list lacks (`unverified`, `complete`, `reason`).
- **Rationale**: 002 M9/Q6/Q8: findings enter `media_repairs`; no second comparison; `GateState` is the only
  per-project report state. The field names already coincide (`duration`, `pixel_size`, `file_size`,
  `file_md5`; `stored`, `current`).
- **Alternatives**: keep the released `plan_media_refresh` (a second script reader and second comparison).

## R4 — Scope of US3 (clarified: all four parts)

- **Decision**: deliver (1) the check at `open` (read-only), (2) the full check before load (`ready`: re-probe
  of changed files and row correction), (3) the save-time re-probe within `REFRESH_DEADLINE_S` (never hashing
  on the save path), (4) the video-index rebuild of a changed video (asyncio subprocess, a busy indexer never
  waited for), plus the repair tool's stored-value re-measurement as `NEEDS_SAVE`.
- **Rationale**: the frontend reconciliation follows this feature, so the editor half must be complete.
- **Alternatives**: read-only report (rejected by the clarification).

## R4a — Released constants and the copy guard

- **Measured at `69d749e`**: `REFRESH_DEADLINE_S = 20` (`CuemsDBProject.py:394`). A file whose `(st_size, st_mtime_ns)` differs before and after its probe is recorded `in_copy`, left for the next load, and its row is not written; `_incomplete_reason` maps `failed` → `probe_failed`, `in_copy` → `copy_in_progress`, `not_reached` → `deadline`, in that priority.
- **Decision**: keep both, unchanged, in the re-implementation; pin them in tests.

## R5 — Engine state mapping

- **Decision**: a four-case result — `running` (defer re-probing, reason `engine_running`), `loaded` and `none`
  (proceed), no answer (reason `engine_silent`). Replaces the released `{'running': True, 'none': False}.get`,
  which maps `loaded` to "no answer".
- **Evidence**: the engine's `project_status` is three-state since rc6-4 (cuems-engine 009 report W2); the
  released mapping skips every check while a project is loaded but stopped. Red test over all four cases.

## R6 — Non-test data files, `ws-command-responses.txt` included (§12 cleanup)

- **Decision (maintainer, 2026-10-23)**: `ws-command-responses.txt` and any similar file end up inside
  `tests/data/`. That covers `tests/fixtures/*` and the new `released-builds.txt`. The one path constant
  `tests/support/paths.py:DATA_DIR` is the only place the location is written.
- **Consequence**: the path is cited by the constitution (twice), CLAUDE.md, a comment in
  `CuemsWsServer.py` and four tests (`test_protocol_doc`, `test_payload_version`, `test_initial_template`, …).
  The move rewrites each citation in the same commit; the constitution change is a PATCH amendment through
  `/speckit-constitution`. The Principle I requirement ("update `tests/ws-command-responses.txt`") keeps its
  meaning at the new path. The cleanup-phase grep guards the old path.
- **Not data**: `tests/packaging/bookworm-build.sh` (a packaging script, stays in `packaging/`);
  `tests/index.html` and `tests/static/` (a manual harness, moves to `dev/scripts/`).

## R7 — `CACHEDIR.TAG` (§12, pre-spec §7.3)

- **Decision**: keep the strip in `debian/rules` (comes with the merge) and *record* the result of
  `dpkg -c cuems-editor_0.1.1-1_all.deb | grep CACHEDIR` from a bookworm-chroot build
  (`tests/packaging/bookworm-build.sh`).
- **Rationale**: utils stopped shipping the file in `0.1.0rc16+1`, so the strip only matters against older
  utils, but it keeps every package agreeing that nobody ships it. Building is part of the evidence, not a
  hosted-runner job (needs user namespaces and `mmdebstrap`).

## R8 — `pypi-publish.yml` environment URL (§12 Q11)

- **Decision**: correct it to `https://pypi.org/project/cuemseditor/…` in the cleanup phase.
- **Rationale**: the URL names `cuemsutils` (a copy-paste); the PyPI name is `cuemseditor` (CLAUDE.md). One
  line, no publication.

## R9 — Silent-wrong callers (constitution IV gate 4)

- **Decision**: hunt and pin: (a) `_engine_running` mapping (R5); (b) `get_media` now raises `ValueError` for a
  media block without a file (utils 017) — the save gate runs first, and a test bypasses it; (c) walkers keyed
  on dict shape (`_walk_media_durations(dict)`) versus the object walk — the merged tree keeps the object walk
  and a grep test forbids the dict forms; (d) item assignment on stored media keys — the existing AST guard
  (`test_media_values`) stays; (e) `str(cue_id)` leaves through the same helper as `media_repairs`.

## R10 — `stop_project` (clarified: this feature drops the marker)

- **Decision**: add the save/reopen round-trip and leftover-target tests as `xfail(strict=True)` against the
  current candidate tag; a dedicated compatibility task runs the same tests against the library that will be
  re-cut (utils head `387598e` carries the value at `script.xsd:321`), then removes the marker if the tag has
  been re-cut by hand-off; otherwise the marker stays and the tag message lists it as owed.
- **Measured**: the candidate tag `4b336cd` has 0 `stop_project` matches in `script.xsd`; the head has it.

## R11 — Lint (clarified: whole tree, final polish)

- **Decision**: `ruff`, configured in `pyproject.toml`: `select = ["E","F","I","W"]`, `line-length = 120`.
- **Measured (isolated, indicative)**: 269 findings in `src/`, 44 in `tests/` (313 total; 67 auto-fixable). A
  wider selection (`UP`, `B`, `BLE`, `TRY`) gave 369 in `src/` alone. Narrow selection chosen so the polish
  phase is behaviour-free; fixes are lint-only commits. `black`/`flake8` are not adopted (black would reformat
  14 of 16 files).
- **Amended at implementation (2026-10-23)**: the rule set is `E4, E7, E9, F, I, W`; **E501 (line length) is not enforced.** Whole
  tree under that set: 474 findings at the start (113 unused imports, 79 names from star imports, 72 pytest fixture
  imports, 56 unsorted imports, …) fixed to 0. E501 had 80 findings in the existing code, lines of 120–400 characters
  (dict literals, logger calls, executor hops); with no formatter adopted, reflowing them would bury the reconciliation
  in noise. The maintainer may turn E501 on later; `E501` alone reports 80. Two rules are handled by idiom, not by
  rewriting: `F811` is ignored in test modules (a fixture imported by name and taken as an argument), and `E712` carries
  a `noqa` on the 11 peewee queries (`Field == False` builds SQL; `not Field` would not).
- **Alternatives**: lint touched files only (rejected by the clarification).

## R12 — Coverage gate

- **Decision**: combined coverage (unit + integration) with `--fail-under` set to **55**, from the measured
  baseline of **57 %** (2726 statements, 271 tests, 2026-10-23). Re-measure at the end of the polish phase and
  ratchet to the measured value minus 2 points.
- **Rationale**: CONTRIBUTORS' "80 %" was never measured and would turn the gate red. Weak modules today:
  `CuemsDBMedia` 36 %, `CuemsDBProject` 61 %, `CuemsWsUser` 61 %.

## R13 — Test classification

- **Decision**: all 25 existing modules are unit or contract (plus the 4 absorbed from the release line and the new ones); the sweep found no real socket, subprocess, JACK
  or `sleep`. `test_probe_duration` mocks `subprocess.run` (its docstring mentions one integration test: check
  at move time). Initial `contract/`: `test_public_surface`, `test_import_smoke`, `test_protocol_doc`,
  `test_payload_version`, `test_upstream_gates`, `test_schema_descriptor`, and the new completeness test.
  `integration/` starts empty or holds the US3 index-rebuild test if it needs a real subprocess. The CI
  `integration` job runs even when it holds one test, so the layout does not rot.
- **Rule** (written in `tests/README.md`): integration = binds or connects a real socket, starts a real
  subprocess or player, touches JACK/ALSA, or sleeps ≥ 0.5 s for correctness; otherwise unit.

## R14 — CI details (see contracts/ci-workflow.md)

- `workflow_dispatch` runs only workflows on the default branch; `main` is a 2021 snapshot with no `.github/`
  (`gh api …/contents/.github/workflows?ref=main` → 404). The maintainer lands `ci.yml` alone on `main`.
- `cuemsutils` cannot come from PyPI: install from `git+https://github.com/stagesoft/cuems-utils@<ref>`; the
  default ref is cuems-utils' `xml-refactor-merge-candidate`. The job logs the resolved commit and
  `cuemsutils.__version__`.
- `tests/test_config_round_trip.py` and `test_upstream_gates.py` read a sibling `../cuems-utils` checkout
  (corpus, `../cuems-nodeconf`). On a hosted runner the job checks out cuems-utils at `<ref>` beside the
  repository; the nodeconf test skips by design.
- No lock file, so no staleness question. `gh-pages.yml` currently deploys on pushes to `main`, `master`,
  `rc1`, `feature/gh-pages`; it is restricted so a dispatch on a non-release ref does not deploy.
- The `.deb` build stays a local recorded step.

## Open, deliberately left to implementation

- The exact byte-identity check of changelog entries against release tags runs only where tags are present
  (CI fetches tags); local runs without tags skip with a reason.
- The disposition of each of the 116 absorbed media tests (ported, retired with reason, passing as is) is
  produced while porting and lands in `evidence/`.
