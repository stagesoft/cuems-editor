<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# The settled decisions that bind `cuems-editor`

**Vendored** 2026-09-25 from `cuems-utils/specs/planning/xml-rebuild/xml-rebuild-07-speckit-prompts.md`
§2, which is authoritative for the full list of thirty-six (D1–D36, plus Q11→(c) and Q14→(i)).

**Do not reopen any of these.** If a question arises that this subset does not answer, read §2
upstream rather than inventing an answer locally — and if a decision changes, it changes there first
and propagates here, never the reverse.

This is the **largest binding subset of any consumer**, because this repository sits on both the show
path and the config path and owns the wire to the UI.

---

## The eleven that bind this repository

| | Decision |
|---|---|
| **D12** | The public surface returns **objects**, never raw dicts |
| **D15** | The public objects are `CuemsScript` (show) and `ConfigManager`/`ConfigBase` (config) |
| **D17 / D18b** | `Media.duration` is `cms:CTimecodeType`. `<duration>TC</duration>` is now `<duration><CTimecode>TC</CTimecode></duration>` in XML, and `{"CTimecode": TC}` on the JSON wire |
| **D19 / D21** | `load()` runs T1 **and** T2. Three outcomes: **old** converts in memory (file untouched); **current-but-repairable** loads with the field repaired and the repair carried in a structured report; **unrepairable** raises. A document **newer** than the library raises. `CuemsScript.load_with_report(path) -> (script, LoadReport)` is the entry point that returns the report; `load()` keeps its signature and discards it |
| **D21b** | **Saving a repaired document overwrites the corrupt original with no backup.** What makes that safe is that a human saw the report first. `cuemsutils` cannot enforce the ordering — `load_with_report` and `save()` are two independent calls — so the obligation is **this repository's, procedurally** |
| **D25** | Template/config generation moves onto a schema-derived descriptor covering all six schemas, emitting field name, XSD type, cardinality, `xs:enumeration` values **and model-layer defaults** |
| **D26** | `initial_template`-as-a-concrete-instance is retired. The script domain is a **migration** of the template call sites; the config domain is **also a migration, not a greenfield build** — a `network_map` editing UI exists and is in daily use |
| **D27** | Nothing in the ecosystem releases until every consumer flow lands |
| **D34** | The descriptor is reached through `ConfigManager`, never through `cuemsutils.xml.descriptor` |
| **D35** | The frontend port is preceded by characterization tests. Not this repository's obligation, but its **coordination partner's** — see §"What you must coordinate" |
| **Q14 → (i)** | `cuemsutils.xml` is internal machinery. Do not import from it — it declares `__all__ == []` for this reason |

## The one constraint that is not a decision

**FR-030a-ii — callers that keep resolving but become wrong** are a distinct and more dangerous class
than callers that stop resolving. Nothing fails, the suite stays green, and the answer is silently
wrong. This repository holds two:

- `CuemsWsServer.py:425`'s `basic_fields` naming `'node_type'` — a key the converted document no
  longer has, so the merge **silently drops the field**;
- `repair_durations.py:87-89`'s `TIMECODE_SHAPE.match(value)` against values that are now dicts, so
  the guard **silently stops catching anything**.

They are **searched for**, and each gets a test that fails against the old value **first**. Do not
wait for a red suite.

**FR-030a-i — the node model lives in `cuemsutils` exclusively.** No consumer re-implements or
re-tests it. A node-model test appearing in this repository during this migration is a regression, not
coverage. The sibling `cuems-power-bridge` carried a fourth private copy of that model for two
features because nothing ever told it this rule existed; the copy, not the vocabulary break, was the
root cause of its silent field failure.

---

## The amended hard constraint

**Stated separately in [`04-wire-contract.md`](04-wire-contract.md)** because it is the item most
likely to be got wrong. In short: the `project_load` payload is byte-identical to today's **except
for exactly two enumerated deltas** — `schemaLocation` absent, `Media.duration` wrapped. Everything
else, including key ordering and the **string** boolean form, is unchanged. `doc_version` is **not** a
third delta.

The pre-2026-09-03 wording said unconditional byte-equality. That contradicts two of this rebuild's
own decisions and **must not be restated**.

---

## What you must coordinate, not decide alone

Three items in this feature are simultaneous behaviour changes with `cuems-frontend`. None of them
can land here first:

1. **Untangling `network_map` from the `initial_mappings` payload.** Three frontend components read
   it, two of them straight out of `localStorage`.
2. **The repair report's rendering.** This repository forwards it; the frontend displays it. A report
   forwarded to a UI that ignores it is silent, which is the outcome D21 exists to prevent.
3. **The payload-version handshake** (FR-108). `cuems-frontend` is not packaged and cannot carry a
   release-gate edge, so the runtime handshake is the only compatibility mechanism at that boundary.

D35 is the frontend's obligation, and it is the reason coordination is possible at all: its three
largest files get characterization tests **before** the port, so equivalence there is measured rather
than argued.

---

## What this repository must *not* do

- **Do not reach into `cuemsutils.xml`** for anything (Q14). If something needed is only available
  there, that is the library's gap to close, not this repository's to work around.
- **Do not patch `cuemsutils` from here.** `cuems-nodeconf` established the precedent twice, reporting
  four defects upstream and leaving all four deliberately unpatched from the consumer side, because a
  characterization guarantee depends on the library's files not being edited by a consumer. All four
  were fixed upstream inside `0.1.0rc16`. Write an upstream report.
- **Do not move `cuemsutils` off `0.1.0rc16`.** `0.1.1` is reserved by
  `_deprecation.REMOVAL_RELEASE` and refused by three consumers' `<< 0.1.1~` ceilings.
- **Do not ship from this branch alone** (D27). See `00-runnable-flow.md` §7.
