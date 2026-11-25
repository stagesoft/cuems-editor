<!-- SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- SPDX-FileContributor: Ion Reguera <ion@stagelab.coop> -->

# Project archive: export and import contract

The zip that a project **export** writes and a project **import** reads, and the WebSocket messages around it.
Both ends are cuems-editor code, so this is the one place that states the contract (Ion, 2026-11-24). The messages are
also listed in `tests/ws-command-responses.txt`.

| Part | Owner | State |
|---|---|---|
| 1 to 7 (the archive, its messages, what is frozen) | the export (ClickUp 1amfwm7kana) | written from the code and measured on rigs on 2026-11-24 |
| 8 (what the importer needs and how it reads) | the import (ClickUp 1amfwm7kcjp) | **to be written by that task**; its plan is `cuems-RELATIONS/Plans/2026-11-24-project-import-from-zip.md` |

**Evidence tags.** `[code]` read in this repo at the symbol named; `[rig]` measured on rig .111 or `test` on 2026-11-24
(logs in `cuems-RELATIONS/baselines/1amfwm7kana/runs/`); `[casas]` measured on the workstation; `[infiero]` inferred, not verified.

## 1. Who writes and who reads

| | |
|---|---|
| Writer | `CuemsDBProject.export()` and the handler `CuemsWsUser.request_export_project` |
| Reader | the import function (`CuemsProjectImport`, task 1amfwm7kcjp), and any person with a zip tool |
| Released form | cuems-editor **0.1.0rc1-8**: zips made by it exist in the field (section 3) |
| One-pass form | cuems-editor from the 1amfwm7kana release on (this page describes it) |

## 2. The archive written by the one-pass export

Entries, in this order `[code]` (`CuemsDBProject.export`, `_zip_add_file`):

| Entry | Content |
|---|---|
| `<unix_name>/` | directory entry |
| `<unix_name>/script.xml` | **byte-exact copy** of the library file `projects/<unix_name>/<script_file_name>` (`script_file_name` is `script.xml`, set in `cli.get_settings`). No rewriting at export time; verified identical byte for byte on both rigs `[rig]` |
| `<unix_name>/media/` | directory entry, **always written**, also for a project with no media |
| `<unix_name>/media/<media unix_name>` | one entry per media file of the project, flat, named by the library's media `unix_name` (the `file_name` of the script's Media blocks). Deduplicated by that name: a file used by two rows appears once |

- **Exactly one top-level directory**, `<unix_name>/`, the project's `unix_name` (its library folder), not its display name.
- **Every entry is method Stored** (no deflate) `[code]` `[rig]`. A reader must accept Stored and Deflated.
- **zip64 is written automatically** for a large entry: `ZipFile.open(..., 'w')` decides from the entry's declared size, about 2 GiB and up. A 4.5 GiB entry and 70 000 entries were read back by Python and Info-ZIP UnZip 6.00 `[casas]`; a real export of 7.44 GB (four media files) was listed, tested and compared byte for byte by UnZip 6.00 on rig `test` `[rig]`. Windows' and macOS' own tools were not tried `[infiero]`.
- Each entry carries its CRC32 (checked by `zipfile` on read). There is **no other checksum** in the archive.
- A media row whose file was **deleted for good** (`media.media is None`) is **left out**, with only a WARNING in the editor's journal (869fat84r D20) `[code]`. A reader detects it by cross-checking the script's Media names against the `media/` entries.
- A media file whose size changes while it is zipped makes the export fail with E6 (section 5); a file replaced by name is exported as the old file that was already open `[code]`.

**Not in the archive:** no manifest, **no format version**, no checksum beyond CRC32. The project uuid, name, description and each Media block's `file_name`, `id` and `duration` (and `file_md5`/`file_size` when the project was saved by an rc15+ editor) are inside `script.xml`; that is the import task's reading and was not verified by the export.

## 3. The archive written by the released editor 0.1.0rc1-8

From the released code (`shutil.copy` into `<tmp>/<unix_name>/`, then `shutil.make_archive(..., 'zip', tmp, unix_name)`) and a probe of that same path on the workstation `[casas]`; **not from a real zip taken in the field**:

- The same entry names: `<unix_name>/`, `<unix_name>/script.xml`, `<unix_name>/media/<file>`.
- **Every entry Deflated** (method 8). Media that is already compressed comes out slightly bigger.
- `<unix_name>/media/` exists **only if the project has media rows** (also when every file is missing); a project with none has no `media/` entry.
- `script.xml` is a plain copy of the library file, as now.
- The zip's own name was `<unix_name>.zip`, then `<unix_name>-001.zip`... (it never overwrote). Never rely on the name (section 6).

## 4. Where the archive lands and how it is fetched (one-pass form)

