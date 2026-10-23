# Conflict resolutions (T005) and the merge commit (T006–T008)

Merge commit `74ec5fa` (`git merge --no-ff origin/debian/bookworm`, resolved by hand, signed). 12 files, 38 hunks.

| File | Hunks | Resolution as made | Reason |
|---|---|---|---|
| `.gitignore` | 1 | ours, plus the 7 theirs-only `debian/` lines (`*.deb`, `*.deb.*`, `*.build`, `*.buildinfo`, `*.changes`, `tmp/`, `cuems-editor.*.debhelper`) | superset without duplicates |
| `CHANGELOG.md` | 1 | both (ours then theirs) | theirs is `## Unreleased` (869fej07m); T041 restructures |
| `debian/changelog` | 1 | ours | released entries `-4…-7` are absorbed verbatim in T040, not by a hunk choice |
| `debian/control` | 2 | hunk 1 (SPDX header) theirs; hunk 2 (relations) ours | rows 11–13 of the 016 matrix |
| `debian/rules` | 2 | theirs, both (SPDX header, `CACHEDIR.TAG` strip) | row 6; ours was empty in both |
| `pyproject.toml` | 1 | ours (`cuemsutils>=0.1.1,<0.1.2`) | row 14 |
| `CuemsDBMedia.py` | 4 | hunk 2 (`_free_filename`) theirs; 1, 3, 4 ours | row 5 is independent of the deferred half; `_md5` stays the 002 port |
| `CuemsDBProject.py` | 12 | all ours | the object walk replaced the dict walk; theirs re-introduces `_clean_dangling_targets`/`CUE_TYPES`, `CuemsParser`, a hand-rolled `XmlReaderWriter` write, `_save_resolvers` |
| `CuemsWsServer.py` | 1 | ours | `send_to_project_sessions` returns with US3 (T031) |
| `CuemsWsUser.py` | 4 | ours; hunk 3 both (as two methods) so `_error_text` is kept | US2 needs it (FR-008) |
| `repair_durations.py` | 7 | all ours; the clean-merged remainder (`_check_stored`, `--no-md5`, `hashlib`) reverted with `git checkout a2431f0 --` | tool writes no script; re-measurement returns in T036 |
| `tests/ws-command-responses.txt` | 2 | both | protocol reference carries both sets of frames |

## Deviations from the plan's table, found while resolving (recorded, not silently absorbed)

1. **`CuemsDBProject.new()`**: the clean-merged text called `self._fix_media_durations(data)` on the raw dict (ours' version
   takes a `CuemsScript`) and `self._media_exists`, which ours' hunk 9 dropped. Reverted to ours; the gate is re-wired in
   T013 behind a red test. Hence the merge commit does **not** wire the 869fej07m gate (the plan's "combine" for hunk 8 is
   T013).
2. **`update_projects_existed_media`**: the clean merge deleted the `project = Project.get(...)` line that
   `update_media_relations(project, …)` needs. Restored in place.
3. **`_NOT_COPIED`** (`export`/`duplicate` ignore patterns, `('*.pre-refresh-*', '.*.tmp')`) lived in the deleted refresh
   section; the clean-merged `export()` still uses it. Restored as a module constant with a comment.
4. **Trashed-project relink**: the released code skips relinking a project that is in the trash ("relinked when it is
   restored and saved", 869fat84r D20 Q2); the refactor loads with `include_trash=True` and relinks anyway. Not changed in
   the merge; decided by the ported relink tests in T025.

## Deleted in the same commit (pre-spec §5.2)

`src/cuemseditor/CuemsMediaRefresh.py`; in `CuemsDBProject.py` the refresh section (`REFRESH_DEADLINE_S` … `RefreshPlan`,
190 lines) and the `plan_media_refresh` … `media_report` methods (190 lines) and the `CuemsDBMedia` import block; in
`CuemsDBMedia.py` the probe/index block (`PROBE_*`, `MediaProbe`, `probe_media`, the index helpers, `run_video_indexer`);
in `CuemsWsUser.py` `_refresh_media`, `_send_media_report`, `_in_background`, `_report_on_open`, `_report_after_save`,
`_engine_running` and their calls. The text is reachable at `origin/debian/bookworm` (`69d749e`); US3 reads it from there.

## Result

`git rev-list --count HEAD..origin/debian/bookworm` = 0 and `..origin/rc1` = 0 (T009). Suite on the merge commit: see
`arm-B-merge-commit.txt`: 288 passed, 3 skipped, **3 failed**, all three in the absorbed `test_validate_media_cues.py`
(pre-013 fixture shape; the update gate unwired). They are the reds of T011/T013, not regressions: every arm-A test still
passes. The plan said "green merge commit"; this is the one honest exception, recorded here.
