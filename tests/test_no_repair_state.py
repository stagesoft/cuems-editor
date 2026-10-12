# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The per-connection repair state is gone (002 T016, constitution IV.4).

The gate lives in ``server.repair_gates``, keyed by project. A caller left on
``self.repair_state`` would read state nobody writes any more.
"""

from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "src" / "cuemseditor"


def test_repair_state_no_longer_occurs_in_the_package():
    offenders = [
        f"{path.name}:{number}"
        for path in sorted(PACKAGE.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "repair_state" in line
    ]
    assert offenders == []
