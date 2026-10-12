<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Quickstart: validating 002-config-round-trip

This is a run guide. It does not specify behaviour: shapes are in
[contracts/ws-messages.md](contracts/ws-messages.md), and state is in
[data-model.md](data-model.md).

## 1. Environment (research R1)

```bash
cd /disk/Projects/StageLab/cuems-editor
E=$(hatch env find)                  # do NOT use `hatch run`: it re-syncs and replaces cuemsutils
$E/bin/python -m pip install -e ../cuems-utils pytest pytest-asyncio
$E/bin/python -c "import cuemsutils; print(cuemsutils.__file__)"   # must be ../cuems-utils/src/...
git -C ../cuems-utils rev-parse HEAD; git -C ../cuems-utils status --short src/   # record both; src/ must be clean
git -C ../cuems-nodeconf rev-parse --abbrev-ref HEAD   # must be a branch with engine_callback (feat/xml-refactor) for gate G4
```

Record these in `specs/002-config-round-trip/evidence/environment.txt` (FR-034):
- the `cuems-utils` SHA, and whether its `src/` is clean;
- `cuemsutils.__file__`;
- the interpreter;
- the `cuems-nodeconf` SHA.

## 2. The suite

```bash
$E/bin/python -m pytest -q
```

**Expected while any upstream gate is open:** everything passes, plus one `xfailed` per open gate
(G1 to G4). Every strict xfail's reason names its gate as `<repo> UR-<n>`.

A gate that its owner has fixed shows as `XPASS(strict)`, which **fails** the run. That is the
signal to replace the xfail with the plain assertion (S6).

**Tag-ready:** no `xfailed` remains (S7, SC-009).

Baseline before this feature: 160 passed, 3 skipped.

## 3. Scenarios and the tests that prove them

| Scenario | Proved by (from spec) | Expected |
|---|---|---|
| A reconnect keeps the repair gate | US1 #1, #2. Written first, and fails at `a3309ab` (FR-005; the failing run is saved in `evidence/`) | `repair_save_refused`, then the echo after re-acknowledging, then a trash copy and a write |
| A second session or a stale tab is refused | US1 #3 | `repair_save_refused`, file untouched |
| A save after an editor restart | US1 #4: a fresh server object over the same temporary library | refused; original in place |
| A file changed after acknowledgment | FR-009a | new `report_id`, acknowledgments dropped, refused |
| A clean project adds no load | US1 #7 | `inspect` is never called (spy) |
| Config round trip | US2 #1, #4: `settings`, `project_mappings` | the edited value is present, the others are equal, the revision changed |
| No file yet | US2 #2 | `exists: false`, `revision: null`, the root `instance` |
| A stale save | US2 #5 | `config_conflict` with the current document; file unchanged |
| Simultaneous saves | US2 #6 (two `config_save` coroutines gathered) | exactly one written, one conflict |
| A library refusal | US2 #7 (`node_role: "bogus"` in a project mapping, or a `settings` value the XSD refuses) | `config_save_refused` with `field` and `location` |
| Restart notice | US2 #8 | `restart` names both services |
| `network_map` is not written | US2 #9, SC-006 | refused; a grep of `src/` finds no `network_map.xml` write path |
| Version 1 restated | US3 | `test_payload_version.py` green; `test_protocol_doc.py` finds no live string boolean |
| Renaming a node | US4 #1 (fake `Communicator`), #2 (no socket), #3, #4 | request shape; `node_list` to all sessions; `unavailable` with no IPC; error relayed verbatim; refusal before IPC |
| G4 against the real handler | research R7 | `xfailed` (`unknown action: node_set`) until nodeconf lands it |

## 4. Manual check against a running editor (optional)

1. Start the editor against a scratch `CUEMS_CONF_PATH` and library (see `tests/README.md` for the
   web client).
2. Send `{"action":"config_load","value":{"schema":"settings"}}`. Keep `revision`.
3. Send `config_save` with one field changed and `base_revision` set to that revision. The reply
   carries a new `revision` and `restart`. A second connected client receives `config_changed`.
4. Re-send the same `config_save`, with the old revision. The reply is `config_conflict`.

## 5. Evidence for the tip capture (FR-030)

```bash
$E/bin/python -I specs/001-cuems-utils-migration/evidence/project-capture/capture_load_tip.py \
  > specs/002-config-round-trip/evidence/project-frame-tip.json
```

This produces one `project` frame. `capture_load.py` stays byte-identical
(`git diff --exit-code` on it).
