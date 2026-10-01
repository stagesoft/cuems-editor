<!--
Sync Impact Report (scratch — remove before committing)
=======================================================
Version change: (unversioned template) → 1.0.0
Bump rationale: first ratification; every placeholder replaced. MAJOR 1 because this is the
  initial adopted governance, not an amendment.

Principles (all new):
  I.   The Wire Is A Contract
  II.  Sessions Are Isolated, The Event Loop Is Shared
  III. User Data Has A Recovery Story
  IV.  Tests Gate The Risky Paths, Honestly
  V.   cuemsutils Is Consumed Through Its Public Surface

Added sections: Operational Constraints; Development Workflow & Quality Gates; Governance.
Removed sections: none.

Deliberately NOT included: a performance principle. No benchmark harness and no measured
  baseline for project_load or WS round-trip exist, so any budget written today would be
  uncheckable. Governance states what would admit one.

Known violations of this constitution AT RATIFICATION (recorded, not waived):
  - Principle V: CuemsDBProject.py:9-10 and repair_durations.py:39-40 import
    cuemsutils.xml.Parsers / cuemsutils.xml.XmlReaderWriter; CuemsWsServer.py:26 imports
    cuemsutils.xml.NetworkMap; CuemsWsServer.py:27 imports cuemsutils.create_script, which
    no longer exists (the process fails at import against its declared dependency).
  - Principle V / Operational Constraints: pyproject declares cuemsutils>=0.1.0rc10, an open
    floor with no ceiling; the ecosystem pin is 0.1.0rc16 with a << 0.1.1~ ceiling.
  - Principle III: CuemsDBProject.delete_from_trash calls shutil.rmtree inside a DB
    transaction; a rollback after rmtree restores the row but not the directory.
  - Principle III: whether XmlReaderWriter.write_from_object writes atomically (temp + rename)
    is unverified; save_xml overwrites the live script in place.
  - Principle IV: the import smoke test required by gate (1) does not exist yet.
  The 001-cuems-utils-migration spec MUST list each of these that it does not resolve, in its
  Complexity Tracking table, per Governance.

Templates reviewed (read-only, not modified by this command):
  ✅ .specify/templates/plan-template.md — its "Constitution Check" gate is generic and reads
     this file at runtime; no edit required.
  ✅ .specify/templates/spec-template.md, tasks-template.md — no principle-specific text.
Follow-up TODOs: none deferred; ratification date is today's adoption.
-->

# cuems-editor Constitution

## Core Principles

### I. The Wire Is A Contract

Every message this repository emits over WebSocket `:9092` is consumed verbatim by
`cuems-frontend`. This repository does not control that UI and cannot deploy in lockstep
with it. Payload shape is a contract, not an implementation detail. The same holds for what
it sends to the engine over `/tmp/editor.ipc`.

- The contract is the observable payload: the message `type`, every key and whether it is
  present, key ordering, and value types. That includes the **string** boolean form
  (`"True"`) that the UI reads and writes back. A refactor that changes any of these is a
  contract change, whatever the intent.
- A contract change MUST be an **enumerated delta**. It names each changed message and key,
  the old and new form, and the consuming `cuems-frontend` file and line. It is recorded in
  the feature's contract document and in `tests/ws-command-responses.txt`. "Byte-identical
  except for the listed deltas" is the only acceptable form of the claim. Unconditional
  byte-identity MUST NOT be asserted once a delta is sanctioned. A claim that cannot be true
  is not a constraint.
- A contract change MUST be verified by comparing against a payload **captured before** the
  change, committed ahead of any source edit. Where an upstream golden corpus exists, it MUST
  be compared too. Verification by inspection is not verification.
- A change that alters what an existing UI component reads MUST NOT land before that UI does,
  unless a runtime payload-version handshake lets the old UI refuse and say so. UI state cached
  in `localStorage` counts as a consumer.
- New message families are contracts from their first commit. Inbound handling MUST keep
  accepting what deployed frontends actually send, until every deployed frontend has moved.
  Today that includes zero media durations from older UIs.
- The payload version (editor ↔ UI handshake) and `doc_version` (the on-disk document marker,
  never on the wire) are different numbers. Wherever either appears, it MUST be named as
  which one it is.

Rationale: the largest risk in this codebase is a payload change nobody noticed. Nothing
crashes. `any`-typed WebSocket data defeats the UI's type checker, and the failure shows up as
wrong behaviour in a show.

