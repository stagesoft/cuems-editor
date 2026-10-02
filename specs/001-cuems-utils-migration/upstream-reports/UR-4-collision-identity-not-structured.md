<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-4 — A duplicate node identity carries no structured identity

**From** cuems-editor 001 (T040), 2026-10-02. cuemsutils `0.1.0rc16` @ `6213b16`.

**Observed.** `ConfigManager.load_network_map()` on a map with one identity on two rows raises
`ValidationError` whose `violation` is `None`; its `__cause__` is a plain `ValueError`. The identity
exists only inside the message (`check_node_identities_unique`, `xml/validators.py`):
`node identities are not unique: <identity> is carried by 2 rows (mac=…, mac=…). …`.
`cuemsutils.errors.node_identity_collision_message(path, exc)` recognises the case and returns
`"<path>: <message>"`, also a string.

**Why the editor needs it.** `network_map_error` sends `{"kind": "duplicate_identity",
"identity": "<string>", "file": "<path>"}` (FR-036a, research R13), and logs once per distinct
identity. Both need the identity as data.

**Workaround taken.** Recognition stays the library's: the editor calls
`node_identity_collision_message` and acts only when it is not `None`. It then lifts the first
identity out of the library's own sentence with one anchored pattern
(`src/cuemseditor/node_reads.py`, `collided_identity`). If the sentence changes, the frame carries
`"identity": ""` and the message is still logged in full. Nothing is retried either way.

**Expected.** The identities (and their MACs) on the exception — for example a `Violation` with
`location=(identity, "uuid")`, or an attribute on a dedicated subclass — so a consumer reads them
instead of parsing prose.
