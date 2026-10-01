<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Data model — 001-cuems-utils-migration

The editor **owns none of the document models**. `CuemsScript`, the config objects, `CTimecode`,
`Uuid`, and `NodeRole` belong to `cuemsutils`. This file is the editor-side view: what it stores
that the library does not, which fields it reads, and the rules it applies. A test that
re-asserts the library's node or script model is a regression (FR-030a-i).

Field shapes for messages are in [contracts/ws-messages.md](contracts/ws-messages.md) and
[contracts/project-payload.md](contracts/project-payload.md). Measurements are in
[research.md](research.md).

## Script document

A project's script file. The filename is `settings` `script_file_name` (`cli.py` default
`script.xml`), under `<library_path>/projects/<unix_name>/`. The directory name is `unix_name`.
The UUID and the display name live in the document and in `project-manager.db`.

| Fact | Where it lives | Editor rule |
|---|---|---|
| `doc_version` | on-disk attribute, read by the library before schema decode | never copied onto a WebSocket payload, never compared with the payload version |
| bytes on disk | the file | unchanged by open. A repaired or converted object reaches disk only through `project_save` (or `project_new` / `duplicate`, which write a path that is not the file just read — see Session acknowledgment) |
| in-memory form | `CuemsScript` from `load_with_report` or `from_json` | the editor does not keep a parallel dict and "fix" it |

### Load outcomes

`load_with_report` returns `(script, LoadReport)` or raises. The editor does not call `load()`.

| Library result | Editor result |
|---|---|
| `Outcome.CLEAN` | `type: project` with `script.to_wire()`, plus `document_load_report` with an empty repair list. `file_differs_from_loaded` is false. No acknowledgment required |
| `Outcome.CONVERTED` or `Outcome.REPAIRED` | same two messages. `file_differs_from_loaded` is true. Milestone 2: `project_save` is refused until this session acknowledges this report |
| `ValidationError` (unrepairable T2, or document newer than the library) | no `project` frame. `document_load_failed` names the path, `violation.location` `(cue_id, field)`, the library message, and the three next steps below. The session stays up. The project remains in the list |
| `SchemaError`, `IngestError`, `OSError` | the existing per-session error path. Not reported as a repair. The file is not written |

Next steps on `document_load_failed`, always all three, because the editor cannot know which
one the operator can carry out:

- `restore_from_conversion_backup`
- `correct_field_by_hand`
- `remove_document`

There is no fourth outcome and no lenient reader.

### What the editor still does to a script object

- **Media duration from the DB**, on the save path (`update`) and inside the repair tool's
  comparison. The library will not fill a duration from `project-manager.db`. The walker
  assigns `CTimecode` on the object. It does not run on open, and it does not edit `to_wire()`
  output.
- **FadeCue duration gate**, on the raw client payload, in `update` and `new` only, before
  `from_json`. Same `ValueError` text as today. `duplicate` does not gain this gate.
- **Dangling `target`**: not touched. The library repairs it and lists it on `LoadReport.repairs`.
- **Dangling `action_target`** (`ActionCue` and `FadeCue`): not cleared. Load raises; save of a
  client payload raises at `CuemsScript.save`.

## `project` payload

The `value` of `{"type":"project"}`. Produced by one call to `script.to_wire()` in the open
path. No later step adds, removes, or reorders keys to achieve an object-level result.

Against a capture taken before the migration, exactly three differences are sanctioned:

| Delta | Old | New |
|---|---|---|
| (a) | `schemaLocation` present | key absent |
| (b) | `Media.duration` a string `HH:MM:SS.mmm` | `{"CTimecode": "HH:MM:SS.mmm"}` |
| (c) | hardware cue key `AudioCue`, `VideoCue`, or `DmxCue`; output key `AudioCueOutput`, `VideoCueOutput`, or `DmxCueOutput` | key `Cue` or `CueOutput`, with `class` inside (`audio`, `video`, `dmx`, or any other string the document carried). `ActionCue`, `FadeCue`, and `CueList` stay their own keys |

Key order is unchanged aside from the absent key and the renamed cue keys. Cue booleans stay the strings `"True"` and
`"False"`. `doc_version` does not appear. Any unlisted difference fails the test. Schema truth is
the XSD under `cuems-utils/src/cuemsutils/xml/schemas/`, enforced by the public load and save.
`tests/golden/xml` may be a superseded snapshot and is not a checksum target (R12). A
contradiction with the XSD is regenerated in `cuems-utils` after the system refactoring.

## Load report and session acknowledgment

### Library report (not owned here)

`cuemsutils.errors.LoadReport`, frozen:

| Field | Meaning |
|---|---|
| `document` | path passed to `load_with_report` |
| `outcome` | `clean`, `converted`, or `repaired` |
| `conversions` | `(from_version, to_version, description, dropped_elements)` each |
| `repairs` | `(field_path, previous_value, substituted_value, rule_name)` each. `field_path` is `"<cue_id>/<field>"` |
| `file_differs_from_loaded` | true when `outcome` is not `clean`. The file on disk was not written |

The library object has no id. The editor assigns `report_id` with `new_uuid()` when it forwards
the report. That id is the acknowledgment key.

