<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# `cuems-editor` — the migration inventory

**Measured 2026-09-25** against **`feat/nodelist-adoption-api`** @ `886f649` — the base this feature
branches from, see `00-runnable-flow.md` §1. Line numbers are given **for that branch**, with the
`rc1` value in brackets where it differs, because the upstream flow-02 prompt and every earlier pass
measured `rc1`.

**Read the brackets carefully.** Upstream's 2026-09-03 figures are exact **for `rc1`**, and `rc1` has
not moved since 2026-08-03 — so a reader comparing this file against the upstream prompt will find
`CuemsWsServer.py` disagreeing at every site and `CuemsDBProject.py` agreeing at every site. That is
not drift in the prompt; it is the base branch changing.

| File | `rc1` | `feat/nodelist-adoption-api` |
|---|---|---|
| `CuemsWsServer.py` | 563 | **651** |
| `CuemsWsUser.py` | 806 | **889** |
| `CuemsDBProject.py` | 896 | 896 — untouched |
| `repair_durations.py` | 294 | 294 — untouched |
| test files | 5 | **6** (`test_nodelist_actions.py`, 392 lines) |

So the branch moves **two** files and neither is where the bulk of this migration's work is. Every
`CuemsDBProject.py` and `repair_durations.py` site below is identical on both branches.

---

## 0. Task zero — the process does not start

| Site | Code | Why |
|---|---|---|
| `src/cuemseditor/CuemsWsServer.py:27` [`:24`] | `from cuemsutils.create_script import create_script, new_uuid` | 008 **deleted** the module, with no deprecation shim. `ModuleNotFoundError`, verified live 2026-09-25 |

**Two fixes, separable — and they must be separated.**

- `new_uuid` re-sources from `cuemsutils.helpers`, where this repository **already imports it at four
  other sites** (`CuemsDBMedia.py:6`, `CuemsDBProject.py:11`, `db.py:4`, and `CuemsDBModel.py:3` for
  `new_datetime`). This is a one-line change and it unblocks everything.
- `create_script`'s replacement is the descriptor work (§5). That carries a real design decision.

**Do not let the second block the first.** Until the import is fixed, no call site in this repository
is reached and the suite's colour is meaningless.

The `create_script()` caller, for the record, is `CuemsWsServer.py:87` [`:84`]:
`self.initital_template = create_script()` — misspelling in the original, preserved here because it
is the identifier you will have to grep for.

## 1. Deprecated import paths

| Site | Import | Note |
|---|---|---|
| `CuemsWsServer.py:26` [`:23`] | `from cuemsutils.xml import NetworkMap` | resolves and warns today; **gone** in the release after `0.1.0rc16` |
| `CuemsDBProject.py:9` | `from cuemsutils.xml.Parsers import CuemsParser` | same |
| `CuemsDBProject.py:10` | `from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter` | same |
| `repair_durations.py:39` | `from cuemsutils.xml.Parsers import CuemsParser` | same |
| `repair_durations.py:40` | `from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter` | same |

All five are also **Q14 violations** independently of the deprecation: `cuemsutils.xml` declares
`__all__ == []` and is internal machinery. The replacement is `CuemsScript` (show) and
`ConfigManager`/`ConfigBase` (config).

**A sixth site upstream's census does not list**, found 2026-09-25:

```
tests/test_repair_durations.py:6   from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter
```

The upstream release-gate contract enumerates the live consumers of the retired surface from `src/`
only, so this one is absent from the required-zero count. It still breaks when the shim goes.
`cuems-nodeconf` set the precedent for exactly this case: **keep the test import and label it**
`# test-only (FR-007)`, so a census can distinguish a shipped consumer from a test that deliberately
exercises the old path. Decide which this is; do not let it be discovered by a red suite after the
deletion lands.

## 2. The five `CuemsParser` call sites

`CuemsParser` is a deprecated alias for `CuemsScript.from_json`.

