<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Where the node lists are assigned (T038, research R8, constitution II)

T038 says `reload_network_map_nodes` returns the loaded lists and does not assign
`self.mappings_dict`. Implemented as `reload_network_map_nodes(assign=True)`:

| Caller | Thread | Call | Who assigns |
|---|---|---|---|
| `CuemsWsServer.__init__` | constructing thread, before the loop exists | `reload_network_map_nodes()` | the method itself (startup read) |
| `notify_all_node_list_update` | executor, awaited on the loop | `reload_network_map_nodes(assign=False)` → `NodeLists` / `IdentityCollision` / `None` | `assign_network_map_nodes`, on the loop |
| `CuemsWsUser.nodelist_get` | executor, awaited on the loop | same | same |

**Why the default still assigns.** `tests/test_nodelist_actions.py` may change only in
`TestNodeconfAvailableFlag._reload`'s mock (FR-041), and its unchanged assertions call
`reload_network_map_nodes()` directly and read `ok is True` and `mappings_dict['nodeconf_available']`
afterwards. `TestNodelistGet` stubs `server.reload_network_map_nodes` and expects `nodelist_get` to call
it through the executor. Keeping the name and adding `assign=False` for the two executor paths
satisfies both without an assertion edit. The executor never writes `mappings_dict`:
`tests/test_node_merge.py::test_the_executor_read_does_not_touch_shared_state`.

`nodeconf_available` is still written into `mappings_dict` at both milestone-1 sites, sampled fresh
each time: `assign_network_map_nodes` (refresh path) and `initial_setting_message` (serve path).
`tests/test_node_merge.py::test_both_paths_sample_nodeconf_available_fresh`.
