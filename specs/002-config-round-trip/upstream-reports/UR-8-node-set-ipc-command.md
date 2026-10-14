<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-8 — `node_set`: the operator's node alias, over `/tmp/nodeconf.ipc`

**Status: CLOSED 2026-10-14.** cuems-nodeconf `feat/xml-refactor` `3d3601d` implements the
handler on cuems-utils `feat/xml-refactor` `38d2ede` (`NodeIndex.set_alias`). nodeconf's brief is
its `specs/planning/12-node-set-alias.md` §3. It was checked against this contract and FR-024 to
FR-027 and they match: the same request, `{"OK": bool, "error"?}` replies, `alias` the only field,
`null` clears it, and a direct route with no engine. The editor needed no code change. The G4
test now seeds a map that holds the node, checks the alias in the written file, and passes without
its marker. Against nodeconf `155fe6c` it still fails with "unknown action: node_set". It ships in
cuems-nodeconf `0.1.1-1`, which is not published yet. A deployed daemon older than that still gives
the "unknown action" answer. The hardware check is still owed (cuems-nodeconf
`specs/002-public-network-map-path/checklists/hardware-verification.md` §7a).

**From** cuems-editor 002 (T053), 2026-10-12. **To** `cuems-nodeconf`. Measured against
`cuems-nodeconf` `feat/xml-refactor` @ `65605de` (`engine_callback` unchanged since research's
`2045897`) and cuemsutils `0.1.0rc16` from `../cuems-utils` @ `cdb3bef`. This is gate **G4** of the
`xml-refactor-merge-candidate` tag. nodeconf's own plan for it is
`specs/planning/12-node-set-alias.md` there.

**Why.** `network_map.xml` has one runtime writer, `cuems-nodeconf`, and it never re-reads the file:
its next write (a discovery change, an IP change, any adopt or un-adopt) silently reverts anything
written beside it (002 S5). So the editor no longer writes that file on any path (`config_save`
refuses `network_map`, 002 FR-019), and an operator's alias, the only node field the operator owns
(`cuems-common` `docs/node-identity-contract.md:35-37`), has to go to nodeconf.

**The contract.** Quoted in full from `specs/002-config-round-trip/contracts/nodeconf-node_set.md`:

> # Contract: `node_set` over `/tmp/nodeconf.ipc` (editor → cuems-nodeconf)
>
> This is the cross-repository half of gate G4. It is proposed by this editor and agreed with
> `cuems-nodeconf` through `cuems-editor` UR-8. That report quotes this file. Nodeconf builds its
> handler on `cuems-utils` `NodeIndex.set_alias` (`cuems-utils` requirements doc §0a G4).
>
> | | |
> |---|---|
> | Transport | `cuemsutils.tools.CommunicatorServices.Communicator('/tmp/nodeconf.ipc')`, which uses `pynng` Req0 (the editor dials) and Rep0 (nodeconf listens), with JSON-encoded dicts. It is the same socket and the same framing the engine uses for `nodelist_modify` |
> | Route | direct from the editor. The engine does not relay it (spec Q2) |
> | Request | `{"action": "node_set", "node_uuid": "<uuid string>", "alias": "<non-empty string>" \| null}` |
> | `node_uuid` | the node's identity, sent as the string of `coerce_identity(value)` |
> | `alias: null` | removes the optional `<alias>` element |
> | Reply: done | `{"OK": true}` |
> | Reply: refused | `{"OK": false, "error": "<text>"}`. For example, an unknown uuid, an invalid alias (it fails `NonEmptyString`), or `"nodeconf is still starting up"` (the existing readiness answer) |
> | Reply today | `{"OK": false, "error": "unknown action: node_set"}` (measured, research R7). That is what the G4 strict xfail asserts against |
> | Effect on nodeconf | the in-place `set_alias` on its in-memory `NodeIndex`. Its write-if-changed path (`signature()` includes `alias`) persists `network_map.xml` and re-publishes the alias over mDNS. The editor's `watch_network_map` push then reaches every UI |
> | Fields | `alias` only. `role_id` and `hostname` are nodeconf's (`cuems-common` `docs/node-identity-contract.md:35-37`). Every discovery field belongs to discovery |
> | Timeout | the editor gives up after `TIMEOUT` and tells the operator `timeout`. It does not retry |

**Today's reply, measured.** The editor's exact request, given to the real
`CuemsNodeConf.engine_callback` (`cuemsnodeconf/CuemsNodeConf.py:368`) with `_ready = True` and
`netifaces`, `systemd`, `dbus` and `zeroconf` stubbed:

```text
request: {"action": "node_set", "node_uuid": "4b9b5a1e-0000-4000-8000-0123456789ab", "alias": "Stage left"}
reply:   {"OK": false, "error": "unknown action: node_set"}
```

**Field ownership** (002 S5): `uuid`, `name`, `node_role`, `ip`, `online` are discovery's, rewritten
on every pass; `adopted` is nodeconf's, through `nodelist_modify` ADD/REMOVE; `role_id` and
`hostname` are nodeconf's; `alias` is the operator's. The editor refuses every field but `alias`
before it sends anything, so nodeconf receives `node_uuid` and `alias` only.

**Depends on `cuems-utils`.** nodeconf delegates every map mutation to the library, so the handler
is built on `NodeIndex.set_alias(node_uuid, alias) -> bool`, the in-place setter `cuems-utils`
requirements doc §0a G4 asks for (002 M8). The gate closes when both have landed: the library's
setter, then nodeconf's handler. Its write-if-changed path (`signature()` includes `alias`) persists
the file; the editor's `watch_network_map` push then reaches every UI.

**The editor side is done.** `CuemsWsUser.node_set` (002 T051) sends the request above directly on
`/tmp/nodeconf.ipc` through `cuemsutils.tools.CommunicatorServices.Communicator`, not through the
engine (002 Q2). It answers `unavailable` at once where the socket does not exist, relays
`{"OK": false, "error"}` verbatim as `node_set_refused` reason `nodeconf_error`, and on
`{"OK": true}` refreshes every session's `node_list`. Pinned against a fake peer in
`tests/test_node_set.py`.

**The editor test that flips.**
`tests/test_upstream_gates.py::test_nodeconf_engine_callback_accepts_node_set`, a
`xfail(strict=True, raises=AssertionError)`. It imports `cuemsnodeconf.CuemsNodeConf` from the
sibling `../cuems-nodeconf` working tree (with the four OS modules stubbed), calls `engine_callback`
with the request above, and asserts `{"OK": true}`. It XPASSes the day the handler lands on the
checked-out branch, which fails the editor's suite until its marker is removed (002 S6). It is
skipped only where `../cuems-nodeconf` does not exist.
