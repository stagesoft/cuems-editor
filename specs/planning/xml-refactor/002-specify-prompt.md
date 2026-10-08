<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Prompt — start `cuems-editor`'s `002` specification (config round trip and consumer-round fixes)

**Paste everything below the rule into a new session running in
`/disk/Projects/StageLab/cuems-editor`.** It is written for a session with no memory of the
2026-10-07/08 analysis: everything it cannot discover from this repository is inlined, with the
measurement that backs it.

Measured 2026-10-07/08 against this repository's `feat/xml-refactor` @ `22093fd`, `cuems-utils` @
`67c89bd` (its 014 branch), `cuems-nodeconf` `origin/feat/xml-refactor` @ `2045897`.

---

You are starting the specification for `cuems-editor`'s feature **`002`**. Suggested short name:
`002-config-round-trip`. It collects the editor-side work that must land before the coordinated
tag `xml-refactor-merge-candidate` can be cut. Feature `001-cuems-utils-migration` is 62/63 done
and stays as it is, except for the bookkeeping in §6.

Branching: **`feat/xml-refactor` is the integration branch**. 001 lived on it, and the merge
candidate is cut from it.
- Start from it, with a clean tree.
- Let `/speckit.specify` create its numbered feature branch the normal way, branched from
  `feat/xml-refactor`.
- That branch **stays local**: commit to it, never push it, and never set an upstream for it.
- When the feature is done, it is merged into `feat/xml-refactor`; the merge and any push of
  `feat/xml-refactor` are the user's call.

## 1. Read these first, in this order

| Order | Document | Why |
|---|---|---|
| 1 | `specs/planning/xml-refactor/FROM-cuems-frontend-001.md` | the consumer's findings: seven items |
| 2 | `tests/ws-command-responses.txt` | the wire contract and the payload-version rule (lines 58-90) |
| 3 | `specs/001-cuems-utils-migration/spec.md`, `tasks.md` | FR numbering, the posture toward upstream gaps, what is already built |
| 4 | `specs/001-cuems-utils-migration/upstream-reports/UR-5-*.md`, `UR-6-*.md` | the strict-xfail posture this repository uses for upstream gaps |
| 5 | `../cuems-utils/specs/planning/upcoming-feature-requirements-2026-10-02.md` | the library's view of every open cross-repository item |
| 6 | `.specify/memory/constitution.md` | binding |

Cite upstream reports as **`<repo> UR-<n>`**, never as a bare number: numbers collide between
repositories (cuems-utils requirements doc §4).

## 2. Settled — do not re-open these in `/speckit.clarify`

1. **The library version stays `cuemsutils 0.1.0rc16`.** It is the coordinated version of the
   merge candidate, and nothing ships before every fix is in. `pyproject.toml`
   (`>=0.1.0rc16,<0.1.1`) and `debian/control` stay as they are. rc16 names both the 013 and the
   014 library, so record the exact `cuems-utils` commit this feature is verified against in
   `evidence/`, as 001 did for 013.
2. **The payload version stays `1`, with its definition restated.** `8f8b46e` moved booleans to JSON
   `true`/`false` without a bump. Version 1 never shipped, so it is redefined as the
   merge-candidate wire (real booleans), which is the "rule restated" option the frontend offered.
   No bump. The protocol doc must say so explicitly, so the frontend can drop its `'True'` string
   branch.
3. **Read values from the file, edit them in the UI, write them back.** The UI shows the file's
   real values, not descriptor defaults. The read projection is `ConfigManager.to_wire(section)` on
   a **freshly loaded** manager. Measured round trip (fixtures → `to_wire` → JSON → `from_json` →
   `save` → reload): `settings` and `network_map` reload equal. The descriptor serves form metadata
   only; its `instance` is the document only when no file exists yet.
4. **Every save sends the whole document.** The library replaces whole documents, and the round
   trip shows untouched fields come back intact. No patch format.
5. **`network_map.xml` is written by `cuems-nodeconf`; the editor does not write it.** Measured
   in nodeconf `CuemsNodeConf.py`:
   - `read_network_map()` runs only at startup.
   - `refresh_network_map` / `_save_network_map` write nodeconf's in-memory copy.
   - `CuemsNetworkMapType.refresh` decides whether to write by comparing in-memory signatures,
     never the file on disk.

   Any outside write is therefore silently reverted by nodeconf's next write (a discovery change,
   an IP change, any adopt or un-adopt). Field ownership:
   - `uuid`/`name`/`node_role`/`ip`/`online`: discovery overwrites them on every pass.
   - `adopted`: nodeconf, through `nodelist_modify` ADD/REMOVE.
   - `alias`: the operator, per the XSD comment. Also `role_id`/`hostname` during the transition.

   nodeconf also publishes `alias` over mDNS. So: `config_save` stops accepting `network_map`;
   reading it through `config_load` is fine; alias edits go to nodeconf over IPC (§3, item D).
