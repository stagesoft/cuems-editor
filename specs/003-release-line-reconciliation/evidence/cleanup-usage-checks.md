# Cleanup: usage checks and verdicts (T051)

A live reference is a path-qualified hit by `git grep -F` outside `specs/` (frozen history), measured 2026-10-23 on the feature
branch after the merge and US3.

| Path | Live references | Verdict |
|---|---|---|
| `src/cuemseditor/db.py` | `tests/test_import_smoke.py` only, to say nothing imports it ("dev scratch script with import-time side effects": at import it creates `./project-manager.db` and reads two hardcoded project UUIDs) | **delete**, and its `NOT_IMPORTED` entry |
| `.packaging-summary.txt` | none | **delete** |
| `BUILD-PACKAGE.md` | the other packaging documents only. Stale: names `cuems-ws-server` (not a script), `0.1.0-1`, `/home/ion/…` | **delete**; the build steps that are true (prerequisites, the bookworm-chroot build) live in CLAUDE.md and are added to `CONTRIBUTORS.md` |
| `DEBIAN-PACKAGING.md`, `MIGRATION-SUMMARY.md`, `PACKAGING-TEMPLATE.md`, `QUICK-REFERENCE.md`, `STRUCTURE.md`, `USAGE.md` | each other only | **delete** |
| `MANIFEST.in` | the packaging documents only; names a `setup.py` and a `static/` that do not exist; the build backend is hatchling, which ignores it | **delete** |
| `planning/documentation-prompt.md` | none | **delete** (a generic prompt for any repository of the family, outside `specs/`) |
| `apache-conf/000-default-le-ssl.conf` | `tests/README.md` (and the deleted `STRUCTURE.md`) | **move** to `docs/deploy/`; fix the reference |
| `tests/index.html`, `tests/static/` (90 files, 680 K, vendored crypto-js) | `tests/README.md` only: a manual upload page, not a test | **move** to `dev/scripts/manual-ui/` with a README |
| `src/cuemseditor/CuemsLibraryMaintenance.py` | `README.md`, `docs/api.md`, `docs/index.md`, `CuemsProjectManager.py` (docstring), `tests/test_media.py` (it builds the library tree in fixtures) | **keep, unchanged** (clarification, 2026-10-22). Not dead: the tests use it |
| `.github/workflows/pypi-publish.yml` | — | **keep**; its `environment.url` names `cuemsutils` (copy-paste): corrected to `cuemseditor` (T064) |
| `.github/workflows/gh-pages.yml` | — | **keep**; restricted to the release refs (T066) |
| `mkdocs.yml`, `docs/` | `gh-pages.yml` | **keep** |
| `.claude/skills/`, `.specify/` | SDD tooling | **keep** |

Checked and absent: no tracked venv, `__pycache__`, `.pyc`; no `poetry.lock`; no `dev/` directory; every `tests/test_*.py` is collected
(`testpaths = ["tests"]`).

Also found: the `.deb` omits the `cuems-editor-repair-durations` console script (`debian/rules` whitelist); pre-existing, recorded in
`bookworm-build.md`, not changed here.
