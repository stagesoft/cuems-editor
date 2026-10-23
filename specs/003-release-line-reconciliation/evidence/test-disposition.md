# Test disposition (T010)

One row per test the release line adds (136). Dispositions: `passing-as-is` / `ported` / `retired` (a retired test names the test that already covers its assertion). Filled as the stories land.

| File | Tests | State |
|---|---|---|
| test_media_refresh.py | 71 | pending (T025) |
| test_media_dimensions.py | 45 | pending (T026) |
| test_validate_media_cues.py | 15 | **ported (T011/T013)**: shape tests moved to the current `Cue`+`class` wire (the released tests used `AudioCue`/`VideoCue` wrappers, which on the 013 wire would find no cue); update tests use the 013 fixture and drop the stale `probe_dimensions` patch; 1 kept as the legacy-wrapper test. Added 5: legacy wrappers ×2, a non-media class, `new()` refuses, library `ValueError` (strict xfail against the candidate tag, passes on utils 387598e) |
| test_media.py (new cases) | 5 | passing-as-is (T015): versioned name against a trashed file, delete keeps `unix_name`, restore refuses an untracked live file, restore moves back, delete rolls back sidecars |

## Findings from porting US2

- **Gate 4 (silent-wrong caller), measured.** The released gate walked `item['AudioCue']` / `item['VideoCue']`. On the 013
  wire a media cue is `{'Cue': {'class': 'audio'|'video'}}`, so the gate would accept every payload. 12 of 18 tests failed
  once the fixtures were moved to the current wire (commit `test(003): media-cue gate on the 013 wire (red)`).
- **The candidate tag `4b336cd` raises `KeyError('file_name')` from `CueList.get_media`.** rc16's `ValueError` guard
  (cuems-utils 017 §1) is in utils `387598e` only. `test_the_librarys_media_error_reaches_the_client_unprefixed` is a strict
  xfail against the tag and passes on the head; it flags the re-cut by turning XPASS.
