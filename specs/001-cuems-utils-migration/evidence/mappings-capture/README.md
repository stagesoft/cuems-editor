<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# `initial_mappings` capture (T009, FR-010, research R11)

`../initial-mappings.json` is the frame `initial_setting_message()` produced after task zero
(T007, import line only) and before any other `src/` edit. cuemsutils `0.1.0rc16` @
**`6213b1603d0a508b6ac7dfb5f46593ba4d870193`** (cuems-utils 013), not `e9ed8af`.

`CuemsWsServer.__init__` still names `create_script()` at that commit, so
`capture_mappings.py` builds the server with `__new__` and sets what `__init__` would set:
`mappings_dict = cli.get_mappings()`, then `reload_network_map_nodes()`, then
`initial_setting_message()`. `CUEMS_CONF_PATH` is this directory. `nodeconf_available` is
pinned to `False` because `/tmp/nodeconf.ipc` is host state.

## Inputs

| File | Source |
|---|---|
| `network_map.xml` | `../cuems-utils/tests/data/network_map.xml` @ `6213b16`, unchanged: node `…0001` (controller, adopted, online) and `…0003` (node, not adopted, not online) |
| `default_mappings.xml` | `../cuems-utils/tests/data/default_mappings.xml` @ `6213b16` plus one `<device class="lighting">` on node `…0001`. Root `<defaults>` is `<default class=… direction=…>` |
| `settings.xml` | `../cuems-utils/tests/data/settings.xml`; `ConfigBase` refuses a conf dir without it |

Node `…0001` is in both files, so it goes through `merge_node_data`. Node `…0003` is only in
the map, so it is appended as the map's own object. Node `…0002` is only in the mappings
(`new_nodes`) and is dropped by the merge, which only keeps nodes the map names.

## What the frame shows (measured, not intended)

- The mappings half carries `devices` / `device` / `class` (`audio`, `video`, `dmx`,
  `lighting`) and `defaults` / `default` / `class` / `direction`, as `to_wire()` emits them.
- **`nodeconf_available` is absent.** `mappings_dict` is a `CuemsProjectMappingsType`;
  `json.dumps` projects it through the mappings schema, which drops every undeclared key. The
  assignment at both injection sites lands in the object and never reaches the wire.
  `tests/test_nodelist_actions.py` uses a plain `dict`, so it did not see this.
- Merged and appended nodes carry JSON `true` / `false` for `adopted` and `online`, and no
  `node_role`: the same schema projection re-encodes them as mapping nodes. The map's own
  `to_wire()` for node `…0003` gives `"node_role": "node"` and `"False"`.

These are the "before" bytes. T034 compares the merged frame with them. Every difference is
either an enumerated delta in `tests/test_node_merge.py` or a bug.
