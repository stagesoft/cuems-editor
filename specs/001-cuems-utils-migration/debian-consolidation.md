<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# debian/ consolidation — what to apply to `debian/bookworm` (T045, FR-038a)

`debian/` was brought onto `feat/xml-refactor` from `origin/debian/bookworm` @ `72f952a`
(`debian: release 0.1.0rc1-3 — fix the removed cuemsutils.daemon import`). This file lists every
`debian/` change made on this branch since, by commit and file. Applying it to `debian/bookworm` is the
maintainer's action. This feature did not touch that branch.

## On `debian/bookworm` but not in `72f952a`

**None.** `git rev-parse origin/debian/bookworm` was `72f952a6a83227761eed84c847fb0c8e766f38ea` when
`debian/` was imported (2026-10-02, after `git fetch`).

## Changes on `feat/xml-refactor`

| Commit | File | Change |
|---|---|---|
| `9067b1a` | `debian/*` (7 files) | imported verbatim from `72f952a`; `git diff 72f952a 9067b1a -- debian/` is empty. Nothing to apply |
| `9067b1a` | `.gitignore` (not under `debian/`) | stop ignoring `debian/` wholesale; ignore only build output. Only needed if `debian/bookworm` ever tracks the source tree's `.gitignore` |
| `6934890` | `debian/control` | `Depends`: `cuems-utils (>= 0.1.0rc10)` → `cuems-utils (>= 0.1.0rc16), cuems-utils (<< 0.1.1~)` |
| `6934890` | `debian/changelog` | new entry `0.1.0rc1-4 UNRELEASED` above `0.1.0rc1-3` |

Apply with:

```bash
git checkout debian/bookworm
git diff 72f952a feat/xml-refactor -- debian/control debian/changelog | git apply
```

Before marking the entry released, set its distribution from `UNRELEASED` to `bookworm` and its date to
the release date.

## Deviation from the task text, recorded

The tasks and `contracts/package-relations.md` name the dependency `python3-cuemsutils`. No such binary
package exists: cuems-utils builds `cuems-utils` (`../cuems-utils/debian/control`), and the pair in
`../cuems-nodeconf/debian/control`, which the contract cites as the model, is
`cuems-utils (>= 0.1.0rc16), cuems-utils (<< 0.1.1~)`. A `Depends` on `python3-cuemsutils` would make
`cuems-editor` uninstallable, so `6934890` uses `cuems-utils`.

## Build

`tests/packaging/bookworm-build.sh` builds the package in an unprivileged bookworm chroot. The result is
in `evidence/bookworm-build.txt`. `debian/rules` is unchanged.
