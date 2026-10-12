<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Data model — 002-config-round-trip

Everything here is **editor state in memory** or a **wire value**. This feature adds no database
table, no new file format, and no field to any schema. The library owns the documents (Principle V).
The editor owns only the bookkeeping around them.

## GateState (server, per project): the repair gate

Held in `server.repair_gates[project_uuid]`. It replaces `CuemsWsUser.repair_state`, which is
deleted. It is read and written only on the event-loop thread.

| Field | Type | Meaning |
|---|---|---|
| `project_uuid` | `str` | the key, repeated for logging |
| `report_id` | `str` (uuid4) | the outstanding report's id. It is minted when the state is derived, and **re-used** by `project_load` while `file_md5` still matches (R8.5) |
| `outcome` | `"clean"`, `"converted"` or `"repaired"` | `LoadReport.outcome.value` |
| `file_differs_from_loaded` | `bool` | from the report: whether the file on disk is stale |
| `file_md5` | `str` | md5 of the script file's bytes that this report describes |
| `preserved` | `bool` | whether the stale original is already in the trash. This makes one move per stale file |
| `acknowledged_by` | `set[str]` | the `session_id`s that acknowledged **this** `report_id` |
| `report` | `LoadReport` | kept so that a re-sent `document_load_report` is identical |

**Transitions**

```text
(absent) --project_load / project_save with no state--> derive(file)
derive(file):  read bytes -> md5 -> load_with_report
               outcome clean  -> CLEAN(file_md5)
               otherwise      -> PENDING(new report_id, acknowledged_by = {})

PENDING --repair_acknowledge(session, report_id matches)--> PENDING(+session)
PENDING --project_save(session)-->
    re-hash != file_md5      -> derive(file); refuse unless now CLEAN
    session not acknowledged -> refuse "unacknowledged"
    acknowledged             -> claim preserved if file_differs and not preserved;
                                update(); -> CLEAN(new md5)
    preserve failed          -> refuse "preserve_failed", preserved = False
CLEAN   --project_save--> update() (no hash, no load) -> CLEAN(new md5)
any     --project_unload(session)--> acknowledged_by -= {session};
                                     drop if no session has loaded_project == uuid
any     --project_delete-->          drop
```

Invariants:
- A `PENDING` state never lets a session write unless that `session_id` is in `acknowledged_by`
  (001 FR-021).
- Every write of a stale file is preceded by a successful preserve (001 FR-021a).
- An editor restart empties the table, and the first save re-derives the state from the file
  (FR-009).

## Revision: a config document's change detector

| Field | Type | Meaning |
|---|---|---|
| `revision` | `str` (32 hex characters) or `null` | `hashlib.md5(file bytes).hexdigest()` at read time. `null` means "no file" |

- It is opaque to clients, and it is never compared with `doc_version` or with the payload version.
- It is computed in the executor.
- It is recomputed under the path lock immediately before every write.

## ConfigTarget: one row per config domain

This extends today's `CONFIG_SAVE_TARGETS`. It is static.

| `schema` | file | scope | `config_load` | `config_save` | `restart` on save |
|---|---|---|---|---|---|
| `settings` | `settings.xml` | controller (`conf_path`) | yes | yes | `["cuems-controller-engine", "cuems-node-engine"]`, the second marked `where_active` |
| `network_map` | `network_map.xml` | controller (`conf_path`) | yes (read only) | **refused**: use `node_set` | (none) |
| `project_mappings` | `mappings.xml` | project (`project_path`) | yes | yes | `[]` |
| `project_settings` | `settings.xml` | project (`project_path`) | **gate G2**: refused, naming `cuems-editor` UR-7 | yes (first save gated by G1) | `[]` |

The load steps per domain are given in [research.md](research.md) R2. Still refused, unchanged:
`script`, `hardware_outputs`, non-schema names, and `default_mappings.xml`.

## FileLocks (server)

`server.file_locks: dict[str, asyncio.Lock]`, keyed by `os.path.realpath(path)`. Entries are
created lazily on the loop thread. One table serves both document families: config documents
(`config_save`) and script files (`project_save`). Nothing is evicted; the key set is bounded by the
number of projects and four config files.

## Restart notice

`restart: list[{"service": str, "where_active": bool}]` in the `config_save` reply. `where_active`
is `true` for `cuems-node-engine`: the editor cannot observe whether it runs on a host, so the
operator decides.

## Node operator fields

`node_set` carries `alias` only (`str`, non-empty, or `null` to remove it). These fields are
refused before any IPC: `uuid` (as a change), `mac`, `name`, `node_role`, `ip`, `online`,
`adopted`, `role_id`, `hostname`. Ownership follows `cuems-common` `docs/node-identity-contract.md`
(spec M7).
