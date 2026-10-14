<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract: `node_set` over `/tmp/nodeconf.ipc` (editor → cuems-nodeconf)

This is the cross-repository half of gate G4. It is proposed by this editor and agreed with
`cuems-nodeconf` through `cuems-editor` UR-8. That report quotes this file. Nodeconf builds its
handler on `cuems-utils` `NodeIndex.set_alias` (`cuems-utils` requirements doc §0a G4).

| | |
|---|---|
| Transport | `cuemsutils.tools.CommunicatorServices.Communicator('/tmp/nodeconf.ipc')`, which uses `pynng` Req0 (the editor dials) and Rep0 (nodeconf listens), with JSON-encoded dicts. It is the same socket and the same framing the engine uses for `nodelist_modify` |
| Route | direct from the editor. The engine does not relay it (spec Q2) |
| Request | `{"action": "node_set", "node_uuid": "<uuid string>", "alias": "<non-empty string>" \| null}` |
| `node_uuid` | the node's identity, sent as the string of `coerce_identity(value)` |
| `alias: null` | removes the optional `<alias>` element |
| Reply: done | `{"OK": true}` |
| Reply: refused | `{"OK": false, "error": "<text>"}`. For example, an unknown uuid, an invalid alias (it fails `NonEmptyString`), or `"nodeconf is still starting up"` (the existing readiness answer) |
| Reply before the handler | `{"OK": false, "error": "unknown action: node_set"}` (measured, research R7). Any daemon older than cuems-nodeconf `3d3601d` (`0.1.1-1`) still answers this; the editor relays it verbatim as `nodeconf_error` |
| Implemented | cuems-nodeconf `feat/xml-refactor` `3d3601d` (2026-10-14) on cuems-utils `38d2ede`; nodeconf's brief is its `specs/planning/12-node-set-alias.md` §3. Gate G4 closed |
| Effect on nodeconf | the in-place `set_alias` on its in-memory `NodeIndex`. Its write-if-changed path (`signature()` includes `alias`) persists `network_map.xml` before it answers, and an unchanged alias is `{"OK": true}` with no write. The alias is **not** published over mDNS, and discovery never overwrites it. The editor's `watch_network_map` push then reaches every UI |
| Fields | `alias` only. `role_id` and `hostname` are nodeconf's (`cuems-common` `docs/node-identity-contract.md:35-37`). Every discovery field belongs to discovery |
| Timeout | the editor gives up after `TIMEOUT` and tells the operator `timeout`. It does not retry |
