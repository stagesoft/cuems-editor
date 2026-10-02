<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Correction 1 to `README.md` in this directory

The capture bytes (`../initial-mappings.json`) are unchanged. Only the README's description of the
inputs was wrong.

`README.md` says node `…0003` is "only in the map" and that node `…0002` is "only in the mappings".
Measured afterwards: `default_mappings.xml` lists **all three** — `…0001` under `<nodes>` with four
devices, `…0002` and `…0003` under `<new_nodes>`, `…0003` with no `<devices>` element. So:

- `…0001` and `…0003` are in both files and both go through `merge_node_data`. `…0003` shows no
  `devices` key because its mapping node has none, not because it was appended unmerged.
- `…0002` is in the mappings only and is dropped by the merge (unchanged statement).
- No node in this fixture is in the map only. `tests/test_node_merge.py` covers that case
  directly, against `merge_node_data`.
