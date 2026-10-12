<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# `cuems-utils` T039 — absorbed by cuems-editor 002

002 FR-047, T078. Written 2026-10-12, after T064 passed.

`cuems-utils` handed its T039 (`specs/planning/t039-editor-media-obligations.md` there: the editor
must write the 014 media values into each cue through the setters, with an `AudioCue` never carrying
a pixel size) to the editor. These six tests, FR-042's, pin it. Each was shown failing first
(`media-values-failing-first.txt`) and passes from commit **`1502d64`**
(`feat(002): US6 — media values ported from 869fat84r 0b291d1 onto objects`):

1. `tests/test_media_values.py::test_an_audio_cue_loses_pixel_size_and_a_video_cue_keeps_it`
2. `tests/test_media_values.py::test_an_unknown_class_media_cue_keeps_its_pixel_size`
3. `tests/test_media_values.py::test_an_uppercase_client_md5_is_stored_lowercase_and_the_save_succeeds`
4. `tests/test_media_values.py::test_a_non_hex_or_wrong_length_md5_is_dropped_and_the_save_succeeds`
   (parametrized: `zzz…`, `abc`, 31 and 33 characters)
5. `tests/test_media_values.py::test_zero_float_and_bool_file_sizes_are_dropped_not_assigned`
   (parametrized: `0`, `1.5`, `True`)
6. `tests/test_media_values.py::test_a_cleared_value_is_absent_not_zero_not_null`

Beside them, `tests/test_media_values.py::test_no_item_assignment_on_stored_media_keys` finds no item
assignment, `del` or `pop` of a stored media key in `src/cuemseditor/` (FR-040, SC-011).

The requirements they close are this feature's FR-036 to FR-046
(`specs/002-config-round-trip/spec.md`, section F): the columns and their migration, the upload
probe, the object fill by cue identity and attribute setters, and the load-time comparison into
`document_load_report.media_repairs`.

cuems-utils may delete specs/planning/t039-editor-media-obligations.md and close T039 against these tests.

The maintainer passes this on to `cuems-utils`. This feature edits nothing in `../cuems-utils`.