| | |
|---|---|
| Written to | `/var/lib/cuems/exports/<unix_name>.zip`. A new export of a project **replaces** the previous one with an atomic `os.replace` (Ion, 2026-11-24): one zip per project, no `-001`, no `-002`. A download that already has the old file open finishes it |
| Downloading across a replace | Only **one continuous `GET`** is promised to give one whole zip. A resumed or multi-range download that spans a replace can join bytes of two zips: with `If-Range` apache should answer `200` with the whole new file (inferred, not tested on a rig), without it the ranges come from whatever owns the name. A client that resumes sends `If-Range`, or starts again |
| Served at | `/exports/<unix_name>.zip`, HTTP 80 and HTTPS 443, `application/zip`, ranges honoured (`206`). A missing file is `404`, the folder listing `403`, an unfinished `.<name>.XXXX.part` `403` `[rig]` |
| Kept | removed by a systemd-tmpfiles rule after one day (a zip goes one to two days after it was last touched); cuems-common installs the folder, the rule and the apache snippet; the editor refuses to export without them (E1) |
| Written how | one pass from the library, under a private `.<unix_name>.XXXX.part` (mode `0600`; the name cut to 200 bytes; locked while its export runs, so another editor's start-up sweep leaves it), then `0644` and the replace. A script or medium whose size changes meanwhile fails the export, and never more is written than was measured |

## 5. The WebSocket messages (editor, `:9092`, through apache `/ws`)

Request: `{"action":"project_export","value":"<project uuid>"}`, with the optional top-level key `"accept_loaded": true` (only the JSON `true` counts).
Answer: `{"type":"project_export","value":"exports/<unix_name>.zip"}`: a path relative to the site root, no leading slash (the UI puts a `/` in front).
Neither the answer nor the error carries a request id, so a client keeps **one export in flight per connection** and waits for it: the answer comes on the connection that asked, however long the export takes. A client that gives up and asks again for the same project cannot tell the two answers apart.

Refusals and failures arrive as `{"type":"error","uuid":"<project uuid>","action":"project_export","value":"<one line>"}` `[code]`:

| Code | When | Text (exact) |
|---|---|---|
| E1a | the exports folder is missing or not writable | `Export folder <folder> is missing or not writable (cuems-common installs it)` |
| E1b | the apache conf `/etc/apache2/conf-enabled/cuems-exports.conf` is not enabled | `Export is not served on this box: the apache conf cuems-exports is not enabled (cuems-common installs it)` |
| E2 | the disk would keep less than the larger of 5 GiB and 10 % of the filesystem | `No space to export "<project name>": needs <X> GiB, <Y> GiB free in <folder>, <R> GiB kept in reserve` |
| E3 | the engine says `running` (also with `accept_loaded`) | `A show is running: stop it before exporting a project` |
| E4 | the engine does not answer (25 s wait) | `Cannot check whether a show is running (the engine does not answer): nothing was exported` |
| E5 | the engine says `loaded` and the frame has no `accept_loaded: true` | `A project is loaded and waiting for GO: an export reads the whole project from disk and can make the next GO late. Accept the warning in the export dialog to go on` |
| E6 | a media file changed size while it was zipped | `Media file <name> changed while it was exported: export again` |

**The guard** runs in `request_export_project` **before** any work: `running` is E3; no usable answer is E4; `loaded` without the key is E5; `none`, or `loaded` with the key, goes on. Nothing is ever stopped, unloaded or reloaded by an export. The status word comes from `CuemsWsUser._engine_status()` (`running`, `loaded`, `none`, or `None` for no usable answer); other code calls it, so its name and those four results are frozen (section 6).
**Timing:** 4.9 s to 6.8 s for 1.99 GB with the media in the page cache, 117 s for a cold 7.44 GB `[rig]`. The UI waits 5 minutes for the answer.

## 6. What a reader may rely on, and what changes need a heads-up

**Frozen** (the import task asked for it): exactly one top-level directory `<unix_name>/`; `<unix_name>/script.xml` a byte-exact copy of the library file with no rewriting at export time; `<unix_name>/media/<media unix_name>`, flat, with the same names as the script's `Media.file_name`; the name of `_engine_status()` and its `running` / `loaded` / `none` / `None` results; the request and answer shapes of section 5. **Whoever owns the export tells the reader's owner before changing any of them**, and the other way round.

**Not to rely on:** the zip's own file name (the importer does not use it); the directory entries (present in the one-pass form, but released archives of a project without media have no `media/` entry); the method of an entry (Stored here, Deflated in released archives); the order of the entries.

**Evolution:** a manifest or a format version is additive and possible later. It would be a new entry beside `script.xml`, never a change to the entries above. None in v1: it would reopen the export's test rounds.

## 7. Contract rows

| Wire | Producer (code) | Consumer (code) |
|---|---|---|
| The archive | `CuemsDBProject.export`, `_zip_add_file` | `CuemsProjectImport` (task 1amfwm7kcjp; to be filled in by it) |
| `project_export` request and answer | `CuemsWsUser.request_export_project`, dispatch line `"project_export"` | cuems-frontend `src/app/services/media/export.service.ts` (`exportProject`, `processServerResponse`) |
| The refusal texts E1 to E6 | `CuemsDBProject.export` (E1, E2, E6), `CuemsWsUser.request_export_project` (E3, E4, E5) | `src/app/services/websocket.service.ts` and the app-level error handler show them as they are |
| `_engine_status()` | `CuemsWsUser._engine_status` | the import's guard handshake (task 1amfwm7kcjp) |

## 8. Import requirements (the reader's side)

To be written by the import task (1amfwm7kcjp): what the reader checks in the archive, how it reads Stored and Deflated entries and zip64, what it does with missing media, a uuid or name that already exists, and a failed import; and the code that reads, for the rows of section 7.
