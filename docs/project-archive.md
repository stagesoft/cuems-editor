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
| 8 (what the importer checks, reads and does; its messages) | the import (ClickUp 1amfwm7kcjp) | written from the code of the import branch, 2026-11-25; its plan is `cuems-RELATIONS/Plans/2026-11-24-project-import-from-zip.md` |

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
| Served at | `/exports/<unix_name>.zip`, HTTP 80 and HTTPS 443, `application/zip`, ranges honoured (`206`). A missing file is `404`, the folder listing `403`, an unfinished `.<name>.XXXX.part` `403` `[rig]` |
| Kept | removed by a systemd-tmpfiles rule after one day (a zip goes one to two days after it was last touched); cuems-common installs the folder, the rule and the apache snippet; the editor refuses to export without them (E1) |
| Written how | one pass from the library, under a private `.<unix_name>.XXXX.part` (mode `0600`), then `0644` and the replace |

## 5. The WebSocket messages (editor, `:9092`, through apache `/ws`)

Request: `{"action":"project_export","value":"<project uuid>"}`, with the optional top-level key `"accept_loaded": true` (only the JSON `true` counts).
Answer: `{"type":"project_export","value":"exports/<unix_name>.zip"}`: a path relative to the site root, no leading slash (the UI puts a `/` in front).

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
| The archive | `CuemsDBProject.export`, `_zip_add_file` | `CuemsProjectImport.open_archive`, `import_archive` (section 8) |
| `project_export` request and answer | `CuemsWsUser.request_export_project`, dispatch line `"project_export"` | cuems-frontend `src/app/services/media/export.service.ts` (`exportProject`, `processServerResponse`) |
| The refusal texts E1 to E6 | `CuemsDBProject.export` (E1, E2, E6), `CuemsWsUser.request_export_project` (E3, E4, E5) | `src/app/services/websocket.service.ts` and the app-level error handler show them as they are |
| `_engine_status()` | `CuemsWsUser._engine_status` | the import's guard (`CuemsWsUser._import_guard`) and every later check (`CuemsProjectImport.ImportSession._status`, `import_archive`) |
| `project_import` request and answer (the guard) | cuems-frontend `import.service.ts` (step 4 of the import plan) | `CuemsWsUser.request_import_project`, dispatch line `"project_import"`; the ticket from `CuemsWsServer.ImportSlot` |
| `/upload`, first frame with `type: "PROJECT"`, then the archive's bytes | cuems-frontend `import.service.ts` | `CuemsUpload.process_upload_message` hands the socket to `CuemsProjectImport.ImportSession.run` |
| `progress`, `imported` and the fatal `error` with a `report`, on that socket | `CuemsProjectImport.ImportSession` | cuems-frontend `import.service.ts` |

## 8. Import requirements (the reader's side)

Written from the code of the import branch (ClickUp 1amfwm7kcjp); `[code]` below means the symbol named, in
`cuemseditor/CuemsProjectImport.py` unless another file is given. Design and decisions D1 to D18 are in the plan.

**Principles.** The show is protected always (a running show is never touched); nothing is written to the library until
the whole archive has been checked; an import only **adds** (it never deletes, overwrites or moves a file or a row that
existed, and takes nothing out of the trash); a failure leaves what was added and says so.

### 8.1 The two steps on the wire

