# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>

"""Retired by 001-cuems-utils-migration (FR-017, research R2).

This module pinned the editor's own dangling-reference walk
(``_collect_cue_ids`` / ``_nullify_dangling_refs`` over a hand-kept cue-type
list). That walk is deleted, not ported, and the guide's collapsed list
``['Cue', 'ActionCue', 'FadeCue', 'CueList']`` was not ported either. The two
behaviours it asserted now belong to the library, rule by rule, in
``cuemsutils`` ``xml/validators.py``:

* ``target_resolves`` (repairable): a dangling ``Cue.target`` is set to
  ``None`` on load and listed on ``LoadReport.repairs``.
* ``action_target_resolves`` (unrepairable): a dangling ``action_target`` on an
  ``ActionCue``, and on a ``FadeCue`` through the MRO, is refused on load and at
  ``CuemsScript.save``. Clearing it to ``None`` would fail
  ``action_target_required``, which is why the editor's old clear is gone.

Both rules match on cue identity, so a ``Cue`` of any ``class`` is covered.
Re-asserting them here would re-test the library. Record:
specs/001-cuems-utils-migration/evidence/test-retirements.md.
"""

import pytest

pytestmark = pytest.mark.skip(
    reason="retired: dangling targets are cuemsutils xml/validators.py rules "
           "target_resolves (library repairs Cue.target) and "
           "action_target_resolves (library refuses); the editor walk is deleted"
)


def test_retired():
    """Placeholder so the skip reason is reported."""
