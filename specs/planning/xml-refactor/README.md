<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# `cuems-editor` — planning bundle for the `cuemsutils` public-API migration

**Assembled** 2026-09-25 from `cuems-utils@b7db53e` (branch `feat/xml-refactor`), whose
`specs/planning/xml-rebuild/010-consumer-prompts/02-cuems-editor.md` is the upstream original.

**Purpose**: make this repository's spec-driven work **self-contained**. Everything the flow needs is
here; the sibling `cuems-utils` checkout is no longer required reading.

## Start here

Read **[`00-runnable-flow.md`](00-runnable-flow.md)** and run it. It is a complete spec-kit flow —
branch and bootstrap, a constitution step (this repository has none), the `/speckit.specify` →
`implement` chain, and exit criteria. It names the feature **`001-cuems-utils-migration`**.

| File | What it is | Why you need it |
|---|---|---|
| [`00-runnable-flow.md`](00-runnable-flow.md) | The flow itself | The SDD. **§0a is the three-repository branch cluster — read it first.** §1 also covers the spec-kit bootstrap, which this repository needs and which has a version problem |
| [`01-settled-decisions.md`](01-settled-decisions.md) | The decisions that bind **this** repository — eleven, more than any other consumer | Do not reopen these |
| [`02-consumer-audit-findings.md`](02-consumer-audit-findings.md) | C2, C3, C4, C5 and the minor half of C11 | Five of the audit's twelve findings are this repository's. That is not an accident — see below |
| [`03-migration-inventory.md`](03-migration-inventory.md) | Every call site, measured 2026-09-25 against the base branch with `rc1` in brackets | Your working inventory. **§8a is scope no upstream document carries** |
| [`04-wire-contract.md`](04-wire-contract.md) | The `project_load` payload contract, as amended | **The highest-risk artefact in this repository.** Read it before writing a line of the spec |

## The one thing to understand before starting

**This repository does not start.** Verified 2026-09-25 against `cuems-utils@b7db53e`:

```
$ python -c "from cuemsutils.create_script import create_script, new_uuid"
ModuleNotFoundError: No module named 'cuemsutils.create_script'
```

`src/cuemseditor/CuemsWsServer.py:24` imports that module. Feature 008 deleted it **with no
deprecation shim** — unlike the six entry points feature 006 retired, which all still resolve and
warn. So this repository fails at import against its own declared dependency, and **"the suite is
green" says nothing until the process starts**, because no call site is reached.

That is why the flow has a task zero. It is also separable from everything else: `new_uuid` is
already imported from `cuemsutils.helpers` at four other sites in this repository, so the import fix
does not wait on the template decision that `create_script` belongs to. Do not let one block the
other — one of them is blocking every other task in the spec.

## Why five of twelve findings are this repository's

Not bad luck. This is the repository where three properties meet:

1. **It is a wire-contract repository.** Its `project_load` payload is transmitted *verbatim* to an
   Angular UI it does not control and cannot deploy in lockstep with. A payload change is a
   coordinated multi-repo event, not an implementation detail.
2. **It owns user data on disk.** Project XML and the media library are the customer's work.
3. **It has five test files.** Against `CuemsDBProject.py` alone at 896 lines.

Every one of the audit's findings here sits at the intersection of at least two of those. The
`repair_durations.py` finding sits at all three: a tool that rewrites user data, guarded by a regex
that post-008 silently stops matching, with one test file covering it.

## The base branch is not `rc1`

**`feat/xml-refactor` branches from `feat/nodelist-adoption-api`** (5 commits, 0 behind `rc1`), not from
`rc1` as the upstream flow says. It is the editor third of an **unmerged three-repository feature** from
2026-09-04 — the node adopt/un-adopt hop — whose other halves are `cuems-engine`'s
`feat/nodelist-modify-dispatch` and `cuems-nodeconf`'s `feat/nodelist-modify-hardening`. The UI tier
does not exist at all.

**`00-runnable-flow.md` §0a is the cluster map and must be read before §1.** It also carries a reported
divergence in `cuems-nodeconf` whose write path this repository's `nodelist_modify` calls.

## Freshness — two sets of coordinates, and the difference is the base branch

The upstream flow measured this repository on **2026-09-03** at `rc1`/`d9e0a39`. Re-measured
2026-09-25: **`rc1` @ `d9e0a39`, in sync with `origin/rc1`, clean — unchanged since 2026-08-03.** So
every upstream line number is still exact **for `rc1`**.

It is **not** exact for the base branch. Two files move:

| File | `rc1` | `feat/nodelist-adoption-api` |
|---|---|---|
| `CuemsWsServer.py` | 563 | **651** |
| `CuemsWsUser.py` | 806 | **889** |
| `CuemsDBProject.py` | 896 | 896 — untouched |
| `repair_durations.py` | 294 | 294 — untouched |
| test files | 5 | **6** |

`03-migration-inventory.md` gives branch line numbers with the `rc1` value **in brackets**, so a reader
comparing against the upstream prompt can see which disagreements are the base branch and which would
be real drift. Every `CuemsDBProject.py` and `repair_durations.py` site — where the bulk of this
migration's work is — is identical on both.

## Corrections applied on vendoring

1. **The hard constraint is an enumerated two-delta, never unconditional byte-identity.** The
   pre-2026-09-03 wording said something stronger and contradicted two of this rebuild's own
   decisions. `04-wire-contract.md` carries the amended form. **This is the single item most likely
   to be got wrong**, and restating the old wording is a defect, not a simplification.
2. **The spec-kit bootstrap has a version problem upstream could not know.** The three landed sibling
   repositories were initialized with spec-kit **1.0.4**; the `specify` CLI on this development
   machine is **0.16.2**. Running `specify init` now would produce a scaffold that differs from the
   siblings'. `00-runnable-flow.md` §1 states the options rather than picking one silently.
3. **The minor half of C11 is recorded here, not in `cuems-engine`'s bundle.** The audit filed
   `repair_durations.py:87`'s dead guard under C11 because it arrived in the same finding, but it is
   this repository's code and this repository's fix.
4. **The base branch changed, and it brings scope no upstream document has.** Corrected 2026-09-25
   after `feat/nodelist-adoption-api` was found — it is remote-only, so the first sweep listed it and
   did not chase it. `03-migration-inventory.md` §8a is the new surface: `nodelist_get`, `node_status`,
   `nodeconf_available`, and the fact that `nodeconf_available`'s injection into `mappings_dict` makes
   the domain entanglement **three-way** rather than two-way.
5. **An earlier version of this bundle said the inventory had "no drift".** That was true of `rc1` and
   is not true of the base branch. Corrected rather than quietly re-measured, because the claim was
   load-bearing: it was the reason to trust the upstream prompt's numbers verbatim.
