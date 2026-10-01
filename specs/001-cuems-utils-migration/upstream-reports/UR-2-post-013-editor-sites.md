<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-2 — editor sites after cuems-utils 013

The guide measured these at `cuems-editor` `106015c`
(`../cuems-utils/specs/013-device-class-reshape/migration-guide.md` §4).
Re-measured on this tree the same day, after that commit and before any `src/`
edit for 001. Line numbers have not moved. This report is how that section is
re-measured. It does not ask for a library function.

The library pin is `6213b1603d0a508b6ac7dfb5f46593ba4d870193`
(`evidence/cuems-utils-013-landed.txt`).

| Guide site | Fresh grep | What 001 does with it |
|---|---|---|
| `src/cuemseditor/CuemsWsServer.py:439` — `# Keep outputs (audio, video, dmx) from existing node` | still line 439. The loop copies `existing_node` after updating `basic_fields`. It does not read `audio`, `video`, or `dmx` | kept. T037 copies the mapping node's blocks through, including `devices` / `device` / `class`. It does not look those three names up. Not one of the fourteen deprecated-surface call sites |
| `src/cuemseditor/CuemsDBProject.py:385` — `CUE_TYPES = ['AudioCue', 'VideoCue', 'DmxCue', 'ActionCue', 'FadeCue', 'CueList']` | still line 385 | deleted with the walks (T024). The guide's collapsed list `['Cue', 'ActionCue', 'FadeCue', 'CueList']` is not ported |
| `src/cuemseditor/CuemsDBProject.py:408` `_collect_cue_ids`, `:422` `_nullify_dangling_refs` | still lines 408 and 422; caller at 398–399 | deleted (T024). The library rule is by cue identity, so a `Cue` of any class is already covered. A second walk would be a second dangling-reference implementation |
| `src/cuemseditor/CuemsDBProject.py:78`–`:82` — `if 'AudioCue' in item` / `elif 'VideoCue' in item` in `_walk_media_durations` | still lines 79 and 81. `DmxCue` is not in this walker | rewritten on the loaded object (T023). `isinstance` of `AudioCue`, `VideoCue`, `DmxCue`, and a `MediaCue` whose `class` is none of those three. The guide's `if 'Cue' in item: cue_data = item['Cue']` walks the wire dict and is not implemented |
| `src/cuemseditor/CuemsDBProject.py:883` and `:895` — `XmlReaderWriter` write and read | still lines 883 and 895 | rewritten to `CuemsScript.save` and `CuemsScript.load_with_report` (T019, T020). An old-shape file fails the strict load. This repository does not reshape it |
| `src/cuemseditor/repair_durations.py:204` and `:231` — `XmlReaderWriter` read then `write_from_object` | still lines 204 and 231 | deleted (T029). A fixture whose element is `AudioCue` and which has no `class` is `SKIPPED_INVALID`. The file checksum is unchanged. `cuems-reshape-devices` is not invoked |

`src/` still contains `'AudioCue' in item` and `CUE_TYPES`. This report does not change that. The tasks are what fail on it.
