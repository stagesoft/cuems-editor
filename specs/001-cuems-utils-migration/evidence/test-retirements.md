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

## `tests/test_repair_durations.py` pass B assertions (T030)

**Retired, recorded in the module header** with `contracts/repair-tool.md` as the reason: the
tool writes no script under any flag. Removed: the assertion that `--apply` rewrote `<duration>`
inside `script.xml` (`'00:00:00.000' not in xml_durs`), the `_xml_durations` helper and its
`XmlReaderWriter` import, and `--db-only` / `--xml-only` (the options are gone, so
`test_skip_trash` and `test_trash_media_fixed_without_skip` run the whole tool).

**Kept:** dry-run, `--apply` plus the DB backup, idempotence, trash, missing DB, invalid XML not
aborting the run.

**Added:** every `script.xml` checksum unchanged after `--apply`; the `NEEDS_SAVE` list equals the
fixture's two media; dry-run lists the same; a pre-013 script is `SKIPPED_INVALID` naming
`cuems-reshape-devices`; saving a listed project through `CuemsDBProject.update` takes it off the
list and is the only write to its file.

## `tests/test_initial_template.py` (T060)

**Retired, skipped module.** It compared `initial_template` (the library's generated example,
milestone 1) with the `v0.1.0rc14` `create_script()` baseline, delta by delta, and its red run is
`initial-template-failing-first.txt`. At payload version 1 the message is not sent; a new script is
built from `schema_descriptor("script")`'s `instance`, pinned by `tests/test_schema_descriptor.py`.
The delta list stays in `tests/ws-command-responses.txt` because a pre-05 UI may still hold the
milestone-1 template in `localStorage`.
