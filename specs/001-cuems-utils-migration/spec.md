<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Feature Specification: cuemsutils public-surface migration

**Feature Branch**: `feat/xml-refactor` (feature directory `specs/001-cuems-utils-migration/`; spec-kit's
own branch naming is deliberately not used — this branch matches every other repository in the
xml-refactor)

**Created**: 2026-10-01

**Status**: Draft — ready for `/speckit-clarify` (which is **not** optional for this feature; see
[Clarification agenda](#clarification-agenda))

**Base**: `feat/nodelist-adoption-api` @ `886f649` → bundle vendor `33d6915` → governance
`2fa5bcf` (spec-kit + constitution 1.0.0, GPG-signed). Not re-based.

**Input**: the bundle's context block, verbatim, from
`specs/planning/xml-refactor/00-runnable-flow.md` §3, followed by four additions that postdate it.

<details>
<summary>Context block (verbatim, 00-runnable-flow.md §3)</summary>

```
CONTEXT — read all four before writing anything. They are in this repository:
  specs/planning/xml-refactor/01-settled-decisions.md        the eleven decisions that bind this repo
  specs/planning/xml-refactor/02-consumer-audit-findings.md  C2, C3, C4, C5 and C11's minor half
  specs/planning/xml-refactor/03-migration-inventory.md      THE INVENTORY — verified 2026-09-25
  specs/planning/xml-refactor/04-wire-contract.md            THE PAYLOAD CONTRACT — read this first

TASK ZERO, BEFORE ANYTHING ELSE: make the process start. CuemsWsServer.py:24 imports
create_script and new_uuid from a module 008 deleted, so this repository currently fails at
import against its own declared dependency. Re-source new_uuid from cuemsutils.helpers, where
this repository already imports it at four other sites. create_script's replacement is the
descriptor work below — but do not let the template decision block the import fix; they are
separable and only one of them is blocking every other task in this spec.

WHAT MUST BE TRUE WHEN DONE:

- All FIVE CuemsParser call sites are gone: four in CuemsDBProject (update:356, new:489,
  duplicate:571, update_projects_existed_media:808) and the fifth in repair_durations.py:230.
  CuemsParser is a deprecated alias for CuemsScript.from_json.

- load_xml/save_xml (CuemsDBProject.py:895/:883) use CuemsScript.load/save, and the load path
  returns script.to_wire(). The payload obeys the AMENDED hard constraint: exactly two
  enumerated deltas, nothing else moved, and NOT unconditional byte-identity. Prove it by
  byte-comparison against a payload captured BEFORE the migration. Never by inspection, and never
  by checksum against `cuems-utils` `tests/golden/xml`: those files may hold a superseded state and
  are restated after the system refactoring. The XSD files under
  `cuems-utils/src/cuemsutils/xml/schemas/` are the schema. The projection appears ONCE, at the
  UI boundary: zero code paths may manipulate the wire dict to achieve an object-level result.

- The three raw-dict pre-parse fixups are resolved case by case, not by category.
  _fix_media_durations (:367) STAYS but operates on the loaded object, not a dict — that half is
  genuinely this repository's domain. _clean_dangling_targets (:387) and _nullify_dangling_refs
  (:417) are DELETED, not ported: the library does this now, and duplicating it here is exactly
  how the two drift apart. CHECK EACH against 008's repair-and-notify path first; what survives
  is what the library does NOT do.

- repair_durations.py is handled on its own terms and needs the most care of anything here. It
  exists to LOAD DELIBERATELY-CORRUPT DOCUMENTS. Move it off CuemsParser and XmlReaderWriter;
  drop its private TIMECODE_SHAPE regex (:43) for the library's canonical form; fix the dead
  guard at :87-89. FOLD PASS B (:187) into cuemsutils' cuems-convert-documents rather than
  maintaining a second <duration> rewriter — exactly ONE document rewriter remains in the
  ecosystem. PASS A (:138, ffprobe + DB) stays editor-local. VERIFY, do not assume, that it can
  still read the corrupt documents it exists to repair; that test is what proves 008's contract.

- 008's repair report reaches the user. load_with_report returns a structured LoadReport; this
  repository forwards it as a WS message and cuems-frontend renders it. cuemsutils deliberately
  CANNOT do this half — it has no UI channel and must not gain one. A repair that happens
  silently is the exact outcome D21's three-outcome design exists to prevent.

- A load stays a READ. A repaired document is never written back as a side effect of load; the
  repaired form reaches disk only through a user-initiated save. Accepted cost: an unsaved
  document is repaired identically on every open — the report's "file on disk is now stale" flag
  is what makes that legible.

- An unrepairable document gets a structured failure on the same channel as the report, naming
  the document AND the failing field, AND the full menu of next steps (restore from a conversion
  backup, correct the field by hand, and remove the document). The editor does not pick one.
  The project stays listed, the session survives, only that document refuses to open. A lenient
  read-only fallback is REJECTED — it reintroduces the permissive path 008 removed and creates a
  second reader for documents the strict path rejects.

- The save-after-repair ordering is honoured (D21b). Saving a repaired script overwrites the
  corrupt original with NO BACKUP. Wherever this repository calls load_with_report and later
  save() on the result, the report MUST have been surfaced first. cuemsutils cannot enforce this;
  state HOW this repository does, not merely that it must.

- The node reads follow the rename and the retyping. basic_fields at CuemsWsServer.py:425 names
  'node_type' — a key the converted document no longer has, so the merge SILENTLY DROPS the
  field. It becomes 'node_role'; its docstring at :384 moves with it. online/adopted are bool
  now, not the strings "True"/"False". The deprecated NetworkMap import at :23 goes, and :470's
  mutating get_nodes_by_adoption becomes partition_by_adoption — whose shape INVERTS: bare node
  objects in tuples, not {"node": ...} wrappers in lists.

- New WS message types serve the schema descriptor and accept config-domain saves. Model them on
  the initial_mappings (serve) + nodelist_modify (accept a mutation) pair, which is a config
  domain that ALREADY has both halves — not on initial_template, which is serve-only. Reach the
  descriptor through ConfigManager (D34), NEVER through cuemsutils.xml.descriptor.

- The network_map / project_mappings wire entanglement is untangled. reload_network_map_nodes
  (:439) merges network_map node status INTO mappings_dict (:417) and serves it as
  initial_mappings (:509-511), so a network_map edit reaches the UI inside a project_mappings
  payload. This is a SIMULTANEOUS behaviour change for three cuems-frontend components, two of
  which read initial_mappings straight out of localStorage. DO NOT LAND THE UNTANGLING BEFORE
  THE UI THAT CONSUMES IT.

- The cuemsutils pin is bounded, not just floored. >=0.1.0rc10 cannot express "refuse a library
  that moved past me". cuems-nodeconf's debian/control:18-19 is the model. Whether this
  repository gains a debian/ directory at all is a decision, not a foregone conclusion.

ALSO IN SCOPE, AND ABSENT FROM EVERY UPSTREAM DOCUMENT: the node-adoption surface the base branch
adds (03-migration-inventory.md section 8a). feat/nodelist-adoption-api is the editor third of an
unmerged three-repository feature from 2026-09-04; its counterparts are cuems-engine's
feat/nodelist-modify-dispatch and cuems-nodeconf's feat/nodelist-modify-hardening, and the UI tier
does not exist at all. Three consequences:
  - nodelist_get, node_status and nodeconf_available are new WS actions this migration carries
    forward. node_status relays the engine's cluster_status, so it is a contract with a branch that
    is also being migrated — coordinate, do not assume.
  - node_status.alive and each node's `online` are DIFFERENT FACTS with different freshness: ~30 s
    discovery versus sub-second ping/pong, and only the second is the signal the GO gate trusts
    (CuemsWsUser.py:469-472). Section 7's retyping of `online` to bool touches only the first. Do not
    let a descriptor-driven form collapse them.
  - nodeconf_available is injected into mappings_dict at :491 AND :537, so the entanglement is now
    THREE-WAY: project_mappings, network_map node status, and a liveness fact about a daemon that
    belongs to no schema. It must not become a project_mappings field. Decide where it lives BEFORE
    porting the config-domain forms.

DO NOT reach into cuemsutils.xml for any of this (Q14). If something needed is only available
there, that is the library's gap to close, not this repository's to work around.

DO NOT re-implement or re-test the node model here (007 FR-030a-i). A node-model test appearing
in this repository is a regression, not coverage.
```

</details>

**The four additions that postdate the block** (stated in full in [Motivation](#motivation),
[Ecosystem state](#ecosystem-state-2026-10-01), [Clarification agenda](#clarification-agenda) Q1 and
[Out of scope](#out-of-scope-deferrals-with-named-successors)):

1. **Ecosystem state has moved.** Four of six consumer flows have landed. `cuems-utils` 011
   (first install) and 012 (uuid4 convergence) have landed on their branches.
2. **This feature is the ecosystem's critical path.** `cuems-utils` 010's gate T049 cannot record zero
   while this repository's imports exist.
3. **The adoption partition has no public path.** The block says *"becomes `partition_by_adoption`"*.
   That method is internal (`UR-1`, open). The block's own last paragraph forbids reaching it. This
   spec resolves the contradiction (Option C, ratified in Clarifications).
4. **The hardware inventory is deferred to `cuems-utils` 014**, by name.

---

## Clarifications

### Session 2026-10-01

- Q: Should this feature also include the two stories that need `cuems-frontend` changes (US4 repair
  report, US8 descriptor/untangling/handshake), or only the work that doesn't? → A: **All of US1–US8
  stay in this feature.** Every repository in the ecosystem lands together under the coordinated
  `xml-refactor-merge-candidate` tag, and the bounded version pins block any partial upgrade. So the
  UI-coordinated stories ride that same release instead of a successor feature. This repository's
  candidate tag therefore waits on `cuems-frontend` 05. The census-zero milestone that unblocks
  `cuems-utils` T049 does **not** wait (FR-048).
- Q: How should the editor work out which nodes are adopted, now that `get_nodes_by_adoption` is
  deprecated and `partition_by_adoption` is internal? → A: **Option C.** File an upstream report
  citing `cuems-engine`'s `UR-1`. Meanwhile, compute the split locally as a read-only selection over
  `ConfigManager.network_map`. The local selection's docstring names the report as its successor
  (FR-009).
- Q: Once `create_script()` is gone, what should the `initial_template` message contain? → A:
  **Option A.**
  - **Milestone 1:** send `ConfigManager.generate_example(SchemaName.SCRIPT)`. Every difference from
    the old `create_script()` output is enumerated as a wire delta. The baseline is reconstructed from
    the last `cuemsutils` release that still shipped the module.
  - **Milestone 2:** retire `initial_template` in favour of the descriptor's per-type empty
    instances, behind the payload-version handshake (FR-008, FR-008a).
- Q: If the library repaired a script on load, what must happen before a session may save it? → A:
  **Option C.** The save is refused until **that session** acknowledges **that report**. Before the
  first save overwrites the corrupt original, a copy of the original is moved to `trash/`
  (FR-021, FR-021a).
- Q: After the migration, what happens to pass B of `cuems-editor-repair-durations`, the
  `<duration>` XML rewriter fed from the editor's DB? → A: **Option B. Pass B is retired.**
  - Pass A corrects the DB.
  - Each project's `script.xml` is corrected on its next user-initiated save, by the existing save
    path.
  - The tool reports every project whose `script.xml` still holds an uncorrected duration as
    *needs a save*.
  - The editor then has no document rewriter, and `cuems-convert-documents` is the only one in the
    ecosystem.
  - The tool never converts a version-1 script, so the old Q5 does not arise.
  - No upstream change is needed, so flow §5.6 is answered "no".

  Accepted cost: an unsaved project keeps its short durations on disk, and the engine plays from
  disk (FR-023–FR-027).
- Q: Where should this repository's Debian packaging live, and should it carry the bounded
  `cuemsutils` dependency? → A: **On `feat/xml-refactor`, with the explicit bound.**
  - `debian/` is brought from `origin/debian/bookworm` (`72f952a`, 7 commits behind) onto the working
    branch. `Depends:` gains the explicit bound `>= 0.1.0rc16`, `<< 0.1.1~`.
  - **`debian/bookworm` is NOT retired.** It stays as the branch future packaging automation builds
    from.
  - What is required is **consolidation**: every `debian/` change made on the working branch is
    applied to `debian/bookworm` as well, so the two never diverge (FR-038, FR-038a).
- Q: When milestone 2 separates node information from the project mappings payload, which message
  carries `nodeconf_available`? → A: **Option B.** It is an envelope field of the new node-list
  message and of `nodelist_get`'s reply. It sits next to the node arrays but outside the
  `network_map` data, and it is sampled each time the message is built (FR-032, FR-046).
- Q: What form should the editor ↔ UI payload version take, what is its first value, and which
  changes bump it? → A: **Option A.** An integer, sent as the first message on every connect, before
  any `initial_*` message. It starts at **1**, and the absence of the handshake means 0. It is bumped
  by one for any change to an existing message; it is not bumped for a new message type or a new
  optional key. The UI refuses any value it was not built for (FR-047, FR-047a).
- Q: When `network_map.xml` lists two nodes with the same identity, what should the editor do?
  → A: **Option A.**
  - No retry.
  - Log the collision distinctly, naming the identity.
  - Keep serving the last good node list.
  - Broadcast a new `network_map_error` message (the kind, the identity, the file) to all sessions.
  - Broadcast its clearing once a later read succeeds (FR-036a).
- Q: How should the unmerged three-repository node-adoption work reach the main line? → A: **Option
  A.** It lands **through** this migration, with no separate merge. The coordinated tag carries it in
  all three repositories. The tag message names the three adoption branches as included, and the PR
  reviews them as part of this feature (FR-039a).
- Q: On an unrepairable document, does the failure name one next step or the full menu? → A: **The
  full menu, always.** `next_steps` is
  `restore_from_conversion_backup`, `correct_field_by_hand`, and `remove_document`, in that order.
  The editor does not pick among them (FR-020, analysis I1, 2026-10-01).
- Q: Does the branch window before the save gate (a repaired script can be saved with no
  acknowledgment) ship? → A: **No.** US1–US8 ship together under one candidate tag. Census zero is
  a source announcement to `cuems-utils` T049, not a package and not a controller deploy. The
  unacknowledged-save window never lands on its own (analysis C1, 2026-10-01).
- Q: Are `cuems-utils` `tests/golden/xml` the schema authority for this migration? → A: **No.** The
  XSD files in `cuems-utils/src/cuemsutils/xml/schemas/` are the single source of truth. The golden
  XML may already be a superseded snapshot. It is restated after the whole system refactoring. If a
  contradiction with the XSD appears during that work, the golden is regenerated in `cuems-utils`.
  This repository does not edit those files, and a golden checksum is not a pass condition here
  (FR-011, FR-040, 2026-10-01).

---

## Motivation

### What this feature is, in constitutional terms

The constitution was ratified 2026-10-01 (1.0.0) and records its own violations at ratification.
**Principle V — "cuemsutils Is Consumed Through Its Public Surface" — is violated by this repository
today.** This feature closes that violation. The census it closes, re-measured on this branch at
`2fa5bcf` with
`grep -rnE "cuemsutils\.(xml|timeoutloop|create_script)" src tests`, gives **seven imports across four
files** (three shipped, one test). That matches the 2026-10-01 measurement it was handed:

| Site | Import | Kind |
|---|---|---|
| `src/cuemseditor/CuemsWsServer.py:26` | `from cuemsutils.xml import NetworkMap` | deprecated alias |
| `src/cuemseditor/CuemsWsServer.py:27` | `from cuemsutils.create_script import create_script, new_uuid` | module already deleted |
| `src/cuemseditor/CuemsDBProject.py:9` | `cuemsutils.xml.Parsers.CuemsParser` | deprecated shim |
| `src/cuemseditor/CuemsDBProject.py:10` | `cuemsutils.xml.XmlReaderWriter.XmlReaderWriter` | deprecated shim |
| `src/cuemseditor/repair_durations.py:39` | `cuemsutils.xml.Parsers.CuemsParser` | deprecated shim |
| `src/cuemseditor/repair_durations.py:40` | `cuemsutils.xml.XmlReaderWriter.XmlReaderWriter` | deprecated shim |
| `tests/test_repair_durations.py:6` | `cuemsutils.xml.XmlReaderWriter.XmlReaderWriter` | deprecated shim, test-only |

Behind those seven imports are **fourteen call sites in three files** (`cuems-utils`
`specs/planning/refactor-sequencing-2026-10-01.md`, corrected upstream at `e9ed8af` the same morning):
in `CuemsDBProject.py`, 4 × `CuemsParser` + 2 × `XmlReaderWriter`; in `repair_durations.py`, 3; in
`CuemsWsServer.py`, 1 × `get_nodes_by_adoption`, 1 × `create_script` and 3 × `new_uuid`.

### Why this is the critical path for the whole ecosystem

This argument is invisible from inside this repository, and it is the strongest one the feature has.

`cuems-utils` feature 010 has a gate, **T049**: an import census of the library's deprecated surface,
taken across all six consumers, must **record zero**. Its tasks T051–T061 are *structurally* blocked
on that zero. Measured 2026-10-01:

| Repository | Hits | Classification |
|---|---|---|
| **`cuems-editor`** | **6 in shipped `src/`** | **the only live ones** |
| `cuems-engine` | 1 | in `dev/CuemsEngine_old.py` — not packaged |
| `cuems-nodeconf` | 1 | prose in a docstring, not an import |
| `cuems-power-bridge`, `cuems-common`, `cuems-frontend` | 0 | clean |

So this repository alone holds back several things in `cuems-utils`:

- the deletion of five library modules;
- the removal of seven deprecated aliases and two deprecated-symbol sites;
- the retirement of 22 contract tests;
- the `v0.1.1` version move that `cuemsutils._deprecation.REMOVAL_RELEASE` has promised for two
  features.

Feature 010 cannot close while these imports exist.

### Why it is urgent locally

**The editor does not start.** Re-verified on this branch, against `cuems-utils` `0.1.0rc16` (`src/`
at `012-uuid4-convergence` @ `e9ed8af`):

```
$ python -c "import cuemseditor.CuemsWsServer"
ModuleNotFoundError: No module named 'cuemsutils.create_script'   (CuemsWsServer.py:27)
```

Finding C2 is live. No call site in this repository is reachable, so the suite's colour means
nothing until task zero lands.

---

## Ecosystem state, 2026-10-01

This supersedes `00-runnable-flow.md` §0 and §7, which were measured 2026-09-25.

| Repository | Flow | State | Candidate tag |
|---|---|---|---|
| `cuems-common` | 03 | landed | `e3c9430`, pushed |
| `cuems-nodeconf` | 04 | landed; re-cut 2026-10-01 for `cuems-utils` 012 | `5be6cf0`, pushed |
| `cuems-power-bridge` | 07 | landed, closed | `399baf7`, pushed |
| `cuems-engine` | 01 | landed as its `008-cuems-utils-migration`, 64/64 | `1662a99`, cut 2026-10-01, not pushed |
| **`cuems-editor`** | **02** | **this feature** | — |
| `cuems-frontend` | 05 | not started; deliberately after `cuems-utils` 013 | — |
| `cuems-utils` | — | 011, 012 landed on their branches; 013/014 not begun | none — tags last (D27) |

What `cuems-utils` 011/012 mean here, as constraints on this spec:

- **012: node identities are uuid4 or the not-provisioned sentinel**, on read and on write
  (`network_map` 1→2, `project_mappings` 1→2, `settings` 2→3). This repository's fixtures carry no
  non-uuid4 identity, so the suite result was the same before and after 012 (54 passed / 7 failed).
- **012: `ConfigManager.node_uuid` returns a `Uuid` on a provisioned node.** `Uuid` compares, hashes
  and sorts like its string form but is **not** a `str` subclass. `CuemsWsUser.py`'s
  `nodelist_modify` uuid check (`isinstance(node_uuid, str)`) is fed from the websocket and is
  unreachable by a library identity today. This feature MUST keep it unreachable (FR-034).
- **012: `cuemsutils.tools.coerce_identity` is public.** Any comparison between an identity from JSON
  and one from the map uses it rather than a local rule (FR-035).
- **012: a duplicate node identity in `network_map` now raises `ValidationError`** for every reader.
  This repository is a map reader (Edge Cases).
- **No `cuems-utils` rollback once the stack restarts**: a document written by the new library
  carries a version marker the old library refuses. This feature has nothing to do about it; it is
  stated here so the upgrade window is planned with it in mind.

---

## Measured findings that correct this spec's inputs

Section 12 of the prompt asked for any mismatch to be stated, not reconciled silently. Each of these
was measured on this branch at `2fa5bcf`, against `cuems-utils` `src/` @ `e9ed8af`, running
`pytest --continue-on-collection-errors`.

**F1 — The census is still seven.** No change from the input.

**F2 — The "7 pre-existing failures" are not unrelated to this migration. They *are* C2.**

- The input described them as unrelated, all in `TestNodeconfAvailableFlag`.
- Measured: they are **3 in `TestNetworkMapWatcher` + 4 in `TestNodeconfAvailableFlag`**. **All seven**
  fail with `ModuleNotFoundError: No module named 'cuemsutils.create_script'`, reached through a lazy
  `from cuemseditor.CuemsWsServer import CuemsWsServer` inside the tests.
- They were "identical before and after 012" because they never reached any 012-affected code.
- Task zero (0a) is expected to turn all seven green. Clarify item §9.4 is answered by measurement:
  they are this feature's to fix, and nobody else owns them.

**F3 — `tests/test_media.py` does not import `cuemsutils.create_script`.**

- Both it and `tests/test_repair_durations.py` fail at collection **transitively**, via
  `cuemseditor.cli` (`:30`) → `CuemsWsServer` (`:27`).
- `test_media.py` has no `cuemsutils` import of its own. `test_repair_durations.py` has one, the census
  site at `:6`.
- So both modules come back into the suite **by construction** when 0a lands. That answers §9.3: both
  are in scope.

**F4 — Exit criterion 9 ("`test_nodelist_actions.py` green throughout and *unedited*") cannot hold
under any option for the partition.**

- `TestNodeconfAvailableFlag._reload` patches `cuemseditor.CuemsWsServer.NetworkMap` and stubs
  `MockNM.get_nodes_by_adoption`.
- Removing that import, which Principle V requires under options A, B and C alike, makes `patch()`
  raise `AttributeError`. That breaks exactly two tests: `test_true_when_the_socket_is_there` and
  `test_false_when_nodeconf_is_disabled`.
- The helper mocks an implementation dependency, not the surface the file pins. FR-041 sanctions one
  narrow, recorded edit to it.

**F5 — `generate_script_example` is internal, but it has a public path.**

- It is defined in `cuemsutils.xml.descriptor`, which consumers must not import.
- It is reachable as `ConfigManager.generate_example(SchemaName.SCRIPT)`. The descriptor itself is
  reachable as `ConfigManager.get_schema_descriptor(SchemaName)` (D34).
- So 0b has a Principle-V-clean answer, and Q2 is a contract question rather than a surface one.

**F6 — The decoded `network_map` node serialises to the old wire form.**

- In memory, `adopted`/`online` are `bool`, `node_role` is a `NodeRole` enum and `uuid` is a `Uuid`.
- `json.dumps` of the decoded node nevertheless emits `"adopted": "True"`, `"node_role": "controller"`
  and the uuid as a string.
- The risk is therefore not the `initial_mappings` wire form of an *unmerged* node. It is:
  - **(a)** in-memory comparisons inside the editor;
  - **(b)** the `merge_node_data` path, which `.copy()`s nodes into fresh dicts and may lose that
    projection.
- (b) is unmeasured, and FR-031 pins it.

**F7 — A census-boundary question the grep cannot see.**

- `cli.py:29` imports `ProjectMappings` **from `cuemsutils.tools.ConfigManager`'s module namespace**.
- The class is defined in `cuemsutils.xml.settings` and bound there by a plain import. It is not
  declared public anywhere (`cuemsutils.tools.__all__ == ["SENTINEL", "coerce_identity"]`).
- The census regex does not match it, so it is not one of the seven. Whether it is a Principle V
  violation is settled in the agenda (Q6): it is, and it is carried to `cuems-utils` 014 together with
  the `default_mappings.xml` read it serves.

---

## User Scenarios & Testing *(mandatory)*

The "users" of this feature are three groups:

- the **show operator**, who opens, edits and saves projects through the UI;
- the **ecosystem maintainer**, who is waiting on T049 and the release;
- the **UI team**, whose code reads every payload this repository emits.

All eight stories are in this feature (Clarifications, Q4). They land in two milestones on
`feat/xml-refactor`:

- **Milestone 1 — census zero.** Stories 1–3 and 5–7 take the census to zero and keep every existing
  payload intact, with no `cuems-frontend` change. This unblocks `cuems-utils` T049, and it MUST NOT
  wait on the UI.
- **Milestone 2 — the coordinated wire.** Stories 4 and 8 are UI-coordinated. They are built on the
  same branch, and the candidate tag is cut only when `cuems-frontend` 05 consumes them.

### User Story 1 — The editor starts again (Priority: P1)

An operator restarts `cuems-editor.service` on a controller running the current `cuemsutils`. Today it
dies at import. After this story, it reaches its listening state and serves clients exactly as it did
before 008.

**Why this priority**: it blocks everything. No other story can be verified while the process cannot
import, and seven of today's nine non-passing tests are this story (F2).

**Independent Test**: import every `cuemseditor` module against the declared `cuemsutils`. Start the
server against a temporary library and confirm it accepts a WebSocket connection. Run the full suite
and confirm all six test files collect.

**Acceptance Scenarios**:

1. **Given** the current `cuemsutils`, **When** every module under `cuemseditor` is imported, **Then**
   none raises. This is pinned by a smoke test that exists before the fix and fails against it
   (constitution gate IV.1).
2. **Given** a configured controller and both 0a and 0b (FR-001, FR-008), **When** the service
   starts, **Then** it reaches its listening state on `:9092`. This is recorded as an observable
   condition, separately from "the suite is green". 0a alone gets the module importing, but the
   constructor still calls the deleted `create_script()`.
3. **Given** the fix, **When** the suite runs, **Then** `test_media.py` and `test_repair_durations.py`
   collect. The seven `test_nodelist_actions.py` failures in F2 pass with no edit to that file.
4. **Given** the 0a fix, **When** the diff is inspected, **Then** it touches only the line-27
   import: `new_uuid` is re-sourced and the `create_script` name is dropped from that import. The
   template replacement (0b) and the partition (0c) are not part of it.

---

### User Story 2 — The editor uses only the library's public surface (Priority: P1)

The ecosystem maintainer runs the T049 census across all six consumers and gets zero hits from this
repository. They can then delete the deprecated surface and move `cuemsutils` to `v0.1.1`.

**Why this priority**: this is what the rest of the ecosystem is waiting on, and it is the
constitutional violation the feature exists to close.

**Independent Test**: run the census grep against `src/`. Run a public-surface test that asserts the
retired names are absent from the editor's modules, following `cuems-engine`'s
`tests/test_public_surface.py`, so the removal cannot be undone by re-spelling it.

**Acceptance Scenarios**:

1. **Given** the migrated tree, **When** the census grep runs over `src/`, **Then** it returns zero.
   Any remaining test-only import carries a `# test-only` label so a census can tell it apart.
2. **Given** the migrated tree, **When** searched, **Then** `CuemsParser`, `XmlReaderWriter`,
   `create_script` and `get_nodes_by_adoption` appear nowhere in `src/`.
3. **Given** a client connects, **When** it receives `initial_template`, **Then** the payload is the
   the library's generated example (FR-008). Every difference from the pre-008 payload is
   enumerated as a wire delta, not discovered.
4. **Given** the adoption partition is needed, **When** the editor computes it, **Then** it does so by
   a read-only local selection, and an upstream report records the library's gap (FR-009).

---

### User Story 3 — Projects open and save exactly as before, except for two named changes (Priority: P1)

An operator opens an existing project, edits a cue and saves. The UI receives the same `project_load`
payload as before 008, byte for byte, except for two deltas:

- **(a)** `schemaLocation` is absent;
- **(b)** `Media.duration` arrives as `{"CTimecode": "HH:MM:SS.mmm"}`.

Key order and the string boolean form are unchanged.

**Why this priority**: the payload is a contract with a UI this repository cannot deploy in lockstep
with (Principle I). A silent third delta shows up as wrong behaviour during a show.

**Independent Test**: capture the `project_load` payload for a fixture set **before any source
change** and commit it. After the migration, compare byte-for-byte and assert that the only
differences are (a) and (b). Schema truth is the XSD under
`cuems-utils/src/cuemsutils/xml/schemas/`, enforced by the library's public load and save. Do not
compare against `tests/golden/xml`: those files may be superseded and are restated after the
system refactoring.

**Acceptance Scenarios**:

1. **Given** a pre-migration capture, **When** the same project loads after migration, **Then** the
   payload differs only by (a) and (b). This is asserted by a test, not by inspection.
2. **Given** the XSD under `cuems-utils/src/cuemsutils/xml/schemas/`, **When** a document is opened
   through the public load, **Then** acceptance or refusal is that schema's. A golden under
   `tests/golden/xml` that disagrees with the XSD is recorded for regeneration in `cuems-utils`. It
   is not a failure of this editor, and this repository does not rewrite it. The editor's own
   pre-migration capture is not regenerated to make the two-delta comparison pass.
3. **Given** a project is opened and closed without saving, **When** the file on disk is inspected,
   **Then** it is byte-identical to before. A load is a read.
4. **Given** a save from the UI, **When** it is written, **Then** it goes through the library's save
   path. The FadeCue duration validation still rejects bad durations with a message naming the
   offenders.
5. **Given** a media item whose stored duration is zero or short, **When** the project is saved,
   **Then** the database-sourced correction still applies, now on the object rather than on a raw
   dict. This save path is also how scripts listed as *needs a save* (US5) get corrected.
6. **Given** a dangling cue reference, **When** the project loads, **Then** the library clears it and
   reports it. The editor no longer runs its own dangling-reference walk.

---

### User Story 4 — The operator is told when a document was repaired, or cannot open (Priority: P2, UI-coordinated, milestone 2)

An operator opens a project whose script the library had to repair on load. The UI receives a
structured report of what was repaired and whether the file on disk is now stale. If the operator then
saves, they have already seen that report.

If the script cannot be repaired, the operator gets a structured failure. It names the document and
the failing field, and always offers the full menu of next steps: restore from a conversion backup,
correct the field by hand, and remove the document. The editor does not pick one. The project stays
listed, the session survives, and only that document refuses to open.

**Why this priority**: D21/D21b. A repair that reaches disk unseen is a constitutional violation
(Principle III). It ranks below P1 because rendering the report is `cuems-frontend`'s half.

**Independent Test**: load a repairable fixture and assert the report message's shape, and that the
file is untouched. Load an unrepairable fixture and assert the failure message's shape. Assert the
session is still alive and other projects still list. Attempt a save of a repaired document by the
acknowledgment gate (FR-021) and assert that the original is preserved first (FR-021a).

**Acceptance Scenarios**:

1. **Given** a repairable document, **When** it loads, **Then** a report message is emitted. It is
   never absent, and never `None` in place of an empty report.
2. **Given** an unrepairable document, **When** it loads, **Then** a failure message names the
   document, the field, and all three next steps (`restore_from_conversion_backup`,
   `correct_field_by_hand`, `remove_document`). There is no lenient fallback reader.
3. **Given** a repaired, unsaved document, **When** it is opened again, **Then** it is repaired and
   reported identically. The report's "stale on disk" flag is set.
4. **Given** a repaired document that the saving session has not acknowledged, **When** a save is
   requested, **Then** it is refused with a message naming the report. **Given** the acknowledgment,
   **When** saved, **Then** the corrupt original is first preserved in `trash/`, and then the
   repaired form is written.

---

### User Story 5 — The duration-repair tool fixes the database and says which projects still need a save (Priority: P2)

A maintainer runs `cuems-editor-repair-durations` against a library whose database and scripts carry
durations the historical `get_duration` bug stored short.

- The tool re-probes the media and corrects the database (pass A). It backs up the database first and
  offers a dry run.
- It then reads every project's script and lists each project whose `script.xml` still holds an
  uncorrected duration, as *needs a save*. It writes no script.
- The operator opens and saves each listed project. The editor's ordinary save path writes the
  corrected durations.

**Why this priority**: the tool's purpose is dealing with corrupt data, which a now-strict parser
opposes. It rewrites user data in bulk (Principle III). Retiring pass B (Clarifications) moves the
script correction onto the save path, which is already validated and backed up.

**Independent Test**: run the tool on a recorded fixture set, in dry-run mode and then with
`--apply`. Assert:

- the database corrections and the database backup;
- that **no** `script.xml` changed (checked by checksum);
- the exact *needs a save* list.

Then save one listed project through the editor, re-run the tool, and assert that the project has left
the list.

**Acceptance Scenarios**:

1. **Given** the recorded corrupt fixture set, **When** the tool runs with `--apply`, **Then** the
   database is corrected and backed up. Every script file is byte-identical afterwards.
2. **Given** the fixture set, **When** the tool reads each script, **Then** every script it exists to
   report on is read. A script it cannot read is reported `SKIPPED_INVALID` with the reason, never
   silently dropped.
3. **Given** a script duration that is now a structured value, **When** the tool compares it with the
   corrected database value, **Then** a mismatch is detected and listed. A test pins this and fails
   first against the pre-migration guard at `repair_durations.py:87-89`, which never fires on
   structured values (FR-030a-ii, C11 minor).
4. **Given** a project listed as *needs a save*, **When** an operator saves it through the editor,
   **Then** its durations are corrected on disk and a re-run no longer lists it.
5. **Given** the migrated tree, **When** searched, **Then** no code in this repository writes a script
   document except the editor's save path. `cuems-convert-documents` is the ecosystem's only document
   rewriter. No version-1 script is converted by this tool.

---

### User Story 6 — The node list stays correct through the port (Priority: P2)

An operator opens Settings. They see every node with its correct role, adoption state and online
status, can adopt and un-adopt nodes, and see a node that powers on later appear without
reconnecting. The adoption controls are greyed out where `cuems-nodeconf` is not running.

**Why this priority**: `node_type` → `node_role` is a silent-wrong site. The merge keeps resolving and
quietly drops the field. The node-adoption surface is unmerged work this branch carries.

**Independent Test**: `tests/test_nodelist_actions.py` passes (with the one FR-041 edit). Add a test
that feeds the merge a converted node carrying `node_role` and asserts the field reaches the merged
output; this test fails against `node_type` first. Add a test that pins the `initial_mappings` wire
form of merged nodes.

**Acceptance Scenarios**:

1. **Given** a converted `network_map`, **When** nodes merge into the mappings payload, **Then**
   `node_role` is carried. A test shows it was dropped before the fix.
2. **Given** a merged node, **When** `initial_mappings` is serialised, **Then** `adopted`, `online`,
   the role and the uuid have the same wire form as before the migration (F6). Any difference is an
   enumerated delta.
3. **Given** `node_status` and a node's `online`, **When** both are served, **Then** they stay two
   distinct facts on two distinct messages.
4. **Given** `cuems-nodeconf` stops while Settings is open, **When** the next message is built,
   **Then** `nodeconf_available` reports `false`. It is sampled live, never cached.
5. **Given** an adopt that fails with `cuems-nodeconf`'s *"Node … not found"* readiness-window error,
   **When** it is relayed, **Then** the string is passed through unchanged. No retry and no
   interpretation is added here.
6. **Given** `cuems-nodeconf` writes a map with a duplicated node identity, **When** the editor reads
   it, **Then** it does not retry, keeps the last good node list, and broadcasts `network_map_error`
   naming the identity. A later good read broadcasts its clearing.

---

### User Story 7 — The release gate can refuse a library that moved past this editor (Priority: P3)

The maintainer packages the ecosystem release. This repository declares the `cuemsutils` range it was
migrated against, bounded on both sides. It does not claim compatibility with the `v0.1.1` that
deletes the surface it used to depend on.

**Why this priority**: required for release (C7, Principle V). It is cheap, and it only matters once
stories 1–3 are true.

**Independent Test**: inspect the declared dependency and confirm it is `>=0.1.0rc16,<0.1.1`. Confirm
the `debian/` decision is recorded either way.

**Acceptance Scenarios**:

1. **Given** the package metadata, **When** read, **Then** the floor is `0.1.0rc16` or higher and the
   ceiling is `<0.1.1`. The floor is never lowered.
2. **Given** the feature is done, **When** the candidate tag is due, **Then** a tag message is prepared
   in `../.xml-refactor-tag-messages/`. The tag itself is the maintainer's to cut.

---

### User Story 8 — Configuration forms are driven by the schema, and the node domain gets its own wire (Priority: P3, UI-coordinated, milestone 2)

The UI team builds configuration forms from a schema descriptor that the editor serves, and saves
them through an accept message. Node status arrives on its own message instead of inside the project
mappings. A UI that does not understand the payload version refuses and says so, rather than
mis-rendering.

**Why this priority**: D25/D26 and FR-108 require it. But it is a **simultaneous** behaviour change
with three `cuems-frontend` components, two of which read `initial_mappings` from `localStorage`.
`cuems-frontend` 05 is deliberately scheduled after `cuems-utils` 013. So this story is in milestone
2: it ships in the coordinated `xml-refactor-merge-candidate` release with that UI, and it must not
hold up milestone 1.

**Independent Test**: a contract test per new message family, asserting the payload and its audience.
A handshake test asserting that the payload version is sent first, and that its value matches the
recorded bump history (FR-047, FR-047a).

**Acceptance Scenarios**:

1. **Given** a client, **When** it asks for a schema descriptor, **Then** it receives one obtained
   through `ConfigManager`, with field names, types, cardinality, enumerations and defaults.
2. **Given** the untangled wire, **When** a node's status changes, **Then** it reaches the UI without
   travelling inside a `project_mappings` payload. `nodeconf_available` does not become a
   `project_mappings` field.
3. **Given** any client, **When** it connects, **Then** the first message it receives is the
   payload version (`1`), before any `initial_*` message. A UI built for another value refuses with
   a stated reason; that is the UI's half. The payload version is never confused with `doc_version`.

---

### Edge Cases

- **Duplicate node identity in `network_map`** (012): the map load now raises `ValidationError`.
  `reload_network_map_nodes` retries three times and then returns `False`. The watcher would then
  keep serving the last good node list with no indication to the operator. The editor MUST log the
  identity collision distinctly from a transient read error, and MUST NOT retry it as if it were one.
  The UI is told through `network_map_error` (FR-036a).
- **A project whose script is newer than the library**: the load raises. This is treated as the
  unrepairable path (US4), naming the document version.
- **`script_file_name` divergence**: `cli.py:41` uses `'script.xml'`, while
  `CuemsProjectManager.py:38`'s docstring shows `'cue_script.xml'`. Recorded only. It is `cuems-utils`
  012's trap, not this feature's work.
- **A legacy project under `duplicate()`**: it stays deliberately unvalidated (CLAUDE.md). The
  migration MUST NOT make `duplicate()` stricter than it is today, beyond what the library's load
  itself enforces. Any project that duplicated before and no longer does is recorded.
- **Old UIs sending zero media durations**: inbound handling keeps accepting them (Principle I).
- **`initial_template` between 0a and 0b**: after FR-001 lands but before FR-008 does, the server
  still calls the deleted `create_script()`. So 0a alone does not make the constructor run. FR-001's
  smoke test covers import. The listening-state check (FR-003) is expected to pass only once FR-008
  lands, and the plan MUST order these two accordingly.
- **Concurrency**: `reload_network_map_nodes` runs in a thread-pool executor and writes
  `self.mappings_dict`. Constitution II says shared server state is mutated only on the loop thread.
  That is a pre-existing deviation. Once the mutating library call is gone, the plan re-checks it and
  either fixes it or records it.

---

## Requirements *(mandatory)*

### Functional Requirements

**Task zero — the process imports (US1)**

- **FR-001**: `new_uuid` in `CuemsWsServer.py` MUST be imported from `cuemsutils.helpers`, as at the
  four existing sites. This change MUST land alone, first, before any other source change in this
  feature except the pre-migration captures (FR-010).
- **FR-002**: A smoke test MUST import every module under `cuemseditor` against the declared
  `cuemsutils`. It MUST be shown failing before FR-001 and passing after (constitution gate IV.1;
  this resolves the ratification violation "the import smoke test does not exist yet").
- **FR-003**: The service MUST reach its listening state against the current library. This is
  verified and recorded as an observable condition, distinct from the suite result.
- **FR-004**: Two baselines MUST be recorded: the import failure itself (the evidence that C2 was
  live) and the full suite result immediately after FR-001 (the first baseline whose colour means
  anything).

**Public surface (US2)**

- **FR-005**: `src/` MUST contain zero imports from `cuemsutils.xml`, `cuemsutils.create_script` or
  `cuemsutils.timeoutloop`, and zero uses of `CuemsParser`, `XmlReaderWriter`, `create_script` or
  `get_nodes_by_adoption`.
- **FR-006**: A public-surface test MUST assert that those names are absent from the editor's modules.
- **FR-007**: `tests/test_repair_durations.py:6` MUST be either migrated or kept with a
  `# test-only` label and a stated reason. It MUST NOT be left unlabelled.
- **FR-008**: In milestone 1, the `create_script()` call (0b) MUST be replaced by
  `ConfigManager.generate_example(SchemaName.SCRIPT)` (F5; Clarifications). `initial_template` keeps
  its message `type` and its `{"CuemsScript": ...}` envelope.
  - The pre-008 `create_script()` output MUST be reconstructed by running the last `cuemsutils`
    release that still shipped `cuemsutils.create_script`. It is then committed as the baseline
    capture (FR-010). The release used MUST be recorded by version and checksum.
  - Every difference between that baseline and the new payload MUST be enumerated as a wire delta.
    This covers keys, key order, value types and placeholder values. The deltas go in
    `tests/ws-command-responses.txt` and the frontend hand-over (FR-018).
  - A test MUST assert that the payload differs from the baseline by exactly those deltas.
- **FR-008a**: In milestone 2, `initial_template` MUST be retired in favour of the descriptor's
  per-type constructible empty instances (FR-045). The retirement lands only behind the
  payload-version handshake (FR-047, FR-050).
- **FR-009**: The adoption partition (0c) MUST be obtained without importing `cuemsutils.xml`
  (Option C, Clarifications). Two things are required:
  - **An upstream report**, filed under `specs/001-cuems-utils-migration/upstream-reports/`. It
    follows `cuems-engine`'s `UR-n-*.md` convention, cites the engine's `UR-1`, and asks for a public,
    non-mutating adoption partition.
  - **An interim local selection**, which MUST be:
    - a read-only selection over the object `ConfigManager.network_map` returns: it reads `adopted`,
      writes nothing, and ports no model;
    - documented in its docstring as interim, with the report named as its successor.

  The public-surface test (FR-006) MUST assert that `get_nodes_by_adoption` and
  `partition_by_adoption` are both absent from the editor's modules. This follows `cuems-engine`'s
  `tests/test_public_surface.py`.

**Payload contract (US3)**

- **FR-010**: Before any source change after FR-001, the `project_load` payload MUST be captured and
  committed for a recorded fixture set. So MUST the `initial_mappings` and `initial_template` payloads.
- **FR-011**: After migration, `project_load` MUST be byte-identical to that capture except for
  delta (a), `schemaLocation` absent, and delta (b), `Media.duration` wrapped. A test MUST assert
  this. `doc_version` MUST NOT appear on the wire. Schema validity is the XSD under
  `cuems-utils/src/cuemsutils/xml/schemas/`, as enforced by the library's public load and save.
  `cuems-utils` `tests/golden/xml` MUST NOT be a pass condition: those files may hold a superseded
  state and are restated after the system refactoring. A contradiction with the XSD is recorded so
  the golden can be regenerated in `cuems-utils`. This repository does not edit that corpus.
- **FR-012**: The wire projection MUST happen exactly once, at the UI boundary. No code path may
  manipulate the wire dict to achieve an object-level result.
- **FR-013**: All five `CuemsParser` call sites MUST be replaced by the library's public
  JSON→object entry. Script load and save MUST go through the library's public load and save.
- **FR-014**: Opening a project MUST NOT write to its files.
- **FR-015**: `_fix_media_durations` MUST remain and operate on the loaded object.
  `_clean_dangling_targets` and `_nullify_dangling_refs` MUST be deleted. Before deletion, each MUST
  be checked against 008's repair path, and anything it does that the library does not MUST be kept
  and named.
- **FR-016**: The save-time FadeCue validation MUST keep its current behaviour and message. It still
  runs before the object is built, in `update()` and `new()` only.
- **FR-017**: `tests/test_dangling_targets.py` MUST be either retired with a recorded reason that
  names the library coverage replacing it, or re-pointed. The default is retire-and-record. It MUST
  NOT be silently deleted or left failing.
- **FR-018**: The handover for delta (a) MUST name `cuems-frontend`'s
  `src/app/services/projects/projects.service.ts:120` (`schemaLocation: string;`, non-optional) in
  the PR description. The edit is the frontend's.

**Repair report and failure (US4)**

- **FR-019**: Script loads MUST use the library's report-returning load, and MUST forward the report
  as a WebSocket message to the requesting session.
- **FR-020**: An unrepairable document MUST produce a structured failure on the same channel. It names
  the document and the field, and `next_steps` MUST be exactly
  `["restore_from_conversion_backup", "correct_field_by_hand", "remove_document"]`, in that order.
  The editor does not choose one step: it cannot know which the operator can carry out. The session
  and the project listing MUST survive. There MUST be no lenient fallback reader.
- **FR-021**: Saving a document whose current load produced a non-empty repair report MUST be refused
  by the save handler until the **saving session** has acknowledged **that report**.
  - The acknowledgment is a new inbound action, and it carries an identifier for the report.
  - The refusal is a structured message that names the outstanding report.
  - Acknowledgment state is per session and per document (Principle II). Session X's acknowledgment
    never unlocks a save by session Y.
  - The state is cleared when the session closes or reloads the document.
  - A test MUST show the save refused without acknowledgment and accepted after it.
- **FR-021a**: Before the first save overwrites a document whose on-disk file is stale (per the
  report), the corrupt original MUST be preserved in `trash/`.
  - It is a versioned copy, using the library's public copy/version helper. It is named so that the
    project and the date are recoverable.
  - If the copy fails, the save MUST be refused. The original is never overwritten without its
    preserved copy (Principle III).
  - A test against a temporary library MUST assert the preserved copy's existence and byte-identity.
- **FR-022**: Four message shapes MUST be added to `tests/ws-command-responses.txt` as new message
  families (Principle I):
  - the report;
  - the failure;
  - the acknowledgment action;
  - the save-refused message.

**Duration-repair tool (US5)**

- **FR-023**: `repair_durations.py` MUST stop using `CuemsParser`, `XmlReaderWriter` and its private
  `TIMECODE_SHAPE` regex. Scripts are read through the library's public load. Timecode parsing and
  comparison are delegated to `CTimecode`.
- **FR-024**: The silent-wrong guard at `repair_durations.py:87-89` MUST get a test that fails against
  the pre-migration code first, with the failing run captured. Its replacement is the
  script-vs-database duration comparison (FR-025a).
- **FR-025**: Pass A (ffprobe + database) MUST stay in this repository. **Pass B is retired**
  (Clarifications): the tool MUST NOT write any script document, under any flag. `pass_b_xml`, its
  XML backup path and its `--apply` effect on scripts MUST be removed.
- **FR-025a**: The tool MUST report, per project, whether its `script.xml` holds any media duration
  that differs from the corrected database value. Each such project is listed as *needs a save*,
  with the media and both values. The tool MUST NOT write the script, and MUST NOT emit or trigger
  any document-version conversion.
- **FR-026**: A test MUST show that the tool still reads the recorded corrupt fixture set and produces
  the expected *needs a save* list. The fixture set MUST be recorded by name.
  `tests/test_repair_durations.py`'s pass-B tests MUST be retired with a recorded reason, which is
  this clarification. Its pass-A tests stay.
- **FR-027**: The tool MUST keep its dry run, back up the database before writing it, and report every
  outcome. The outcomes are: corrected, unchanged, `SKIPPED_INVALID` and *needs a save*. The help text
  and module docstring MUST state that scripts are corrected by saving them in the editor.
- **FR-027a**: The *needs a save* list, and the cost behind it, MUST be documented in `CLAUDE.md`
  "Field notes". The cost is that an unsaved project keeps short durations on disk, and the engine
  plays from disk.

**Node surface (US6)**

- **FR-028**: The merge's field list and its docstring MUST name `node_role`, not `node_type`. A test
  MUST fail against `node_type` first. `src/` MUST contain no `node_type` or `NodeType.`.
- **FR-029**: In-memory comparisons of `adopted`/`online` MUST work with the typed values. No
  comparison against the string `"True"` may remain on a typed value.
- **FR-030**: The node model MUST NOT be re-implemented or re-tested here (FR-030a-i).
- **FR-031**: A test MUST pin the `initial_mappings` wire form of a **merged** node (F6b): role, uuid,
  `adopted`, `online` and key presence. Any difference from the pre-migration capture is an
  enumerated delta, or it is fixed.
- **FR-032**: `nodeconf_available` MUST stay a live sample, taken each time a message carrying it
  is built. It MUST NOT become a field of any schema: not `project_mappings`, not `network_map`.
  - **Milestone 1:** its injection points into `mappings_dict` (refresh path and serve path) stay
    where they are.
  - **Milestone 2:** it moves to the **envelope** of the new node-list message and of
    `nodelist_get`'s reply, as a sibling of the node arrays (Clarifications). A test MUST assert
    that it is present there, sampled per message, and absent from both the `project_mappings`
    payload and the `network_map` node data.
- **FR-033**: `node_status.alive` and node `online` MUST remain separate facts on separate messages.
- **FR-034**: No library `Uuid` or enum object may reach a wire payload except through the library's
  own JSON projection. The websocket-fed `isinstance(..., str)` check in `nodelist_modify` stays
  unreachable by library identities.
- **FR-035**: Any comparison between a JSON-sourced identity and a map-sourced identity MUST use
  `cuemsutils.tools.coerce_identity`.
- **FR-036**: `nodelist_modify`'s error string MUST be relayed unchanged. The `cuems-nodeconf`
  readiness-window bug MUST be recorded as an external dependency and not compensated for here.
- **FR-036a**: A `network_map` read that fails because of a node identity collision (the library's
  `ValidationError`, `cuems-utils` 012) MUST be handled differently from a transient read error:
  - It is **not retried**.
  - It is logged once per distinct collision, naming the duplicated identity and the file.
  - The last good node list keeps being served unchanged.
  - A new `network_map_error` message is broadcast to **all sessions**, carrying
    `{kind: "duplicate_identity", identity, file}`. It is sent on detection and to each session
    that connects while the error stands.
  - When a later read succeeds, a `network_map_error` with a cleared value is broadcast. The
    refreshed node list follows by the usual path.
  - The identity on the wire is the string form (FR-034).

  It is a new message type, so it causes no payload-version bump (FR-047a) and lands in milestone 1.
  Its shape is recorded in `tests/ws-command-responses.txt`. A test MUST feed a duplicate-identity map
  and assert all of these: no retry, last list retained, the error broadcast, and its clearing.

**Release gate (US7)**

- **FR-037**: `pyproject.toml` MUST declare `cuemsutils>=0.1.0rc16,<0.1.1`. The floor MUST NOT be
  lowered to make anything pass.
- **FR-038**: `debian/` MUST be brought onto `feat/xml-refactor`, starting from
  `origin/debian/bookworm`'s current tree (`72f952a`) so that its changelog and history are carried
  rather than re-authored.
  - Its `debian/control` `Depends:` MUST carry an explicit
    `python3-cuemsutils (>= 0.1.0rc16), python3-cuemsutils (<< 0.1.1~)`, alongside
    `${python3:Depends}`. This follows `cuems-nodeconf`'s `debian/control:18-19`.
  - A `debian/changelog` entry MUST record the migration.
  - CLAUDE.md's `debuild` build instruction MUST work from the working branch.
- **FR-038a**: `debian/bookworm` MUST NOT be deleted, retired or force-moved by this feature. It
  remains the packaging-automation branch.
  - Every `debian/` change made on the working branch MUST be listed in a consolidation record at
    `specs/001-cuems-utils-migration/debian-consolidation.md`, by commit and file, so it can be
    applied to `debian/bookworm`.
  - Applying it there is the maintainer's action, in the same way as tags (FR-039).
  - The record MUST also list anything on `debian/bookworm` not yet on the working branch at the
    moment of import. Expected: none.
- **FR-039**: A candidate tag message MUST be prepared in `../.xml-refactor-tag-messages/`, alongside
  `engine-tag.msg` and its siblings. The tag MUST NOT be created or moved by this feature's
  implementation.
- **FR-039a**: The node-adoption work (`feat/nodelist-adoption-api`, 5 commits up to `886f649`) lands
  through this feature. It gets no separate merge into a main line, before or after.
  - The tag message MUST name all three adoption branches as included, with this repository's
    commits by hash: this one, `cuems-engine`'s `feat/nodelist-modify-dispatch` and
    `cuems-nodeconf`'s `feat/nodelist-modify-hardening`.
  - The PR description MUST present those five commits for review as part of this feature.
  - The `cuems-nodeconf` third is 47 commits behind its main line and is largely superseded. Its
    state MUST be named as a coordination item for that repository's flow, not resolved here.

**Characterization discipline (cross-cutting)**

- **FR-040**: This repository's captures and payload fixtures MUST NOT be regenerated to make a test
  pass. A re-base of the editor capture is a recorded, argued, diffed event. At most one per feature
  is sanctioned. `cuems-utils` `tests/golden/` is a different corpus. It may be stale relative to the
  XSD in `cuems-utils/src/cuemsutils/xml/schemas/`, which is the schema. Goldens are regenerated in
  that repository when a contradiction with the XSD arises, and they are restated after the system
  refactoring. This feature does not perform that rewrite, and it does not treat a golden checksum
  as something to satisfy.
- **FR-041**: `tests/test_nodelist_actions.py` MUST stay green from FR-001 onward. Its only permitted
  edit is the `TestNodeconfAvailableFlag._reload` helper's mock of the removed `NetworkMap` import
  (F4). That edit MUST:
  - leave every assertion unchanged;
  - land in the same commit as the import removal;
  - be recorded in the commit message.

  Any other edit to the file signals that the port moved something it should not have.
- **FR-042**: `tests/ws-command-responses.txt` MUST describe what the server actually sends at every
  commit that changes a payload.
- **FR-043**: Every constitution violation recorded at ratification that this feature does not resolve
  MUST appear in the plan's Complexity Tracking table. These include `delete_from_trash`'s
  `rmtree`-inside-transaction and save atomicity. So does the `cli.py:29` `ProjectMappings` import
  (F7), whose successor is `cuems-utils` 014. For save atomicity, the plan MUST measure whether
  the library's save path writes atomically.
- **FR-044**: Every exit criterion that cannot be met MUST be recorded per entry as *not performed*,
  with a reason. Silence is not a third state.

**Milestones and the coordinated release (Q4)**

- **FR-048**: Milestone 1 (US1–US3, US5–US7) MUST be completable on `feat/xml-refactor` without any
  `cuems-frontend` change. It is reached when the census over `src/` records zero and all payloads
  are unchanged except for the enumerated deltas. Reaching it MUST be announced to the `cuems-utils`
  flow as the T049 input.
- **FR-049**: Milestone 2 (US4, US8) is built on the same branch. The candidate tag message
  (FR-039) MUST NOT be marked ready until `cuems-frontend` 05 consumes both of these:
  - the repair report and failure messages;
  - the US8 message families.

  Until then, the message names the frontend dependency as the outstanding item.
- **FR-050**: No milestone-2 change may land in a state that a deployed pre-05 UI misreads. The
  repair report and the new US8 message families may be emitted before the UI renders them, because
  an unknown `type` is ignored. The untangling (FR-046) MUST NOT remove anything from
  `initial_mappings` until the handshake (FR-047) lets an old UI refuse.

**UI-coordinated (US8, milestone 2)** — ships with `cuems-frontend` 05 in the coordinated release.

- **FR-045**: Descriptor serve and config-domain accept messages MUST be modelled on the
  `initial_mappings` / `nodelist_modify` pair, and reached via `ConfigManager` (D34).
- **FR-046**: The `network_map` / `project_mappings` / `nodeconf_available` entanglement MUST be
  untangled into two messages:
  - **project mappings** (outputs only);
  - **a node-list message**, which carries the `network_map` node arrays plus the
    `nodeconf_available` envelope field (FR-032). It is pushed by `watch_network_map` and pulled
    by `nodelist_get`.

  It needs a `localStorage` eviction story, and it MUST NOT land before the consuming UI.
- **FR-047**: The **payload version** MUST be sent to every client as the **first** message on
  connect, before any `initial_*` message. It is an integer.
  - **Version 1** is the wire as of the coordinated `xml-refactor-merge-candidate` tag. That wire
    includes every delta this feature enumerates: `project_load` (a) and (b), the `initial_template`
    deltas, and the untangling.
  - A connection with no payload-version message is, by definition, **version 0**: the wire before
    this feature.
  - Its message `type` and shape are recorded in `tests/ws-command-responses.txt`. A test asserts
    the ordering.
  - It MUST be named "payload version" everywhere. It MUST NOT be derived from, or compared with,
    `doc_version` (the on-disk document marker, never on the wire), and MUST NOT be confused with
    the editor's package version.
- **FR-047a**: The payload version MUST be bumped by exactly one for any change to an **existing**
  message.
  - **Bump:** a key is removed, renamed or reordered; a value's type or form changes (including
    the string boolean form); or a message's audience changes (Principle II).
  - **No bump:** a new message `type`, or a new optional key that old readers can ignore.
  - Every bump MUST be recorded with its enumerated delta (Principle I) in
    `tests/ws-command-responses.txt`.
  - A test MUST fail if the advertised value changes without a matching record.
  - The UI's half is to refuse, with a stated reason, any value it was not built for. That is
    `cuems-frontend` 05's obligation and is handed over by name.

### Key Entities

- **Script document**: a project's `script.xml`, which is user data. It has a `doc_version` on disk
  and is never on the wire. It loads in one of three ways: converted in memory, repaired with a
  report, or refused.
- **`project_load` payload**: the wire projection of a script. It is a contract with the UI, with
  exactly two sanctioned deltas.
- **Repair report**: the library's per-load record of the document, its repairs, the conversions run
  and whether the file on disk is stale. It is forwarded by this repository and rendered by the UI.
- **Network map node**: a node's identity (uuid4 or sentinel), role, adoption state and discovery
  `online`. It is owned by the library and merged here with project output mappings.
- **`node_status`**: the engine's liveness view, the only signal the GO gate trusts. It is distinct
  from `online`.
- **`nodeconf_available`**: a live observation about a daemon. It belongs to no schema.
- **Upstream report**: a recorded library gap that this repository does not work around silently.
- **Pre-migration capture**: the committed payload baseline that makes the two-delta claim
  falsifiable.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The editor service starts and accepts a client connection against the current library.
  Today it fails 100% of the time.
- **SC-002**: The deprecated-surface census over this repository's shipped code records **0** hits,
  down from 6. That unblocks `cuems-utils` T049.
- **SC-003**: All six test files collect and run, up from four. The seven F2 failures pass.
  `test_nodelist_actions.py` has at most the one sanctioned edit.
- **SC-004**: For every project in the recorded fixture set, the opened payload differs from the
  pre-migration capture in exactly two enumerated ways and no others. Schema acceptance is the
  XSD's, through the library's public load and save. A checksum of `tests/golden/xml` is not part
  of this result.
- **SC-005**: Opening any project changes **0** bytes on disk.
- **SC-006**: Every repairable document opened produces a report the operator receives. Every
  unrepairable document produces a named failure whose `next_steps` are all three recovery
  options, and the session survives.
- **SC-007**: The repair tool reads 100% of the recorded corrupt fixture set, corrects the database
  and lists every project that needs a save, with **0** script files changed. Exactly **1** document
  rewriter exists ecosystem-wide, and it is not in this repository.
- **SC-008**: Both silent-wrong sites (the merge field list and the repair tool's guard) have a test
  shown failing before its fix, with the failing run captured.
- **SC-009**: `src/` contains **0** occurrences of `node_type`, `NodeType.`, `CuemsParser` and
  `XmlReaderWriter`.
- **SC-010**: The declared library range refuses `0.1.1`.
- **SC-011**: Every exit criterion is marked met, or *not performed* with a reason. **0** are left
  silent.

## Clarification agenda

`/speckit-clarify` MUST resolve these. The flow's own §5 list applies too, and these items are added
to it. A default is stated for each so that this spec is complete as written. Clarify ratifies or
overrides the default; it does not discover the question.

| # | Question | Default in this spec |
|---|---|---|
| **Q1** | Adoption partition: A (report and block), B (local selection), or C (report **and** local selection as interim)? | **Resolved 2026-10-01: C** (Clarifications, FR-009) |
| **Q2** | `initial_template` after `create_script` is gone? | **Resolved 2026-10-01**: `generate_example(SCRIPT)` with enumerated deltas in milestone 1; retired behind the handshake in milestone 2 (FR-008, FR-008a) |
| **Q3** | How is D21b enforced structurally? | **Resolved 2026-10-01**: per-session acknowledgment gate, plus the original preserved in `trash/` on first save (FR-021, FR-021a) |
| **Q4** | Are US4 and US8 in this feature or split into a successor? | **Resolved 2026-10-01: in this feature** (Clarifications). Two milestones, one coordinated tag (FR-048–FR-050) |
| **Q5** | Pass B and version-1 scripts in `repair_durations` | **Resolved 2026-10-01**: pass B retired. The tool writes no scripts, so it converts none (FR-025–FR-027a). It also answers flow §5.6: no upstream change |
| **Q6** | `cli.py:29` takes `ProjectMappings` from `ConfigManager`'s module namespace (F7). Public, or a Principle V violation that needs an upstream report? | **Settled by measurement, 2026-10-01**: its only use is `cli.py:60`, inside `get_mappings()`, which reads `default_mappings.xml`. That is the read deferred to `cuems-utils` 014 (Out of scope). The import is a Principle V violation, and it is **carried to 014** in Complexity Tracking with that successor rather than migrated twice (FR-043). It is outside the T049 census pattern, so it does not block milestone 1 |
| **Q7** | Does this repository gain a `debian/` directory? (Flow §5.1) | **Resolved 2026-10-01**: yes, on the working branch with the explicit bound. `debian/bookworm` is kept and consolidated, not retired (FR-038, FR-038a) |
| **Q8** | Do `tests/test_dangling_targets.py`'s five tests retire-and-record, or re-point? (Flow §5.3) | **Default stands, not asked**: retire-and-record (FR-017) |
| **Q9** | Does the three-repository node-adoption cluster merge before or after this migration? (Flow §5.9) | **Resolved 2026-10-01**: it lands **through** this migration and the coordinated tag, with no separate merge (FR-039a) |

Of the flow's US8 items:
- §5.7 (`nodeconf_available`'s home) is **resolved** (Clarifications, FR-032).
- §5.8 (`online` and `alive` stay distinct) is pinned by FR-033.
- §5.5 (the payload version's initial value and bump policy) is **resolved** (Clarifications,
  FR-047, FR-047a).

## Out of scope (deferrals with named successors)

- **The hardware/port inventory → `cuems-utils` 014.** 014 moves the port inventory out of
  `project_mappings` and retires `default_mappings.xml`. This repository reads that file at
  `src/cuemseditor/cli.py:59` (`cf_manager.conf_path('default_mappings.xml')`). That read is not one of
  the seven imports and is not on the T049 path. Migrating it now would mean migrating it twice.
  **Deferred, not omitted.** The same applies to every other reader of the port inventory. The
  successor is `cuems-utils` 014, followed by this repository's next migration feature.
- **`cuems-nodeconf`'s readiness-window bug** (`set_comms()` before `run()`): this is nodeconf's fix,
  a readiness flag. This feature records the dependency only (FR-036).
- **`cuems-frontend`'s edits**: the `schemaLocation` interface (FR-018), rendering the repair report,
  and consuming the untangled wire. These are handed over by file and line, and not made here.
- **The `script_file_name` divergence**: recorded (Edge Cases). It is `cuems-utils` 012's trap.
- **The `delete_from_trash` transaction ordering** (ratification violation, Principle III): carried in
  Complexity Tracking, not fixed here, unless the plan finds it touched.
- **Cutting or moving any tag**: the maintainer's call. This feature prepares the message only.
- **`../cuems-wsclient`**: a stale checkout of `cuems-power-bridge`. It is never included in a census.

## Assumptions

- `cuems-utils` stays at `0.1.0rc16` for the life of this feature. A library change that this feature
  needs (UR-1) arrives as an upstream report, never as a local
  patch or vendored copy.
- The test environment resolves `cuemsutils` from the sibling `../cuems-utils/src` checkout, through
  `tests/conftest.py`'s fallback, or from an installed package at the same version. The measurements
  above used the former (`cuemsutils` hatch `test.py3.11` environment, Python 3.11, with `src/`
  precedence). Note: the `../cuems-utils/.venv` lacks `pynng` and cannot run this suite.
- The fixture set for the pre-migration capture is drawn from this repository's `tests/fixtures/`
  (today `script_minimal.xml`). It is not supplemented from `cuems-utils` `tests/golden/xml`. Those
  files may be superseded. The XSD files in `cuems-utils/src/cuemsutils/xml/schemas/` are the schema,
  and the goldens are restated after the system refactoring.
- The concurrent-edit policy stays "last writer wins, then notify". This feature does not change it.
- Commits are GPG-signed. On `gpg failed to sign`, the commit is retried, never bypassed.
