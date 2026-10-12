<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract: WebSocket messages this feature adds or changes

The transport is unchanged: JSON text frames on `:9092`, `{"action": …}` inbound and
`{"type": …}` outbound. Audience is part of the contract (constitution II).
`tests/ws-command-responses.txt` is updated in the same commit as any frame below (Principle I).

**Payload version stays 1.** Every **new** `type` below needs no bump. The **changed** frames
(`config_save`'s reply and the JSON booleans) are folded into the restated version 1 (spec S2,
M3, FR-002), because version 1 has not shipped.

`revision` is a 32-hex-character md5 of the file's bytes, or `null` for "no file". It is never
`doc_version`, and never the payload version.

---

## Restated version 1: the row that replaces `ws-command-responses.txt:68-71`

```text
payload_version 1: the coordinated xml-refactor-merge-candidate wire. It has
not shipped, so it was restated on 2026-10-12 rather than bumped, and the
restatement is the definition: every boolean on the wire is a JSON true /
false. A client built for version 1 needs no "True" / "False" handling.

Contents: project deltas (a) (b) (c) (d) (e); initial_template not sent;
node_list carries the node arrays and nodeconf_available, and initial_mappings
no longer does; adopted / online on node_list nodes and autoload / enabled /
timecode on project are JSON booleans (8f8b46e, folded in, not bumped);
config_save's reply is an object {schema, project_uuid, revision, restart},
not "OK" (002, folded in, not bumped).
```

## `config_load`: new

| | |
|---|---|
| Inbound | `{"action": "config_load", "value": {"schema": "<name>", "project_uuid": "<uuid>"}}`. `project_uuid` is required for `project_mappings` and `project_settings`, and ignored otherwise |
| Reply | `{"type": "config_load", "value": {"schema", "project_uuid", "exists", "revision", "document"}}` |
| Audience | the caller only |
| `exists: true` | `revision` is the file's md5. `document` is `ConfigManager.to_wire(section)` on a manager loaded for this request |
| `exists: false` | `revision: null`. `document` is the descriptor `instance` of the domain's root type (the one whose key has no `/`). **It is a starting point for a form, not saveable as-is.** Required leaves are `null`, and `network_map`'s instance is not in `to_wire` shape (`cuems-frontend` UR-1, research R4). Saving it unedited gets `config_save_refused` |
| Domains | `settings`, `network_map` (read only), `project_mappings`, `project_settings` (refused with the error frame naming `cuems-editor` UR-7 until gate G2 flips) |
| Library refusal | `config_load_failed` (shape as `config_save_refused`), e.g. a `settings.xml` in the pre-013 device shape |
| Other failures | the error frame: unknown schema, missing or unknown `project_uuid`, I/O |

## `config_save`: changed

| | |
|---|---|
| Inbound | `{"action": "config_save", "value": {"schema", "document", "base_revision", "project_uuid"?}}`. **`base_revision` is required** (Q3): the `revision` from `config_load`, or `null` meaning "I expect no file" |
| Reply (success) | `{"type": "config_save", "value": {"schema", "project_uuid", "revision", "restart"}}`. `revision` is the md5 of the file just written. `restart` is `[{"service": "cuems-controller-engine", "where_active": false}, {"service": "cuems-node-engine", "where_active": true}]` for `settings`, and `[]` otherwise. **Changed from `"OK"`, folded into version 1** |
| Audience | the caller (the reply). The other sessions get `config_changed` |
| Conflict | `config_conflict` (below). Nothing is written |
| Library refusal | `config_save_refused` (below). Nothing is written |
| Refused (error frame) | missing `base_revision`; `network_map` ("network_map.xml is written by cuems-nodeconf; set an alias with node_set"); `script`; `hardware_outputs`; non-schema names; `default_mappings.xml`; missing or unknown `project_uuid` |
| Removed | the all-session node refresh after a `network_map` save, along with that save |

The document is always whole (S4). The client must take the new revision from this reply and must
not compute it: a save re-indents the XML, upgrades `doc_version` and rewrites `schemaLocation`
(FR-023). `from_json('settings')` takes the fields one level deeper than `to_wire('settings')`
returns them, by design.

## `config_conflict`: new

| | |
|---|---|
| Shape | `{"type": "config_conflict", "value": {"schema", "project_uuid", "revision", "document"}}`, carrying the **current** revision and document (`exists: false` is expressed as `revision: null` with the instance) |
| Audience | the caller only |
| When | the file's md5, taken under the per-file lock, differs from `base_revision` |

