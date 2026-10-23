# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The media modules import each other's normalisers through a leaf (003, FR-021).

The release line's ``CuemsDBProject`` imported ``INDEX_STALE`` and more from
``CuemsDBMedia``, while the refactor's ``CuemsDBMedia`` imported ``_md5`` from
``CuemsDBProject``: a circular import that the trial merge hit first (17 test
modules failed at collection). The shared normalisers live in
``cuemseditor.media_values``, which imports neither module, and each module
imports on its own in a fresh interpreter.
"""
from support.paths import DATA_DIR, PACKAGE_DIR, ROOT, SIBLINGS_DIR, SPECS_DIR
import os
import subprocess
import sys

import pytest

SRC = str(ROOT / 'src')


def _run(code):
    """Run *code* in a fresh interpreter with ``src/`` first on the path."""
    prefix = f'import sys; sys.path.insert(0, {SRC!r}); '
    return subprocess.run([sys.executable, '-c', prefix + code], capture_output=True, text=True)


def _import_alone(module):
    return _run(f'import {module}')


@pytest.mark.parametrize('module', [
    'cuemseditor.media_values',
    'cuemseditor.CuemsDBMedia',
    'cuemseditor.CuemsDBProject',
])
def test_each_module_imports_alone(module):
    done = _import_alone(module)
    assert done.returncode == 0, done.stderr[-600:]


def test_the_leaf_imports_neither_media_module():
    done = _import_alone('cuemseditor.media_values')
    assert done.returncode == 0, done.stderr[-600:]
    code = ("import sys, cuemseditor.media_values; "
            "print([m for m in ('cuemseditor.CuemsDBMedia', 'cuemseditor.CuemsDBProject') if m in sys.modules])")
    out = _run(code)
    assert out.stdout.strip() == '[]', out.stdout


def test_the_normalisers_behave():
    from cuemseditor.media_values import _md5, _positive_int, _valid
    assert _md5('A' * 32) == 'a' * 32
    assert _md5('a' * 31) is None and _md5('g' * 32) is None and _md5(None) is None
    assert _positive_int('12') == 12 and _positive_int(0) is None and _positive_int(True) is None
    assert _valid('file_md5', 'B' * 32) == 'b' * 32 and _valid('file_size', 5) == 5
