<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# `cuems-editor` — the runnable flow for `001-cuems-utils-migration`

**Derived** 2026-09-25 from `cuems-utils/specs/planning/xml-rebuild/010-consumer-prompts/02-cuems-editor.md`,
re-verified against the live tree. Where the two differ, **this file is the one to run**; the upstream
original is a dated 2026-09-03 record and is not edited.

**Feature name**: `001-cuems-utils-migration` (this repository has no `specs/` features yet).
**Branch**: `feat/xml-refactor`, matching every other repository in this work.

The largest Python-side migration in the consumer set, and the only repository whose **first** task is
making the process start at all.

---

## 0. State of this repository, measured 2026-09-25

| | |
|---|---|
| Checked-out branch | `rc1` @ `d9e0a39` (2026-08-03), in sync with `origin/rc1`, clean |
| **Base for `feat/xml-refactor`** | **`feat/nodelist-adoption-api`** @ `886f649` — **changed from `rc1`**, see §0a and §1 |
| That branch | 5 commits ahead of `rc1`, **0 behind**; pushed; a local tracking branch was created 2026-09-25 |
| Spec-kit | **absent** — added on first run, §1 |
| Constitution | **absent** — written on first run, §2 |
| Existing features | none → this becomes **`001-cuems-utils-migration`** |
| Tests | `hatch test` (hatchling, `testpaths = ["tests"]`) — **6 test files** on the base branch (5 on `rc1`) |
| `cuemsutils` pin | `pyproject.toml:27` `cuemsutils>=0.1.0rc10`; **no `debian/control`** |
| **Runs against current `cuemsutils`?** | **NO — `ModuleNotFoundError` at import.** Verified live 2026-09-25, and true on both branches |

`rc1` has not moved since 2026-08-03, so every line number the upstream flow-02 prompt recorded is
still exact **for `rc1`**. It is **not** exact for the base branch this feature uses:
`CuemsWsServer.py` goes 563 → 651 lines and `CuemsWsUser.py` 806 → 889.
`03-migration-inventory.md` carries both, with the `rc1` value in brackets.

---

## 0a. The base branch is one third of an unmerged three-repository feature

Read this before §1. It is the reason the base changed, and it adds scope the upstream prompt has none
of.

On **2026-09-04**, fourteen commits landed across three repositories as one coordinated feature — the
node adopt/un-adopt hop and cluster liveness. **None of the three branches is merged anywhere**, and
they carry three different names, which is why the cluster is easy to miss:

| Tier | Repository | Branch | Commits | State |
|---|---|---|---|---|
| UI | `cuems-frontend` | — | **none** | **the tier does not exist** |
| middleware | **`cuems-editor`** | **`feat/nodelist-adoption-api`** | 5 ahead of `rc1`, 0 behind | **this feature's base** |
| engine | `cuems-engine` | `feat/nodelist-modify-dispatch` | 6 ahead of `rc_1` | that repository's migration base, by the same decision |
| node daemon | `cuems-nodeconf` | `feat/nodelist-modify-hardening` | 3 ahead, **47 behind**, **not merged** | see the warning below |

