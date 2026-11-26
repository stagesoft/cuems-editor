<!-- SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- SPDX-FileContributor: Ion Reguera <ion@stagelab.coop> -->

# Changelog

## Unreleased — project import (1amfwm7kcjp)

Project import: the counterpart of the export (ClickUp 1amfwm7kcjp). Released together with the export (1amfwm7kana), whose archive it reads; the contract is `docs/project-archive.md`, section 8.

### Added
- `project_import` (the guard) and the `/upload` first frame with `"type": "PROJECT"` and a one-use ticket: the browser uploads the zip that Export made and the editor recreates the project and its media in the library. The show is protected always: a running show refuses, a loaded project needs `"accept_loaded": true`, and the rule is asked again when the upload ends, before each file and before the project is created.
- `CuemsProjectImport`: checks the archive with no write to the library (the zip's directory bounded in bytes, the script through the defused parser and the box's schema, every entry read to its CRC), registers each media file through `CuemsDBMedia.new` (reusing a file of the same size and MD5, renaming on another content, taking a capital name to the library name as the upload does), creates the project under a new uuid and a free name, and answers with progress frames and a report. An import only adds; a failure keeps what was added and says so (I9).
- `CuemsDBProject.import_project`, `add_media_relations(allow_missing=True)` (a file the library does not have becomes a relation with no media, healed by a later upload), `CuemsWsServer.ImportSlot` (one import at a time), `ProjectImportError`, and a staging folder `<library>/.import/` made 0700 and swept at start.

### Known limit
- A GO cuts the import's work in hand, except a Python step on the script (reading, parsing, validating, writing it: it ends, the next does not start; its time grows with the script, ClickUp 1amfwm7kkpe) and a copy into a `media/` on another filesystem.
- `CuemsDBMedia.new` holds one database transaction across a file's sidecars (ClickUp 1amfwm7kcwk): a save from another session that lands in that window makes the registration fail, as it already does for an upload. Measured on .111, 1.05 GB: a 4.7 s window.

## Unreleased — project export (1amfwm7kana)

Project export reaches the browser on an installed controller (ClickUp 1amfwm7kana). Released together with cuems-common, which creates, serves (`Alias /exports`) and cleans (one day) `/var/lib/cuems/exports`; the editor does not work without it.

### Fixed
- The export wrote its zip under `/var/www/cuems/exports`, which nothing creates and the `cuems` user cannot create, and nothing served. `html_root_path` is now `/var/lib/cuems` (the parent of the exports folder, no longer a web root).
- Two exports of one project at once collided in `<tmp>/<unix_name>`: the second's cleanup removed the first's files and the first published a valid but incomplete zip, with no error. Each export now writes its own file and publishes it with an atomic `os.replace`, so both complete and the last one owns the name.
- Export is one pass instead of three: the zip is written stored (no deflate), straight from the library into `.<unix_name>.XXXX.part` (name cut to 200 bytes, locked while written) in the exports folder (`0600`, 1 MiB chunks, zip64 when needed), then `0644` and published as `<unix_name>.zip`, **replacing the project's previous export** (one zip per project, no `-001`, `-002`; a download already reading the old file finishes it). Nothing is copied to `/tmp`. The answer to the UI is unchanged (`exports/<file>.zip`).

### Added
- Refusals with one-line texts (the UI shows them as they are): the exports folder missing or not writable, or the apache conf `/etc/apache2/conf-enabled/cuems-exports.conf` not enabled (the editor creates neither); less than the reserve left on the exports filesystem (the larger of 5 GiB and a tenth of it, counting exports in progress); a media file whose size changed while it was zipped.
- The show is protected always: `project_export` asks the engine first. `running` is refused; `loaded` is refused unless the request carries `"accept_loaded": true` (sent by the UI after the operator accepts a warning); no usable answer is refused; `none` goes on. Nothing is stopped or unloaded. New `CuemsWsUser._engine_status()`; `_engine_running()` keeps its answers.
- A media file listed twice for one project gives one zip entry. `ExportError`.
- At start the editor removes the `*.part` files an export killed in mid-write left in the exports folder, not one a running editor still holds; it never creates the folder.
- An export writes no more than it measured for the free-space check, and fails if the project script or a medium changes size while it is zipped.

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
