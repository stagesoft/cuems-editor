<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract: changelog completeness (permanent test)

Test: `tests/contract/test_changelog_complete.py`. Manifest: `tests/data/released-builds.txt`.

## Invariants

1. Every version in the manifest is a `cuems-editor (<version>)` header in `debian/changelog`.
2. Every manifest version is named in `CHANGELOG.md` (a `<!-- source: … <version> … -->` marker or an inline
   revision).
3. The top of `debian/changelog` is `<pyproject version>-1`, and `CHANGELOG.md`'s top header is
   `## <pyproject version>`; `cuemseditor.__version__` equals the `pyproject` version.
4. The `0.1.1-1` entry does not contain "NOT YET RECONCILED".
5. `0.1.0rc1-5+nodeadopt2` is not a header (rig build); the exclusion list is explicit and each entry has a
   reason.
6. Where the tags `v0.1.0rc1-4 … -7` exist locally (CI fetches tags), each entry's text is byte-identical to
   the entry at its tag; without tags this check skips with a reason.

## Manual equivalent (review)

```bash
comm -13 <(git show HEAD:debian/changelog | grep -oE '^cuems-editor \([^)]+\)' | sort -u) \
         <(git show origin/debian/bookworm:debian/changelog | grep -oE '^cuems-editor \([^)]+\)' | sort -u)
# must print nothing
```
