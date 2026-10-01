<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Research — 001-cuems-utils-migration

**Date**: 2026-10-01 · **Editor**: `feat/xml-refactor` @ `36260e2` · **Library**: sibling
`../cuems-utils` `src/` (`cuemsutils.__version__` `0.1.0rc16`)

Every entry was measured against that library tree. The planning bundle
(`specs/planning/xml-refactor/`) is not re-derived here. These entries are what the bundle did
not measure, or where a later spec decision overrides the bundle's wording. The spec wins on
conflict; each such case says so.

---

## R1 — The import failure and the template call are separable

**Probe**: `python -c "import cuemseditor.CuemsWsServer"` against `cuemsutils` 0.1.0rc16.

```
ModuleNotFoundError: No module named 'cuemsutils.create_script'
```

Raised from `src/cuemseditor/CuemsWsServer.py:27`:

```python
from cuemsutils.create_script import create_script, new_uuid
```

`new_uuid` is already imported from `cuemsutils.helpers` at `CuemsDBMedia.py`, `CuemsDBProject.py`,
`db.py`, and `CuemsDBModel.py` (`new_datetime` at the last). The only caller of `create_script` is
`CuemsWsServer.__init__` (`self.initital_template = create_script()`, misspelling original).

The seven non-passing tests in `tests/test_nodelist_actions.py` (`TestNetworkMapWatcher` 3,
`TestNodeconfAvailableFlag` 4) fail with the same `ModuleNotFoundError`, reached through a lazy
`from cuemseditor.CuemsWsServer import CuemsWsServer`. `tests/test_media.py` and
`tests/test_repair_durations.py` fail at collection the same way, via `cuemseditor.cli`.

**Decision**: the first source commit after the pre-migration captures changes only that import.
`new_uuid` comes from `cuemsutils.helpers`. The `create_script` name is dropped from it. The
constructor keeps calling `create_script()` until the template stand-in (R10) lands. The
listening-state check is ordered after that stand-in, because an importing module whose
constructor still names a deleted function does not listen.

**Rationale**: until the process imports, no other call site is reached, and a green suite is
not evidence. Coupling the one-line fix to the template decision blocks every later measurement.

**Alternatives rejected**: a local `create_script` shim (a second template, which is the drift
D25 exists to end); importing `cuemsutils.xml` to reach the generator early (Q14).

---

## R2 — The three pre-parse fixups, checked against `repair()`

**Probe**: `cuemsutils.xml.validators.repair` and the rule table. Rules match on MRO class
names (`validators.py`, `class_names = frozenset(cls.__name__ for cls in type(node).__mro__)`).
`FadeCue` subclasses `ActionCue` (`cues/FadeCue.py`).

| Editor method | What it does today | Library |
|---|---|---|
| `_fix_media_durations` (`CuemsDBProject.py:367`) | overwrites cue `Media.duration` from the media DB | `media_duration` is `repairable=False`. No DB hook |
| `_clean_dangling_targets` / the `target` half of `_nullify_dangling_refs` | sets a missing `target` to `None` on the raw dict, on `update` only | `target_resolves` is `repairable=True`. A dangling `Cue.target` is set to `None` and a `RepairRecord` is appended. The rule's own comment says it reproduces this walk |
| the `action_target` half, including `FadeCue` | sets a missing `action_target` to `None` | `action_target_resolves` is `repairable=False`, and it applies to `FadeCue` through the MRO. The default of `action_target` is `None`, which `action_target_required` rejects. The rule's comment names this editor walk as the thing being deleted: clearing to `None` produced documents the library rejects |

`repair()` raises `ValidationError` at the first unrepairable finding. It runs from
`CuemsScript._load_full`, not from `from_json` (R3).

**Decision**:

- Keep `_fix_media_durations`, rewritten to walk the `CuemsScript` object and assign through the
  field (`CTimecode`). It must not edit the dict `to_wire()` returned.
- Delete `_clean_dangling_targets`, `_nullify_dangling_refs`, and `_collect_cue_ids`. Do not
  port the `action_target` clear. A dangling `action_target` is `document_load_failed`.
- Retire `tests/test_dangling_targets.py`. Its five tests assert the deleted walk. Re-asserting
  `target` repair or `action_target` refusal here re-tests the library (FR-030a-i applied to
  this rule, FR-017).