The pairings are one-to-one. This repository's `c2eeb80 relay the engine's liveness view as
node_status` answers the engine's `52962d9 expose runtime cluster liveness to the UI`; its
`829c56c nodeconf_available was cached and could tell the UI a comfortable lie` answers the engine's
`cf5c4ad refuse instantly when nodeconf is not running`. And the engine's own
`8e36d13 land the adopt/un-adopt hop **the editor was already calling**` says which side came first.

**The chain is Frontend → (WS :9092) → Editor → (NNG, /tmp/editor.ipc) → Engine → (NNG) → nodeconf.**
Three tiers are built. Measured 2026-09-25,
`grep -rn "nodelist_get\|node_status\|cluster_status\|cluster_warning\|nodeconf_available"
../cuems-frontend/src/` returns **nothing** — so this whole feature currently has no UI, and
`cuems-frontend`'s own flow does not know it exists either.

**What that means for scope here**: the new surface — `nodelist_get`, `node_status`,
`nodeconf_available`, and `nodeconf_available`'s injection into `mappings_dict` — is part of what this
migration must carry forward, and `03-migration-inventory.md` §8a is the only place it is written down.
The `nodeconf_available` injection in particular makes the domain entanglement **three-way** rather
than two-way: read §8a before scoping the untangling.

### ⚠ One open `cuems-nodeconf` bug is reachable from a WS action this feature migrates

`cuems-nodeconf`'s third of the cluster is not in its published candidate `6c0cca7`. Measured against the
current tree (`../cuems-utils/specs/010-consumer-migration/nodeconf-map-write-divergence.md`), most of it
is superseded — the IPC-reply fix was ported verbatim, the truncated-map hazard is gone **by
construction**, and the lost-adopt race does not reproduce in 60 concurrent trials.

**One open bug is this repository's problem**, because `nodelist_modify` is the caller:
`cuems-nodeconf`'s `start()` calls `set_comms()` **before** `run()`, so its responder accepts
adopt/unadopt for up to 10 s while the map is still empty. An adopt in that window returns
`{'OK': False, 'error': 'Node <uuid> not found'}` for a node that is present — and `cuems-engine` forwards
it, because its readiness probe is the existence of `/tmp/nodeconf.ipc`, which `set_comms()` creates
before the window opens.

**What this means for the port**: `nodelist_modify`'s error path (`CuemsWsUser.py:385-431`) relays that
string to the UI. A *"Node not found"* for a node the operator can see listed is indistinguishable, at
this layer, from a genuine one. Do not add retry or interpretation logic here to compensate — the fix is
nodeconf's (a readiness flag), and inventing a client-side heuristic for it is how the two ends drift.
Record the dependency; leave the string alone.

---

## 1. Branch and bootstrap

```bash
cd /disk/Projects/StageLab/cuems-editor
git checkout feat/nodelist-adoption-api     # local tracking branch created 2026-09-25
git pull --ff-only
git checkout -b feat/xml-refactor
```

**The upstream flow-02 prompt says `rc1`. That is superseded, by decision taken 2026-09-25 with the
maintainer**, for the same reason `cuems-engine` bases on `feat/nodelist-modify-dispatch`: the two are
halves of one unmerged feature (§0a), and basing the two migrations on different sides of it would
migrate one half and not the other. The branch is 0 behind `rc1`, so nothing is lost by taking it.

### The spec-kit bootstrap has a version problem — resolve it before running

Spec-kit is not installed here. The upstream flow says:

```bash
specify init --here --integration claude --script sh --force
```

**Measured 2026-09-25**: the `specify` CLI on this development machine is **0.16.2**, while the three
landed sibling repositories (`cuems-common`, `cuems-nodeconf`, `cuems-power-bridge`) were all
bootstrapped with **1.0.4** — see any of their `.specify/init-options.json`. `cuems-utils` itself was
initialized still earlier, at `0.5.1.dev0`.

So running the command above **as-is** produces a scaffold that differs from every sibling's. Three
options, and the choice should be recorded rather than defaulted into:

| | Option | Cost |
|---|---|---|
| (a) | Upgrade the CLI to ≥ 1.0.4, then `specify init` | The stated intent — the seven repositories stay comparable. Needs network |
| (b) | Copy `.specify/{scripts,templates,workflows,integration.json,init-options.json}` from `../cuems-nodeconf` (verified **byte-identical** to `../cuems-power-bridge`'s), install the `.claude/skills/speckit-*` set to match its `integrations/claude.manifest.json` hashes, and leave `memory/constitution.md` as the unfilled template for §2 | Offline-safe and exactly matches the siblings, but the manifest's `installed_at` and file hashes must be made honest, not copied verbatim |
| (c) | `specify init` at 0.16.2 and accept the divergence | Cheapest, and it makes "the seven repositories stay comparable" false. If chosen, say so in the spec |

**Commit the scaffold as its own commit** before `/speckit.constitution` — GPG-signed, per the
standing rules.

Spec-kit's sequential branch numbering will want its own branch. **Stay on `feat/xml-refactor`**; let
it name `specs/001-cuems-utils-migration/` only.

---

## 2. Constitution — write one, this repository has none

```
/speckit.constitution

