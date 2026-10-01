<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract — WebSocket messages this feature adds or splits

Transport is unchanged: JSON text frames on `:9092`, `{"action": ...}` inbound and
`{"type": ...}` outbound, except the binary file frames that already exist. Audience is part of
the contract (constitution II).

`tests/ws-command-responses.txt` is updated in the same commit as any frame below. An unknown
`type` is ignored by today's UI, so a new type may be emitted before `cuems-frontend` 05 renders
it. Removing or reshaping a key of an existing type may not (FR-050).

Payload version and `doc_version` are different numbers. See
[data-model.md](../data-model.md).

## Payload version (milestone 2)

| | |
|---|---|
| Direction | server → the connecting client |
| When | the first frame on that connection, before `initial_template`, `initial_mappings`, `session_id`, or anything else |
| Shape | `{"type":"payload_version","value": 1}` |
| Audience | that client |
| Bump | integer, +1 only. Bump when an existing message loses, renames, or reorders a key, changes a value's form (including the string boolean), or changes audience. Do not bump for a new `type` or a new optional key. Each bump is a row in `tests/ws-command-responses.txt` |
| Absence | a peer that never sends this type is version 0, the wire before this feature |

Version 1 is the coordinated-tag wire: `project` deltas (a) and (b), `initial_template` retired,
`node_list` split out of `initial_mappings`. A test fails if the advertised integer changes
without that row.

The UI's refusal of a version it was not built for is `cuems-frontend` 05's obligation. This
repository only sends the integer and does not disconnect an old client by itself in milestone 1,
because milestone 1 does not send the integer yet.

## `document_load_report` (milestone 2)

Sent on every successful `project_load`, including a clean one. Never omitted and never `null`.

| | |
|---|---|
| Direction | server → the session that loaded |
| Audience | that session only |
| Shape | `{"type":"document_load_report","value": { ... }}` |

`value`:

| Key | |
|---|---|
| `report_id` | string, editor-assigned (`new_uuid`) |
| `project_uuid` | the project that was opened |
| `document` | path the library reported |
| `outcome` | `"clean"`, `"converted"`, or `"repaired"` |
| `file_differs_from_loaded` | bool, JSON `true`/`false` (this key is editor state about the file, not a `cms:BoolType` field) |
| `conversions` | list of `{from_version, to_version, description, dropped_elements}` |
| `repairs` | list of `{field_path, previous_value, substituted_value, rule_name}` |

`previous_value` and `substituted_value` are JSON-safe renderings of the library values (string
form of a `CTimecode`, `null` for `None`). The editor does not invent repairs the library did
not return.

## `document_load_failed` (milestone 2)

Sent instead of `type: project` when `load_with_report` raises `ValidationError`.

| | |
|---|---|
| Direction | server → the session that loaded |
| Audience | that session only |
| Shape | `{"type":"document_load_failed","value": { ... }}` |

`value`:

| Key | |
|---|---|
| `project_uuid` | the project that was requested; the list entry is unchanged |
| `document` | path |
| `cue_id` | string or `null` (document-scoped, including a too-new document) |
| `field` | string or `null` |
| `message` | `str(violation)`, library text, not rewritten |
| `next_steps` | `["restore_from_conversion_backup", "correct_field_by_hand", "remove_document"]` |

The session is not closed. No second read is attempted with a permissive parser.

## `repair_acknowledge` (milestone 2)

| | |
|---|---|
| Direction | client → server |
| Shape | `{"action":"repair_acknowledge","value": {"project_uuid": "...", "report_id": "..."}}` |
| Effect | if both match the session's current load, set `acknowledged`. Otherwise `repair_save_refused` (or the existing error frame if the session has no report) |
| Audience of the reply | that session only |
| Reply on success | `{"type":"repair_acknowledge","value": {"project_uuid": "...", "report_id": "..."}}` |

Does not write the file.

## `repair_save_refused` (milestone 2)

| | |
|---|---|
| Direction | server → the session that sent `project_save` |
| When | that session's current report for that project is not `clean` and has not been acknowledged, or the `trash/` copy failed |
| Audience | that session only |
| Shape | `{"type":"repair_save_refused","value": {"project_uuid": "...", "report_id": "...", "reason": "unacknowledged" \| "preserve_failed"}}` |

`preserve_failed` means the original is still in place and `save` was not called. Another
session's acknowledgment does not clear this.

On `reason: "unacknowledged"` the first successful save after acknowledgment, when
`file_differs_from_loaded` is true, has already moved the original into `trash/` (see
[data-model.md](../data-model.md)). There is no further backup inside `CuemsScript.save`.

