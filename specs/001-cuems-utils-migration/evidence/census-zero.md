<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Census zero — cuems-editor, milestone 1 exit (T047, FR-048, SC-002)

Source announcement for the `cuems-utils` flow (its T049 input). **Not a package and not a controller deploy**: the `project` frame now carries `Cue` / `CueOutput` with `class` and a wrapped `Media.duration`, and there is no payload-version handshake yet, so a pre-05 `cuems-frontend` mis-reads both.

Editor `feat/xml-refactor` @ `6934890`. cuemsutils `0.1.0rc16` from `../cuems-utils` @ `6213b16` (the 013 pin, `6213b16`). Measured 2026-10-02.

```
$ grep -rnE 'cuemsutils\.(xml|timeoutloop|create_script)' src
# exit 1 (1 = no match)

$ grep -rnE 'CuemsParser|XmlReaderWriter|create_script|get_nodes_by_adoption|_select_adopted' src
# exit 1 (1 = no match)

$ grep -rn partition_by_adoption src
src/cuemseditor/CuemsWsServer.py:28:from cuemsutils.tools.NodeList import partition_by_adoption
src/cuemseditor/CuemsWsServer.py:503:                adopted, unadopted = partition_by_adoption(cf_manager.network_map)

$ grep -rnE 'node_type|NodeType\.' src
# exit 1 (1 = no match)

$ hatch test tests/test_public_surface.py tests/test_import_smoke.py
37 passed, 1 warning in 0.28s
```

Every `partition_by_adoption` hit is the `cuemsutils.tools.NodeList` import or its one call. The one carried exception, `src/cuemseditor/cli.py` importing `ProjectMappings` through `cuemsutils.tools.ConfigManager` (defined under `cuemsutils.xml`), is named in `tests/test_public_surface.py` and owned by cuems-utils 014. The census regex does not match it.
