<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Research — 002-config-round-trip

Phase 0 of [plan.md](plan.md). Every entry was measured on 2026-10-12 against:

- **this repository**: `002-config-round-trip` @ `d87a967`. Its source equals `feat/xml-refactor`
  @ `a3309ab`.
- **`cuems-utils`**: `b2ea09a` on `014-xs-boolean-and-media-elements`. `src/` is clean; the only
  modified files are under `specs/` and `CLAUDE.md`. Since `67c89bd` the library code has not
  changed: `b2ea09a` is a docs commit.
- **`cuems-nodeconf`**: `origin/feat/xml-refactor` @ `2045897`, read with `git show` and
  `git archive` into the scratchpad. The local checkout is on `main` and was not touched.

The probes were run with the hatch environment's interpreter, `python -I`, from a scratchpad
directory, against copies of `tests/fixtures/conf`.

---

## R1. The test environment: how to run the suite against the sibling `cuems-utils`

**Measured.**
- `hatch run …` re-syncs dependencies first. That sync replaced the editable `cuemsutils` with a
  non-editable `0.1.0rc16` in `site-packages`, with no `direct_url.json`. After that,
  `tests/conftest.py`'s fallback to `../cuems-utils/src` never fires, because `cuemsutils` imports
  from the installed copy.
- The default hatch environment has no `pytest`. `hatch run pytest` therefore ran anaconda's
  `pytest` (`/home/adria/anaconda3/bin/pytest`), outside the environment.

**Decision.**
1. Run the suite with the environment's own interpreter:
   `<env>/bin/python -m pytest`. Here `<env>` is
   `~/.local/share/hatch/env/virtual/cuemseditor/ObVrCH_5/cuemseditor`, which `hatch env find`
   prints.
2. Before each recorded run, run `<env>/bin/python -m pip install -e ../cuems-utils`, then assert
   that `cuemsutils.__file__` is under `../cuems-utils/src`.
3. Never record a run that followed `hatch run` without re-applying step 2.

FR-034's `evidence/environment.txt` records:
- the `cuems-utils` SHA;
- whether its `src/` is clean;
- `cuemsutils.__file__`;
- the interpreter;
- the suite result.

**Baseline.** With step 2 applied and `pytest` and `pytest-asyncio` installed into the
environment: **160 passed, 3 skipped**.

**Alternatives rejected.**
- Pinning to an index release: PyPI stops at rc15 (prompt §7).
- Adding a hatch `test` environment to `pyproject.toml`: that edits `pyproject.toml`, which S1
  freezes.

## R2. `config_load`'s read projection, per domain

**Measured.** `ConfigManager(load_all=False)` already holds `settings`, `node_uuid`, and an empty
`network_map` dict.

| Domain | Steps on a fresh `load_all=False` manager | Result |
|---|---|---|
| `settings` | `to_wire('settings')` | OK. Fields at the top level (`conf_path`, `library_path`, …), with no `Settings` wrapper |
| `network_map` | `load_network_map()`, then `to_wire('network_map')` | OK: `{"node_list": [{"node": {…}}]}`. Without the load: `TypeError: … is a dict, which carries no projection` |
| `project_mappings` | `load_net_and_node_mappings()`, `load_project_mappings(uname)`, then `to_wire('project_mappings')` | OK, with keys `number_of_nodes`, `defaults`, `nodes`, `new_nodes`. Without the first call: `AttributeError: … '_mappings'`, even when the file exists, because `load_project_mappings` reads `self.mappings['number_of_nodes']` |
| `project_settings` | (none) | Not in `_PROJECTABLE_SECTIONS`. This is `cuems-editor` UR-7 (gate G2) |

All three loader calls are public methods of `ConfigManager`.

**Round trip** (`to_wire` → JSON → `from_json` → `.save`): OK for `project_mappings`. It was
measured OK for `settings` and `network_map` before this spec (S3).

**Decision.**
- `config_load` builds one `ConfigManager(load_all=False)` per request, in the executor, and runs
  exactly the steps in the table for its domain.
