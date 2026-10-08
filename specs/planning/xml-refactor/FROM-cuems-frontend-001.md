<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# From `cuems-frontend` 001 — what the consuming end measured about this editor

**From** `cuems-frontend` `feat/xml-refactor`, feature `001-schema-descriptor-migration`, tag
`xml-refactor-merge-candidate` (local, 2026-10-07). **Measured** against this repository's
`feat/xml-refactor` @ `22093fd` (unchanged at the time of writing) and `cuems-utils` @ `69acaef`
(its 014 branch). `cuems-utils` has since reached `67c89bd`
(`file_hash` → `file_md5`, `Md5Type`): an optional `Media` field the frontend never writes, so
nothing below changes; the descriptor fixture the frontend recorded at `69acaef` still says
`file_hash`.

**Not a numbered report.** The `UR-N` files in this directory are this editor's own findings,
addressed to `cuems-utils`. This file runs the other way: findings a *consumer* addressed to this
editor, filed here so they sit beside the reports they touch (UR-5, UR-6). Numbers in these
repositories are per repository and collide, so `cuems-frontend` UR-1 / UR-2 below are that
repository's, not this one's.

The consumer's index of every upstream gate, with the code that stands in for each answer:
`../cuems-frontend/specs/001-schema-descriptor-migration/upstream-gates.md`. Each item below names
the frontend finding it comes from (`findings.md`, F-numbers).

---

## 1. The boolean form changed without a payload-version bump

**Observed.** `8f8b46e` (`feat(014): T032 — xs:boolean gate`) moved `adopted` / `online` on
`node_list`, and `enabled` / `autoload` / `timecode` on `project`, from `"True"` / `"False"` to
JSON `true` / `false`. `CuemsWsServer.PAYLOAD_VERSION` is still `1`
(`src/cuemseditor/CuemsWsServer.py:234`).

**Against this repository's own rule.** `tests/ws-command-responses.txt:62-64`: "Bump +1 when an
existing message … changes a value's form (the string booleans included)".

**Consequence.** Two different wires both announce version 1, and a client cannot tell which it
got. `cuems-frontend` therefore keeps a dual read on both sides of 014 (cue intake
`enabled === true || enabled === 'True'`; node adoption `online === true || online === 'True'`) and
cannot retire the string half. (frontend F5, F6)

**Expected.** Version 2 for the 014 wire, with its row in `ws-command-responses.txt` and
`tests/test_payload_version.py` — or the rule restated if the ecosystem decides 014 does not count
as a form change. Either way, one statement a client can act on.

## 2. A reconnect drops the repair gate

**Observed.** The repair gate lives on the per-connection `CuemsWsUser`: `self.repair_state` is
`None` at construction (`src/cuemseditor/CuemsWsUser.py:197`) and set only by `send_project`
(`:809`, `:819`). After a WebSocket reconnect the new session has no state, so for a project the
*previous* connection opened as `repaired` or `converted`:

- `received_project` finds no state (`:913-915`), so `project_save` is **accepted without an
  acknowledgement**;
- `preserve` is computed from that state (`:918`), so the original file is **not moved into the
  library trash** before the repaired document is written over it;
- a re-sent `repair_acknowledge` answers the error frame "no load report to acknowledge on this
  session" (`:855-857`), not the echo.

**Consequence.** The case the load-report design exists to prevent — a repaired document
overwriting the original unseen — is reachable by any dropped socket. `cuems-frontend`'s planned
path (re-acknowledge and retry once when a refusal names a report the operator already
acknowledged) cannot fire, because no refusal comes. (frontend F22)

**Stand-in on the consumer side.** On every reconnect `cuems-frontend` re-sends `project_load` for a
project whose last report was not clean, so this editor rebuilds its state; the new report is shown
and must be acknowledged again (`src/app/services/projects/load-report.service.ts`).

**Expected.** The gate keyed by something that outlives one socket. `server.sessions[session_id]`
already carries `loaded_project` across connections (`project_unload`, `:515-518`, clears both
together) and is a natural home for `repair_state` too. Or: refuse `project_save` for a project
whose last load in *any* session was not clean and not acknowledged. Then the consumer's reload can
go.

## 3. No action reads a config document — `cuems-frontend` UR-2

**Observed.** The action map (`src/cuemseditor/CuemsWsUser.py:258-284`) has `config_save` for all
four config domains (UR-5, closed) but nothing that returns a document's contents.
`schema_descriptor` serves the schema; `initial_mappings` is `default_mappings.xml`
(`cli.get_mappings`), which is neither a project's `mappings.xml` nor a `config_save` target;
`node_list` is the merged node view, not the `network_map` document.

**Consequence.** A client can describe a config document but not show what the controller holds,
and `config_save` replaces the whole document, so an editing form would overwrite a working
configuration with blanks or defaults. `cuems-frontend` ships the settings, project-settings and
project-mappings views read-only and descriptor-only, and fails its own test gate on any
`config_save`. (frontend F27, R10)