| Site | Method |
|---|---|
| `CuemsDBProject.py:356` | `update` |
| `CuemsDBProject.py:489` | `new` |
| `CuemsDBProject.py:571` | `duplicate` |
| `CuemsDBProject.py:808` | `update_projects_existed_media` |
| `repair_durations.py:230` | pass B, the XML rewriter |

## 3. Load and save

| Site | Today | After |
|---|---|---|
| `CuemsDBProject.py:895` | `XmlReaderWriter(...)` in `load_xml` | `CuemsScript.load` — or `load_with_report`, §6 |
| `CuemsDBProject.py:883` | `XmlReaderWriter(...)` in `save_xml` | `CuemsScript.save` |

The load path's return value becomes `script.to_wire()`. That projection appears **once**, at the UI
boundary — upstream FR-013b requires **zero** consumer code paths that manipulate the wire dict to
achieve an object-level result. See `04-wire-contract.md`.

Note both sites resolve the filename through `self.script_file_name` (`:212`), which is
**configuration, not a constant** — `cli.py:41` sets `'script.xml'` while
`CuemsProjectManager.py:38`'s own docstring example shows `'cue_script.xml'`. The sibling
`cuems-engine` hardcodes `"script.xml"` at `BaseEngine.py:505`. Record the divergence; it is
`cuems-utils` feature 012's trap (a library-walking procedure that hardcodes the name skips a library
silently and completely), not this feature's work.

## 4. The three raw-dict pre-parse fixups

All three mutate the JSON payload **before** parsing, and the parser they feed is now strict.

| Site | What it does | Disposition |
|---|---|---|
| `CuemsDBProject.py:367` `_fix_media_durations` | corrects zero/short durations from the DB | **stays.** Database-sourced correction is genuinely this repository's domain — but it operates on the **loaded object**, not on a dict |
| `CuemsDBProject.py:387` `_clean_dangling_targets` | clears references to cues that do not exist | **deleted, not ported.** The library does this now |
| `CuemsDBProject.py:417` `_nullify_dangling_refs` | the recursive half of the above (self-recursive at `:426`) | **deleted** with it |

Callers: `:337` and `:339`, both in `update`.

**Check them against 008's repair-and-notify path first.** Some of what they do is the library's job
now, and duplicating it here is exactly how the two drift apart. **What survives is what the library
does not do** — measured case by case, not decided by category.

**A consequence worth stating in the spec because it reaches past this repository**: FR-043a widens
behaviour for *every* consumer. A document with a dangling reference now loads with it cleared and
reported **wherever it is loaded**, where previously only documents passing through this editor were
corrected. `cuems-engine` could previously dispatch against a reference to a cue that does not exist.

## 5. The template surface

| Site | Code |
|---|---|
| `CuemsWsServer.py:87` [`:84`] | `self.initital_template = create_script()` |
| `CuemsWsServer.py:510-512` [`:501-503`] | the `initial_template` payload — `{"type": "initial_template", "value": {"CuemsScript": ...}}` |

D26 retires `initial_template`-as-a-concrete-instance. D25's descriptor replaces it, covering all six
schemas and emitting per field: name, XSD type, cardinality, restricted `xs:enumeration` values **and
model-layer defaults**. Defaults are not optional — two of `cuems-frontend`'s call sites consume
*values*, not shape.

Upstream's clarification Q2 added the piece that makes this buildable: the descriptor emits, **per
complex type, a constructible empty instance**. That was the one new library capability feature 010
sanctioned, and it exists because the alternatives were a hand-authored seed in the UI (which drifts
from the schema — the exact failure the cutover ends) and cloning from a generated example (which
works only while the example happens to contain one of every cue type).

## 6. The repair report, and the save-after-repair ordering

`CuemsScript.load_with_report(path)` returns `(script, LoadReport)`. `load()` keeps its old signature
and discards the report.

