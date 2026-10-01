<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract — what the editor may import from `cuemsutils`

Guarded by `tests/test_public_surface.py`, following `cuems-engine`'s
`tests/test_public_surface.py`. The test scans `src/` as text. It does not need a successful
import of `cuemseditor` to decide that a forbidden name is present, so it still means something
on the commit before task zero.

## Forbidden in `src/`

1. Any import of `cuemsutils.xml` or a submodule (`from cuemsutils.xml …`,
   `import cuemsutils.xml…`). `__all__` is `[]`. This removes `NetworkMap`, `CuemsParser`, and
   `XmlReaderWriter`.
2. Any import of `cuemsutils.config` or a submodule.
3. Any import of `cuemsutils.create_script` or `cuemsutils.timeoutloop`.
4. The names `CuemsParser`, `XmlReaderWriter`, `create_script`, `get_nodes_by_adoption`,
   `_select_adopted`, `def partition_by_adoption`, `CUE_TYPES`, `'AudioCue' in`, `'VideoCue' in`,
   `'DmxCue' in`, `node_type`, and `NodeType.` anywhere in
   `src/`, including comments and docstrings. `isinstance` against `AudioCue`, `VideoCue`, or
   `DmxCue` is not one of those substrings.
5. Any use of the name `partition_by_adoption` that is not
   `from cuemsutils.tools.NodeList import partition_by_adoption` or a call of that imported
   name. The function returns two tuples of bare node objects. The editor does not define it.

`tests/` may mention a forbidden name only inside `test_public_surface.py`'s ban list, or in a
retired-test record. A test import that deliberately exercises a retired path carries a
`# test-only` comment and a one-line reason. This feature's expectation is that
`tests/test_repair_durations.py` does not need one: its `XmlReaderWriter` import leaves with
pass B.

## Allowed surface this feature uses

| Import | For |
|---|---|
| `cuemsutils.cues.CuemsScript` (`.load_with_report`, `.from_json`, `.save`, `.to_wire`) | script open and save |
| `cuemsutils.errors.LoadReport`, `Outcome`, `ValidationError` | report forwarding and the unrepairable path |
| `cuemsutils.errors.node_identity_collision_message` | distinguish a duplicate node identity from a transient read error |
| `cuemsutils.tools.ConfigManager.ConfigManager`, `SchemaName` | descriptor, `generate_example(SchemaName.SCRIPT)`, `network_map`, `save_network_map`, `save_settings`, `save_project_mappings`, `save_project_settings` |
| `cuemsutils.tools.NodeList.partition_by_adoption` | adopted and unadopted tuples, after the 013 commit pin |
| `cuemsutils.tools.coerce_identity` | JSON identity compared with a map identity |
| `cuemsutils.helpers.new_uuid` | already used; the `CuemsWsServer` import joins it |
| `cuemsutils.tools.CTimecode.CTimecode` | duration fix and the repair tool's comparison; already used by the fade gate |
| `cuemsutils.tools.CopyMoveVersioned.CopyMoveVersioned` | move the pre-repair script into `trash/` before the first overwrite; already imported by `CuemsDBProject` |

Not imported: `cuemsutils.xml.descriptor`. `cuemsutils.tools.NodeList` is imported for
`partition_by_adoption` only. `NodeRole`, `NodeIndex`, and `Uuid` are not re-tested here.
Nodes stay the objects the partition function returned.

## Known exception, carried

`src/cuemseditor/cli.py` imports `ProjectMappings` from `cuemsutils.tools.ConfigManager`. The
class is defined under `cuemsutils.xml` and bound into that module namespace. The census regex
`cuemsutils\.(xml|timeoutloop|create_script)` does not match it. It is still a Principle V
violation. It stays until `cuems-utils` 014, because its only call reads `default_mappings.xml`.
The public-surface test names this file and this symbol as the one allowed exception, so a
second such import fails the test. See plan.md Complexity Tracking.

## Anti-vacuity

The test fails if it scans zero files under `src/`, or if after milestone 1 it finds zero
`cuemsutils` imports at all. A wrong root would otherwise turn the census green. It also fails
if `src/cuemseditor/CuemsWsServer.py` does not contain
`from cuemsutils.tools.NodeList import partition_by_adoption`. Until T036 that line is absent,
so the first run stays red.
