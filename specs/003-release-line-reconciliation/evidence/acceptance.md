# Acceptance sweep (T071) — 2026-10-23

Head of the feature branch when this was written: `1d2e307` (the final commits only add this file and delete the pre-spec).

| SC | Criterion | Result | Proof |
|---|---|---|---|
| SC-001 | 0 release-line commits missing | **met** | `HEAD..origin/debian/bookworm` = 0, `..origin/rc1` = 0 after a fresh fetch (bookworm `69d749e`, unmoved since the start); `ancestry.md` |
| SC-002 | 0 failures that `a2431f0` lacks; baseline intact; every absorbed test has a disposition; 3 identical runs | **met** | `suite-after-cleanup.txt` (463 passed vs 271 on arm A, A ⊂ B), `test-disposition.md`; in the real tree one test fails in BOTH arms because a sibling checkout is present (environment.md) |
| SC-003 | 100 % of `0.1.0rc1-1 … -7` in both changelogs; the check fails when one is removed | **met** | `tests/contract/test_changelog_complete.py` (it was red before T040/T041), manifest `tests/data/released-builds.txt` |
| SC-004 | 121 verdicts, 0 FAIL; builds in a bookworm chroot | **met** | `relation-verdicts.txt`, `bookworm-build.md` (Version `0.1.1-1`, `home = /usr/bin`, no CACHEDIR.TAG) |
| SC-005 | a malformed media cue is refused in one step with 0 writes | **met** | `tests/unit/test_validate_media_cues.py` (20): snapshots of DB and XML unchanged after a refusal; the current wire |
| SC-006 | stale values reported on open and load with the same findings as the load report; never blocks a save | **met** | `tests/unit/test_media_report.py` (golden frames; one comparison; the gate untouched), the 71 ported `test_media_refresh.py` cases |
| SC-007 | 0 uses of the retired surface; public-surface and import tests pass | **met** | `tests/contract/test_retired_surface.py`, `test_public_surface.py`, `test_import_smoke.py` |
| SC-008 | 0 references to moved paths; 0 tests outside the marked directories; pass set unchanged | **met** | `git grep` of the old paths outside `specs/` is empty; `tests/contract/test_layout.py`; `suite-after-cleanup.txt`; ruff clean (E501 not enforced: `research.md` R11) |
| SC-009 | one dispatched CI run green and recorded | **OPEN — blocked on the maintainer** | `ci.yml` is written and validated locally in the CI layout (`ci-local-validation.md`); `main` has no `.github/`, so the maintainer must land the file before `gh workflow run` can start it; the request is in `ci-gate.md` |
| SC-010 | three upstream reports and the tag message exist; no sibling file and no tag changed | **met** | `upstream-reports/` (utils, frontend, engine); `../.xml-refactor-tag-messages/cuems-editor.txt` rewritten (a text file outside the repository); no tag created or moved, nothing pushed, no sibling file edited |

## Decisions the maintainer should ratify

- **E501 is not enforced** by the lint (80 existing lines of 120–400 characters). Everything else was fixed to 0. (`research.md` R11)
- **A behaviour of `0.1.0rc1-4` did not survive**: the in-place write fallback when the project directory is not writable (the library raises). Reported to cuems-utils.
- **Pre-existing, not changed**: the `.deb` omits the `cuems-editor-repair-durations` console script.
- **Trashed projects** are no longer relinked on a re-upload (the refactor's `include_trash=True` raised `FileNotFoundError`; the released behaviour is back).
- The merge commit is not entirely green: it left three of the absorbed tests red until their fixtures and gate were adapted (`conflict-resolutions.md`).

## Pre-spec traceability (T072)

The temporary pre-spec `specs/planning/release-line-reconciliation-0.1.1.md` is deleted by the next commit; its last commit is `bcc49e5` (`git show bcc49e5ec | Carried by |
|---|---|
| §0 decisions D1–D5 | spec.md Clarifications; plan.md; research R2–R4 |
| §1 scope | spec.md (Purpose, Assumptions, FR-001…FR-040) |
| §2 lines measured | `evidence/lines-measured.md`, `ancestry.md`, `stray-sweep.md` |
| §3 strategy and methods | plan.md (Summary, Complexity Tracking, phases); `conflict-resolutions.md` |
| §4 inventory, §4.1 strays | `evidence/inventory-proofs.md`, `stray-sweep.md` |
| §5 conflict rules | `evidence/conflict-resolutions.md` |
| §6 seams (6.1 measured, 6.2 reading) | `evidence/arm-A.txt`, `arm-B-merge-commit.txt`, `test-disposition.md`; research R5, R9; tests named in `inventory-proofs.md` |
| §7 packaging, versions, changelogs | FR-025…FR-030; `bookworm-build.md`, `relation-verdicts.txt`; `tests/contract/test_changelog_complete.py`; contracts/changelog-completeness.md |
| §8 sibling relations | `upstream-reports/`; `stop-project-compat.md`; `unknown-frame-check.md` |
| §9 docs | CLAUDE.md field notes; `tests/README.md`, `CONTRIBUTORS.md`; constitution 1.0.1 |
| §10 acceptance criteria | this file (SC-001…SC-010) |
| §11 execution order | tasks.md |
| §12 clarify questions | spec.md Clarifications; research.md R1–R14 |
| §13 how it was measured | `evidence/environment.md`, `lines-measured.md`, `suite-final-runs.txt` |
| §14 cleanup phase and CI gate | `cleanup-usage-checks.md`, `lint-baseline.txt`, `ci-local-validation.md`, `ci-gate.md`, contracts/ci-workflow.md |
| Appendix A prompt | spec.md (Input) |
