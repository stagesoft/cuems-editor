<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Test retirements (FR-017, FR-026)

## `tests/test_dangling_targets.py` (T024, T025)

**Retired, skipped module.** Its five tests (`test_fadecue_ids_are_collected`,
`test_actioncue_targeting_fadecue_is_preserved`, `test_fadecue_dangling_action_target_is_cleared`,
`test_fadecue_valid_action_target_is_preserved`, `test_nested_cuelist_fadecue_ids_count`) asserted the
editor's own walk over a hand-kept cue-type list.

**The walks stay deleted.** `_clean_dangling_targets`, `_nullify_dangling_refs` and `_collect_cue_ids`
are gone from `src/cuemseditor/CuemsDBProject.py`, with the cue-type list they read. The guide's
collapsed list `['Cue', 'ActionCue', 'FadeCue', 'CueList']` was **not** ported: the library rules match
on cue identity, so a `Cue` of any `class` is already covered, and a second walk would be a second
dangling-reference implementation.

**Where the behaviour lives now**, `cuemsutils` `xml/validators.py` @ `6213b16`:

| Rule | Repairable | Effect |
|---|---|---|
| `target_resolves` | yes | a dangling `Cue.target` is set to `None` on load and listed on `LoadReport.repairs` |
| `action_target_resolves` | no | a dangling `action_target` (ActionCue, and FadeCue through the MRO) raises `ValidationError` on load and at `CuemsScript.save` |
| `action_target_required` | no | the reason the old clear-to-`None` cannot be ported: `None` is what this rule rejects |

Measured consequence of the old walk on a 013 document: it did not know the `Cue` key, so it treated
every hardware cue id as absent and nulled the fixture's valid `action_target`, and the library then
refused the save (`project-payload-failing-first.txt`, the three save-path cases).

## `tests/test_repair_durations.py` pass B assertions

Recorded with US5 (T030).