### Editor session state

Stored on the session that issued `project_load`, keyed by that session and by project UUID.
Not readable by another session.

| Field | Cleared when |
|---|---|
| `project_uuid` | `project_unload`, session close, or a load of a different project |
| `report_id` | the same, and on every new load of this project (the new report replaces it) |
| `outcome` | the same |
| `file_differs_from_loaded` | the same |
| `acknowledged` | starts false; set true only by `repair_acknowledge` for this `report_id` on this session |

**Save gate** (milestone 2), in the `project_save` handler:

1. If `outcome` is not `clean` and `acknowledged` is false, reply `repair_save_refused` and do
   not call `save`.
2. If `file_differs_from_loaded` is true, `CopyMoveVersioned.move` the on-disk script into that
   project's `trash/`. The destination name must make the project and the date recoverable. If
   the move fails, reply with a refusal and do not call `save`. The original stays where it was.
3. Call `CuemsScript.save` on the object built from the client payload (`from_json`, after the
   DB duration fix and the fade gate).

`duplicate` does not use this gate. It writes `new_unix_name`. The source path is not the
target. The `project_duplicate` reply may include the source report as an optional key.

## Three node facts

These are not one field and not one message.

### Network-map node (library object)

Read from `ConfigManager.network_map["node_list"][i]["node"]` only as the library's own input
shape. On cuemsutils `0.1.0rc16` the entry is `{"node": <node>}`. The editor does not unwrap it.
`partition_by_adoption`, imported from `cuemsutils.tools.NodeList` after the cuems-utils 013
commit is pinned, returns `(adopted, unadopted)`: two tuples of those bare node objects. An
empty side is `()`. Feature 014 does not own `node_list`.

| Field | Type on the object | On the wire, via `to_wire()` |
|---|---|---|
| `uuid` | `Uuid` (uuid4) or the not-provisioned sentinel | string form |
| `node_role` | `NodeRole` | string (`"controller"`, `"node"`, …) |
| `adopted` | `bool` | `"True"` or `"False"` |
| `online` | `bool` | `"True"` or `"False"` |
| `ip`, `name`, `mac` | as the library delivers them | as `to_wire()` delivers them |

The editor compares a JSON identity to a map identity only through `coerce_identity`. It does
not compare `node_role` to a string and does not compare `adopted` to `"True"` once the value
is the typed object. The merge into mapping nodes copies **wire** fields from `to_wire()` so
the `initial_mappings` payload keeps the string booleans. Output blocks on the mapping node
are copied through, including `devices` / `device` / `class`. They are not looked up as
`audio`, `video`, or `dmx`.

`node_type` is not a field. A merge list that still names it drops the role.

### `node_status` (engine relay)

Not a document. `CuemsWsUser.node_status` asks the engine for `cluster_status` and forwards the
dict. `alive` is the sub-second ping/pong set. It is the signal the GO gate trusts. It is not
derived from `online`, and `online` is not overwritten from `alive`. This feature does not
change that message's shape.

### `nodeconf_available` (daemon liveness)

`True` when `/tmp/nodeconf.ipc` exists, computed at message-build time, never cached.

| Milestone | Where it is |
|---|---|
| 1 | still injected into `mappings_dict` on the refresh path and the serve path, so `initial_mappings` does not lose the key |
| 2 | envelope field of `node_list` and of the `nodelist_get` reply, sibling of the node arrays, absent from `project_mappings` and from each node |

It is not a `FieldDescriptor` and it is not written by `config_save`.

## Payload version and `doc_version`

| | Payload version | `doc_version` |
|---|---|---|
| What | editor ↔ UI handshake | on-disk document marker |
| Where | first WebSocket message on connect, `{"type":"payload_version","value": <int>}` | XML attribute; library reads it before decode |
| First value | `1` at the coordinated tag. A connection that sends no such message is version 0, the wire before this feature | whatever the file says; the frontend never sees it |
| Bump | +1 when an existing message loses, renames, or reorders a key, changes a value's type or form, or changes audience. Not bumped for a new message type or a new optional key | the library's version table, not this repository's |

Version 1 means the wire of the coordinated tag: `project` deltas (a) and (b), the
`initial_template` retirement, and the split of `node_list` from `initial_mappings`.

## Schema descriptor (served, not stored)

`ConfigManager.get_schema_descriptor(SchemaName)` returns one `TypeDescriptor` per complex
type: `key`, `fields`, `instance`. Each field has name, XSD type, cardinality (`required`,
`repeated`), enumeration values, model-layer default, and repairability. `instance` is the
constructible empty instance. Callable defaults are `None` in that instance.

`SchemaName` members: `SCRIPT`, `SETTINGS`, `NETWORK_MAP`, `PROJECT_MAPPINGS`,
`PROJECT_SETTINGS`, `HARDWARE_OUTPUTS`. The last is reserved and has no model bindings;
`config_save` rejects it. `generate_example` exists only for `SCRIPT` and `SETTINGS`.

`config_save` persists through the matching `ConfigManager.save_*` method. It does not write
`default_mappings.xml`.
