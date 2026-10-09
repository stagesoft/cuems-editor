# Changelog

## Unreleased

Save-time gate for media cues without a usable media block (closes ClickUp 869fej07m).

### Fixed
- `project_save` / `project_new` with an AudioCue or VideoCue whose `Media` block is missing, `null`, `{}`, has an empty `file_name` or no `id` died inside the atomic transaction with a bare `KeyError 'file_name'` (raised by `CueList.get_media`'s `hasattr` guard in cuems-utils < rc16). The frontend sends exactly that shape when it cannot match a cue's file in its library list (e.g. the file is in the media trash). Had the save not died, it would have written an empty `<Media/>` and lost the cue's media. Now `validate_media_cues_in_contents` refuses the save **before** anything is written — in particular before `_fix_media_durations`, which used to write `Media` rows even for a save that the fade gate then rejected — and names every offending cue. A file that is in the media trash passes (it can be restored); a file unknown to the library is refused with its name.
- The WebSocket error for a save refused by a gate (`ValueError`) now reaches the client without the `<class '…'>` prefix, in `project_save` and `project_new` alike.

### Added
- `validate_media_cues_in_contents(contents, media_exists=None)` in `CuemsDBProject`, next to `validate_fade_durations_in_contents`.

## 0.1.0rc1 — 2026-05-26

CTimecode hardening migration (closes ClickUp 869cyndtv PR #9). Pins `cuemsutils` to the PR #6 release (`0.1.0rc6`+) to consume the `.milliseconds_rounded` / `.milliseconds_exact` precision-split.

### Changed
- Pinned `cuemsutils` from `>=0.1.0rc1` to `>=0.1.0rc6` (ships transitively with `0.1.0rc7` from cuemsutils PR #10).
- Migrated the only `.milliseconds` call-site — the `audiowaveform -e` CLI argument in `CuemsDBMedia.generate_thumbnail` — to `.milliseconds_rounded`. Applied to both `CuemsDBMedia.py` copies in the repo (root-level and `src/cuemseditor/`); both had the same site.

### Notes
- The CLI arg semantics are seconds-equivalent (the `/1000` in the expression converts ms to seconds for `audiowaveform`'s `-e` flag). At integer framerates (which is what audio media uses in cuems) `.milliseconds_rounded` and the old `.milliseconds` are identical; at fractional framerates the new behavior rounds where the old truncated, a difference of at most 1 ms in the waveform endpoint. Visually undetectable in the rendered waveform.
- This branch (`fix/ctimecode-migration`) sits on `fix/mtc-bias-compensation`, which was created here from `rc1` (not `master` per the original 869cyndtv plan) since `rc1` is 86 commits ahead of `master` and is the active editor branch.
