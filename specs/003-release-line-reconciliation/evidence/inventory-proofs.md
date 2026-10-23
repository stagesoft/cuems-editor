# Inventory proofs (T045) — pre-spec §4, one proof per row

Environment: `evidence/environment.md`; suite on the head: see `suite-final-runs.txt` (T050). Test ids are in `tests/`.

| # | Item | Method | Proof |
|---|---|---|---|
| 1 | pixel size, file size, MD5 stored at upload and written on every save (869fat84r D18) | M + ported by 002 | `test_media_dimensions.py::TestUpload`, `TestSavePaths` (update, new, duplicate), `test_media_values.py` (the six FR-042 tests), `test_media_migration.py` |
| 2 | media values corrected / relink cleanup, export and relink for files deleted for good (D20) | M (clean hunks) + decision | `test_media_refresh.py::TestReupload` (relink only; a trashed project is skipped; export skips a dangling row; one failing project does not fail the upload) |
| 3 | check and report at load, never rewrite (D20 rev 2): `CuemsMediaRefresh`, `media_check_report`, save-time re-measurement, index rebuild, repair-tool re-measurement | **I** (D1) | `test_media_refresh.py` (71 ported), `test_media_report.py` (golden frames from the released producer at `69d749e`), `test_engine_state.py`, `test_media_dimensions.py::TestRepairTool` |
| 4 | save gate for media cues (869fej07m) | M + A | `test_validate_media_cues.py` (20: the current wire, the legacy wrappers, nothing written before a refusal, `new()`, the library's own error) |
| 5 | media name collisions (trash/stray files) | M | `test_media.py` (5 new tests) |
| 6 | no `CACHEDIR.TAG` | M + R | `debian/rules`; `evidence/bookworm-build.md` (`dpkg -c … | grep CACHEDIR`) |
| 7 | node adoption over the WebSocket | none (in this line) | `test_nodelist_actions.py`, `test_node_set.py` |
| 8 | Dec 2025 – Mar 2026 packaging, `72f952a` | M (ancestry) | content already present (`0834e99`); `HEAD..origin/debian/bookworm` = 0 (`evidence/ancestry.md`) |
| 9 | nine root-level packaging documents | M then delete | removed in the cleanup (T053) |
| 10 | released changelog entries `0.1.0rc1-4`…`-7` | M + R | `test_changelog_complete.py` (byte-identical to the tags) |
| 11 | `CHANGELOG.md` `## Unreleased` (869fej07m) | M + R | folded into the `0.1.0rc1-5` entry; `test_changelog_complete.py` |
| 12 | `cuems-utils (>= 0.1.0rc15)` floor | R → ours | `evidence/relation-verdicts.txt` (121 verdicts, 0 FAIL) |

Strays: `evidence/stray-sweep.md`.
