# Lines measured (T001)

Measured 2026-10-23 after `git fetch --all --tags`, on `003-release-line-reconciliation` (source tree identical to
`a2431f0`).

| Ref | Commit |
|---|---|
| `origin/debian/bookworm` | `69d749e` (0.1.0rc1-7) |
| `origin/rc1` | `fdba0bc` |
| merge-base | `886f649` |

- `git rev-list --count HEAD..origin/debian/bookworm` = **43**; `..origin/rc1` = **16**; `origin/debian/bookworm..origin/rc1` = **0**
  (rc1 is inside bookworm).
- `git merge-tree --write-tree --name-only HEAD origin/debian/bookworm`: 12 conflicted files (`.gitignore`,
  `CHANGELOG.md`, `debian/changelog`, `debian/control`, `debian/rules`, `pyproject.toml`, `CuemsDBMedia.py`,
  `CuemsDBProject.py`, `CuemsWsServer.py`, `CuemsWsUser.py`, `repair_durations.py`, `tests/ws-command-responses.txt`).
- `comm -13` recipe (headers in bookworm absent from HEAD): `0.1.0rc1-4`, `-5`, `-6`, `-7`.
- The release line did not move since the pre-spec measurement (2026-10-22); no pre-spec numbers change.
