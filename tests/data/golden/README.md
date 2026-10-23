<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Golden `media_check_report` frames, captured from the released producer

Constitution I: a contract claim is verified against a payload **captured before** the change. These are the
`value` of the `media_check_report` frame (`{"type": "media_check_report", "value": …}` as `json.dumps` sends it)
produced by the code released in `0.1.0rc1-4 … -7`.

| | |
|---|---|
| Source | `origin/debian/bookworm` @ `69d749e` (0.1.0rc1-7), tag `v0.1.0rc1-7` |
| Library | `cuemsutils 0.1.0rc16` (`git archive v0.1.0rc16` of cuems-utils), in its own venv; the released suite passes there (207 passed) |
| Fixture | the released `tests/conftest.py` `library` fixture (**pre-013** device-shape `script.xml`, four media rows) and the helpers of the released `tests/test_media_refresh.py` |
| Stubs | `probe_media` is a `FakeProbe` (no ffprobe); the engine-state callable answers `none` (`ready`/`save`/`open`) or `running` (`engine_running`); no sockets |
| Harness | [`capture_at_69d749e.py`](capture_at_69d749e.py): copied, not collected; to re-run, drop it into a checkout of `69d749e` as `tests/test_capture_golden.py` and set `GOLDEN_OUT` |
| Captured | 2026-10-23 |

| File | Scenario | `context` |
|---|---|---|
| `media_check_report_ready.json` | a replaced video file is re-probed and its row corrected; the project still holds the old duration | `ready` |
| `media_check_report_open.json` | read-only check: duration, pixel size, file size and md5 all differ for one video used by two cues; a changed file is not measured | `open` |
| `media_check_report_save.json` | stale audio and stale video, two files in `files` | `save` |
| `media_check_report_copy_in_progress.json` | the file grows while it is probed: `complete: false`, `reason: copy_in_progress`, `unverified` lists it | `ready` |
| `media_check_report_engine_running.json` | a show is running: no write, `reason: engine_running`, the changed file is `unverified` | `ready` |
| `media_check_report_all_clear.json` | rows, files and project agree: `complete`, no `files`, no `unverified` | `ready` |

Key order is the released one (`project_uuid`, `project_name`, `context`, `complete`, `reason`, `files`,
`unverified`, `total_files`; each file `file_name`, `cues`, `changes`). The comparison normalises only the volatile
`project_uuid` (a fixture-generated uuid); never edit these files to make a test pass.
