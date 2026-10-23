<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract: `.github/workflows/ci.yml`

The file name is fixed: `workflow_dispatch` runs only workflows present on the default branch (`main`), and
`main` has no `.github/`. The maintainer lands this one file on `main`; this feature authors it on its branch.

## Triggers

- `workflow_dispatch` with input `cuemsutils_ref` (string, default `xml-refactor-merge-candidate`, a tag or SHA
  of `stagesoft/cuems-utils`);
- `push` and `pull_request` on `feat/xml-refactor` and `003-release-line-reconciliation` (and `main` once the
  file lands there).

## Jobs

| Job | Needs | Runs |
|---|---|---|
| `lint` | — | `ruff check .` (whole tree, config in `pyproject.toml`) |
| `unit` | lint | `pytest tests/unit tests/contract -n auto --cov`; no network at test time; uploads `.coverage.unit` |
| `integration` | lint | `pytest tests/integration --cov`; in parallel with `unit`; uploads `.coverage.integration` |
| `coverage` | unit, integration | `coverage combine`, `report --fail-under=<measured>` (55 initially) |
| `gate-summary` | all | writes the job summary: editor SHA, `cuemsutils_ref` and its resolved commit, `cuemsutils.__version__`, pass / xfail counts, the strict-xfail list |

## Library and sibling inputs

- `pip install "cuemsutils @ git+https://github.com/stagesoft/cuems-utils@${cuemsutils_ref}"` (rule 5: nothing
  waits for PyPI). The resolved commit comes from `git ls-remote`.
- cuems-utils is also checked out at `<ref>` beside the repository for the two tests that read
  `../cuems-utils/tests/data/corpus`; the `../cuems-nodeconf` test skips by design.

## Gating

- The run is the pre-publication gate; it is manual. It gates `pypi-publish.yml` and the `.deb` upload
  (maintainer acts).
- Dispatch on a ref other than a release ref must not deploy docs: `gh-pages.yml` is restricted to the release
  refs `main`, `debian/bookworm` and `rc1` (pushes and `workflow_dispatch` from those only; `master` and
  `feature/gh-pages` are dropped).
- Strict xfails (`stop_project` until the re-cut, UR-1/UR-6/UR-7 while open) make the run green and honest;
  re-dispatching after the re-cut turns a stale marker XPASS-strict (red), which is the signal to drop it.
- The `.deb` bookworm-chroot build is not a hosted-runner job; it is recorded locally in `evidence/`.

## Evidence

`evidence/ci-gate.md`: run URL, editor head SHA, `cuemsutils_ref` and commit, summary, strict-xfail list.