**Rationale**: FR-015 says what survives is what the library does not do, measured case by case.
The duration fix is the editor's DB. The `target` clear is the library's. The `action_target`
clear is the permissive behaviour the library removed on purpose; keeping it would write
documents `save()` then rejects.

**Alternatives rejected**: port both walks onto the object "to be safe" (two implementations of
one rule); keep only the `FadeCue` half (the MRO already covers it); leave
`test_dangling_targets.py` failing.

---

## R3 — `from_json` does not repair; `save` validates; open uses `load_with_report`

**Probe**: `CuemsScript.from_json` (`cues/CuemsScript.py`) returns `_decode(_ingest(payload))`.
`_load_full` is the only caller of `repair()`. `save` builds a tree, raises on the first T1/T2
violation, then `write_tree`.

So the editor's two directions are different library entry points:

- **Open** (`project_load` → `CuemsDBProject.load`): `load_with_report`. Repair and conversion
  happen in memory. The file is untouched. The report is how the session learns which.
- **Save of a client payload** (`project_save` → `update`, and `project_new`): `from_json`, then
  the object duration fix, then `save`. T2 runs at `save`, not at `from_json`. A dangling
  `action_target` in a client payload fails at `save` with `ValidationError`, which the existing
  error path already forwards as text. It is not silently cleared.
- **`update_projects_existed_media`** today does `CuemsParser(self.load(...)).parse()`. After
  `load` returns a wire dict, parsing that dict again is a second projection. The caller needs
  the object `load_with_report` already built.

`load()` discards the report. This repository does not use it on the open path. A caller that
needs the object and will not surface a report is how a repair becomes silent.

**Decision**: every editor open of a script goes through `load_with_report`. `load()` is not
called. Client payloads enter through `from_json`. Disk writes of a script go through `save`.

**Rationale**: D21's three outcomes exist only if the report is observable. `from_json`'s lack
of repair is the documented asymmetry, not a gap to paper over with a local repair pass.

**Alternatives rejected**: call `repair()` ourselves (it lives in `cuemsutils.xml`); run
`validate()` and then mutate (a second repair implementation).

---

## R4 — `CuemsScript.save` is atomic

**Probe**: `CuemsScript.save` calls `write_tree` (`xml/documents.py`). `write_tree` creates a
temp file in the target's directory (`tempfile.mkstemp`, prefix `.{name}.`, suffix `.tmp`),
writes the tree, and `os.replace`s it onto the target. On validation failure `save` raises
before `write_tree`, so the target is not created or truncated.

**Decision**: `save_xml` becomes `script.save(path)`. No editor-side temp file. The ratification
question — whether `XmlReaderWriter.write_from_object` is atomic — is answered for the
replacement: yes. It is removed from Complexity Tracking.

**Rationale**: Principle III asks for a write that completes or leaves the prior file intact.
The library already does that. A second temp-file layer in the editor would be a second writer.

**Alternatives rejected**: keep `XmlReaderWriter` until someone proves its atomicity (the import
itself is the violation); wrap `save` in another rename (two rename protocols).

`delete_from_trash`'s `rmtree` inside a transaction is a different function. R4 does not touch
it. It stays in Complexity Tracking.

---

## R5 — There is no public adoption partition

**Probe**:

```
grep -n "def partition_by_adoption\|def get_nodes_by_adoption" \
  ../cuems-utils/src/cuemsutils/xml/settings.py
grep -rn "def partition_by_adoption" ../cuems-utils/src/cuemsutils/tools
```

Both methods are on `cuemsutils.xml.settings.NetworkMap`. `get_nodes_by_adoption` is deprecated
and mutates its argument: it returns `{"node": ...}` wrappers in lists. `partition_by_adoption`
does not mutate, and returns bare node objects in tuples. `cuemsutils.xml.__all__ == []`.
Nothing under `cuemsutils.tools` re-exports either name. `ConfigManager.network_map` returns
the wrapped list (`node_list` entries are `{"node": node}`); `adopted` and `online` are `bool`
on that object.

`tests/test_nodelist_actions.py` `TestNodeconfAvailableFlag._reload` patches
`cuemseditor.CuemsWsServer.NetworkMap` and stubs `get_nodes_by_adoption`. Deleting the import
makes that `patch()` raise `AttributeError` on two tests. The assertions of those tests are
about `nodeconf_available`, not about the partition.