Establish the constitution for cuems-editor, grounded in what this repository actually is
rather than in a generic template. Read CLAUDE.md first; it is accurate and current.

WHAT THIS REPOSITORY IS: WebSocket middleware for multi-user project editing and media
management, sitting between the browser frontend (cuems-frontend) and the engine
(cuems-engine). Python 3.11+, PyPI name cuemseditor, systemd service cuems-editor.service
on the controller. Frontend -> Editor is WebSocket :9092 carrying JSON
{"action": ..., "value": ...}; Editor -> Engine is a Unix IPC socket /tmp/editor.ipc over
NNG. Main classes: CuemsWsServer (asyncio WS server, session multiplexer, command router),
CuemsWsUser (per-connection session), CuemsProjectManager (owns the DB managers),
CuemsDBProject (project CRUD, XML script I/O, filesystem management). The project store is
/opt/cuems_library/, resolved from settings.xml's library_path.

PRINCIPLES THE CODE ALREADY IMPLIES — derive from these, do not invent unrelated ones:
- It is a WIRE-CONTRACT repository. Its output is consumed verbatim by an Angular UI that
  this repository does not control and cannot deploy in lockstep with. Payload shape is a
  contract, not an implementation detail, and a change to it is a coordinated multi-repo
  event. Make this a principle, because the single largest risk in this codebase is a
  payload change nobody noticed.
- It is MULTI-USER and stateful per session. CuemsWsServer multiplexes sessions and routes
  commands; concurrency and per-session isolation are correctness concerns, not performance
  ones.
- It OWNS USER DATA on disk. Project XML and the media library are the customer's work.
  Destructive operations need a recovery story, and "the parser accepted it" is not one.
- It has FIVE test files against a codebase of this size (CuemsDBProject.py alone is 896
  lines). State the testing expectation you actually intend to hold, and make it honest: a
  gate this repository will meet, with a stated direction of travel, beats an aspirational
  rule that gets waived in the first PR.
- Its dependency on cuemsutils is a CONSUMER relationship with a library that versions
  deliberately. Reaching into that library's internal modules is a violation to name now,
  before the temptation arrives (cuemsutils.xml declares __all__ == [] for this reason).

Include a performance principle only if you can state a measurable budget this repository
can actually check — project load and WS round-trip are the candidates. Do not copy
cuems-utils' Principle IV wording; its budgets are per-test and this repository's are not.