- The table becomes a single dispatch table, `CONFIG_LOAD_STEPS`, next to `CONFIG_SAVE_TARGETS`.
- Nothing is cached between requests. That avoids prompt trap 2 (the startup copy).

**Alternatives rejected.**
- `ConfigManager(load_all=True)`: it reads every document, and the server's startup instance
  would serve stale data.
- Reading the XML directly: Principle V.

## R3. "Does the file exist?" and its revision, without duplicating the path convention

**Measured.**
- `project_path(uname, file)` and `conf_path(file)` raise `FileNotFoundError` exactly when the
  file is absent. That is `cuems-editor` UR-6's complaint about the write side.
- On the read side, the same behaviour is the public existence signal.

**Decision.**
- The target path comes from `conf_path` / `project_path`. `FileNotFoundError` from that call means
  `exists: false`.
- When the path resolves, the editor reads the bytes once in the executor and takes
  `hashlib.md5(bytes).hexdigest()` as the `revision`.
- The projection is loaded after the hash. If the file changes between the hash and the load, the
  client's next save gets `config_conflict`, which is safe, because the conflict carries the
  current document.

**Alternatives rejected.**
- `os.path.join(library_path, 'projects', uname, file)`: S6 forbids it.
- `mtime`: the prompt rules it out.

## R4. The no-file document: the descriptor's root `instance`

**Measured.** `get_schema_descriptor(schema)` marks root types with `key.is_path == True`.

| Domain | Root type(s) | Root `instance` |
|---|---|---|
| `settings` | `CuemsSettings` (`{"Settings": null}`) and `CuemsSettings/Settings` (the fields, all `null`) | two roots |
| `network_map` | `CuemsNetworkMap` | `{"node_list": {"node": [{…}]}}`, **not** the `to_wire` shape `[{"node": {…}}]` |
| `project_mappings` | `CuemsProjectMappings` | nested blocks, every leaf `null` |
| `project_settings` | `CuemsProjectSettings` | `{"setting": [{"name": null, "value": null}]}` |

`from_json(instance)` followed by `.save()` **is refused for every domain**, with `SchemaError`
`[T1]`: a required value is `null`. In `network_map`'s case, the `instance` also has the wrong
wire shape. This is the same defect `cuems-frontend` UR-1 reports for `script`, now measured on the
configuration schemas.

**Decision.**
1. Spec FR-013 stands as written (S3 is settled). For an absent file, the document is the
   `instance` of the root type whose `key.name` contains no `/` (`CuemsSettings`, `CuemsNetworkMap`,
   `CuemsProjectMappings`, `CuemsProjectSettings`). It is served unchanged, as a starting point for
   the form, not as a saveable document. `contracts/ws-messages.md` says so.
2. A client that saves it unedited gets `config_save_refused` with the library's location (R6).
   That is the structured refusal FR-020 adds. No data is lost, and no file is written.
3. Gate G3's report scope is extended by evidence, not by a new report: the
   `evidence/descriptor-instance-config.txt` capture lists the four refusals, and the G3 entry in
   the tag-readiness record names it. `cuems-frontend` UR-1 is the open report for "the instance is
   not wire-shaped and has null required defaults". The config schemas are more instances of it,
   and a second report would split one defect in two.

**Not decided here; recorded for the maintainer.**
- For a project with no `mappings.xml`, the library itself (`load_project_mappings`'s
  `FileNotFoundError` branch) adopts the **default mappings**. Those are what the engine actually
  uses for that project.
- S3 settles that the UI shows the `instance` in that case.
- Reconsidering would mean amending S3. It is not a plan decision.

## R5. Library refusals: where the location comes from

**Measured.**

| Input | Raised at | Exception | `violation` |
|---|---|---|---|
| unknown top-level key (`{"bogus": 1}`) | `from_json` | `IngestError` | none (no attribute) |
| `node_role: "bogus"` | `.save()` (T1), **not** `from_json` | `SchemaError` | `Violation(tier='T1', rule='XsdEnumerationFacets', location=(None, 'node_role'), message="… (at /…/node_role)")` |
| `adopted: "maybe"` | `.save()` | `SchemaError` | `None` |
| empty `database_name` | (none) | saved | (none) |

