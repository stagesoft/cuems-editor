# Test disposition (T010)

One row per test the release line adds (136). Dispositions: `passing-as-is` / `ported` / `retired` (a retired test names the test that already covers its assertion). Filled as the stories land.

| File | Tests | State |
|---|---|---|
| test_media_refresh.py | 71 | pending (T025) |
| test_media_dimensions.py | 45 | pending (T026) |
| test_validate_media_cues.py | 15 | 12 pass on the merge commit; 3 red until T011/T013 |
| test_media.py (new cases) | 5 | pass on the merge commit (as-is) |
