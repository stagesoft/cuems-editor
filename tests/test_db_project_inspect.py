# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``CuemsDBProject.open`` and ``inspect`` return the md5 of the script's bytes (002 T007, T008).

The repair gate keys its re-derivation on that md5 (FR-009a). ``inspect`` is
the gate's view of the file on disk and must write nothing.
"""

import hashlib

import pytest

from cuemseditor.CuemsErrors import DocumentLoadFailed

from test_document_load_report import SCRIPT_ID, _sha256, _write_variant, lib  # noqa: F401  (fixture)


def _md5(path):
    with open(path, 'rb') as fh:
        return hashlib.md5(fh.read()).hexdigest()


@pytest.mark.parametrize('kind', ['clean', 'repairable'])
def test_open_returns_the_md5_of_the_files_bytes(lib, kind):
    _write_variant(lib.script, kind)

    value, report, script_md5 = lib.project.open(SCRIPT_ID)

    assert script_md5 == _md5(lib.script)
    assert value['CuemsScript']['id'] == SCRIPT_ID
    assert report.outcome.value == ('clean' if kind == 'clean' else 'repaired')


@pytest.mark.parametrize('kind', ['clean', 'repairable'])
def test_inspect_returns_the_report_and_md5_and_writes_nothing(lib, kind):
    _write_variant(lib.script, kind)
    before = _sha256(lib.script)

    report, script_md5 = lib.project.inspect(SCRIPT_ID)

    assert script_md5 == _md5(lib.script)
    assert report.outcome.value == ('clean' if kind == 'clean' else 'repaired')
    assert _sha256(lib.script) == before


@pytest.mark.parametrize('call', ['open', 'inspect'])
def test_an_unrepairable_file_is_document_load_failed_from_both(lib, call):
    _write_variant(lib.script, 'unrepairable')
    before = _sha256(lib.script)

    with pytest.raises(DocumentLoadFailed):
        getattr(lib.project, call)(SCRIPT_ID)

    assert _sha256(lib.script) == before
