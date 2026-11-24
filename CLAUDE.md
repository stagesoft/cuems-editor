<!-- SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
<!-- SPDX-FileContributor: Ion Reguera <ion@stagelab.coop> -->

# cuems-editor

Part of the **CUEMS** ecosystem — see the [`cuems-RELATIONS`](https://github.com/stagesoft/cuems-RELATIONS) repo for the system index, architecture diagram, and protocol/port map.

## Role

WebSocket middleware for multi-user project editing and media management — sits between the browser frontend (`cuems-frontend`) and the engine (`cuems-engine`). Python 3.11+, systemd service `cuems-editor.service` (controller-side). PyPI name `cuemseditor`.

- **Frontend → Editor**: WebSocket `:9092`, JSON `{"action": "...", "value": ...}`.
- **Editor → Engine**: Unix IPC socket `/tmp/editor.ipc` (serialized objects) over NNG.

Main classes: `CuemsWsServer` (asyncio WS server / session multiplexer / command router), `CuemsWsUser` (per-connection session handler), `CuemsProjectManager` (owns the DB managers), `CuemsDBProject` (project CRUD, XML script I/O, filesystem management).

## Build

```bash
cd <this repo> && debuild -b -uc -us -nc
```

## Project store / library — `/opt/cuems_library/`

The authoritative path is `settings.xml <library_path>` (read by the editor as `library_path`). **There is NO `/opt/cuems/` directory** — that was a long-standing doc error; everything project-related is under `/opt/cuems_library/`.

Contents:
- `projects/` — one dir per project, **named by `unix_name`**. The project UUID and display `name` live *inside* `script.xml` and in the index DB, **not** in the dir name.
- `media/`, `trash/`.
- `project-manager.db` — SQLite index (tables `project`, `media`, `projectmedia`).

## Field notes / gotchas

- **Project export (`CuemsDBProject.export`, 1amfwm7kana): one pass, into a folder cuems-common owns.** The zip is written stored (every entry `ZIP_STORED`, 1 MiB chunks through `ZipFile.open(..., 'w')`) straight from the library into `<html_root_path>/<export_folder_name>/.<unix_name>.XXXX.part` (`mkstemp`, `0600`), then `chmod 0644` and published with `os.link` as `<unix_name>.zip`, `-001`, `-002`… (`FileExistsError` = name taken; `O_EXCL` + `os.replace` where the filesystem has no hard links). Nothing goes to `tmp_path`; each run has its own file, so two exports of one project at once both complete. The answer to the UI is `exports/<file>.zip`, relative, no leading slash. **The editor never creates the folder** (it runs as `cuems` and cannot write under `/var/www`): `html_root_path` is `/var/lib/cuems` and cuems-common creates `exports` (tmpfiles, `cuems:cuems` 0755, zips removed after one day), serves it at `/exports` (`Alias`, outside the DocumentRoot) and enables `/etc/apache2/conf-enabled/cuems-exports.conf`. `export()` refuses with a one-line `ExportError` when the folder is missing or not writable or that conf is missing (setting `export_conf_path`; the folder alone proves nothing, the tmpfiles rule recreates it at every boot), when the filesystem would keep less than the larger of 5 GiB and a tenth of itself (exports in progress count), and when a media file's size changed while it was zipped. `ensure_directories()` removes leftover `*.part` files at start (listed with `os.scandir`: a glob does not see dot-files). The two packages are released together (`Depends:`).
- **`project_export` protects the show always** (`CuemsWsUser.request_export_project`, before the executor): the engine is asked `project_status` through `_engine_status()` (`running` / `loaded` / `none`, anything else `None`; `_engine_running()` still maps `loaded` to `None`). `running` -> refused; `loaded` -> refused unless the frame carries `"accept_loaded": true` (only the JSON `true`; the UI sends it after the operator accepts a warning); no usable answer -> refused (up to 25 s, `TIMEOUT`); `none` -> goes on. Nothing is stopped or unloaded, and a load or GO that arrives during an export does not abort it. Texts and the optional key: `tests/ws-command-responses.txt`.
- **Save-time FadeCue validation** (`CuemsDBProject.validate_fade_durations_in_contents`, called in `update()` and `new()` before `CuemsParser`): rejects any FadeCue whose duration is missing, unparseable, or `<= 0` with a single `ValueError` naming the offenders (forwarded verbatim to the frontend over WS). Parsing delegates to the real cuemsutils `CTimecode` — its ms semantics are literal (`'.3'` = 3 ms) and `'00:00:03'` raises `IndexError`, so a private parser would diverge. `duplicate()` is deliberately NOT validated (legacy projects must stay duplicable; the engine's reveal guard covers them).
- **`CUE_TYPES` includes `FadeCue`** (dangling-target cleanup): before the fix, `_collect_cue_ids` ignored FadeCue ids — an ActionCue targeting a FadeCue was wrongly nullified on **every save** — and FadeCue's own dangling `action_target` was never cleaned.
- **After hand-editing `network_map.xml` or `default_mappings.xml`, restart BOTH `cuems-editor` AND `cuems-controller-engine`** (plus `cuems-node-engine` if active). Both daemons cache topology at startup via `ConfigManager(load_all=True)`; there is no on-disk reload. Restarting only the editor leaves the engine on the stale topology. Verify: editor logs `"number_of_nodes": N`.
- **The node list is pushed, not polled by clients.** `watch_network_map` (a 3 s mtime poll, one per host) broadcasts `initial_mappings` whenever **cuems-nodeconf** rewrites `network_map.xml` — which it does on every avahi event or every 30 s, since it is resident. Without this the editor only re-read the map on connect and after its own successful `nodelist_modify`, so a node powered on *after* the operator opened Settings never appeared in `new_nodes` and adoption looked broken exactly when it was needed. `nodelist_get` is the on-demand pull of the same payload; `nodeconf_available` in that payload says whether adoption can work on this host at all (`/tmp/nodeconf.ipc` present — it is absent on most of the fleet, where every adopt/un-adopt click can only fail). Protocol reference: `tests/ws-command-responses.txt`.
- During the nodeconf transition, operators hand-populate `<role_id>`/`<alias>`/`<hostname>` in `network_map.xml`; restart the editor so the merged dict picks up the new fields. `cuems-frontend` falls back to a legacy `Node ${index + 1}` label when both `alias` and `role_id` are absent — partial migrations are safe.
