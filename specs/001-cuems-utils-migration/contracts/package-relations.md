<!--
SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
SPDX-License-Identifier: GPL-3.0-or-later
-->

# Contract — dependency pin, Debian packaging, candidate tag

The gate's claim is that an unmigrated editor refuses a `cuemsutils` that has moved past it,
and that this editor refuses the `v0.1.1` which deletes the surface it used to import.
`cuemsutils._deprecation.REMOVAL_RELEASE` is `v0.1.1`. This feature does not move the library
off `0.1.0rc16`.

## Python package

`pyproject.toml` `dependencies`:

```text
cuemsutils>=0.1.0rc16,<0.1.1
```

The floor is not lowered to make a test pass. There is no extra upper bound (`<0.1.0rc17` or
similar): `0.1.1` is the removal release, and release candidates of `0.1.0` after rc16 are the
line this migration tracks until the ecosystem says otherwise.

## Debian

`debian/` is added on `feat/xml-refactor`, starting from `origin/debian/bookworm` at `72f952a`,
so the changelog history is carried. `debian/bookworm` is not deleted, renamed, or force-updated
by this feature. It remains the branch packaging automation builds from.

`debian/control` `Depends` gains, beside `${python3:Depends}`:

```text
python3-cuemsutils (>= 0.1.0rc16), python3-cuemsutils (<< 0.1.1~)
```

That is the `cuems-nodeconf` `debian/control` pair. `debian/changelog` gains an entry for this
migration. `CLAUDE.md`'s `debuild -b -uc -us -nc` instruction is run from the working branch
once `debian/` is there.

Every `debian/` change made on `feat/xml-refactor` is listed in
`specs/001-cuems-utils-migration/debian-consolidation.md` by commit and file, plus anything on
`debian/bookworm` that was not in `72f952a` at import time (expected: none). Applying that list
to `debian/bookworm` is the maintainer's action, as with tags.

## Tag message

Prepared at `../.xml-refactor-tag-messages/`, next to the sibling messages. This feature does
not create, move, or push `xml-refactor-merge-candidate`.

The message names the adoption work as included, not as a separate merge:

- this repository, `feat/nodelist-adoption-api`, through `886f649`
- `cuems-engine`, `feat/nodelist-modify-dispatch`
- `cuems-nodeconf`, `feat/nodelist-modify-hardening` (47 commits behind its main line and
  largely superseded; named as a coordination item for that repository's flow, not resolved here)

Until `cuems-frontend` 05 consumes the repair report, the failure message, and the milestone 2
families in [ws-messages.md](ws-messages.md), the message states that dependency as the
outstanding item and is not marked ready. Milestone 1 (census zero over `src/`) is announced to
the `cuems-utils` flow as the T049 input without waiting for that tag.

## Not in this contract

- Cutting the tag, or tagging `cuems-utils` (it tags last, D27).
- A pin on `cuems-engine` or `cuems-nodeconf`. Those repositories own their relations.
- The `cli.py` `ProjectMappings` import. It is outside this pin; it is carried to `cuems-utils`
  014 in the plan's Complexity Tracking.
