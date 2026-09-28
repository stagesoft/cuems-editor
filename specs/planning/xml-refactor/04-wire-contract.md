<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# The `project_load` payload contract, as amended

**The highest-risk artefact in this repository.** Governs the editor → UI boundary. Vendored
2026-09-25 from `cuems-utils/specs/planning/xml-rebuild/xml-rebuild-05-ui-wire-contract.md` and
`specs/010-consumer-migration/contracts/editor-ui-messages.md`, amended per finding C3.

---

## 1. The constraint, stated correctly

> The `project_load` payload is transmitted **verbatim** to the Angular UI, so it stays
> byte-identical to today's **except for exactly two already-landed, deliberate changes**:
>
> **(a)** `schemaLocation` is **absent** — feature 006's `to_wire()` drops it.
> **(b)** `Media.duration` is `{"CTimecode": "HH:MM:SS.mmm"}`, not a bare string — feature 008's
> D17/D18b.
>
> Everything else — **every other key, the ordering, and the string boolean form** — is unchanged.

## 2. What this is *not*, and why the distinction is load-bearing

**It is not unconditional byte-equality.** That wording was true until 008 landed and it stood in the
shared context block until 2026-09-03, when finding C3 caught that it contradicts two of the
rebuild's own decisions. **Do not restate it.** A spec that asserts unconditional byte-identity
cannot be satisfied, and the reviewer who notices will be the one who has to redo the work.

**`doc_version` is not a third delta.** It is a document property, not a domain field: excluded from
`spec._derive_attributes` and from every wire projection, read by a pre-validation probe before any
schema decode is attempted. The frontend never sees it. Confirmed 2026-09-25 by measurement —
`grep -rn 'doc_version' ../cuems-frontend/src/` returns nothing.

**The string boolean form survives.** The UI reads
`cueData.enabled === true || cueData.enabled === 'True'` (measured live at
`../cuems-frontend/src/app/components/projects/project-edit/sequence/sequence.component.ts:492`) and
writes back the **string** form. That dual read is not legacy debt to clean up in this feature — it
is the compatibility mechanism, and changing the wire to a real boolean here would be a third delta
this contract does not sanction.

---

## 3. How the two deltas are verified

**Not by inspection.** Two methods, and the second is the one upstream requires.

| Method | Use |
|---|---|
| Byte-comparison against a payload **captured before** the migration | Establishes that nothing *else* moved. Capture it as the first commit of the feature, before any source change |
| Comparison against **`cuems-utils`' own golden corpus** — `tests/golden/`, which already carries `doc_version="2"` and the wrapped duration, recorded **by checksum** | The authoritative check (upstream T027). A payload captured at migration time can itself be wrong; a golden cannot drift without a recorded re-basing event |

Do both. The captured payload answers *"did I change something I did not mean to"*; the goldens
answer *"is the result the shape the library intends"*.

**Do not ask for a golden to be re-cut.** Upstream FR-021: a golden is never regenerated to make a
test pass. Re-basing is a recorded, argued event, and that feature sanctioned exactly three across
its whole span.

---

## 4. Delta (a) has a live consequence in the frontend, which this contract must hand over

Measured 2026-09-25 in the sibling checkout:

```
../cuems-frontend/src/app/services/projects/projects.service.ts:120    schemaLocation: string;
```

It is a **non-optional** property of the TypeScript interface describing this payload. After delta
(a) the key is absent, so the interface is false. Nothing crashes — the payload arrives as `any` from
a WebSocket message, so TypeScript's structural typing never checks it — but an interface that lies
is how the next reader concludes the field is still there.

**This is `cuems-frontend`'s edit, not this repository's.** It is recorded here because this
repository is what makes the key disappear, and a hand-over that names the exact line is the
difference between a coordinated change and a surprise.

---

## 5. The new message families this feature adds

Two, and they are modelled on different existing pairs on purpose.

**The schema descriptor (serve + accept).** Model it on the `initial_mappings` (serve) +
`nodelist_modify` (accept a mutation) pair — a config domain that **already has both halves** — not
on `initial_template`, which is serve-only. Reach the descriptor through `ConfigManager` (D34),
**never** through `cuemsutils.xml.descriptor`: `cuemsutils.xml` declares `__all__ == []` and is
internal machinery (Q14).

**The repair report (serve only).** `CuemsScript.load_with_report(path)` returns
`(script, LoadReport)`. This repository forwards the report as a WS message; `cuems-frontend` renders
it. `cuemsutils` deliberately **cannot** do this half — it has no UI channel and must not gain one.
A repair that happens silently is the exact outcome D21's three-outcome design exists to prevent.

The report answers, from data alone and never `None` in place of an empty report: which document,
which fields were repaired and to what, which conversions ran, and **whether the file on disk is now
stale**. That last flag is what makes the "repaired identically on every open" state legible rather
than confusing.

---

## 6. The untangling, and why it cannot land alone

`reload_network_map_nodes` (`CuemsWsServer.py:439`) merges `network_map` node status **into**
`mappings_dict` (`:417`) and serves the result as `initial_mappings` (`:509-511`). So a `network_map`
edit reaches the UI inside a `project_mappings` payload — two config domains on one wire key.

Untangling it is a **simultaneous** behaviour change for three `cuems-frontend` components:

```
../cuems-frontend/src/app/components/settings/settings.component.ts          (nodelist_modify, adopt/unadopt)
../cuems-frontend/src/app/components/projects/project-show/audio-mixer/audio-mixer.component.ts:80
../cuems-frontend/src/app/components/projects/project-show/video-mixer/video-mixer.component.ts:94
```

The two mixers read `localStorage.getItem('initial_mappings')` directly. **Do not land the untangling
before the UI that consumes it** — and note that `localStorage` makes this worse than a normal wire
change: a cache that outlives a schema change is how a UI shows the wrong shape after an upgrade, and
these two components will read a stale entangled payload until it is evicted.

Coordinate with `cuems-frontend`'s flow. Upstream's D26 is explicit that the config domain is a
**migration, not a greenfield build**: a `network_map` editing UI exists and is in daily use on the
controller. Adopt/unadopt must keep working through the port.

---

## 7. The compatibility handshake, for the boundary that has no package manager

`cuems-frontend` is not packaged, so it cannot carry a release-gate edge. Upstream's answer (FR-108)
is a **runtime payload-version handshake**: the editor advertises a payload version when a client
connects, and a UI that does not understand it **refuses and says so** rather than rendering a
wrapped duration as an object.

Two things to keep straight, because merging them is a recorded hazard:

- the **payload version** is this handshake, editor ↔ UI;
- **`doc_version`** is the on-disk document marker, never on the wire.

They are different numbers with different lifecycles. State both wherever either appears.
