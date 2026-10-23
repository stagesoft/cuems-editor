# CI, validated locally (T067) — 2026-10-23

`.github/workflows/ci.yml` and `gh-pages.yml`:

- `actionlint 1.7.12` (via `actionlint-py`): 0 errors on both files (shellcheck was not installed, so the shell snippets were
  not shell-linted); `yaml.safe_load` parses `ci.yml` into the five jobs `lint`, `unit`, `integration`, `coverage`,
  `gate-summary` and the three triggers.
- A dry run of the jobs in the **CI layout**: `git clone` of this branch and of cuems-utils at `xml-refactor-merge-candidate`
  (`4b336cd`) side by side in a scratch workspace, a fresh Python 3.11 venv, `pip install ./cuems-utils` then
  `pip install -e "./cuems-editor[dev]"` (the editor's `cuemsutils>=0.1.1,<0.1.2` is satisfied by the checkout, nothing is
  taken from PyPI):

| Job's command | Result |
|---|---|
| `ruff check .` | All checks passed |
| `pytest tests/unit tests/contract -n auto --cov=cuemseditor` | 456 passed, 6 skipped, 5 xfailed |
| `pytest tests/integration --cov=cuemseditor` | 7 passed |
| `coverage combine` + `report --fail-under=70 --include='src/cuemseditor/*'` | TOTAL 3172 statements, **72 %** (unit 71 %, integration 24 %) |
| the `gate-summary` script, on those junit files | prints the editor SHA, the library ref and commit, 474 tests / 0 failed / 6 skipped / 5 expected failures, and the five strict xfails |

- Coverage floor: **70**, the measured combined 72 % minus two points (it was 57 % before the media-check tests of 003; it
  moves with the code, so ratchet it when it rises). CONTRIBUTORS' former "80 %" was never measured.
- Artifact layout: `upload-artifact@v4` roots a multi-path upload at the least common ancestor, so the files land at the top of
  each artifact; the `coverage` and `gate-summary` jobs read `artifacts/<job>/.coverage.*` and `artifacts/<job>/junit-*.xml`.
- Not exercised until it runs on GitHub: the hosted runners, `actions/checkout` of `stagesoft/cuems-utils` (a public repository),
  the artifact hand-off. FR-038 (a green dispatched run) is therefore **still open**; see `ci-gate.md`.
