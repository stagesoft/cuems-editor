<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# `cuems-editor` — the consumer-audit findings that are this repository's

**Vendored** 2026-09-25 from `cuems-utils/specs/planning/xml-rebuild/xml-rebuild-09-consumer-audit.md`
(measured 2026-09-03). **Five of the audit's twelve findings** touch this repository: C2, C3, C5 and
the minor half of C11 directly, and C4 because it is the upstream gap this repository's descriptor
work depended on.

---

## C2 — `cuems-editor` does not start against the current branch

`src/cuemseditor/CuemsWsServer.py:24`:

```python
from cuemsutils.create_script import create_script, new_uuid
```

Feature 008 deleted that module **with no deprecation shim**. Unlike the six entry points feature 006
retired — which all still resolve and warn — this one simply is not there.

**Re-verified live 2026-09-25** against `cuems-utils@b7db53e`:

```
ModuleNotFoundError: No module named 'cuemsutils.create_script'
```

**The consequence that matters more than the line**: the process does not start, so **no call site in
this repository is reached**, and "the suite is green" says nothing until it does. Every other finding
below is downstream of a repository nobody can run.

**Disposition**: task zero, and separable. `new_uuid` re-sources from `cuemsutils.helpers`, already
imported at four other sites here. `create_script`'s replacement is the descriptor work, which carries
a design decision. Do not let the second block the first.

---

## C3 — the shared context block's HARD CONSTRAINT contradicts 008

The cross-repo context block asserted the `project_load` payload stays **unconditionally
byte-identical**. Two of this rebuild's own landed decisions make that false:

- 006's `to_wire()` **drops `schemaLocation`**;
- 008's D17/D18b makes `Media.duration` `{"CTimecode": "..."}` rather than a bare string.

**Resolution**: the constraint is an **enumerated two-delta**, not unconditional identity. The
amended form is in [`04-wire-contract.md`](04-wire-contract.md). `doc_version` is **not** a third
delta — it is excluded from every wire projection.

**Why this finding is in the audit at all**, and why it is worth reading rather than skimming: the
wrong wording had already been copied into a shared context block and was on its way into three
specs. A constraint that cannot be satisfied does not fail loudly — it gets quietly reinterpreted by
whoever implements it, differently each time.

---

## C4 — the schema descriptor has no public import path

Feature 008 built the descriptor over all six schemas but left it inside `cuemsutils.xml`, which
declares `__all__ == []`. So the two consumers that need it — this repository and `cuems-frontend` —
could only reach it by violating Q14.

**Closed upstream** by feature 010's wave 0: the descriptor is reached through `ConfigManager`
(D34). Recorded here because it explains why this repository's descriptor work was *gated* on the
library's own flow, and because the rule it restores is the one to hold: **if something you need is
only available inside `cuemsutils.xml`, that is the library's gap to close, not this repository's to
work around.**

---

## C5 — the frontend template inventory undercounts, in files and in kind

Filed against `cuems-frontend`, and reproduced here because this repository is the **other end of
every one of those call sites**: it is what serves `initial_template` and `initial_mappings`.

The operative half for this repository: the template surface is consumed for **values**, not only for
shape. That is why D25 makes model-layer defaults non-optional in the descriptor, and why replacing
`create_script()` with "a description of the schema" is insufficient on its own.

---

## C11, the minor half — an FR-030a-ii site inside the tool this feature migrates

The audit filed this under C11 (whose major half is `cuems-engine`'s deploy path) because it arrived
in the same finding. **It is this repository's code and this repository's fix.**

`src/cuemseditor/repair_durations.py:87-89` guards `duration`, `in_time`, `out_time`, `offset` and
neighbours with `TIMECODE_SHAPE.match(value)` against **string** values. Post-008 those are dicts on
the wire, so `match` is never reached with a string and **the guard silently stops catching
anything**.

This is the finding that sits at the intersection of every one of 008's decisions, which is why
upstream flagged this file as needing the most care of anything in this repository: it is a tool whose
**purpose** is to load deliberately-corrupt documents, against a parser that just became strict, with
a private duplicate of the library's canonical timecode form, rewriting user data on disk.

---

## The findings that are *not* this repository's

For orientation, so nothing is picked up by mistake:

| | Finding | Owner | State 2026-09-25 |
|---|---|---|---|
| C1 | a sixth consumer, unlisted everywhere, already silently wrong | `cuems-power-bridge` (audited as `cuems-wsclient` — the same repository renamed) | **landed** |
| **C2** | this repository does not start | **`cuems-editor`** | **open** |
| **C3** | the HARD CONSTRAINT contradicts 008 | **`cuems-editor`** / `cuems-frontend` | resolved as the two-delta statement |
| C4 | the descriptor has no public path | `cuems-utils` | closed upstream |
| **C5** | the frontend template inventory undercounts | `cuems-frontend` (this repository is the serving end) | open |
| C6 | the Avahi TXT vocabulary has two owners | `cuems-nodeconf` + `cuems-common` | **landed** |
| C7 | the release gate has one enforced edge | `cuems-engine` + every consumer, **this one included** | open — `03-migration-inventory.md` §9 |
| C8 | the frontend has no coverage where 010 works hardest | `cuems-frontend` | open |
| C9 | three stale documents that are 010's own inputs | `cuems-utils` | closed |
| C10 | work landed after 008 closed, in no plan | `cuems-nodeconf` | **landed** |
| **C11** | third distribution surface — **minor half here** | `cuems-engine` (major) / **`cuems-editor`** (minor) | **open here** |
| C12 | the zero-`node_type` criterion cannot pass as written | `cuems-utils` | open |