**Decision**: spec Q1 option C. A private `_partition_by_adoption(network_map)` reads `adopted`
and returns the library node objects. It writes nothing. Its docstring names the upstream
report, which cites `cuems-engine`'s UR-1 and asks for a public non-mutating partition. The
public-surface test forbids both names in editor modules. The `test_nodelist_actions.py` edit
is confined to that helper's mock, lands in the same commit as the import removal, and changes
no assertion (FR-041).

**Rationale**: the context block's "becomes `partition_by_adoption`" contradicts the block's own
Q14 paragraph. The spec resolved the contradiction. A local read of a bool is not a node model;
re-testing `NodeRole` or uuid shape here would be.

**Alternatives rejected**: import `NetworkMap` anyway (Q14, and the symbol disappears in the
release after rc16); block the editor until the library ships the method (option A, rejected
in clarify); two readers, one per call site (the engine's UR-1 failure mode).

---

## R6 — Typed nodes serialise to the old wire form only through `to_wire`

**Probe**: `cms:BoolType` adapter `_Bool.to_wire` returns `str(obj)`, so `True` becomes
`"True"` (`xml/adapters.py`). In memory, `network_map` nodes hold real `bool`s, a `NodeRole`
enum, and a `Uuid`. `Uuid` compares and hashes equal to its string form and is not a `str`
subclass. `json.dumps` of a plain `dict` that has had those objects copied in does **not** run
the adapter: a `bool` becomes JSON `true`.

`merge_node_data` (`CuemsWsServer.py:388`) does `existing_node.copy()` and then assigns
`basic_fields`, which includes `'node_type'`. The converted document has `node_role`. The
assignment `if field in new_node` skips the missing key, and the merged dict keeps no role.
That is the FR-030a-ii silent drop.

**Decision**: status fields on the merged mapping node are taken from `node.to_wire()`, which
already uses `node_role` and the string booleans. Output blocks (audio, video, dmx) stay from
the existing mapping node. Identity comparison uses `cuemsutils.tools.coerce_identity`, not
`==` between a JSON string and a `Uuid`. `basic_fields` and the docstring at `:392` drop
`node_type`. A test feeds a converted node and fails while the list still says `node_type`.

**Rationale**: F6's risk is the merge, not an unmerged node's own `json.dumps`. Hand-converting
`True` to `"True"` in the editor is a second bool model. `to_wire()` is the one projection.

**Alternatives rejected**: assign the in-memory bools and rely on a `json.dumps` default (easy
to forget on the next builder); keep `node_type` as an alias (the document no longer has it,
so the alias would still drop the field).

---

## R7 — Pass B is not a missing library feature

**Probe**: `cuems-convert-documents` is `cuemsutils.xml.convert_documents:main`. `convert_file`
returns immediately when `version >= current`. The script 1→2 step reshapes a bare
`<duration>` into `<duration><CTimecode>…</CTimecode></duration>`. It does not read the editor
database and does not replace a short duration with an ffprobe result. `media_duration` on load
is unrepairable (R2), so a short-but-well-formed duration is also not a load repair.

**Decision**: spec Q5. Delete pass B (`pass_b_xml`, the XML backup, the `--xml-only` write).
Pass A still corrects the database, with the existing dry-run and the database backup. The tool
then loads each script through the public load and lists projects whose media duration differs
from the corrected database value as *needs a save*. It writes no script and runs no version
conversion. The operator's save (R3) is what writes the corrected duration. No upstream report.

**Rationale**: folding pass B into `cuems-convert-documents` would add DB-and-ffprobe behaviour
to a library tool that has neither a database nor a media file. The ecosystem then still has
one rewriter (`cuems-convert-documents`) and the editor has zero.

**Alternatives rejected**: keep pass B on `CuemsScript.save` (a second writer of scripts, which
is the exit criterion this feature is closing); ask the library to accept a duration override
map (an upstream change spec Q5 said is unnecessary).

---

## R8 — `reload_network_map_nodes` mutates shared state off the loop

**Probe**: `CuemsWsServer.notify_all_node_list_update` (`:608`) and `CuemsWsUser.nodelist_get`
(`:450`) both `run_in_executor(..., reload_network_map_nodes)`. That method assigns
`self.mappings_dict['nodes']`, `['new_nodes']`, and `['nodeconf_available']` before returning.
`__init__` also calls it directly, on the constructing thread, before the executor exists.

Constitution II: shared server state is mutated only on the event-loop thread. This is a
pre-existing deviation. Removing `NetworkMap.get_nodes_by_adoption`'s in-place mutation does
not remove the editor's own writes.

**Decision**: the executor callable returns the data (merged node lists, or a typed failure
for R13) and does not assign `self.mappings_dict`. The coroutine that awaited it assigns, on
the loop thread, and then builds the outbound message. `__init__` still runs before the loop;
that single call stays on the constructing thread, which is the only thread at that moment.
The plan records it as the startup read, not as a second executor path.

**Rationale**: Principle II is a correctness rule. The cheapest fix that satisfies it is to
move the assignment, not to add a lock.

**Alternatives rejected**: leave the write and record it forever (the spec says re-check once
the mutating library call is gone, and either fix or record; the fix is smaller than the
record); hop back to the loop with `call_soon_threadsafe` from inside the executor (two ways
to reach the same assignment).

---

## R9 — `duplicate` writes a new file; `project_save` overwrites

**Probe**: `CuemsDBProject.duplicate` copies the project tree, loads the source script, patches
id and name, and `save_xml`s under `new_unix_name`. `project_save` → `received_project` →
`update` → `save_xml` of the loaded project's own path. Nothing in the editor chains
`project_load` into a save. `load_xml` only reads.

**Decision**: the acknowledgment gate and the `trash/` copy apply only to a save whose target
path is the file `load_with_report` just read — `project_save`. `duplicate` still calls
`load_with_report` so the copy is the repaired object, and the `project_duplicate` reply gains
an optional `report` key. The source file is not moved and not overwritten. Old clients ignore
the extra key (FR-047a: a new optional key is not a payload-version bump).

**Rationale**: D21b is about destroying the corrupt original. A new path is not that. Hiding
the report on duplicate would still make the repair silent, so the reply carries it.

**Alternatives rejected**: require acknowledgment before duplicate (the source is intact; the
gate would block a copy on a UI that has no ack button yet, during milestone 1); write the
duplicate from the raw file bytes (the copy would keep the corruption the library had already
repaired in memory).

---

## R10 — `generate_example` covers script and settings only

**Probe**: `ConfigManager.generate_example` (`tools/ConfigManager.py:569`) dispatches
`SchemaName.SCRIPT` and `SchemaName.SETTINGS`. Any other `SchemaName` raises
`NotImplementedError`. `get_schema_descriptor` (`:530`) accepts all six, including
`HARDWARE_OUTPUTS`, and returns `tuple[TypeDescriptor, ...]`. Each `TypeDescriptor` has `key`,
`fields` (`FieldDescriptor`: name, xsd type, required, repeated, order, kind, enum values,
default, repairability), and `instance` (a nested empty instance; callable defaults are `None`
because the descriptor is cached and is served over the socket).

`SchemaName` is on `ConfigManager`'s module. Reaching `generate_script_example` through
`cuemsutils.xml.descriptor` is the import D34 forbids. F5 is confirmed.

**Decision**: milestone 1 sets `initital_template` from
`ConfigManager.generate_example(SchemaName.SCRIPT)`. The message type stays `initial_template`
and the value stays `{"CuemsScript": ...}`. The baseline is the output of the last `cuemsutils`
release that still contained `cuemsutils.create_script`, recorded by version and checksum.
Differences are enumerated, not waved through. Milestone 2 stops sending that message; the UI
builds from `get_schema_descriptor` instances. `config_save` does not call `generate_example`
for `network_map` or `project_mappings`.

**Rationale**: D26 retires the concrete template, and C5 says two frontend sites consume
values, not only shape. The example is the milestone-1 way to keep values flowing. The
descriptor's `instance` is the milestone-2 replacement, which is why the example generator's
limited coverage is not a blocker.

**Alternatives rejected**: hand-author a seed in this repository (the drift the cutover ends);
serve `initial_template` from `get_schema_descriptor` in milestone 1 (that is the retirement,
and it is a wire change behind the handshake).

---

## R11 — The open frame's type is `project`

**Probe**: `tests/ws-command-responses.txt` line 17, and `CuemsWsUser.send_project`. The client
sends `{"action":"project_load","value":"<uuid>"}`. The server replies
`{"type":"project","value": <dict>}`. There is no message type `project_load`.

**Decision**: captures, the two-delta test, and the contract all use the `project` frame. The
action name stays `project_load`. Docs that say "the `project_load` payload" mean this frame's
`value`.

**Rationale**: a test that asserts a type the server does not send passes nothing and fails
nothing useful.

**Alternatives rejected**: rename the frame to `project_load` (an existing-message change, a
payload-version bump, and a frontend edit this feature does not own).

---

## R12 — Goldens are checked by `MANIFEST.sha256`

**Probe**: `../cuems-utils/tests/golden/MANIFEST.sha256`. Script goldens carry `doc_version="2"`
(for example `tests/golden/xml/cuems-editor__script_minimal.xml`). Reader JSON carries
`"duration": {"CTimecode": "..."}`. `doc_version` is not a key in those reader JSON files.

**Decision**: the two-delta test compares the editor's `project` value to a capture committed
before the migration, and separately checks the relevant golden files against
`MANIFEST.sha256`. A mismatch fails the test. Nobody regenerates a golden or the capture to
make it pass. At most one re-baseline of the *editor's* capture is allowed, and it is a
recorded diff (FR-040). The library's goldens are not a re-baseline target at all.

**Rationale**: a capture taken on the day can repeat a mistake. A golden moves only when
upstream records a re-base. Checksum comparison does not depend on a human reading the JSON.

**Alternatives rejected**: vendor the goldens into this repository (a second corpus); compare
by eye; call the library's pytest as this package's test (couples the suites).

---

## R13 — A duplicate node identity is not a transient read error

**Probe**: `validate_node_identities` raises `ValueError` with the substring
`node identities are not unique`. `ConfigBase.load_config_document` wraps it as
`ValidationError`. `cuemsutils.errors.node_identity_collision_message` recognises that
substring and prefixes the file path; it returns `None` for anything else.
`reload_network_map_nodes` catches `Exception` and retries three times with backoff, then
returns `False`. A collision is stable: the third read fails the same way. The watcher then
keeps the last list and tells nobody.

**Decision**: before the retry, if `node_identity_collision_message(path, exc)` is not `None`,
stop. Log once per distinct identity. Keep the last successful node list. Broadcast
`network_map_error` with `{kind: "duplicate_identity", identity, file}` to every session, and
send it to a session that connects while the error stands. A later successful read broadcasts
the clear and then the usual node refresh. The identity on the wire is the string form. Other
exceptions keep the existing retry. This message is new, so it does not bump the payload
version, and it lands in milestone 1 (FR-047a, FR-036a).

**Rationale**: retrying a deterministic validation failure looks like a disk race and hides
the only fact the operator can act on. The helper is public (`cuemsutils.errors`); matching
the substring locally would be a second copy of that recognition.

**Alternatives rejected**: treat every `ValidationError` as a collision (a schema failure is
not one); drop the last good list (the UI would show no nodes for a bad write it can still
ignore); add a retry with a longer delay (the file will not become unique by waiting).

---

## R14 — `nodeconf_available` belongs to no schema

**Probe**: `CuemsWsServer.nodeconf_available` (`:516`) returns whether `/tmp/nodeconf.ipc`
exists. It is intentionally uncached (`829c56c`). It is written into `mappings_dict` at
`:491` (inside `reload_network_map_nodes`) and again at `:537` (inside
`initial_setting_message`). `project_mappings` and `network_map` have no such field.
`node_status` (`CuemsWsUser.py:463`) returns the engine's `cluster_status` dict, whose
`alive` list is the sub-second ping/pong. The docstring at `:469` says `online` is
nodeconf's discovery view, about 30 seconds, and that `alive` is the signal the GO gate
trusts.

**Decision**: spec Q7 option B, applied in milestone 2. Until then both injection points
stay, so `initial_mappings` does not lose a key the current UI may read. In milestone 2 the
flag moves to the envelope of `node_list` and of the `nodelist_get` reply, beside the node
arrays and outside the `network_map` data, sampled when the message is built. It is absent
from `project_mappings` and from each node. `alive` is not added to the descriptor and is
not copied onto `online`.

**Rationale**: a descriptor-driven form has nowhere legal to put a daemon liveness bit. Putting
it on a node would collapse it with `online`. Putting it on `project_mappings` would make a
non-document fact survive a schema save.

**Alternatives rejected**: a third schema for one bool (the library would have to grow a
schema for a socket that is not a document); cache the flag on the server (the bug `829c56c`
removed); derive "is it up?" from `online or alive` (one question, two facts, and the GO
gate would be wrong for up to 30 seconds).
