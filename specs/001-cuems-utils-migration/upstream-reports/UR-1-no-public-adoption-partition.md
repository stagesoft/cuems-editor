<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# UR-1 — No public adoption partition (resolved upstream by cuems-utils 013)

**Same report as** `cuems-engine` `specs/008-cuems-utils-migration/upstream-reports/UR-1-no-public-adoption-partition.md`
(engine `9b16412`). This repository adds no new request. It records the editor's side of it.

**Observed on `0.1.0rc16` as published.** The only non-mutating adoption partition was
`cuemsutils.xml.settings.NetworkMap.partition_by_adoption`. `cuemsutils.xml` is internal (Q14).
The editor called the deprecated, mutating `NetworkMap.get_nodes_by_adoption` through
`from cuemsutils.xml import NetworkMap` (`src/cuemseditor/CuemsWsServer.py:26`, `:478`).

**Resolved by.** cuems-utils 013 publishes the same function object as
`from cuemsutils.tools.NodeList import partition_by_adoption`, without a version bump.

| | |
|---|---|
| Pinned commit | `6213b1603d0a508b6ac7dfb5f46593ba4d870193` |
| Subject | `docs(planning): prompt the editor to amend 001 once 013 is the library it imports` |
| Evidence | `../evidence/cuems-utils-013-landed.txt`, `../evidence/cuems-utils-013-pin.txt` |
| Signature | `partition_by_adoption(network_map) -> tuple[tuple, tuple]`: adopted, then unadopted, both tuples of bare node objects. An empty side is `()`. The input `node_list` stays a list of `{"node": <node>}`; the function unwraps it |

**What the editor does (T036).** `adopted, unadopted = partition_by_adoption(network_map)`, imported
from `cuemsutils.tools.NodeList`. The editor does not unwrap or re-wrap, does not read `adopted`
itself, and does not define a local helper. `tests/test_public_surface.py` allows that import and
calls of that name, and rejects `cuemsutils.xml`, `get_nodes_by_adoption`, `_select_adopted`, and a
local `def partition_by_adoption`.

**Version pin.** `cuemsutils>=0.1.0rc16,<0.1.1` is unchanged by this report. A checkout of
cuems-utils older than the pinned commit, still at `0.1.0rc16`, satisfies the version range and fails
the import. The commit is the pin for this one name until cuems-utils cuts a release that carries it.
