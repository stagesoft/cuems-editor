<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-5 — No public way to build a config document from JSON

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
