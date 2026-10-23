# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The shape of ``tests/`` (003, FR-035), the one cuems-utils uses.

::

    tests/
      conftest.py     fixtures; marks each test unit / integration / contract from its directory
      support/        shared helpers; paths.py holds DATA_DIR, the one place the data path is written
      data/           every non-test data file: fixtures, the protocol reference, golden frames
      unit/           pure logic, every socket / JACK / subprocess mocked, xdist-safe
      integration/    binds or connects a real socket, starts a real subprocess, touches JACK/ALSA,
                      or sleeps >= 0.5 s for correctness
      contract/       repository and packaging invariants (public surface, imports, changelogs, layout)
      packaging/      the bookworm build script

A test cannot be mislabelled by forgetting a decorator: the mark comes from the directory.
"""
import pathlib

TESTS = pathlib.Path(__file__).resolve().parent.parent
MARKED = ('unit', 'integration', 'contract')
ALLOWED_AT_ROOT = {'conftest.py', 'README.md', '__pycache__', '.pytest_cache'}
ALLOWED_DIRS = {'support', 'data', 'unit', 'integration', 'contract', 'packaging'}


def _test_files():
    return sorted(p for p in TESTS.rglob('test_*.py') if '__pycache__' not in p.parts and 'data' not in p.parts)


def test_no_test_module_sits_at_the_root_of_tests():
    assert sorted(p.name for p in TESTS.glob('test_*.py')) == []


def test_tests_holds_only_the_known_directories_and_files():
    extra = sorted(p.name for p in TESTS.iterdir() if p.name not in ALLOWED_AT_ROOT | ALLOWED_DIRS)
    assert extra == []


def test_every_test_module_lives_in_exactly_one_marked_directory():
    stray = [str(p.relative_to(TESTS)) for p in _test_files() if p.relative_to(TESTS).parts[0] not in MARKED]
    assert stray == []


def test_the_data_directory_holds_no_test_module():
    assert sorted(str(p.relative_to(TESTS)) for p in (TESTS / 'data').rglob('test_*.py')) == []


def test_every_collected_test_carries_exactly_one_directory_mark(request):
    items = [i for i in request.session.items]
    assert items, 'nothing collected'
    for item in items:
        marks = {m.name for m in item.iter_markers() if m.name in MARKED}
        top = pathlib.Path(str(item.path)).relative_to(TESTS).parts[0]
        assert marks == {top}, f'{item.nodeid}: {marks} (directory {top})'


def test_the_integration_directory_is_not_empty():
    """CI runs an integration job; pytest exits 5 when it collects nothing."""
    assert list((TESTS / 'integration').glob('test_*.py'))
