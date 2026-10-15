# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""What a read of ``network_map.xml`` hands back to the event-loop thread.

The read runs in the server's executor and must not touch shared state
(constitution II). It returns one of these, and the coroutine that awaited it
assigns. A plain module so ``CuemsWsServer`` and ``CuemsWsUser`` can both name
the types without importing each other.
"""

from typing import NamedTuple

from cuemsutils.errors import NodeIdentityCollisionError


class NodeLists(NamedTuple):
    """A successful read, already merged into the mapping nodes."""

    nodes: list
    new_nodes: list


class IdentityCollision(NamedTuple):
    """The map names one node identity on two rows.

    Deterministic: re-reading the same file fails the same way, so it is not
    retried. Built from the library's structured
    :class:`cuemsutils.errors.NodeIdentityCollisionError` (cuems-editor UR-4,
    cuems-utils 015 S1), never from its message text.
    """

    identity: str
    file: str
    message: str
    #: ``{identity: (mac, ...)}``, every colliding identity with the hardware
    #: addresses carrying it, as the library reports it.
    collisions: dict

    @classmethod
    def from_error(cls, exc: NodeIdentityCollisionError) -> 'IdentityCollision':
        """The collision *exc* describes. ``identity`` is the first colliding
        one, the identity the library's own ``violation`` locates."""
        location = getattr(exc.violation, 'location', None)
        identity = location[0] if location else next(iter(exc.collisions))
        return cls(str(identity), exc.file, f'{exc.file}: {exc}',
                   {str(k): tuple(v) for k, v in exc.collisions.items()})
