# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Every module under ``cuemseditor`` imports against the declared ``cuemsutils``.

Constitution IV gate 1 (FR-002): a green suite that never imported the code is
not evidence. Each module is its own test case, so a failure names the module.
"""
import importlib
import os
import pkgutil
import re

import pytest

import cuemseditor

# Not imported, with the reason. Anything listed here must also be imported by
# no other module, or the exclusion would hide a real import failure.
NOT_IMPORTED = {
    # A pre-src/ scratch script, not a module: at import it creates
    # ./project-manager.db in the working directory and .get()s two hardcoded
    # project UUIDs, so it raises on any library but the author's.
    'cuemseditor.db': 'dev scratch script with import-time side effects',
}


def _module_names():
    names = [cuemseditor.__name__]
    for info in pkgutil.walk_packages(cuemseditor.__path__, prefix=cuemseditor.__name__ + '.'):
        names.append(info.name)
    return sorted(names)


ALL_MODULES = _module_names()
MODULES = [name for name in ALL_MODULES if name not in NOT_IMPORTED]


def test_the_walk_found_the_modules():
    # A wrong path would turn every case below into nothing.
    assert 'cuemseditor.CuemsWsServer' in MODULES
    assert len(MODULES) > 10
    assert set(NOT_IMPORTED) <= set(ALL_MODULES)


def test_excluded_modules_are_imported_by_nothing():
    src = os.path.dirname(cuemseditor.__file__)
    for excluded in NOT_IMPORTED:
        short = excluded.rsplit('.', 1)[1]
        pattern = re.compile(
            rf'^\s*(from\s+{re.escape(excluded)}\b|import\s+{re.escape(excluded)}\b'
            rf'|from\s+(cuemseditor|\.)\s+import\s+.*\b{short}\b|from\s+\.{short}\b)',
            re.M)
        for name in os.listdir(src):
            if name.endswith('.py'):
                with open(os.path.join(src, name), encoding='utf-8') as fh:
                    assert not pattern.search(fh.read()), f'{name} imports {excluded}'


@pytest.mark.parametrize('name', MODULES)
def test_module_imports(name):
    importlib.import_module(name)