**D21b: saving a repaired document overwrites the corrupt original with no backup.** What makes that
safe is that a human saw the report first. `cuemsutils` **cannot** enforce the ordering —
`load_with_report` and `save()` are two independent calls — so the obligation is **this repository's,
procedurally**. Wherever this repository calls `load_with_report` and later calls `save()` on the
result, the report must have been surfaced first. The spec must state *how*, not merely that.

Upstream's clarification settled the two behaviours this repository owes:

- **A repaired document is never written back as a side effect of load.** The report is surfaced, the
  file on disk is left as it was, and the repaired form reaches disk only through an ordinary
  user-initiated save. **A load stays a read.** Accepted cost: an unsaved document is repaired
  identically on every open and reports the same repair each time — the report's own *"the file on
  disk is now stale"* flag is what makes that legible.
- **An unrepairable document gets a structured failure message on the same channel as the report**,
  naming the document and the failing field. The project stays listed, the session survives, and only
  that one document refuses to open. A lenient read-only fallback was rejected: it reintroduces the
  permissive path 008 deliberately removed and creates a second reader for documents the strict path
  rejects.
- **The operator needs a next step.** A failure that says only *"this will not open"* leaves a broken
  project and nowhere to go. The three recovery actions are: restore from a conversion backup,
  correct the named field by hand, or remove the document from the library.

## 7. The node reads

| Site | Today | After |
|---|---|---|
| `CuemsWsServer.py:433` [`:425`] | `basic_fields = ['online', 'adopted', 'ip', 'name', 'node_type', 'mac', ...]` | `'node_role'`. **FR-030a-ii**: a key the converted document no longer has, so the merge silently drops the field. Its docstring at `:392` [`:384`] names the same list and must move with it |
| `CuemsWsServer.py:435` [`:427`] | `for field in basic_fields:` | the loop that does the dropping |
| `CuemsWsServer.py:478` [`:470`] | `NetworkMap.get_nodes_by_adoption(network_map_dict)` | `partition_by_adoption` — non-mutating. **The shape inverts**: bare node objects in tuples, not `{"node": ...}` wrappers in lists |
| `CuemsWsServer.py:447` [`:439`] | `reload_network_map_nodes` | the entanglement, §6 of `04-wire-contract.md` |
| `CuemsWsServer.py:102` [`:98`], `:604-610` [`:516-522`] | callers of `reload_network_map_nodes` (one in the thread-pool executor) | re-check the concurrency story once the mutation is gone |

`online` and `adopted` are **`bool` in memory** after the decode — `network_map` is the one config
schema whose decode runs the adapter table (007 R1) — but the **wire form is unchanged**:
`json.dumps` still emits the strings `"True"`/`"False"` (spec F6, exit criterion 4). In-memory
comparisons in the editor use the typed values; anything reading the WS payload sees strings.

**A consumer already reads the wire form wrongly.** This is a `cuems-frontend` read, not an editor one:

| Site | Today | After |
|---|---|---|
| `cuems-frontend` `settings.component.ts:176` | `node.online === true` against a payload that carries `"True"`/`"False"` | **Broken as written**: a string is never `=== true`, so the online badge shows *off* for every node. The fix is on the frontend side, not here: compare against the wire string (or normalise once on receipt). The editor must **not** switch the wire to real booleans to suit it — that is a payload change outside the two-delta statement, and the two mixers plus `localStorage` readers would see it too (`04-wire-contract.md` §6) |

Not verifiable from this repository (the frontend is a sibling checkout): confirm the line number
there, and `grep` the same file for the matching `adopted === true` read before closing the item.

## 8. `repair_durations.py` — the item needing the most care

It exists to **load deliberately-corrupt documents**: its whole purpose is repairing durations a
historical `get_duration` bug stored short. A strict parser is the opposite of what it wants.

