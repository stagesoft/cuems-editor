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

That is the command on a **bookworm** host. On a Debian 13 (trixie) development machine do not run it: it would target trixie, and dh-virtualenv bakes the host `python3` into the venv. Build inside an unprivileged bookworm chroot instead: `tests/packaging/bookworm-build.sh` (mmdebstrap `--mode=unshare`; needs `mmdebstrap`, subuid/subgid ranges, network). It builds the `cuemsutils` wheel from `../cuems-utils` because PyPI stops at rc14, and checks that the venv's `pyvenv.cfg` says `home = /usr/bin` and the chroot `python3` is 3.11.

## Project store / library — `/opt/cuems_library/`

The authoritative path is `settings.xml <library_path>` (read by the editor as `library_path`). **There is NO `/opt/cuems/` directory** — that was a long-standing doc error; everything project-related is under `/opt/cuems_library/`.

Contents:
- `projects/` — one dir per project, **named by `unix_name`**. The project UUID and display `name` live *inside* `script.xml` and in the index DB, **not** in the dir name.
- `media/`, `trash/`.
- `project-manager.db` — SQLite index (tables `project`, `media`, `projectmedia`).

## Field notes / gotchas

- **Save-time FadeCue validation** (`CuemsDBProject.validate_fade_durations_in_contents`, called in `update()` and `new()` before `CuemsParser`): rejects any FadeCue whose duration is missing, unparseable, or `<= 0` with a single `ValueError` naming the offenders (forwarded verbatim to the frontend over WS). Parsing delegates to the real cuemsutils `CTimecode` — its ms semantics are literal (`'.3'` = 3 ms) and `'00:00:03'` raises `IndexError`, so a private parser would diverge. `duplicate()` is deliberately NOT validated (legacy projects must stay duplicable; the engine's reveal guard covers them).
- **Dangling targets are the library's, not the editor's** (001): the editor's `_clean_dangling_targets` walk and its cue-type list are deleted. `cuemsutils` `target_resolves` repairs a dangling `Cue.target` on load; `action_target_resolves` refuses a dangling `action_target` (ActionCue and FadeCue) on load and at `CuemsScript.save`. Do not reintroduce a walk keyed on cue names: after cuems-utils 013 hardware cues are `Cue` with `class`, and the old walk nulled valid targets on every save.
- **`cuems-editor-repair-durations` never writes a script** (001, FR-027a). It corrects `media.duration` in the DB (pass A) and lists projects whose scripts still hold a different duration as `NEEDS_SAVE`. Script files change only when an operator opens the project in the editor and saves it; until that save, the engine plays the file on disk, short durations included. A script still in the pre-013 device shape is `SKIPPED_INVALID`: run `cuems-reshape-devices` over the whole library, then save in the editor.
- **After hand-editing `network_map.xml` or `default_mappings.xml`, restart BOTH `cuems-editor` AND `cuems-controller-engine`** (plus `cuems-node-engine` if active). Both daemons cache topology at startup via `ConfigManager(load_all=True)`; there is no on-disk reload. Restarting only the editor leaves the engine on the stale topology. Verify: editor logs `"number_of_nodes": N`.
- **The node list is pushed, not polled by clients.** `watch_network_map` (a 3 s mtime poll, one per host) broadcasts `node_list` (before payload version 1: `initial_mappings`) whenever **cuems-nodeconf** rewrites `network_map.xml` — which it does on every avahi event or every 30 s, since it is resident. Without this the editor only re-read the map on connect and after its own successful `nodelist_modify`, so a node powered on *after* the operator opened Settings never appeared in `new_nodes` and adoption looked broken exactly when it was needed. `nodelist_get` is the on-demand pull of the same payload; `nodeconf_available` in that payload (an envelope field, sampled per frame, absent from `initial_mappings`) says whether adoption can work on this host at all (`/tmp/nodeconf.ipc` present — it is absent on most of the fleet, where every adopt/un-adopt click can only fail). Protocol reference: `tests/ws-command-responses.txt`.
- During the nodeconf transition, operators hand-populate `<role_id>`/`<alias>`/`<hostname>` in `network_map.xml`; restart the editor so the merged dict picks up the new fields. `cuems-frontend` falls back to a legacy `Node ${index + 1}` label when both `alias` and `role_id` are absent — partial migrations are safe.
