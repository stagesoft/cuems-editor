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
| Reply today | `{"OK": false, "error": "unknown action: node_set"}` (measured, research R7). That is what the G4 strict xfail asserts against |
| Effect on nodeconf | the in-place `set_alias` on its in-memory `NodeIndex`. Its write-if-changed path (`signature()` includes `alias`) persists `network_map.xml` and re-publishes the alias over mDNS. The editor's `watch_network_map` push then reaches every UI |
| Fields | `alias` only. `role_id` and `hostname` are nodeconf's (`cuems-common` `docs/node-identity-contract.md:35-37`). Every discovery field belongs to discovery |
| Timeout | the editor gives up after `TIMEOUT` and tells the operator `timeout`. It does not retry |
