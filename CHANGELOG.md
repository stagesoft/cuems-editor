# Changelog

## 0.1.1 — Unreleased

Coordinated `xml-refactor` landing (cuems-utils feature 016): every CUEMS repository moves to its own next stable minor. The editor is on the public `cuemsutils` surface (feature 001), round-trips configuration documents through it (002), and closes the library's consumer gates (feature 015). It bounds `cuemsutils>=0.1.1,<0.1.2` and `cuems-common (>= 1.3.1~)`.

Contains every change released in `0.1.0rc1-1` … `0.1.0rc1-7`, absorbed from `origin/debian/bookworm` at `69d749e` (release-line reconciliation, feature 003): see the `0.1.0rc1` section below for each build. The controller, the engine and the frontend upgrade together; mixed versions are not supported.

### Added
- The media check and its `media_check_report` (released in `0.1.0rc1-4`), re-implemented on `CuemsScript` objects: at open (read-only), before the load, and after a save; one comparison feeds both this report and the load report's `media_repairs`, and it never gates a save. The frame is the released one, key order included (golden payloads in `tests/data/golden/`).
- `new()` and `duplicate()` fill each cue's stored media values from the library, as a save does.
- `cuems-editor-repair-durations` re-measures the stored pixel size, file size and MD5 of every row (`DIMS_CHANGED`, `MD5_CHANGED`; `--no-md5`) and lists the projects whose scripts then differ as `NEEDS_SAVE`. It still writes no script.

### Changed
- The save gate for media cues (869fej07m) recognises the current wire (`Cue` with `class` audio or video) as well as the pre-013 wrappers; the released gate only knew the wrappers.
- The media check reads the engine's `project_status` as `running`, `loaded` or `none`; a loaded but stopped project is not a show running.
- A re-upload relinks only projects that are not in the trash (they relink when restored and saved).

### Removed
- A save into a directory the editor cannot create files in no longer falls back to writing in place: `CuemsScript.save` writes atomically and raises (reported to cuems-utils).

## 0.1.0rc1 — 2026-05-26

### Debian builds of `0.1.0rc1`

One entry per build, newest first; the text is the Debian changelog's. `debian/changelog` holds each build verbatim.

#### 0.1.0rc1-7 — 2026-10-09 <!-- source: debian/bookworm 0.1.0rc1-7 (049b362) -->
- Node adoption over the editor WebSocket (869ebkkme, PR #7): `nodelist_get`, `nodelist_modify` relayed to the engine, map changes pushed to every client, the engine's liveness view as `node_status`.
- Media library (PR #10): uploading a file named like a media in the trash no longer fails with `UNIQUE constraint failed: media.unix_name`; it gets the versioned name `<base>-NNN<ext>`. Delete and restore keep the media's `unix_name`: an untracked file already in the trash is moved aside, an untracked live file refuses the restore with a clear error, and both undo their own moves on rollback.

#### 0.1.0rc1-6 — 2026-10-09 <!-- source: debian/bookworm 0.1.0rc1-6 (cb39846) -->
- Packaging: stop shipping `/usr/lib/cuems/CACHEDIR.TAG` (virtualenv infrastructure; cuems-utils 0.1.0rc16 shipped the same path, so installing utils after the editor failed with "trying to overwrite"). No code change.

#### 0.1.0rc1-5 — 2026-10-08 <!-- source: debian/bookworm 0.1.0rc1-5 (f6344fa) -->
Save-time gate for media cues without a usable media block (closes ClickUp 869fej07m).

##### Fixed
- `project_save` / `project_new` with an AudioCue or VideoCue whose `Media` block is missing, `null`, `{}`, has an empty `file_name` or no `id` died inside the atomic transaction with a bare `KeyError 'file_name'`. The frontend sends exactly that shape when it cannot match a cue's file in its library list (e.g. the file is in the media trash). Had the save not died, it would have written an empty `<Media/>` and lost the cue's media. Now `validate_media_cues_in_contents` refuses the save **before** anything is written and names every offending cue. A file in the media trash passes (it can be restored); a file unknown to the library is refused with its name.
- The WebSocket error for a save refused by a gate (`ValueError`) now reaches the client without the `<class '…'>` prefix, in `project_save` and `project_new` alike.

##### Added
- `validate_media_cues_in_contents(contents, media_exists=None)` in `CuemsDBProject`, next to `validate_fade_durations_in_contents`.

#### 0.1.0rc1-4 — 2026-10-06 <!-- source: debian/bookworm 0.1.0rc1-4 (e93e133) -->
- (869fat84r) Each media file's pixel size (video), size and MD5 are stored at upload and written into every cue of a project on save (new, update, duplicate); legacy rows are measured once at save, never hashed. At load and save the project's media is checked against the library and a `media_check_report` is sent to the project's sessions; the project file is never rewritten at load.
- `debian/control`: require `cuems-utils (>= 0.1.0rc15)`; an older utils schema rejects every save of a project with a video cue.

#### 0.1.0rc1-3 — 2026-08-05 <!-- source: debian/bookworm 0.1.0rc1-3 (72f952a) -->
- Fix: the `0.1.0rc1-1`/`-2` debs were cut from a base predating `80c7642` and still did `from cuemsutils.daemon import run_daemon`; against cuems-utils 0.1.0rc14 the service died at import and restart-looped. The merged `rc1` source uses foreground mode under systemd.
- `debian/control`: require `cuems-utils (>= 0.1.0rc10)`, matching `pyproject.toml`.
- Brings in save-time FadeCue duration validation and the FadeCue dangling-target fix.

#### 0.1.0rc1-2 — 2026-03-10 <!-- source: debian/bookworm 0.1.0rc1-2 (886275f) -->
- Development build (never released as such: `UNRELEASED` in the Debian changelog).

#### 0.1.0rc1-1 — 2025-12-11 <!-- source: debian/bookworm 0.1.0rc1-1 (6c85404) -->
- Initial Debian package: WebSocket server for collaborative editing, database management for projects and media, integration with the cuems-utils virtual environment, a systemd service, `src/` layout, dual-mode CLI (manual and daemon).

### CTimecode hardening migration (2026-05-26)
CTimecode hardening migration (closes ClickUp 869cyndtv PR #9). Pins `cuemsutils` to the PR #6 release (`0.1.0rc6`+) to consume the `.milliseconds_rounded` / `.milliseconds_exact` precision-split.

#### Changed
- Pinned `cuemsutils` from `>=0.1.0rc1` to `>=0.1.0rc6` (ships transitively with `0.1.0rc7` from cuemsutils PR #10).
- Migrated the only `.milliseconds` call-site — the `audiowaveform -e` CLI argument in `CuemsDBMedia.generate_thumbnail` — to `.milliseconds_rounded`. Applied to both `CuemsDBMedia.py` copies in the repo (root-level and `src/cuemseditor/`); both had the same site.

#### Notes
- The CLI arg semantics are seconds-equivalent (the `/1000` in the expression converts ms to seconds for `audiowaveform`'s `-e` flag). At integer framerates (which is what audio media uses in cuems) `.milliseconds_rounded` and the old `.milliseconds` are identical; at fractional framerates the new behavior rounds where the old truncated, a difference of at most 1 ms in the waveform endpoint. Visually undetectable in the rendered waveform.
- This branch (`fix/ctimecode-migration`) sits on `fix/mtc-bias-compensation`, which was created here from `rc1` (not `master` per the original 869cyndtv plan) since `rc1` is 86 commits ahead of `master` and is the active editor branch.