## `network_map_error` (milestone 1)

New type, so it does not bump the payload version.

| | |
|---|---|
| Direction | server → all connected sessions, and to each session on connect while the error stands |
| Audience | all sessions |
| Shape | `{"type":"network_map_error","value": {"kind":"duplicate_identity","identity":"<string>","file":"<path>"} }` or `{"type":"network_map_error","value": null}` for the clear |

`identity` is the string form (FR-034). The last good node list continues to be served on
`initial_mappings` until a later read succeeds. That success broadcasts `value: null` and then
the usual node refresh. The editor does not retry the colliding read.

## `initial_template` (milestone 1, retired in milestone 2)

Unchanged message type and envelope: `{"type":"initial_template","value":{"CuemsScript": ...}}`.
The value becomes `ConfigManager.generate_example(SchemaName.SCRIPT)`. Deltas against the
reconstructed `create_script()` baseline are enumerated in `tests/ws-command-responses.txt`
before the switch. Milestone 2 stops sending this type, behind payload version 1. The
replacement data is the descriptor, not a renamed template.

## `schema_descriptor` / `config_save` (milestone 2)

Modelled on `initial_mappings` (serve) and `nodelist_modify` (accept a mutation). Not on
`initial_template`.

**Serve**

| | |
|---|---|
| Inbound | `{"action":"schema_descriptor","value": "<SchemaName value>"}` — one of `script`, `settings`, `network_map`, `project_mappings`, `project_settings`, `hardware_outputs` |
| Outbound | `{"type":"schema_descriptor","value": {"schema": "<name>", "types": [ ... ]}}` |
| Audience | the caller |
| Source | `ConfigManager.get_schema_descriptor(SchemaName(name))` only |

Each type in `types` has `key`, `fields`, and `instance`. Each field has `name`, `xsd_type`,
`required`, `repeated`, `order`, `kind`, `enum_values`, `default`, `repairability`. `instance`
is the descriptor's constructible empty instance. The editor does not reshape field objects to
add behaviour.

**Accept**

| | |
|---|---|
| Inbound | `{"action":"config_save","value": {"schema": "<name>", "document": { ... }}}` |
| Outbound | `{"type":"config_save","value":"OK"}` or the existing error frame |
| Audience | the caller. A successful `network_map` save also runs the usual all-session node refresh, same as `nodelist_modify` already does |
| Writes | `save_settings`, `save_network_map`, `save_project_mappings`, `save_project_settings` |

Rejected schemas: `script` (that remains `project_save`), `hardware_outputs` (no model
bindings), and anything that is not a `SchemaName`. `default_mappings.xml` is not a target.
The document is applied through the `ConfigManager` object, not by editing a wire dict and
hand-writing XML.

## `initial_mappings` and `node_list`

**Milestone 1.** `initial_mappings` stays the entangled payload: project output mappings, merged
network-map node status (`nodes` / `new_nodes`), and `nodeconf_available`. Node status inside
it uses `to_wire()` field forms (`node_role`, string booleans, string uuid). Output blocks stay
from the mapping node. This is not a key removal, so it is not the untangling.

**Milestone 2**, only once `payload_version` is sent first:

| Message | Carries | Does not carry |
|---|---|---|
| `initial_mappings` | project output mappings | node arrays, `nodeconf_available` |
| `node_list` | `nodes`, `new_nodes`, and envelope `nodeconf_available` | project output mappings |

`node_list` is pushed to all sessions from `watch_network_map` and returned to the caller from
`nodelist_get`. `nodeconf_available` is sampled when the frame is built.

Frontend hand-over, by file, for the split and for the `localStorage` cache of
`initial_mappings`:

- `cuems-frontend` `src/app/components/settings/settings.component.ts`
- `src/app/components/projects/project-show/audio-mixer/audio-mixer.component.ts` (line 80)
- `src/app/components/projects/project-show/video-mixer/video-mixer.component.ts` (line 94)

## Unchanged on purpose

| Message | Why it stays |
|---|---|
| `node_status` | relay of engine `cluster_status`. `alive` is not `online` |
| `nodelist_modify` | OK / error strings forwarded as the engine sent them, including `Node <uuid> not found` during nodeconf's readiness window. No retry added here |
| `project_duplicate` | gains an optional `report` object, same shape as `document_load_report`'s `value`, when the source load was not clean. Old readers ignore the key. The source file is not overwritten |
