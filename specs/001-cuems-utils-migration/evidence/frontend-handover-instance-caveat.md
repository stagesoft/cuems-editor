<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Caveat to `frontend-handover.md:44` — the descriptor `instance` is not yet a document

Added by cuems-editor 002 (T072, FR-028), 2026-10-12. `frontend-handover.md` is immutable evidence
(`README.md:8-10`), so this qualification is a new file that names the line it qualifies.

`frontend-handover.md:44` says, for `cuems-frontend` `src/app/services/projects/projects.service.ts:240`:

> `initial_template` is no longer sent. Build new scripts from `schema_descriptor("script")`'s
> per-type `instance`

**Qualified:** that `instance` is **not directly usable** until `cuems-frontend` UR-1 is fixed in
`cuems-utils`. It is not in `to_wire()` shape, and some required fields have `null` defaults, so a
script built from it unedited is refused on save. The configuration schemas' root-type instances
are refused the same way: all four (`settings`, `network_map`, `project_mappings`,
`project_settings`) fail `from_json` + `save` with `SchemaError` `[T1]`, measured in
`specs/002-config-round-trip/evidence/descriptor-instance-config.txt`.

Until then a client maps the instance into wire shape and fills the required values itself
(`cuems-frontend`'s `toWireShape` + `UR1_UI_STARTING_VALUES`). The tag gate is G3
(`tests/test_upstream_gates.py`); the protocol document's `schema_descriptor` section says the
same (`tests/ws-command-responses.txt`).
