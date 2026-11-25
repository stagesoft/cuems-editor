# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""The disk space that running exports and imports have claimed and not yet
written (1amfwm7kana D14, 1amfwm7kcjp D6, change review R3).

An export or an import writes for minutes, and until its bytes land the
filesystem's free space does not show them. Each one registers here what it
will write (a :class:`Reservation`); every space check of either counts the
bytes the others on the **same filesystem** still have to write (``need``
minus what is already on disk, never below zero), and :func:`claim` makes the
check and the registration one hold of the lock, so two checks can never both
pass on the same free bytes. Whoever claims releases, on every exit path.

Only the standard library is imported here: ``CuemsDBProject`` and
``CuemsProjectImport`` both import this module and neither imports the
other's internals.
"""
import os
import shutil
import threading

_lock = threading.Lock()
#: Every reservation held in this process.
_held = set()


def device_of(path):
    """The filesystem of *path* (``st_dev``): a reservation on another one is
    not counted (an exports folder and a library on two disks)."""
    return os.stat(path).st_dev


def size_of(path):
    """The bytes in *path*; 0 when there is no such file (not made yet, or
    already moved on)."""
    try:
        return os.path.getsize(path) if path else 0
    except OSError:
        return 0


class Reservation:
    """*need* bytes to be written on the filesystem *device*; ``written()``
    says how many of them are already on it, so already gone from free."""

    def __init__(self, device, need, written=None):
        self.device = device
        self.need = need
        self.written = written or (lambda: 0)

    def outstanding(self):
        try:
            done = self.written()
        except Exception:
            done = 0                   # counted whole: refuses rather than overfills
        return max(0, self.need - done)


class NoSpace(Exception):
    """Writing the bytes would leave less than the reserve: *free* is the
    filesystem's real free space, as each side's text prints it."""

    def __init__(self, free, reserve):
        super().__init__(f'{free} bytes free, {reserve} kept in reserve')
        self.free = free
        self.reserve = reserve


def _others(device):
    return sum(r.outstanding() for r in _held if r.device == device)


def _check(folder, device, need, reserve_of):
    # The others first, then free: a byte that lands in between is counted
    # twice (refuses a little early), never not at all.
    others = _others(device)
    usage = shutil.disk_usage(folder)
    reserve = reserve_of(usage)
    if usage.free - others - need < reserve:
        raise NoSpace(usage.free, reserve)


def check(folder, need, reserve_of):
    """Raise :class:`NoSpace` unless *need* bytes fit in *folder*'s filesystem
    with ``reserve_of(usage)`` to spare, the others' outstanding bytes
    counted. Registers nothing."""
    device = device_of(folder)
    with _lock:
        _check(folder, device, need, reserve_of)


def claim(folder, need, reserve_of, written=None):
    """:func:`check`, then register *need* bytes on *folder*'s filesystem in
    the same hold of the lock. Returns the :class:`Reservation`; the caller
    must :func:`release` it whatever happens."""
    reservation = Reservation(device_of(folder), need, written)
    with _lock:
        _check(folder, reservation.device, need, reserve_of)
        _held.add(reservation)
    return reservation


def release(*reservations):
    """Forget the reservations given (``None`` and unknown ones are ignored)."""
    with _lock:
        for reservation in reservations:
            _held.discard(reservation)