Do NOT weaken any rule to accommodate the migration that follows. If the migration
violates the constitution you write, that is information, and the spec records the
exception explicitly.
```

---

## 3. Context block — paste verbatim into `/speckit.specify` and `/speckit.plan`

Everything below resolves **inside this repository**. That is the point of the bundle.

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
  enumerated deltas, nothing else moved, and NOT unconditional byte-identity. Prove it two ways
  — byte-comparison against a payload captured BEFORE the migration, and against cuems-utils'
  golden corpus recorded BY CHECKSUM. Never by inspection. The projection appears ONCE, at the
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
  the document AND the failing field, AND a next step (restore from a conversion backup, correct
  the field by hand, or remove the document). The project stays listed, the session survives,
  only that document refuses to open. A lenient read-only fallback is REJECTED — it reintroduces
  the permissive path 008 removed and creates a second reader for documents the strict path rejects.

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

---

## 4. The chain

```
/speckit.specify   <paste §3>
/speckit.clarify                 <- do NOT skip; §5 lists what it must force
/speckit.plan      <paste §3>
/speckit.tasks
/speckit.check-integration       <- earns its place here more than anywhere
/speckit.optimize
/speckit.implement               <- never on a red suite
/speckit.verify
```

**`check-integration` matters most in a migration**: the failure mode is writing the new call
*alongside* the old one instead of replacing it.

**The baseline is special here.** In every other repository you capture a green suite before starting.
Here the process does not import, so capture **two** baselines: the import failure itself (that is the
evidence C2 was live), and the suite once task zero lands — which is the first moment the suite's
colour means anything.

---

## 5. What `/speckit.clarify` must force

1. **Does this repository gain a `debian/` directory?** It has none. The release gate wants a bounded
   package relation, and there is nothing to put one in. If it does gain one, note the sibling
   convention settled 2026-09-24: `debian/` lives on the **working branch**, not a separate
   `debian/bookworm` branch — that pattern was abandoned upstream after the packaging branch fell
   seven weeks and 132 commits behind and two release candidates left the tree with no changelog entry.
2. **What is the testing gate this repository will actually hold?** Five test files, and two of them
   are themselves migration targets (`test_dangling_targets.py` tests code this feature deletes;
   `test_repair_durations.py` tests a tool this feature splits in half). An honest gate on new and
   changed code beats a repository-wide rule waived in the first PR — and the constitution step above
   asks for the honest one, so do not let the spec quietly raise it.
3. **What is the disposition of `test_dangling_targets.py`?** Its five tests assert behaviour that is
   now the **library's** guarantee. Re-asserting it here is re-testing `cuemsutils` from a consumer.
   Retire-and-record, or re-point? Either is defensible; silence is not.
4. **Where exactly does the report get surfaced, such that the D21b ordering is structural rather than
   a convention?** "State how" is the requirement. A comment saying *"call this first"* is the same
   class of thing as the `ORDER MATTERS` docstring the engine's migration is deleting.
5. **What is the payload version's initial value and its bump policy?** It must not be confused with
   `doc_version`. Two numbers, two lifecycles, and merging them is a recorded hazard.
6. **Does pass B's fold into `cuems-convert-documents` need an upstream change?** If it does, that is
   an upstream report, not a local workaround — and it is a dependency this flow must declare rather
   than discover.
7. **Where does `nodeconf_available` live after the untangling?** The base branch injects it into
   `mappings_dict` at two sites (`:491`, `:537`), so `initial_mappings` now carries **three** things:
   `project_mappings`, `network_map` node status, and a liveness observation about a *daemon* that
   belongs to no schema at all. It must not become a `project_mappings` field. Decide before porting
   the config-domain forms.
8. **Do `online` and `node_status.alive` stay distinct through the port?** They are different facts
   with different freshness — ~30 s discovery versus sub-second ping/pong, and only the second is the
   signal the GO gate trusts (`CuemsWsUser.py:469-472`). §7's retyping of `online` to `bool` touches
   only the first. A descriptor-driven form that renders "is this node up?" once has silently picked
   one.
9. **Does the three-repository cluster merge before or after this migration?** It is unmerged in all
   three repositories (§0a). This flow assumes *before*, by basing on it. If the intent is to merge it
   only after the migration, say so — the answer changes which branch the candidate tag sits on.

---

## 6. Exit criteria, measured

| | Criterion |
|---|---|
| 1 | **The process starts and reaches its listening state** against the current library — stated as an observable condition, and explicitly distinguished from "the suite is green" |
| 2 | `grep -rn 'from cuemsutils\.\(xml\|config\)' src/` returns **zero**. Test-only imports, if kept, are **labelled** as such so a census can tell them apart |
| 3 | `CuemsParser` appears nowhere; `XmlReaderWriter` appears nowhere |
| 4 | The payload matches the **two-delta** statement — verified against a pre-migration capture **and** against `cuems-utils`' goldens by checksum. Key order and the string boolean form unchanged |
| 5 | Exactly **one** document rewriter remains in the ecosystem, and `repair_durations.py` still reads the corrupt documents it exists to repair — with the fixture set recorded |
| 6 | Both FR-030a-ii sites (`:425` `basic_fields`, `repair_durations.py:87`) have a test that **failed** against the pre-migration value, with the failing run captured |
| 7 | `grep -rn 'node_type\|NodeType\.' src/` returns **zero** |
| 8 | The pin is bounded; the `debian/` decision is recorded either way |
| 9 | **`tests/test_nodelist_actions.py` is green throughout and unedited.** It pins the node-adoption surface this migration must preserve, not replace — an edit to it is the signal that the port moved something it should not have |
| 10 | **`tests/ws-command-responses.txt` still describes what the server actually sends.** It is the UI team's reference for these messages |
| 11 | Items that could not be performed are recorded as **not performed**, per entry. Silence is not an acceptable third state — the convention both landed siblings followed |
| 12 | **The adoption screen's online badge reads the wire form.** `cuems-frontend` `settings.component.ts:176` checks `node.online === true`, but the editor sends `"True"`/`"False"`, so the badge shows off for every node. Met when the frontend compares against the wire form (or normalises on receipt) and a node with `"online": "True"` renders online — **or** recorded as *not performed* with the frontend flow named as owner. The editor's payload does not change to satisfy it (criterion 4). Check the adjacent `adopted` read in the same file |

---

## 7. The candidate tag, and what it now waits on

When the exit criteria are met: `xml-refactor-merge-candidate`, annotated and **signed**, on
`feat/xml-refactor`. Three siblings have already cut theirs:

| Repository | Tag at | Carries |
|---|---|---|
| `cuems-power-bridge` | `d5c4226` | features 001 + 002 |
| `cuems-common` | `3af31cc` | the `node_role` conversion, the fixed `cuems-cluster-poweroff` |
| `cuems-nodeconf` | `6c0cca7` | its own two features |
| `cuems-utils` | — | **tags last, by decision** — it is the library everything here pins |

By the shared convention the tag moves **only** when a candidate is genuinely re-cut (packaged content
changes), and a re-cut is announced to the other flows. `cuems-common`'s was relocated once,
2026-09-24, and force-pushed with the maintainer's confirmation — moving a published tag rewrites what
other checkouts see, so it is a decision, not a fix.

**Nothing releases from this branch alone** (D27). And the whole-system tag waits on more than the
consumer flows: `cuems-utils` features **011–014** (`/etc/cuems` first install, uuid4 convergence, the
device-class reshape, `hardware_outputs`) are a hard successor, and the tag comes after them. See
`cuems-utils/specs/planning/etc-cuems-first-install-execution.md` §8.

---

## 8. Traps

**"Dead code" is not provable from one repository.** This is a library-consumer ecosystem; a grep that
finds no in-repo caller finds nothing. Check `../cuems-engine`, `../cuems-frontend`,
`../cuems-nodeconf`, `../cuems-power-bridge`, `../cuems-common` and `../cuems-utils` first — and note
that `cuems-wsclient` **is** `cuems-power-bridge`, the same repository renamed, which once inflated the
ecosystem count from seven to eight.

**A green suite is evidence of nothing until the process imports.** And after that, two of the five
test files cover code this feature removes.

**`localStorage` outlives a wire change.** `initial_mappings` is cached in the browser by two
`cuems-frontend` components. A cache that survives a schema change is how a UI shows the wrong shape
after an upgrade — the untangling needs an eviction story, not just a new payload.

**Do not regenerate a golden to make a test pass.** Upstream FR-021. Re-basing is a recorded, argued
event; that feature sanctioned exactly three across its whole span. `tests/golden/outcomes.json`
upstream is **not** a regeneration target at all — it records pre-refactor verdicts that a test asserts
the *difference* against.

**Commits are GPG-signed.** On `gpg failed to sign`, retry — never `--no-gpg-sign`.

**Planning artefacts stay in `specs/planning/`; feature artefacts in `specs/001-*/`.** This bundle is
planning.