## `config_save_refused` / `config_load_failed`: new

| | |
|---|---|
| Shape | `{"type": "config_save_refused" \| "config_load_failed", "value": {"schema", "project_uuid", "field", "location", "rule", "message"}}` |
| `field` | `violation.location[1]`, or `null` |
| `location` | `violation.location` as a list (for example `[null, "node_role"]`), or `null` when the library gives no violation |
| `rule` | `violation.rule` (for example `"XsdEnumerationFacets"`), or `null` |
| `message` | the library's text, verbatim. Clients display it and never parse it |
| From | `IngestError`; `SchemaError` / `ValidationError` raised by `from_json` or by `.save()` (T1 runs at save, research R5) |
| Audience | the caller only |

## `config_changed`: new

| | |
|---|---|
| Shape | `{"type": "config_changed", "value": {"schema", "project_uuid", "revision"}}` |
| Audience | **every session except the saver** |
| Meaning | your copy is stale. Re-run `config_load` before editing. It carries no document |

## `node_set`: new

| | |
|---|---|
| Inbound | `{"action": "node_set", "value": {"node_uuid": "<uuid>", "alias": "<text>" \| null}}`. `null` removes the alias |
| Reply (success) | `{"type": "node_set", "value": {"node_uuid", "alias"}}` to the caller, then `node_list` to **all** sessions (as after `nodelist_modify`) |
| Refusal | `{"type": "node_set_refused", "value": {"node_uuid", "reason", "message"}}`, caller only. `reason` is one of: `unavailable` (no nodeconf socket on this host; answered at once, no IPC), `timeout`, `nodeconf_error` (`message` is nodeconf's `error`, verbatim, not retried), `not_operator_field` (the request carried a field the operator does not own) |
| Never | written to `network_map.xml` by the editor, on any path |
| IPC | [nodeconf-node_set.md](nodeconf-node_set.md) |

## `document_load_report`: two new optional keys (spec Q6, Q7, FR-043, FR-044)

```text
{"type": "document_load_report", "value": {
   "report_id", "project_uuid", "document",
   "outcome": "clean|converted|repaired",            # the library's verdict, verbatim
   "file_differs_from_loaded": bool,                 # library flag OR media_repairs non-empty
   "conversions": [...], "repairs": [...],           # the library's, verbatim
   "media_repairs": [{"cue_id", "file_name",
                      "field": "duration|pixel_size|file_size|file_md5",
                      "stored": "<as in the file>",
                      "current": "<library row>" | null}],   # null: the save removes it
   "acknowledgment_required": bool                   # outcome != clean OR media_repairs non-empty
}}
```

- New optional keys, so no payload-version bump.
- `media_repairs` is always present: `[]` when nothing is stale.
- A client gates its save UI on `acknowledgment_required`, not on `outcome`.
- `media_repairs` lists values **present** in the file that differ from the library. A value the
  file lacks (a pre-rc15 project) is added by the next save and is never listed.
- The deferred media check, when it exists, adds its findings here. It sends no gating frame of its
  own (FR-046).
- `project_duplicate`'s optional `report` has the same shape.

## Repair gate frames: unchanged shapes, new durability

`repair_acknowledge` and `repair_save_refused` keep their shapes. What changes (spec US1,
FR-006 to FR-011, FR-045):

- The gate is per project. Each session acknowledges for itself, and that acknowledgment survives
  a reconnect that re-uses the `session_id`.
- A session that never loaded the project, or a save after an editor restart, is refused while the
  file on disk is not clean. The refusal's `report_id` is the one `project_load` returns.
- A file changed on disk since the report, or a library media row changed since it, invalidates the
  report. A new `report_id` is issued, and every acknowledgment is dropped.
- The gate covers media entries too: a project with only `media_repairs` is refused until it is
  acknowledged, and its original is moved to the trash before the first save.
- `repair_acknowledge` from a reconnected session answers with the echo, not the error frame.
- The `ws-command-responses.txt:169-175` text is replaced. It also states that `cuems-frontend`'s
  reload-on-reconnect (`load-report.service.ts`) is no longer needed.

## Documentation-only rows (no wire change)

- `project_save`: `value` is `{"CuemsScript": …}` and nothing beside it (FR-029).
- `schema_descriptor`: building from `instance` is not directly usable until `cuems-frontend` UR-1
  is fixed. `network_map`'s node `uuid` is rendered as a one-value enumeration (the NOT
  PROVISIONED sentinel); render it as text (FR-028, FR-031).