**Decision.** `config_save_refused` / `config_load_failed`'s `value` is:
- `schema`, `project_uuid`;
- `field`: `violation.location[1]`, or `null`;
- `location`: `violation.location` as a JSON list of strings or `null`s, or `null` when there is
  no violation;
- `rule`: `violation.rule`, or `null`;
- `message`: `str(error)`, verbatim.

The editor never parses the message for a path. `cuems-editor` UR-4 is the lesson there: prose is
not an interface.

`IngestError` and `SchemaError` (including `ValidationError` subclasses) map to the refusal frame.
Everything else (`OSError`, an unknown project) stays the error frame.

**Alternatives rejected.** Extracting the `(at /xpath)` suffix with a regex: it would make a library
sentence load-bearing.

## R6. Serialising saves of one file: an asyncio lock keyed by resolved path

**Measured.**
- `_save_config_document` runs `from_json` and `.save` in the executor.
- `.save` is an atomic temp-file rename (`save_xml`'s docstring; the same `write_tree` body).
- The editor is a single process, and all handlers run on one loop.

**Decision.**
- `server.file_locks`: a `dict[str, asyncio.Lock]` keyed by `os.path.realpath(target)`. It is
  created on the loop thread and never touched from the executor (Principle II).
- `config_save` acquires the lock, then awaits the executor three times: the hash, then the build
  and save, then the new hash. It releases the lock after the reply is queued.
- The same lock table, keyed by the script path, serialises `project_save`'s re-hash and update
  (R8). One table serves both document families.

**Alternatives rejected.**
- `fcntl` file locks: they guard against other processes, and nodeconf (the only other writer)
  writes a file the editor no longer writes (S5).
- A single global lock: it serialises unrelated files for no benefit.

## R7. `node_set`: the direct IPC hop to nodeconf

**Measured.**
- `cuemsutils.tools.CommunicatorServices.Communicator` (public; the engine, the editor and nodeconf
  all use it) is `pynng` `Req0`/`Rep0` with JSON-encoded dicts. It prefixes `ipc://` when the
  address lacks it.
- Its `__init__` calls `sys.exit(1)` on `PermissionError` from `check_path(address)`. Constructing
  one for an unreadable socket path kills the editor.
- Nodeconf's `engine_callback` (`CuemsNodeConf.py:368`) answers every request with
  `{"OK": bool, "error"?: str}`. Before `_ready` it answers `"nodeconf is still starting up"`.
  Today it answers `node_set` with `{'OK': False, 'error': 'unknown action: node_set'}`. That was
  measured by calling the real handler from an export of `2045897`, with `netifaces`, `systemd`,
  `dbus` and `zeroconf` stubbed in `sys.modules`.

**Decision.**
1. Check `server.nodeconf_available()` first. If it is false, reply at once with
   `node_set_refused`, reason `unavailable`, and no `Communicator` is built (FR-025).
2. Otherwise, build `Communicator('/tmp/nodeconf.ipc')` per request inside a `try` that catches
   `SystemExit` and `PermissionError` and turns them into `unavailable`. The `sys.exit` trap must
   never stop the process. Send `{"action": "node_set", "node_uuid": <coerce_identity string>,
   "alias": <str or null>}` under `asyncio.timeout(TIMEOUT)`.
3. A reply with `OK: true` gives the `node_set` confirmation to the caller, then
   `notify_all_node_list_update()`. A reply with `OK: false` relays `error` verbatim with no retry
   (FR-026), as `node_set_refused` with reason `nodeconf_error`. A timeout gives reason `timeout`.
4. `alias: null` asks nodeconf to remove the alias. That mirrors `cuems-utils` §0a G4's
   `set_alias(uuid, None)`.

**G4 test.** It imports `cuemsnodeconf.CuemsNodeConf` from the sibling `../cuems-nodeconf` working
tree, with the four OS modules stubbed. It calls `engine_callback` with the exact request the editor
sends, and asserts `{"OK": True}`.
- It is `xfail(strict=True, raises=AssertionError)`: an import failure is an error, not a silent
  xfail.
- It is skipped only when `../cuems-nodeconf` is absent (a deployed host).
- The checkout must be on a branch carrying `engine_callback` (`feat/xml-refactor`). On `main` the
  test errors, and says so. Quickstart step 1 lists this precondition.

**Alternatives rejected.**
- A long-lived `Communicator` built at startup: it would carry the `sys.exit` risk into startup and
  hold a socket for a daemon that is absent on most of the fleet.
- Relaying through the engine: rejected by Q2.

## R8. The repair gate keyed by project (Q1, Q4)

**Measured.**
- `CuemsDBProject.open(uuid)` resolves `script_path(unix_name)` and calls
  `CuemsScript.load_with_report(path)`.
- `update(uuid, data, preserve_original=)` does the trash move (`_save_preserving_original`) and an
  atomic save.
- `server.sessions[session_id]` persists across reconnects. A known `session_id` is reused
  (`CuemsWsServer.py:310-318`).

**Decision.**
1. `CuemsDBProject.open` also returns the md5 of the bytes it loaded. It reads the bytes once,
   hashes them, then loads that path. A change in the tiny window between the hash and the load
   shows up as a hash mismatch on the next save, which re-derives the gate, so the race fails
   safe.
2. A new `CuemsDBProject.inspect(uuid) -> (LoadReport, md5)` does the same read without building
   the wire value. It is used by FR-009 and FR-009a.
3. `server.repair_gates: dict[project_uuid, GateState]` (see [data-model.md](data-model.md)). It is
   read and written only on the loop thread.
4. `received_project` takes the path lock (R6), then decides:

   | State | Action |
   |---|---|
   | none | `inspect` in the executor. Create the state. Refuse if the outcome is not clean |
   | not clean | re-hash in the executor. A mismatch re-derives via `inspect`, gives a new `report_id`, clears the acknowledgments, and refuses unless the outcome is now clean |
   | not clean, hash matches | the session must be in `acknowledged_by` |
   | clean | no hash and no load (Q4) |

5. The refusal names a `report_id` that the session obtains through `project_load`. When the file
   is unchanged, `project_load` re-uses the outstanding `report_id` instead of minting a new one,
   so a second session loading the project does not revoke the first session's acknowledgment.
6. After a successful write, the state becomes clean, with the new file's md5 and no
   acknowledgments.
7. `project_unload` removes the session from `acknowledged_by`. The state is dropped when no
   session's `loaded_project` is the project. `project_delete` drops it.
8. `repair_acknowledge` checks `project_uuid` and `report_id` against `server.repair_gates`, not
   against `self.repair_state`. `self.repair_state` is deleted.

**Alternatives rejected.**
- Keying by `session_id` only: Q1.
- Re-loading on every save: Q4.
- Persisting the gate to disk: FR-009 re-derives it from the file, which already is the persistent
  record.

## R9. The `project` frame and boolean statements in the protocol document

**Measured.**
- `tests/ws-command-responses.txt` describes string booleans at `:103` (retired `initial_template`
  delta (a)), `:139` (`project`) and `:206-209` (nodes).
- `tests/test_project_payload.py` pins delta (e).
- `tests/test_payload_version.py` requires that a row exists for the advertised integer.

**Decision.**
- The restated row replaces lines 68-71.
- A new test, `tests/test_protocol_doc.py`, parses the document's live-frame sections. These are
  delimited by headings: `project`, `Nodes: adoption`, and the frame table. The test fails on
  `"True"` / `"False"` there. The `initial_template (retired …)` section is excluded by its
  heading.

## R10. Evidence immutability and `capture_load.py`

**Decision**, as the spec states (FR-030, M6):
- New: `specs/001-cuems-utils-migration/evidence/project-capture/capture_load_tip.py`. Its
  docstring names `capture_load.py` as superseded at the tip. It is a new file, which
  `evidence/README.md:10` permits.
- New: `specs/001-cuems-utils-migration/evidence/frontend-handover-instance-caveat.md`, naming
  `frontend-handover.md:44`.
- The run of the tip script is saved in `specs/002-config-round-trip/evidence/`.
- No existing evidence byte changes.
