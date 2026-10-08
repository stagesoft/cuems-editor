<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Specification Quality Checklist: Config round trip, a durable repair gate, and the restated version 1 wire

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-08
**Feature**: [spec.md](../spec.md)

## Content Quality

- [~] No implementation details (languages, frameworks, APIs). **Deliberate exception.** In this
  repository the product is the wire contract and the library surface (constitution Principles I
  and V). Frame types, keys, and `ConfigManager` calls are the requirement, not a choice of how to
  meet it. Feature 001 follows the same convention. Internal design (lock structure, module
  layout, test file names beyond the ones the prompt names) is left to the plan.
- [x] Focused on user value and business needs (operator data safety, the UI team's single
  contract, the maintainer's tag gate)
- [~] Written for non-technical stakeholders. **Deliberate exception.** The readers are the UI team
  and the ecosystem maintainer (see "User Scenarios"). The user stories are written in operator
  terms, and the FRs are not.
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain. The three open decisions are in the Clarification
  agenda, each with a default, for `/speckit-clarify`, as the prompt asks for Q1.
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic. SC-001 to SC-010 are stated as outcomes: counts,
  paths, and the document's content.
- [x] All acceptance scenarios are defined (US1 to US5)
- [x] Edge cases are identified (reconnect with an unknown id, a restart, a file changed between
  load and save, simultaneous saves, the pre-013 settings shape, the save quirks)
- [x] Scope is clearly bounded (Out of scope, Settled inputs)
- [x] Dependencies and assumptions identified (Upstream gates G1 to G4, plus G5 for context;
  Assumptions)

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [~] No implementation details leak into specification. Same deliberate exception as the first
  item.

## Notes

- Validation, iteration 1: two cross-references were wrong (M5 → FR-030, and US5 → FR-024 to
  FR-028). Both are corrected to G1/FR-032 and FR-028 to FR-031.
- Upstream drift during writing: `cuems-utils` `specs/planning/upcoming-feature-requirements-2026-10-02.md`
  gained §0a (uncommitted in that checkout, 2026-10-08). The spec now cites it for G4's library half
  (M8), G5, and the field ownership (M7).
- `[~]` marks a template item that this repository's convention deliberately does not meet. The
  reason is stated beside each one. None of them blocks `/speckit-clarify` or `/speckit-plan`.