**Expected.** Filed in full as
`../cuems-frontend/specs/001-schema-descriptor-migration/upstream-reports/UR-2-no-config-document-read.md`:
a `config_load` symmetric to `config_save`, returning the document in the JSON form `config_save`
accepts, `project_uuid` required for the two project domains as `config_save` requires it, and an
explicit "no document yet" rather than the error frame for a project file never saved. The library
side looks sufficient already — `ConfigManager.load_network_map`, `load_project_settings`,
`load_project_mappings` (`../cuems-utils/src/cuemsutils/tools/ConfigManager.py:374`, `:494`, `:554`),
and `load_project_settings` already tolerates a missing file — so unlike UR-5 this may need nothing
from `cuems-utils`. The "no document yet" case is UR-6's missing-file state seen from the read side.

## 4. Building from the descriptor `instance`, as this repository advises, cannot produce a saveable cue

**Observed.** `tests/ws-command-responses.txt:69-70` and `:95` and
`evidence/frontend-handover.md:44` tell clients to build new scripts from
`schema_descriptor("script")`'s per-type `instance`. Run through this editor's own save path
(`CuemsDBProject.update` → `CuemsScript.from_json(data)` at `src/cuemseditor/CuemsDBProject.py:413`,
then `.save`), a cue built that way is refused, for two reasons:

- the instance is not in `to_wire()` shape (no `CueOutput` wrapper; `{"channel": [...]}` where the
  wire has `[{"channel": {...}}]`; the cue's example output carries `class: null`) — reported to
  cuems-utils as `cuems-frontend` UR-1;
- several **required** output fields have a **null** descriptor default — `AudioCueOutputsType.output_vol`,
  `AudioChannelType.channel_num` / `channel_vol`, `VideoOutputGeometryType.x_scale` / `y_scale`,
  `Coordinates.x` / `y` — so even a correctly shaped output is refused until a client invents values.
  Also: an alias video output must carry **no** `canvas_region`, which the instance includes.

**Stand-in on the consumer side.** One transform tagged UR-1 (`toWireShape`) plus one constant of UI
starting values (the old template's 80 / 1 / 0) where a required default is null. Measured: the
resulting payload saves and reloads clean through this repository's save path. (frontend F12, F18)

**Expected here.** The advice in `ws-command-responses.txt` and the handover qualified — the
instance is not directly usable until `cuems-frontend` UR-1 is answered — so the next consumer does
not rediscover it. The fix itself is cuems-utils'.

## 5. Any key beside `CuemsScript` is refused on save — worth one line in the frame list

**Observed.** `CuemsScript.from_json` (`../cuems-utils/src/cuemsutils/cues/CuemsScript.py:577` at
`67c89bd`; called at `CuemsDBProject.py:413`)
refuses a payload with any top-level key but `CuemsScript`:
`IngestError: expected a CuemsScript payload; the mapping declares none of [...] (got
['CuemsScript', 'uuid'])`. `received_project` passes the payload through unstripped. The pre-001
frontend sent a top-level `uuid` (and display decorations) on every save, so against this tip every
save was refused independently of the cue keys. (frontend F15; recorded refusal texts in
`../cuems-frontend/specs/001-schema-descriptor-migration/fixtures/project-save-refusals.json`)

**Expected.** Not a defect. Delta (a) already says `schemaLocation` is absent; one line beside
`project_save` in `ws-command-responses.txt` — "`value` is `{"CuemsScript": …}` and nothing beside
it" — would state the rule for every key at once.

## 6. `evidence/project-capture/capture_load.py` no longer runs

**Observed.** It calls `CuemsDBProject.load_xml` (`capture_load.py:12`), which now returns
`(CuemsScript, LoadReport)`; the following `json.dumps` raises `TypeError: Object of type LoadReport
is not JSON serializable`. The script that produced `script_minimal.frame.json` cannot reproduce
the tip's `project` frame.

**Workaround taken by the consumer.** `../cuems-frontend/specs/001-schema-descriptor-migration/fixtures/capture/capture_tip.py`
mirrors `CuemsDBProject.open` and imports this repository's own `load_report_value` /
`schema_descriptor_value` / `load_failed_value`.

**Expected.** Low impact — evidence tooling. A note in `project-capture/README.md`, or the script
updated to `script, report = …; script.to_wire()`.

## 7. Status of `evidence/frontend-handover.md`

Every row of the handover (line numbers measured at `cuems-frontend` `3183845`) is consumed by
`cuems-frontend` 001 at `xml-refactor-merge-candidate`: `schemaLocation` gone from the interface and
from every save; `initial_template` and its cache deleted; the per-type cue keys replaced by
`Cue` / `CueOutput` + `class`; `payload_version` read and a mismatch refused; the cache namespaced and
evicted on version change (the two mixers no longer read storage); `node_list` and
`network_map_error` consumed; `document_load_report`, `repair_acknowledge`, `repair_save_refused`
and `document_load_failed` rendered. The one row the frontend could not follow as written is the
`schema_descriptor` advice (item 4).
