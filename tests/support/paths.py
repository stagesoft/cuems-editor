# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where things are, written once. Tests import these; none builds a path with ``__file__`` and ``..``."""
from pathlib import Path

TESTS = Path(__file__).resolve().parent.parent
ROOT = TESTS.parent
DATA_DIR = TESTS / 'data'
SRC_DIR = ROOT / 'src'
PACKAGE_DIR = SRC_DIR / 'cuemseditor'
SPECS_DIR = ROOT / 'specs'
SIBLINGS_DIR = ROOT.parent
