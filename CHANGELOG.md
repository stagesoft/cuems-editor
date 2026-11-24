<!-- SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- SPDX-FileContributor: Ion Reguera <ion@stagelab.coop> -->

# Changelog

## Unreleased — project export (1amfwm7kana)

Project export reaches the browser on an installed controller (ClickUp 1amfwm7kana). Released together with cuems-common, which creates, serves (`Alias /exports`) and cleans (one day) `/var/lib/cuems/exports`; the editor does not work without it.

### Fixed
- The export wrote its zip under `/var/www/cuems/exports`, which nothing creates and the `cuems` user cannot create, and nothing served. `html_root_path` is now `/var/lib/cuems` (the parent of the exports folder, no longer a web root).
- Two exports of one project at once collided in `<tmp>/<unix_name>`: the second's cleanup removed the first's files and the first published a valid but incomplete zip, with no error. Each export now writes its own file and takes its name with `os.link`, so both complete (`<name>.zip`, `<name>-001.zip`).
- Export is one pass instead of three: the zip is written stored (no deflate), straight from the library into `.<unix_name>.XXXX.part` in the exports folder (`0600`, 1 MiB chunks, zip64 when needed), then `0644` and published. Nothing is copied to `/tmp`. The answer to the UI is unchanged (`exports/<file>.zip`).

### Added
- Refusals with one-line texts (the UI shows them as they are): the exports folder missing or not writable, or the apache conf `/etc/apache2/conf-enabled/cuems-exports.conf` not enabled (the editor creates neither); less than the reserve left on the exports filesystem (the larger of 5 GiB and a tenth of it, counting exports in progress); a media file whose size changed while it was zipped.
- The show is protected always: `project_export` asks the engine first. `running` is refused; `loaded` is refused unless the request carries `"accept_loaded": true` (sent by the UI after the operator accepts a warning); no usable answer is refused; `none` goes on. Nothing is stopped or unloaded. New `CuemsWsUser._engine_status()`; `_engine_running()` keeps its answers.
- A media file listed twice for one project gives one zip entry. `ExportError`.
- At start the editor removes the `*.part` files an export killed in mid-write left in the exports folder; it never creates the folder.

## Unreleased — save-time gate for media cues (869fej07m)

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
