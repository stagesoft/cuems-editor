# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Normalisers for the values a cue's ``Media`` stores about its file.

A leaf module: it imports nothing from ``cuemseditor``. ``CuemsDBMedia`` (the
upload stores a row) and ``CuemsDBProject`` (a save writes the values into the
script) both need the same rules, and each used to import them from the other,
a circular import (003, FR-021).

The rules (utils 014, 002 FR-040): a size is a positive ``int`` (a digit string
is accepted); an MD5 is 32 hex digits and is stored **lowercase**.
"""


def _positive_int(value):
    """A usable stored size: a positive int (a digit string is accepted and
    converted). ``None`` for anything else, ``bool`` included."""
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _md5(value):
    """A usable MD5: 32 hex digits, returned lowercase; ``None`` otherwise."""
    if isinstance(value, str) and len(value) == 32 and all(
            c in '0123456789abcdef' for c in value.lower()):
        return value.lower()
    return None


def _valid(key, value):
    return _md5(value) if key == 'file_md5' else _positive_int(value)
