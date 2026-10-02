# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retired by 001-cuems-utils-migration T060 (FR-008a).

This module pinned ``initial_template`` — ``ConfigManager.generate_example``
served in place of the deleted ``create_script()`` — against the v0.1.0rc14
baseline, delta by delta. At payload version 1 the editor no longer sends that
message: clients build a new script from ``schema_descriptor("script")``'s
per-type ``instance`` (``tests/test_schema_descriptor.py``). The deltas it
asserted are kept in ``tests/ws-command-responses.txt`` for whoever still holds
a cached template in ``localStorage``. Record:
specs/001-cuems-utils-migration/evidence/test-retirements.md.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="retired: initial_template is not sent at payload version 1; "
           "clients build from schema_descriptor (test_schema_descriptor.py)"
)


def test_retired():
    """Placeholder so the skip reason is reported."""