| Site | Issue |
|---|---|
| `:43` | `TIMECODE_SHAPE = re.compile(r'^\d\d:\d\d:\d\d\.\d\d\d$')` — a private regex duplicating the library's canonical form |
| `:87-89` | `if key in ('duration', 'in_time', 'out_time', 'offset', ...)` then `TIMECODE_SHAPE.match(value)`. **Post-008 those are dicts on the wire**, so `match` is never reached with a string and **the guard silently stops catching anything**. FR-030a-ii, inside the tool this feature is migrating |
| `:204`, `:231` | `XmlReaderWriter(...).read()` / `.write_from_object(obj)` |
| `:230` | `CuemsParser(data).parse()` |

**The split, decided upstream:**

- **Pass A** (`:138`, ffprobe + database) **stays editor-local.** That half is genuinely this
  repository's domain.
- **Pass B** (`:187`, the XML rewriter) **folds into `cuemsutils`' `cuems-convert-documents`** rather
  than maintaining a second `<duration>` rewriter. Exit criterion: exactly **one** document rewriter
  remains in the ecosystem.

**Verify, do not assume, that it can still read the corrupt documents it exists to repair.** 008's
repair-and-notify contract is what makes that possible, and this is the test that proves the contract
holds. Its test file is `tests/test_repair_durations.py`; keep the fixture set and record it.

## 8a. The node-adoption surface the base branch adds — in scope, and not in the upstream prompt

`feat/nodelist-adoption-api` (5 commits, 2026-09-04) is the editor half of a three-repository feature
landed the same day: `cuems-engine`'s `feat/nodelist-modify-dispatch` and `cuems-nodeconf`'s
`feat/nodelist-modify-hardening` are the other two. None of the three is merged anywhere. See the
cluster map in `00-runnable-flow.md` §0a.

Because this feature branches from it, **its surface is part of this migration's scope** and the
upstream flow-02 prompt does not mention any of it.

### New WS actions (`CuemsWsUser.py`)

| Site | Action | Talks to |
|---|---|---|
| `:140` | `nodelist_modify` — `lambda: self.nodelist_modify(value, action, data.get("modify_action"))` | the engine's `nodelist_modify` IPC handler |
| `:141` | `nodelist_get` | the engine |
| `:142` | `node_status` | the engine's **`cluster_status`** (`:496`, `:501`) |
| `:385-431` | `nodelist_modify`'s body — uuid validation at `:408`, `{"type": "nodelist_modify", "value": "OK"}` at `:421` | — |
| `:437` | `nodelist_get`'s body | — |
| `:463-504` | `node_status`'s body, returning `{"type": "node_status", "value": result}` | — |

**`node_status` is not `online`, and its docstring says so** (`:469-472`): `online` in each
`initial_mappings` node is `cuems-nodeconf`'s discovery view, refreshed within ~30 s; `alive` in
`node_status` is the engine's sub-second ping/pong, *"the only signal the GO gate trusts"*. **Do not
let the descriptor-driven form port collapse the two** — they are different facts with different
freshness, arriving on different messages, and §7's retyping of `online` to `bool` touches only the
first.

### New server-side state (`CuemsWsServer.py`)

| Site | What |
|---|---|
| `:516` | `def nodeconf_available(self)` — deliberately **not cached**; commit `829c56c`'s message is *"nodeconf_available was cached and could tell the UI a comfortable lie"* |
| `:491`, `:537` | `self.mappings_dict['nodeconf_available'] = self.nodeconf_available()` — injected into `mappings_dict` on **both** the refresh path and the serve path |
| `:567`, `:577` | `last_nodeconf` / `nodeconf_now` in the `while True:` poller at `:570` |

**`:537` makes the entanglement worse, and this is the most important consequence for §6 of
`04-wire-contract.md`.** On `rc1`, `initial_mappings` carried `project_mappings` plus `network_map`
node status — two domains. On this branch it carries a **third** fact, `nodeconf_available`, which is
neither: it is a liveness observation about a *daemon*, computed at serve time, belonging to no
schema at all. So the untangling this feature owes now has three things to separate, not two, and the
third has no domain to go home to. **Decide where `nodeconf_available` lives before porting the
config-domain forms** — it is not a `project_mappings` field and must not become one.

