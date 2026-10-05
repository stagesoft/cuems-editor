<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-5 — No public way to build a config document from JSON (resolved upstream by cuems-utils 014)

**From** cuems-editor 001 (T059), 2026-10-02. cuemsutils `0.1.0rc16` @ `6213b16`.

**Observed.** cuems-utils 008 gave every config domain a save: `ConfigManager.save_settings`,
`save_network_map`, `save_project_mappings`, `save_project_settings`. Each writes the object the
`ConfigManager` already holds. For scripts the inbound direction exists (`CuemsScript.from_json`,
with ingest and decode-time T1). For config documents it does not:

- `ConfigDict.from_decoded` is on an internal class (`cuemsutils.config.base`), takes the *decoded*
  document shape rather than the wire shape, and by design stores values verbatim. For
  `network_map` the adapters run before it, in the mapper, so a wire `"node_role": "node"` would stay
  a string where the saved object expects a `NodeRole`.
- The `network_map` property setter accepts a `dict`, but `save_network_map` then calls `.save` on
  it.
- `validate_config_document(path)` validates a file, not a payload.

**Why the editor needs it.** `config_save` (FR-045) accepts a document a client edited from the
schema descriptor's `instance` and must persist it through the matching `save_*`. Without a public
JSON → object call the editor would either import `cuemsutils.config` (Q14) or hand-build an object
or XML (a second decoder). It does neither.

**Workaround taken.** `config_save` refuses `script`, `hardware_outputs`, non-schemas and
`default_mappings.xml` as specified, and answers the four config domains with an error naming this
report. `tests/test_schema_descriptor.py::test_config_save_of_settings_persists_through_save_settings`
is `xfail(strict=True)` and starts failing as XPASS the day the library offers the call.

**Expected.** One public ingestion per config domain, symmetric with `CuemsScript.from_json` —
e.g. `ConfigManager.from_json(SchemaName, payload)` returning the root object `save_*` writes, or a
`ConfigManager.set_document(SchemaName, payload)` that decodes through the same mapper and adapters
as `load_*`.

**Resolved by.** cuems-utils 014 adds exactly the expected call.

| | |
|---|---|
| Pinned commit | `429f8d279d634f153be8feb938de3c4e88c61230` |
| Subject | `feat(014): phases 3 and 4 — the public config ingestion, the release note, the budgets` |
| Signature | `ConfigManager.from_json(schema: SchemaName, payload) -> <root config object>`. Decodes through the same `Mapper.decode_config` call `load_*` uses — `network_map` still runs the adapter table, the other three still store every scalar verbatim. Returns the object; there is deliberately no installer, so the caller writes it with the object's own `save(path)` |
| Refuses | `SchemaName.SCRIPT` and `SchemaName.HARDWARE_OUTPUTS`, same reasons `config_save` already names |

**What the editor does (T059).** `config_save` for `settings`/`network_map`/`project_mappings`/
`project_settings` calls `ConfigManager(load_all=False).from_json(name, document)` and writes the
result with `.save(path)` — the same body each `save_*` delegates to. The `xfail(strict=True)` on
`tests/test_schema_descriptor.py::test_config_save_of_settings_persists_through_save_settings` is
removed; it is a real pass.

**Left open, filed separately.** `project_mappings`/`project_settings` additionally need a project
identifier `config_save`'s wire shape did not carry (fixed locally — see below) and expose a second,
distinct gap this report did not cover: `ConfigManager.project_path`/`conf_path` raise
`FileNotFoundError` for a file that has never been saved before, which blocks a project's *first*
`config_save` even once it is told which project. See `UR-6-config-path-helpers-require-existence.md`.
