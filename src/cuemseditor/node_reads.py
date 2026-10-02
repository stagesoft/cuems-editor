# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a read of ``network_map.xml`` hands back to the event-loop thread.

The read runs in the server's executor and must not touch shared state
(constitution II). It returns one of these, and the coroutine that awaited it
assigns. A plain module so ``CuemsWsServer`` and ``CuemsWsUser`` can both name
the types without importing each other.
"""

import re
from typing import NamedTuple


class NodeLists(NamedTuple):
    """A successful read, already merged into the mapping nodes."""

    nodes: list
    new_nodes: list


class IdentityCollision(NamedTuple):
    """The map names one node identity on two rows.

    Deterministic: re-reading the same file fails the same way, so it is not
    retried. ``message`` is the library's text from
    ``cuemsutils.errors.node_identity_collision_message``.
    """

    identity: str
    file: str
    message: str


# Recognition is the library's (node_identity_collision_message). This only
# lifts the identity out of the sentence the library wrote, because the
# exception carries no structured field for it (upstream report UR-4).
_COLLIDED_IDENTITY = re.compile(r'node identities are not unique: (\S+) is carried by')


def collided_identity(exc):
    """The first colliding identity named in *exc*, as a string ('' if none)."""
    match = _COLLIDED_IDENTITY.search(str(exc))
    return match.group(1) if match else ''
