# Test disposition (T010)

One row per test the release line adds (136). Dispositions: `passing-as-is` / `ported` / `retired` (a retired test names the test that already covers its assertion). Filled as the stories land.

| File | Tests | State |
|---|---|---|
| test_media_refresh.py | 71 | **ported (T025)**: harness moved to the 013 fixture (`lib` ← `library013`) and `CuemsScript.load_with_report`; 2 retired (below); 1 rewritten (`the_project_frame_goes_first_at_open` now drives 002's `open` and expects the load report between the two frames); the status-query test extended by `tests/test_engine_state.py` (loaded) |
| test_media_dimensions.py | 45 | **ported (T026)**: TestProbeDimensions/TestMigration/TestUpload passing-as-is (20); TestFill (13 cases) rebuilt on objects (`from_json` of the 013 wire, raw values in the payload); TestSavePaths on `library013`; TestRepairTool: Pass B (`--xml-only`, writes scripts) **retired** by 002 FR-027a, replaced by `test_apply_migrates_and_fills_the_db_but_writes_no_script` and `test_no_mode_writes_a_script` |
| test_validate_media_cues.py | 15 | **ported (T011/T013)**: shape tests moved to the current `Cue`+`class` wire (the released tests used `AudioCue`/`VideoCue` wrappers, which on the 013 wire would find no cue); update tests use the 013 fixture and drop the stale `probe_dimensions` patch; 1 kept as the legacy-wrapper test. Added 5: legacy wrappers ×2, a non-media class, `new()` refuses, library `ValueError` (strict xfail against the candidate tag, passes on utils 387598e) |
| test_media.py (new cases) | 5 | passing-as-is (T015): versioned name against a trashed file, delete keeps `unix_name`, restore refuses an untracked live file, restore moves back, delete rolls back sidecars |

## Findings from porting US2

- **Gate 4 (silent-wrong caller), measured.** The released gate walked `item['AudioCue']` / `item['VideoCue']`. On the 013
  wire a media cue is `{'Cue': {'class': 'audio'|'video'}}`, so the gate would accept every payload. 12 of 18 tests failed
  once the fixtures were moved to the current wire (commit `test(003): media-cue gate on the 013 wire (red)`).
- **The candidate tag `4b336cd` raises `KeyError('file_name')` from `CueList.get_media`.** rc16's `ValueError` guard
  (cuems-utils 017 §1) is in utils `387598e` only. `test_the_librarys_media_error_reaches_the_client_unprefixed` is a strict
  xfail against the tag and passes on the head; it flags the re-cut by turning XPASS.

## Retirements (T025, T026), each with the test that covers the assertion

| Retired test | Why | Covered by |
|---|---|---|
| `test_media_refresh::TestSaving::test_a_failed_write_leaves_the_old_file_and_no_temporary` | tested the editor's own atomic writer (`XmlReaderWriter`, temp file, `os.replace`); the script is written by the library's `CuemsScript.save` (FR-023) | the library's own save tests (utils `CuemsScript.save`: "answers atomically"); `test_retired_surface` forbids bringing the writer back |
| `test_media_refresh::TestSaving::test_an_unwritable_directory_falls_back_to_writing_in_place` | the in-place fallback does not exist in the library: it raises when it cannot create its temporary file. **A behaviour of rc1-4 that did not survive**, reported to cuems-utils | `upstream-reports/cuems-utils.md` (T046) |
| `test_media_dimensions::TestRepairTool::test_pass_b_writes_values_into_a_project_whose_durations_are_right` | Pass B writes scripts; the tool never does (002 FR-027a) | `test_no_mode_writes_a_script`, `test_apply_migrates_and_fills_the_db_but_writes_no_script` |
| `test_media_dimensions::TestFill::*` (dict form) | the walk takes the script's cues, not dict items | the same assertions, on objects, in the rebuilt class; plus 002's `test_media_values` |

## Findings from porting US3

- **Trashed-project relink.** The refactor loaded with `include_trash=True`, which reads `projects/<unix_name>/script.xml`; a
  trashed project lives in the trash, so the relink of a re-uploaded file **raised `FileNotFoundError`** (released test
  `test_a_reupload_only_relinks_and_trashed_projects_are_skipped` failed on the object API). Fixed to the released behaviour:
  a trashed project is skipped (relinked when it is restored and saved, 869fat84r D20 Q2).
- **The save path probes again.** 002 Q5 said the save path never probes; 869fat84r D13 says a save measures a legacy or
  changed row first. Clarification D1 (all four parts) decides for D13; the AST guard and the "no MD5 on the save path"
  rule stay.
- **`new()` and `duplicate()` did not fill the stored values** on the refactor line (only `update()` did); the released
  code did both (`test_new_fills_the_values`, `test_duplicate_fills_the_values` were red).
- **The frame needs no change in `document_load_report`**; its tests only needed `_drain` to leave the informational
  `media_check_report` out.
