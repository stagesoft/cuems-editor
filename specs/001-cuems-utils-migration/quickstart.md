<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Quickstart — verifying 001-cuems-utils-migration

Run from the repository root. `cuemsutils` comes from the sibling checkout or from an installed
package at `0.1.0rc16`. The `../cuems-utils/.venv` has no `pynng` and cannot run this suite; use
this repository's hatch environment, which is how the spec's measurements were taken.

```bash
export SPECIFY_FEATURE=001-cuems-utils-migration
# git branch is feat/xml-refactor; spec-kit scripts want the feature id above
```

Shapes under test are in [contracts/](contracts/). Do not treat a reading of the JSON as the
check. The editor capture is compared, not inspected. `cuems-utils` golden XML is not that
check: the XSD under `cuems-utils/src/cuemsutils/xml/schemas/` is the schema.

## 0. Environment

```bash
hatch run python -c "import cuemsutils; print(cuemsutils.__version__, cuemsutils.__file__)"
# expect: 0.1.0rc16 and .../cuems-utils/src/cuemsutils/__init__.py
#         (or an installed copy of that same version)
```

## 1. Before task zero — the failure is the baseline

```bash
hatch run python -c "import cuemseditor.CuemsWsServer"
# expect: ModuleNotFoundError: No module named 'cuemsutils.create_script'
# record the traceback. This is the evidence C2 was live (FR-004).
```

The pre-migration captures of `type: project`, `initial_mappings`, and `initial_template` are
committed before any source change other than the import line. The `project` capture is the
`value` of `{"type":"project"}` ([contracts/project-payload.md](contracts/project-payload.md)).

## 2. After task zero — the first suite whose colour means something

```bash
hatch test
# expect: the six pre-feature test files collect
# (test_media, test_nodelist_actions, test_probe_duration, test_dangling_targets,
#  test_repair_durations, test_validate_fade_durations)
# plus tests/test_import_smoke.py, which this phase adds and which is not part of that six
# the seven TestNetworkMapWatcher / TestNodeconfAvailableFlag failures caused by the import
# pass, with no edit to tests/test_nodelist_actions.py yet
```

`hatch run python -c "import cuemseditor.CuemsWsServer"` succeeds. The process still does not
listen until `create_script()` is replaced (tasks phase 4, User Story 2). Record that
distinction: import is not the listening-state check (FR-003).

## 3. Census and public surface (milestone 1 exit)

```bash
grep -rnE 'cuemsutils\.(xml|timeoutloop|create_script)' src
# expect: no output. Down from 6 hits.

grep -rnE 'CuemsParser|XmlReaderWriter|create_script|get_nodes_by_adoption|_select_adopted' src
# expect: no output

grep -n 'partition_by_adoption' src/cuemseditor/CuemsWsServer.py
# expect: the import `from cuemsutils.tools.NodeList import partition_by_adoption`
# and the call. No definition. No cuemsutils.xml.

grep -rnE 'node_type|NodeType\.' src
# expect: no output

hatch test tests/test_public_surface.py tests/test_import_smoke.py
# expect: green. The surface test still names cli.py's ProjectMappings import as the one
# carried exception (contracts/public-surface.md).
```

`tests/test_nodelist_actions.py` differs from `886f649` only in the `NetworkMap` mock helper.
Its assertions are unchanged.

## 4. The `project` frame (SC-004, SC-005)

```bash
hatch test tests/test_project_payload.py
```

The test fails unless, for every named fixture:

- the new `value` differs from the committed capture only by `schemaLocation` absent and
  `Media.duration` wrapped as `{"CTimecode": ...}`;
- opening the project changes no byte of its `script.xml` (checksum before and after).

Do not regenerate the editor capture to turn this green. Do not compare against
`../cuems-utils/tests/golden/`. Those XML files may be superseded. The XSD files in
`../cuems-utils/src/cuemsutils/xml/schemas/` are the schema. A golden that contradicts the XSD
is regenerated in `cuems-utils` and restated after the system refactoring.

## 5. Silent-wrong sites, failing first (SC-008)

Two captured failing runs, taken before the fix each one guards:

- merge a node that has `node_role` and no `node_type`, and assert the merged payload contains
  `node_role`. The run against the old `basic_fields` list fails.
- compare a structured media duration with the database value. The run against
  `TIMECODE_SHAPE.match` on that value fails, because `match` is never called with a string.

Both failing logs are kept. A test that was only ever seen passing does not satisfy this step.

## 6. Repair tool (SC-007)

On the recorded fixture set used by `tests/test_repair_durations.py`:

```bash
# dry-run: database unchanged, every script.xml checksum unchanged, exit reflects MISSING media
# --apply: database backup exists, database durations corrected,
#          every script.xml checksum still unchanged,
#          stdout lists the projects that need a save

hatch test tests/test_repair_durations.py
```

Then save one listed project through the editor's save path, re-run the tool, and confirm that
project has left the list and that its script checksum changed only on that save. That
round-trip is a test in `tests/test_repair_durations.py`, not only this checklist.

```bash
# the ecosystem's other rewriter is the library's; this repository has none
grep -rn 'write_from_object\|XmlReaderWriter\|\.save(' src/cuemseditor/repair_durations.py
# expect: no script write. CuemsScript.save appears in CuemsDBProject, not here.
```

## 7. Milestone 2 frames

Not required for the census-zero announcement. Required before the tag message is marked ready.

- A repairable fixture produces `document_load_report` with `file_differs_from_loaded: true`
  and the script checksum unchanged. A second open reports the same repairs.
- `project_save` before `repair_acknowledge` returns `repair_save_refused` and does not change
  the file. After acknowledge, the original's bytes exist under `trash/` and the saved file is
  the repaired document.
- An unrepairable fixture (dangling `action_target`, or a document newer than the library)
  produces `document_load_failed` naming the document and the field, with the three
  `next_steps`. A following `project_list` on the same connection still succeeds.
- The first frame on a new connection is `payload_version` with value `1`, and
  `tests/ws-command-responses.txt` has a row for that value.
- `nodeconf_available` is on `node_list` and on the `nodelist_get` reply, and is absent from
  the `project_mappings` payload and from each node.
- `schema_descriptor` for `SchemaName.SCRIPT` returns types with `instance` and field
  defaults. `config_save` of `hardware_outputs` or of a script is refused.

## 8. Pin (SC-010)

```bash
grep cuemsutils pyproject.toml
# expect: cuemsutils>=0.1.0rc16,<0.1.1

grep cuemsutils debian/control
# expect: python3-cuemsutils (>= 0.1.0rc16) and python3-cuemsutils (<< 0.1.1~)
```

Do not run `debuild` on a Debian 13 host. `/usr/bin/python3` there is 3.13, and `python3` on
`PATH` may be a pyenv shim. Build inside an unprivileged bookworm chroot
(`mmdebstrap --mode=unshare`, then `dpkg-buildpackage -b -us -uc` inside it), as
`cuems-nodeconf/tests/packaging/release-gate-demo.sh` does. The package's `pyvenv.cfg` must
say `home = /usr/bin`. See `contracts/package-relations.md`.

`debian/bookworm` still exists on the remote. `debian-consolidation.md` lists the commits to
apply there. The tag file under `../.xml-refactor-tag-messages/` exists and, until
`cuems-frontend` 05 lands, says the frontend is the outstanding item.

## 9. Exit criteria that were not run

Anything in section 6 of `specs/planning/xml-refactor/00-runnable-flow.md` that this environment
cannot perform (a live controller, a UI rendering the report, applying the consolidation onto
`debian/bookworm`) is written down as *not performed* with the reason. An omitted row is not a
pass.