1. **The guard**, on the user's session: `{"action":"project_import","value":{"size":<bytes of the zip>,"name":"<file name>"},"accept_loaded":true}`
   (`accept_loaded` optional; only the JSON `true` accepts) `[code]` `CuemsWsUser.request_import_project`. The editor
   asks the engine (`_engine_status()`, the export's, unchanged) and applies the rule of D3 (`import_refusal`):
   `running` is refused (also with the acceptance), no usable answer is refused, `loaded` needs `accept_loaded: true`,
   `none` goes on. Then a held slot answers I1 (before the space, whose check counts the running import's own claim). Then it checks the space (`space_refusal`: the staging folder's filesystem keeps the export's
   reserve, the larger of 5 GiB and a tenth, the bytes claimed by running exports and imports counted; it claims
   nothing, see "Space shared with the export" below) and takes the one import slot (`CuemsWsServer.ImportSlot.take`). Answer:
   `{"type":"project_import","value":{"ticket":"<32 hex>","expires_s":60}}`; a refusal is the existing action error
   `{"type":"error","action":"project_import","value":<text>}`.
2. **The upload**, on `/upload`: first frame `{"action":"upload","value":{"name","size","type":"PROJECT","ticket"}}`
   (`size` equal to the guard's, `ticket` one use, void unused after 60 s; without `type` the frame is a media upload as
   always) `[code]` `CuemsUpload.process_upload_message` → `ImportSession.run`. The editor claims the zip's size on the
   staging folder's filesystem (`claim_space`): when a running export took that room since the guard, the answer is
   I2 as a fatal error and no byte is taken. Then, as for a media upload: the editor
   answers `{"ready": true}`, each binary frame (at most 500 000 bytes, the socket's limit being 1 048 576) is answered
   `{"ready": true}`, and `{"action":"finished","value":"<md5 hex of the whole zip>"}` ends the transfer; any other text
   frame during the transfer is I7 (`_receive`). The editor compares the size and the MD5 (I7), asks the rule of D3 again
   (D4), and imports.

While it works the editor sends `{"progress":{"phase","done","total","name"}}` (`phase` is `check` in bytes, `media` in
files or `project`) at least every 5 s (`HEARTBEAT_S`, a timer of the session's own). It ends with
`{"imported":<report>}` then `{"close": true}`. A failure is `{"error":<text>,"fatal":true}`, with a `"report"` key beside
it once something was written. The socket serves one import and is closed after it. A frontend must treat `imported`,
not `finished`, as the success.

### 8.2 What the reader checks (no write to the library up to the end of this list)

All of it is `import_archive` → `_check` and what it calls; a refusal is I8a (`Not a project archive made by Export:
<reason>`), the script's schema being I8b.

| Check | Rule | `[code]` |
|---|---|---|
| The zip's directory | the byte size the end record gives (`MAX_DIRECTORY_BYTES`, 4 MiB) and the real number of records (`MAX_ENTRIES`, 10 000) are bounded **before** `ZipFile` builds anything, whatever count the end record declares | `open_archive`, `_read_directory`, `_count_records` |
| Entries | one top folder named as the library's sanitiser would keep it; `<top>/script.xml` once; `<top>/media/<name>` for each name the script lists; a name with `..`, an absolute name, a backslash or a NUL (read in the name as the archive
writes it, `ZipInfo.orig_filename`: `zipfile` cuts `filename` at the NUL), a symlink, an encrypted entry or a method other than Stored (0) or Deflated (8) refuses the whole archive; sizes that overlap or add up to more than the zip, and a CRC32 that fails (every used entry is read to its end), refuse it | `_check_entry`, `_check_sizes`, `_top_folder`, `_copy_entry` |
| Ignored, and listed in the report | directory entries, `__MACOSX/`, `.DS_Store`, `Thumbs.db` and any entry the script does not name | `_is_noise`, `report["ignored"]` |
| The script | one file, at most `MAX_SCRIPT_BYTES` (64 MiB), read through the defused parser (a `DOCTYPE` or an entity is I8a), validated by the box's schema (cuems-utils; a schema failure is I8b with the version and the reason), parsed and serialised once; the save-time gates (zero fade, media cue without a file) are **not** applied: what they would refuse is listed under `warnings` | `_read_script`, `_gate_warnings` |
| Media names | refused: empty, `.`, `..`, a separator, a control character, more than 255 bytes in UTF-8, or a name with no known media type. A name with capitals is **accepted** and taken to the name the library holds (as the upload does: `CuemsUpload.py:129`), reported as a rename; a name already lower-case and made of alphanumerics, `.`, `_`, `-` and U+0307 is kept. The archive is refused if the library name is empty, `.` or `..`, or if two used names share one (`A.wav` + `a.wav`), or if the library name of a file the archive carries is longer than `MAX_LIBRARY_NAME_BYTES` (234 bytes in UTF-8: 255 less the `-NNN` that `new()` adds on a taken name and the 17 bytes the longest name built from it adds, the loop period's temporary `.<name>.period.XXXXXXXX`) | `media_name_problem`, `library_name`, `_match_media` |
| Space | the exact bytes to be added against the library's filesystem and the reserve (I2), claimed | `_claim_space` |

**Space shared with the export** (change review R3) `[code]` `CuemsSpace`. A running export or import writes for
minutes, and the free space shows its bytes only as they land. Each registers what it will write (`CuemsSpace.claim`:
the check and the registration are one hold of one lock), and every space check of either, the export's E2 included,
subtracts from the free space the bytes the others **on the same filesystem** (`st_dev`) still have to write: what each
claimed less what is already on disk, never below zero. The import claims the zip's size from the start of the upload,
and, after the checks, the bytes of the files it adds: on one filesystem a file counts as written once extracted (its
move into `media/` is a rename), on two the library's claim shrinks as each file is registered and the staging's holds
the largest file. Every claim is released on every exit path (`finally`). The texts keep the filesystem's real free
space; a single export or import alone is checked exactly as before.

### 8.3 What it does

Per media file named by the script (`_decide`, D8; `_register`):

| Case | Result | Report |
|---|---|---|
| the archive carries it and the library has no file of that name | registered through `CuemsDBMedia.new` (moved into `media/`, sidecars built, row created) | `media.added` |
| the library has a live file of that name with the same size and MD5 (or, under that name with the `-NNN` that `new()` adds) | reused, nothing written; a row with no `file_md5` is compared by hashing the library's file once, read only | `media.reused` |
| the library has another file of that name, or the name is only in the trash | registered under the free name `new()` picks; the script's `file_name` and `id` follow | `media.added` and `media.renamed` `{from, to}` |
| the script names it and the archive does not carry it | the project gets a relation with **no media** (the state a delete for good leaves, healed by a later upload of that name); if the library has a live file of that name it is linked | `media.missing`, `media.from_library` |
| the script names it, the archive does not carry it, and the library has it only in the media trash | linked to the trashed row, as a delete of a used media leaves it: restoring the file from the trash heals the project; nothing is taken out of the trash (a name has one row, live or trashed: `name` and `unix_name` are unique) | `media.missing` and a line in `warnings` saying the file is in the media trash |

Then the project (`CuemsDBProject.import_project`, D10): a **new uuid**, the dates of now, and the first free pair
`<unix_name>` / `<name>` (a taken pair gets `-NNN` and ` (N)`, the name cut to the schema's 60 characters); the probes
that fill the media durations run before the one short transaction that writes the row, the folder, the relations and
`script.xml`. Other projects whose dangling relation a new file satisfies are relinked first, best effort, as an upload
does (`_relink`, `report.relinked`). The other sessions get `list_update` for `file_list` after each registration, and
at the end for `project_list` (also after a relink changed a project) and for `file_list` again: the media list names
each file's projects, the reused files' too.

**The report**, in `{"imported": ...}` and beside a fatal error:
`{"project":{"uuid","name","unix_name","renamed"},"media":{"added":[],"reused":[],"renamed":[{"from","to"}],"missing":[],"from_library":[]},"sidecars_failed":[{"name","what"}],"relinked":[{"project","name"}],"ignored":[],"warnings":[]}`;
`what` is one of `thumbnail`, `waveform`, `index`, `period`; `project.renamed` is a boolean.

### 8.4 A failure

The staging folder (`<library>/.import/import-<hex>/`, 0700, on the library's filesystem) is removed in a `finally` and
swept at editor start (`cli.sweep_import_staging`); the slot is freed in a `finally`. A failure after the first file was
registered is I9 with the report so far: **what was added stays** (the files, their rows and sidecars) and the project is
not created; importing the same archive again reuses what was added. Once the project is created
(`import_project` committed) the import is a success: a failure in what follows (the report of the files not carried,
`project_list`, the last progress frame) is logged and listed under `warnings` (`_after_creation`). A show that starts, or a project that is loaded
without the operator's acceptance, between two files stops the import at the next check (D4). A hard kill of the editor
in the move-to-row window of `CuemsDBMedia.new` leaves a file with no row (the documented limit of ClickUp 1amfwm7kcwk):
the next import stores it again as `<base>-001<ext>`.

### 8.5 The texts

| Code | When | Text (symbol) |
|---|---|---|
| I1 | another import holds the slot | `Another import is in progress: wait for it to end` (`I1`) |
| I2 | the reserve would be broken, at the guard, when the upload starts or after the checks | `No space to import: needs <X> GiB, <Y> GiB free in <folder>, <R> GiB kept in reserve` (`no_space_text`) |
| I3 | the engine says `running` | `A show is running: stop it before importing a project` (`I3`) |
| I4 | the engine does not answer | `Cannot check whether a show is running (the engine does not answer): nothing was imported` (`I4`) |
| I5 | `loaded` and no `accept_loaded: true` | `A project is loaded and waiting for GO: an import writes the whole project to disk and builds its previews, and can make the next GO late. Accept the warning in the import dialog to go on` (`I5`) |
| I6 | no valid ticket on `/upload` | `Import refused: start it again from the project list` (`I6`) |
| I7 | the upload is not what was announced, or a text frame other than `finished` arrives during it | `The upload is not complete or does not match: import again` (`I7`) |
| I8a | the archive is refused | `Not a project archive made by Export: <reason>` (`I8A`, `_refused`) |
| I8b | the script is refused by the schema | `This project's script is not valid for this controller (cuems-utils <version>): <reason>. If the archive comes from a newer version, update this controller first` (`schema_text`) |
| I9 | a later check refuses, or a failure while adding | `Import interrupted: <the text of I3, I4 or I5, or the failure>. Nothing that existed was changed; media added: <names, or none>` (`interrupted_text`) |