6. **Every upstream gap stays a strict xfail that flips when the library fixes it**, never a
   hand-rolled workaround. Do not duplicate the `library_path/projects/<uname>/<file>` convention.
   Do not read `ConfigManager._project_settings_document`: `tests/test_public_surface.py` forbids it.
7. **Exit criterion: no strict xfail may remain when the tag is cut.** Every upstream gap in §4 is a
   tag gate, not a follow-up.

## 3. Scope — what the specification must cover

Each item names its evidence. Line numbers are at `22093fd`.

### A. Payload version 1 restated (frontend item 1)
- In `tests/ws-command-responses.txt`, the text still describes string booleans at lines 103, 139
  and 208. Delta (e) (`autoload`/`enabled`/`timecode` are JSON booleans) is pinned in
  `tests/test_project_payload.py` but is missing from the doc.
- Restate version 1 per §2.2. `tests/test_payload_version.py` keeps passing with `1`.

### B. The repair gate must survive a reconnect (frontend item 2)
- Today the gate state lives on the connection object, so a reconnect drops it:
  - `CuemsWsUser.repair_state` is set to `None` at construction (`CuemsWsUser.py:197`) and set only
    in `send_project` (`:809`, `:819`).
  - After a reconnect, `received_project` finds no state (`:913-915`). The save is accepted
    without an acknowledgement, and `preserve` (`:918`) is false, so the original file is not
    moved to the trash.
  - A re-sent `repair_acknowledge` gets the error frame (`:855-857`).
- `server.sessions` is keyed by a `session_id` that a reconnecting client reuses
  (`CuemsWsServer.py:310-318`).
- **Open for clarify:** key the gate by `session_id` (fixes reconnects only) or by project UUID on
  the server (also covers a second session, or a stale tab, saving a project it never loaded).
  Recommendation: by project UUID, because the risk is to the file on disk.
- Write the failing test first: load a repaired fixture, reconnect with the same `session_id`,
  send `project_save`, and expect `repair_save_refused`.
- `project_unload` (`:515-518`) must clear the new state.
- The frontend's workaround (re-loading the project on reconnect) becomes unnecessary.

### C. `config_load` + revision-checked `config_save` (frontend item 3)
- **New action `config_load`** `{schema, project_uuid?}` →
  `{schema, project_uuid, exists, revision, document}`.
  - `revision` is the md5 of the file's bytes. cuems-utils has no helper; use `hashlib`. Not
    mtime, which has coarse resolution on some filesystems.
  - A file that doesn't exist yet: `exists: false`, `revision: null`, and the descriptor's
    `instance` as the document, instead of the error frame.
  - `project_uuid` is required for the two project domains, resolved as `config_save` already does
    it (`get_project_unix_name`).
  - Domains: `settings`, `network_map` (read only), `project_mappings`, `project_settings`.
- **`config_save`** (`CuemsWsUser.py`, `_save_config_document`) gains `base_revision`.
  - Under one `asyncio` lock per target file, re-hash the file. A mismatch is refused with
    `config_conflict`, carrying the current document and revision.
  - Otherwise `from_json` → `save` → reply with the new `revision`.
  - Broadcast `config_changed` `{schema, project_uuid, revision}` to the other sessions.
  - Refuse `network_map` (§2.5), keeping the existing refusals of `script` and `hardware_outputs`.
- **Structured refusals:** today `SchemaError`/`IngestError` reach the client as a plain error
  string. Add `config_save_refused` carrying the violation's location, modelled on
  `load_failed_value` / `document_load_failed`.
- **Restart notice:** a `settings` save replies that `cuems-controller-engine` (plus
  `cuems-node-engine` where active) must restart. CLAUDE.md: the engine caches config at startup.
  Engine-side reload is out of scope.
- Every new frame type gets a row in `ws-command-responses.txt`. New types need no version bump.
- **Measured quirks to document, not fix:**
  - `save` writes unindented XML (`settings` went from 2429 bytes / 44 lines to 1901 bytes / 1 line).
  - `save` upgrades `doc_version` (2 → 3 for `settings`) and rewrites `schemaLocation`.
  - `from_json('settings')` accepts `to_wire('settings')`'s one-level-deeper body by design.

### D. Alias editing through nodeconf
- Forward a new IPC command to `/tmp/nodeconf.ipc`, shaped like `nodelist_modify`:
  `{"action": "node_set", "node_uuid": ..., "alias": ...}`. Operator fields only.
- The exact message shape is a **cross-repository contract** to agree with `cuems-nodeconf`. Today
  its `engine_callback` accepts only `nodelist_modify` ADD/REMOVE and answers anything else with
  `{"OK": false, "error": "unknown action: ..."}`.