### A sixth test file

`tests/test_nodelist_actions.py` (392 lines) pins the node-adoption surface, and it is described in
its own commit as *"pin the node-adoption surface and document it for the UI team"* (`6c37f79`). It
imports only `cuemseditor.CuemsWsUser` — **no `cuemsutils` import at all**, so it adds nothing to §1's
census. Treat it as a **characterization test for the surface this migration must preserve**: it is the
nearest thing this repository has to the yardstick discipline `cuems-nodeconf` used, and it was written
before the migration rather than during it.

`tests/ws-command-responses.txt` also grows (+59 lines on the branch, +19 more in `886f649`); it is
the UI team's reference for these messages and must stay true through the port.

## 9. The dependency pin

`pyproject.toml:27` — `"cuemsutils>=0.1.0rc10"`. No `debian/` directory at all.

A `>=` floor cannot express the gate's claim, which runs the other way: *an unmigrated consumer must
refuse a library that has moved past it.* That is an upper bound or a `Breaks:`.

**This repository and `cuems-engine` are now the only two consumers that cannot express it.** Three
siblings have moved:

| Repository | `pyproject.toml` | `debian/control` |
|---|---|---|
| `cuems-nodeconf` | `>=0.1.0rc16,<0.1.1` | `>= 0.1.0rc16`, `<< 0.1.1~` — **the model** |
| `cuems-common` | — | `>= 0.1.0rc16`, `<< 0.1.1~` |
| `cuems-power-bridge` | `>=0.1.0rc16,<0.1.1` | `>= 0.1.0rc16` (upper bound missing in control) |

**Whether this repository gains a `debian/` directory is a wave-4 decision, not a foregone one.** If
it does, note the sibling convention settled 2026-09-24: `debian/` lives on the **working branch**, not
a separate `debian/bookworm` branch — that pattern was abandoned in `cuems-utils` after the packaging
branch sat seven weeks and 132 commits behind and two release candidates left the tree with no
changelog entry.

## 10. Test coverage, stated as a fact rather than a complaint

**Six** files on this base branch, five on `rc1`: `test_dangling_targets.py`, `test_media.py`,
`test_probe_duration.py`, `test_repair_durations.py`, `test_validate_fade_durations.py`, and
**`test_nodelist_actions.py`** (392 lines, added by the base branch — §8a). Runner: `hatch test`
(hatchling, `testpaths = ["tests"]`).

Note which of them cover code this feature changes, measured rather than assumed:

- **`test_dangling_targets.py`** (73 lines, 5 tests) calls `_nullify_dangling_refs` **directly**
  (`:26`) — every one of its five tests exercises the method §4 **deletes**. They do not simply need
  re-pointing: what they assert (a dangling FadeCue action target is cleared, a valid one preserved)
  is now the **library's** guarantee, so re-asserting it here would be re-testing `cuemsutils` from a
  consumer — the same reasoning FR-030a-i applies to the node model. The honest disposition is
  retire-and-record, with the library's own coverage named as the replacement.
- **`test_repair_durations.py`** (108 lines) covers the tool §8 **splits in half**, and imports
  `XmlReaderWriter` itself (§1's sixth site). Its pass-A tests stay; its pass-B tests move with
  pass B.

- **`test_nodelist_actions.py`** (392 lines) is the opposite case: it pins a surface this migration must
  **preserve**, not replace. Keep it green throughout and treat a change to it as a signal that the port
  moved something it should not have — the yardstick discipline, applied to the one part of this
  repository that already has one.

So **two of the six test files are migration targets, and a third is a guard**. Retiring or re-homing a
test is a recorded, argued event — never a silent one. Upstream's equivalent (retiring 22 contract
tests) is explicitly required to be stated rather than silent; hold the same line here.
