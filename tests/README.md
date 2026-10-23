<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Tests

```bash
pip install -e ".[dev]"            # pytest, pytest-cov, pytest-xdist, ruff
pytest                             # everything
pytest tests/unit tests/contract -n auto      # what CI's unit job runs (no network)
pytest tests/integration           # what CI's integration job runs
```

`cuemsutils` must be the version the package bounds (`>=0.1.1,<0.1.2`). Two tests read a sibling checkout when there is
one (`../cuems-utils/tests/data/corpus/`, `../cuems-nodeconf`) and skip when there is not.

## Layout

The shape cuems-utils uses, so a contributor meets one layout across the ecosystem.

| Directory | What goes there |
|---|---|
| `unit/` | Pure logic. Every socket, JACK and subprocess is mocked. Safe under `pytest-xdist`. |
| `integration/` | A test that binds or connects a real socket, starts a real subprocess or player, touches JACK or ALSA, or sleeps 0.5 s or more for correctness. |
| `contract/` | Repository and packaging invariants: the public `cuemsutils` surface, every module importing, the protocol reference, payload version, changelog completeness, the layout itself. |
| `support/` | Shared helpers. `paths.py` is the one place the data path is written (`DATA_DIR`). |
| `data/` | Every non-test data file: the fixtures (`script_minimal*.xml`, `conf/`), the protocol reference `ws-command-responses.txt`, the golden `media_check_report` frames, the released-builds manifest. See `data/README.md`. |
| `packaging/` | `bookworm-build.sh`: builds the `.deb` in an unprivileged bookworm chroot. Not a hosted-CI job. |

**Marks come from the directory.** `conftest.py` adds `unit`, `integration` or `contract` to each test after the
directory it lives in, so a test cannot be mislabelled by forgetting a decorator. `--strict-markers` is on.
`contract/test_layout.py` fails on a test module at the root of `tests/`, in a directory that is not one of these,
or an empty `integration/`.

A unit test that needs something an integration test would use, mocks it. Cross-imports between test modules stay
inside one directory (`unit/` imports `unit/` and `support/`); anything shared by several directories belongs in
`support/`.

## Rules the tests enforce

- A wire change updates `data/ws-command-responses.txt` and is pinned by a test that fails against the old behaviour
  (constitution I). The `media_check_report` frame is compared with `data/golden/`, captured from the released editor.
- `src/` uses none of the retired surface (`contract/test_retired_surface.py`) and only the public `cuemsutils` surface
  (`contract/test_public_surface.py`).
- Every shipped Debian build is in `debian/changelog` and `CHANGELOG.md` (`contract/test_changelog_complete.py`, manifest
  `data/released-builds.txt`). Add a line when you release.
- Strict expected failures name their reason and the report that explains them; they turn red when the thing they wait
  for arrives (the `stop_project` and `get_media` markers wait for the cuems-utils re-cut).

## The manual upload page

Not a test: `dev/scripts/manual-ui/` (see its README).
