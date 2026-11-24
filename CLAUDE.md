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

## Concurrency model and the multi-user groundwork

Written 2026-11-24 from a read of `rc1` (753b294) while planning the export fix (ClickUp 1amfwm7kana). Cite the symbols, not line numbers: they drift.

**How work runs.** The event loop is single-threaded. Each WebSocket connection starts `consumer_handler`, `producer_handler` and three `consumer` tasks (`CuemsWsServer.project_manager_session`). Anything slow or blocking (project load/save/export, media, DB) goes to `self.executor`, a `ThreadPoolExecutor(max_workers=5)` (there is a `TODO: adjust max workers` on it). **Code that runs in the executor really runs in parallel**, and one operator can start the same action twice (a reload, a second tab, a double click).

**There is no locking anywhere** (no `Lock`/`RLock` in `CuemsWsServer`, `CuemsWsUser`, `CuemsDBProject`, `CuemsDBMedia`), and `db.py` opens one module-level `SqliteDatabase('project-manager.db')` that the pool threads share (how peewee behaves under that is not verified). So the rule for any executor-side code is: **a working path, a temp name or a DB row must not be shared by two runs of the same action.** The known failure (2026-11-24): `CuemsDBProject.export` built its working folder as `<tmp>/<unix_name>`, so two exports of one project collided, the second's `finally` deleted the first's folder, and the first published a valid but incomplete zip with no error anywhere (plan `Plans/2026-11-24-project-export-served-and-cleaned-1amfwm7kana.md` in cuems-RELATIONS). When touching save, media save or upload, ask the question "can this run twice at once?" first. Do not answer it with a lock by reflex: removing the shared state (a private folder per run) is usually the smaller fix.

**The session plumbing is deliberate groundwork for multi-user, not dead code** (Ion, 2026-11-24: it was written as the base to add multi-user later). Do not delete it as unused:
- `check_session` assigns a session id and **reuses it when the client connects with `?session=<uuid>`** (an unknown id gets a new session). `CuemsWsServer.sessions[session_id]` holds `ws` and `loaded_project`.
- `register` calls `load_session`, an intentional **no-op hook** whose commented body would re-send the loaded project to a reconnecting session. `loaded_project` is written (`CuemsWsUser`, on project load and unload) but read by nothing yet.
- Live today: the `users` registry, the user-count broadcast (`notify_users`), and `notify_others_list_changes` / `notify_others_same_project`, which tell the other sessions when a list or the open project changed (`list_update`).
- **Not wired yet:** the UI never sends `?session=` (`cuems-frontend` `websocket.service.ts` reconnects after 10 s with the plain URL, so every reconnect is a new session). Apache already has the matching rule (`RewriteCond %{QUERY_STRING} uri=(.*)$` rewriting `/ws` to `/?session=%1`); whether it wins over the plain `ProxyPass "/ws"` line has not been tested. The `sessions` dict is never purged (no deletion anywhere), so it grows with every connection.
- **Missing for real multi-user:** a user identity and any authorization. Nothing authenticates a client today, here or in the apache vhosts. The accepted boundary is the site WiFi passphrase, and a centralized per-user access control is planned. Anything added now that serves data to clients (the project export zips under `/exports`) should sit where an access control can be put later without moving files.

## Field notes / gotchas

- **Save-time FadeCue validation** (`CuemsDBProject.validate_fade_durations_in_contents`, called in `update()` and `new()` before `CuemsParser`): rejects any FadeCue whose duration is missing, unparseable, or `<= 0` with a single `ValueError` naming the offenders (forwarded verbatim to the frontend over WS). Parsing delegates to the real cuemsutils `CTimecode` — its ms semantics are literal (`'.3'` = 3 ms) and `'00:00:03'` raises `IndexError`, so a private parser would diverge. `duplicate()` is deliberately NOT validated (legacy projects must stay duplicable; the engine's reveal guard covers them).
- **`CUE_TYPES` includes `FadeCue`** (dangling-target cleanup): before the fix, `_collect_cue_ids` ignored FadeCue ids — an ActionCue targeting a FadeCue was wrongly nullified on **every save** — and FadeCue's own dangling `action_target` was never cleaned.
- **After hand-editing `network_map.xml` or `default_mappings.xml`, restart BOTH `cuems-editor` AND `cuems-controller-engine`** (plus `cuems-node-engine` if active). Both daemons cache topology at startup via `ConfigManager(load_all=True)`; there is no on-disk reload. Restarting only the editor leaves the engine on the stale topology. Verify: editor logs `"number_of_nodes": N`.
- **The node list is pushed, not polled by clients.** `watch_network_map` (a 3 s mtime poll, one per host) broadcasts `initial_mappings` whenever **cuems-nodeconf** rewrites `network_map.xml` — which it does on every avahi event or every 30 s, since it is resident. Without this the editor only re-read the map on connect and after its own successful `nodelist_modify`, so a node powered on *after* the operator opened Settings never appeared in `new_nodes` and adoption looked broken exactly when it was needed. `nodelist_get` is the on-demand pull of the same payload; `nodeconf_available` in that payload says whether adoption can work on this host at all (`/tmp/nodeconf.ipc` present — it is absent on most of the fleet, where every adopt/un-adopt click can only fail). Protocol reference: `tests/ws-command-responses.txt`.
- During the nodeconf transition, operators hand-populate `<role_id>`/`<alias>`/`<hostname>` in `network_map.xml`; restart the editor so the merged dict picks up the new fields. `cuems-frontend` falls back to a legacy `Node ${index + 1}` label when both `alias` and `role_id` are absent — partial migrations are safe.