### II. Sessions Are Isolated, The Event Loop Is Shared

`CuemsWsServer` multiplexes many operators onto one asyncio loop and one project store.
Concurrency and session isolation are correctness concerns. A stall or a cross-session leak
is a bug, not a slowdown.

- Each command MUST have a declared audience: the caller only, other sessions on the same
  project, or all sessions. A mutation that other sessions can observe MUST notify them
  through the server's notify paths, and the audience is part of the contract (Principle I).
- Per-session state (loaded project, session UUID, upload state) MUST be keyed by session and
  MUST NOT be read or written on behalf of another session.
- Blocking work (DB, filesystem, subprocess, NNG round-trips) MUST run off the event loop, via
  the server's executor or an equivalent. On this loop, one blocked handler freezes every
  connected operator.
- Shared server state (`users`, `sessions`, watcher state) MUST be mutated only on the event
  loop thread, never from executor threads.
- The concurrent-edit policy MUST be explicit. Today it is **last writer wins, then other
  sessions on the project are notified**. Changing that policy is a contract change under
  Principle I, not a local fix.

Rationale: per-connection handlers are easy to test alone and fail only under multi-user
load, which is the controller's normal operating condition.

### III. User Data Has A Recovery Story

Project XML, the media library and `project-manager.db` under `library_path` are the
customer's work. This repository writes to them on every save.

- Every operation that destroys or overwrites user data MUST name its recovery path before
  it merges. Those operations are permanent delete, purging the trash, overwriting a script,
  bulk rewrites by maintenance tools, and media replacement. Acceptable recovery paths are
  trash-before-purge, a backup taken before the write, or a human-confirmed step with the
  consequence shown. "The parser/schema accepted it" is validation, not recovery.
- Soft delete (move to `trash/`) MUST stay the default destructive action reachable from the
  UI. Permanent deletion MUST only operate on items already in the trash.
- A write MUST either complete or leave the prior file intact. Where a DB transaction and a
  filesystem side effect are combined, they MUST be ordered so that a failure can be rolled
  back. An irreversible filesystem step MUST NOT run before a step that can still fail and
  roll back.
- Tools that rewrite user data in bulk (e.g. `cuems-editor-repair-durations`) MUST back up
  what they touch before writing, MUST offer a dry run, and MUST report what changed.
- Saving a document that the library repaired on load overwrites the original with no
  library-side backup. This repository MUST ensure an operator has seen the repair report
  before that save. A repair that reaches disk unseen is a violation.
- Save-time validation (e.g. FadeCue durations) MUST reject with a message that names the
  offenders and reaches the operator. Silently dropping or "fixing" a field is not
  validation.

Rationale: an editor bug costs a re-click, but a data bug costs a production. Validation
keeps bad data from being written. It does nothing for good data that was already lost.

### IV. Tests Gate The Risky Paths, Honestly

At ratification there are six test files against roughly 4,700 lines of source. The suite
has never exercised most of `CuemsDBProject`, `CuemsDBMedia`, `CuemsWsUser` or the command
router. This principle states a gate the repository will meet on every PR, plus a direction
of travel. It does not claim coverage that does not exist.

The gate (MUST, every PR):

1. **The process imports.** A smoke test MUST import every module under `cuemseditor`
   against the declared `cuemsutils`. A green suite that never imported the code is not
   evidence.
2. **Wire changes are pinned.** Any change under Principle I MUST come with a test that
   asserts the changed payload, and that test MUST fail against the pre-change behaviour.
3. **Writes to user data are pinned.** Any new or changed path under Principle III MUST
   come with a test that runs it against a temporary library and asserts the recovery path,
   not only the happy path.
4. **Silent-wrong callers are hunted, not awaited.** When a dependency changes the shape of
   a value, every caller that still resolves but now computes the wrong answer MUST be
   searched for. Typical examples are a key-name filter and a regex guard over a value that
   became a dict. Each one MUST get a test that fails against the old shape **first**.
5. **Bug fixes carry their regression test.**

Direction of travel (SHOULD; reviewed at each amendment): a PR that modifies a function with
no test adds one for that function. The suite's test-file count and the set of covered
modules MUST NOT shrink without a recorded reason.

Not required: blanket coverage percentages, and tests of models `cuemsutils` owns.
Re-testing the library's node or script model here duplicates its ownership (Principle V).
A test like that is a regression, not coverage.

