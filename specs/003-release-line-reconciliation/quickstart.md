<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Quickstart: validating the reconciliation

Prerequisites: Debian 13 host with pyenv 3.11.9; sibling checkouts beside this repository; for the package
build `mmdebstrap` with subuid/subgid ranges and network. Replace paths with your scratch directory.

## 1. Baseline (arm A)

```bash
mkdir -p $S/utils-tag && git -C ../cuems-utils archive 4b336cd | tar -x -C $S/utils-tag
python3.11 -m venv $S/venv && $S/venv/bin/pip install $S/utils-tag pytest pytest-cov pytest-xdist peewee websockets ruff
ln -sfn $S/utils-tag $S/cuems-utils            # the corpus test reads ../cuems-utils
git worktree add --detach $S/wtA a2431f0 && cd $S/wtA
PYTHONPATH=src $S/venv/bin/python -m pytest -q -p no:cacheprovider --cov=cuemseditor
```
Expect: 271 passed, 3 skipped, coverage 57 %.

## 2. Ancestry (US1)

```bash
git fetch --all --tags
git rev-list --count HEAD..origin/debian/bookworm HEAD..origin/rc1   # both 0 at hand-off
```

## 3. Suite on the feature head

Run the baseline command on the head. Expect no failure that arm A lacks, the released tests ported or
retired per the disposition table, and the strict xfails exactly as in the plan. Three interleaved runs of
arms A and B give identical sets.

## 4. Save gate and media names (US2)

`pytest tests/unit/test_validate_media_cues.py tests/unit/test_media.py` : a refused save writes nothing; a trashed file
passes; collisions get versioned names; rollback restores moves.

## 5. Media check (US3)

`pytest tests/unit -k "media_refresh or media_check"` : the ported acceptance set. Manual: open a project whose
media file was replaced under the same name; a `media_check_report` with context `open` arrives after the
`project` frame; `project_ready` with the engine `loaded` runs the full check; the project file is unchanged on
disk until a save.

## 6. Changelogs and packaging (US4)

```bash
pytest tests/contract/test_changelog_complete.py
sh ../cuems-utils/specs/016-coordinated-minor-bump/tools/verdicts.sh   # 121 verdicts, 0 FAIL
tests/packaging/bookworm-build.sh                                       # Version 0.1.1-1, home = /usr/bin
dpkg -c cuems-editor_0.1.1-1_all.deb | grep CACHEDIR                   # record the result
```

## 7. `stop_project` (US5)

`pytest tests/unit -k stop_project` : strict xfail against the candidate tag; run again with the cuems-utils
head installed to see XPASS before removing the marker.

## 8. Cleanup and lint (US6)

```bash
ruff check .                                                            # 0 findings after the polish phase
git grep -nE "tests/ws-command-responses|tests/fixtures|tests/static|apache-conf|planning/documentation-prompt|cuemseditor\.db\b" -- . ':!specs'
pytest tests/unit tests/contract -n auto                                # no network
```

## 9. CI gate

After the maintainer lands `ci.yml` on `main`:
`gh workflow run ci.yml --ref 003-release-line-reconciliation -f cuemsutils_ref=xml-refactor-merge-candidate`,
then record the run in `evidence/ci-gate.md`.