- Where nodeconf is not running (`nodeconf_available` false, which is most of the fleet), answer
  "unavailable"; never write the file as a fallback.
- After a successful reply, refresh all sessions as `nodelist_modify` does. The `watch_network_map`
  push also covers it.
- Test against a fake IPC peer, as `tests/test_nodelist_actions.py` does.

### E. Documentation fixes (frontend items 4, 5, 6)
- Qualify the advice to build from `instance` (`ws-command-responses.txt:69-70`, `:95`;
  `specs/001-cuems-utils-migration/evidence/frontend-handover.md:44`). It is not directly usable
  until cuems-frontend UR-1 is fixed in cuems-utils.
- Add one line beside `project_save`: `value` is `{"CuemsScript": …}` and nothing beside it
  (`CuemsScript.from_json` refuses any other top-level key).
- `specs/001-cuems-utils-migration/evidence/project-capture/capture_load.py` fails on
  `load_xml`'s `(CuemsScript, LoadReport)` tuple. Update it to
  `script, report = …; script.to_wire()`, or add a note to its README. The evidence-immutability
  rule in `evidence/README.md` applies, so decide which.
- Document in the protocol doc that the descriptor renders `network_map`'s node `uuid` as a
  one-value enumeration (the NOT PROVISIONED sentinel). It is a known cuems-utils gap
  (requirements doc §5).

## 4. Upstream gates — each becomes a strict-xfail test here, all must flip before the tag

| Gate | Repo | Editor test that flips |
|---|---|---|
| **cuems-editor UR-6**: `conf_path`/`project_path` refuse a file not yet created; wanted shape `must_exist=False` | cuems-utils | existing `test_config_save_of_project_settings_fails_before_the_file_exists_pending_ur6` → a round-trip assertion |
| **cuems-editor UR-7 (to file in this feature)**: `project_settings` has no public read projection. It is missing from `_PROJECTABLE_SECTIONS` (`ConfigManager.py:166`) and has no public property | cuems-utils | `config_load('project_settings')` round trip |
| **cuems-frontend UR-1**: the descriptor `instance` is not in `to_wire()` shape, and required output fields have null defaults | cuems-utils | a cue built from `schema_descriptor('script')`'s instance, saved through `project_save` |
| **`node_set` IPC command** | cuems-nodeconf | the item D test against a real-shaped reply. Write the request to nodeconf as a report in `upstream-reports/` |

## 5. Out of scope

- cuems-engine config reload (the editor only sends the restart notice).
- The union-type descriptor fix, the library's XML formatting, and the release-time rebind of
  `<< 0.1.1~` across siblings (cuems-utils requirements doc §3). That rebind belongs to 0.1.1,
  not to this tag.
- `hardware_outputs` stays refused until cuems-utils gives it a model (planned for feature 015).
- Frontend changes. The frontend consumes this feature's contract.

## 6. Bookkeeping in 001 — already done on `feat/xml-refactor`

Committed together with this prompt and `FROM-cuems-frontend-001.md`, so the feature branch starts
clean:
- **T059** checked: implemented by `365d57f` and `d6fa83b`.
- **T034**'s text amended: its string `adopted`/`online` premise was retired by `8f8b46e`.

Verify both with `git log -1 -- specs/001-cuems-utils-migration/tasks.md` before starting.

## 7. Traps

- **The local hatch environment can't install from the index.** PyPI stops at `cuemsutils` rc15,
  so `hatch run` fails to create the default environment on the rc16 pin. Install from the sibling
  checkout, as `evidence/environment.txt` records (`pip install -e ../cuems-utils` into the
  environment), and record which commit it was.
- **`ConfigManager(load_all=True)` caches.** `config_load` must build a fresh manager per request,
  or it will serve the startup copy. The `_save_config_document` pattern (`load_all=False`) is the
  model.
- **`network_map`** is the only config schema whose decode runs the adapter table: `adopted`/
  `online` are `bool`, `node_role` is a `NodeRole`. The other three store scalars as given. Do not
  normalise.
- **A daemon that writes a file by replacing it whole** (`os.replace`) and never re-reads defeats
  any check the editor makes on disk. That is why §2.5 removes the write instead of checking
  revisions for `network_map`.
- **Files under `specs/001-cuems-utils-migration/evidence/` are immutable** (`evidence/README.md`). A re-baseline is a
  recorded diff.

## 8. Run

`/speckit-specify` with §2-§5 as the feature description, then `/speckit-clarify`. Clarify must at
least settle:
- the repair-gate key (§3 B);
- the `node_set` message shape, and whether `role_id`/`hostname` are editable;
- whether a `config_conflict` reply carries the current document or only the revision.

Then `/speckit-plan`, `/speckit-tasks`, `/speckit-analyze`.