Rationale: a rule that is waived in its first PR teaches that rules are waivable. These
five gates target exactly the paths where this repository's past failures came from.

### V. cuemsutils Is Consumed Through Its Public Surface

`cuemsutils` is a library that versions deliberately. This repository is a consumer of it,
not a co-author.

- Imports MUST come from the surface `cuemsutils` declares public. `cuemsutils.xml` is
  internal machinery (`__all__ == []`), and any import from it or its submodules is a
  violation. Other examples are `_`-prefixed modules and removed or deprecated entry points.
  If something needed exists only internally, the gap is the library's to close. Raise an
  upstream report. Do not work around it here.
- This repository MUST NOT patch, monkeypatch or vendor-modify `cuemsutils`. Defects found
  here are reported upstream and left visibly unpatched on the consumer side.
- This repository MUST NOT re-implement a model `cuemsutils` owns, such as the node, script
  or timecode models. Delegating is how `validate_fade_durations_in_contents` stays
  consistent with `CTimecode` semantics.
- The `cuemsutils` version range MUST be bounded on both sides. It moves only together with
  the ecosystem release, never ahead of it and never alone.
- Deprecation warnings from `cuemsutils` are defects to schedule, not noise to silence.

Rationale: the library's compatibility guarantees cover its public surface and nothing else.
A consumer that reaches past that surface turns every upstream refactor into a silent break
here. The `create_script` import failure is the precedent.

## Operational Constraints

- Runtime: Python ≥ 3.11, packaged as `cuemseditor` and built with `debuild`. It runs as
  `cuems-editor.service` on the controller.
- The project store is `settings.xml <library_path>` (`/opt/cuems_library/`). There is no
  `/opt/cuems/`. Project directories are named by `unix_name`. UUID and display name live in
  `script.xml` and the index DB, and code MUST NOT derive them from the directory name.
- Topology is cached at startup by both this service and the engine. Any change that relies
  on edited `network_map.xml` or `default_mappings.xml` MUST document that both daemons need
  a restart. The node list reaches clients by push (`watch_network_map`), and
  `nodelist_get` is its pull form. Capability flags such as `nodeconf_available` MUST be
  computed live, never cached past the condition they report.
- No feature ships from this repository alone when it is part of a multi-repository
  change. The release follows the ecosystem's release ordering.

## Development Workflow & Quality Gates

- Every spec's plan MUST include a Constitution Check against Principles I–V. It names each
  wire delta, each user-data write path and its recovery story, and each `cuemsutils` import
  added or removed.
- Every PR MUST satisfy the five Principle IV gates. The reviewer checks that the
  pre-change-failing tests actually fail against the old code, not only that they pass.
- A contract change (Principle I) MUST update `tests/ws-command-responses.txt` and hand off
  to `cuems-frontend` by file and line in the same PR description.
- Field knowledge that a future maintainer would need goes in `CLAUDE.md` "Field notes" in
  the same PR. That covers gotchas, restart requirements and deliberate non-validation (e.g.
  `duplicate()`).

## Governance

This constitution overrides local convention and individual preference for this repository.
Ecosystem-wide settled decisions (upstream in `cuems-utils`) bind alongside it. Where the
two conflict, the conflict is raised upstream. It is not resolved locally.

- **Exceptions are information, not amendments.** A spec that cannot meet a rule MUST record
  the exception in its plan's Complexity Tracking table. The record names the rule, the exact
  violation, why it is unavoidable now, and the task or feature that retires it. No rule is
  weakened to make a feature pass. The violations known at ratification are listed in this
  file's history and MUST be carried that way.
- **Amendments** are made by PR to this file. The PR states the reason, the version bump and
  its justification, and any principle whose meaning changes.
- **Versioning** follows semver. MAJOR covers removing or redefining a principle or
  weakening a MUST. MINOR covers a new principle or section, or materially expanded
  guidance. PATCH covers wording that does not change meaning.
- **A performance principle** may be added (MINOR) once a measured, repeatable baseline
  exists for `project_load` or WS round-trip on controller-class hardware. The budget is
  then stated against that baseline. Until then, no performance budget is binding, because
  one that nobody can check is decoration.
- **Compliance** is reviewed at every PR (the gates above) and at every `/speckit-plan`
  (the Constitution Check). Principle IV's direction-of-travel clause is re-read at each
  amendment.

**Version**: 1.0.0 | **Ratified**: 2026-10-01 | **Last Amended**: 2026-10-01
