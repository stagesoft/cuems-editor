# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Stale media values are reported at load and acknowledged before a save (002 US6, FR-043 to FR-046).

At load the editor compares each media cue's PRESENT stored values (duration,
pixel size, file size, md5) with its library row, on the loaded object. A
value that differs, or that the cue may not carry, is a ``media_repairs``
entry in ``document_load_report``, under the same ``report_id`` and the same
acknowledgment as a script repair (Q6, Q7). A merely missing value is not
stale (Q6), and neither is an orphan. A row that changes while the report is
outstanding re-derives it (FR-045).

The library: ``tests/test_media_values.py``'s rows. The script on disk is the
fixture with every media duration equal to its row's and no stored values (a
pre-rc15 project), then edited per test. The session stub:
``tests/test_repair_gate_durable.py``'s.
"""

import json
import os
import shutil

import pytest

from cuemseditor.CuemsDBModel import Media, database
from cuemsutils.cues import CuemsScript
from cuemsutils.tools.CTimecode import CTimecode

from test_document_load_report import _drain, _run, _session, _sha256
from test_media_values import (
    AUDIO_CUE, OTHER_CUE, ROWS, SCRIPT_ID, VIDEO_CUE, cues, load, make_media_lib, stored, wire)
from test_repair_gate_durable import _close, _make_server

ROW_DURATION = '00:01:00.000'


def write_aligned(lib, edit=None):
    """The fixture with each media duration equal to its row's, edited by *edit*, saved to disk."""
    script = load(lib)
    for cue_id in (VIDEO_CUE, AUDIO_CUE, OTHER_CUE):
        cues(script)[cue_id]['Media'].duration = ROW_DURATION
    if edit:
        edit(cues(script))
    script.save(lib.script)


@pytest.fixture
def mlib(tmp_path):
    lib = make_media_lib(str(tmp_path))
    write_aligned(lib)
    yield lib
    database.close()


@pytest.fixture
def server(mlib):
    server = _make_server(mlib)
    yield server
    _close(server)


def _open(server, session):
    _run(server, session.send_project(SCRIPT_ID, 'project_load'))
    frames = _drain(session)
    assert [f['type'] for f in frames] == ['project', 'document_load_report']
    return frames[1]['value']


def _save(server, session, lib):
    payload = json.loads(json.dumps(lib.project.load(SCRIPT_ID)))
    _run(server, session.received_project(payload, 'project_save'))
    return _drain(session)


def _ack(server, session, report_id):
    _run(server, session.repair_acknowledge({'project_uuid': SCRIPT_ID, 'report_id': report_id},
                                            'repair_acknowledge'))
    return _drain(session)


def _trash_copies(lib):
    trash = os.path.join(lib.root, 'trash', 'projects')
    return [os.path.join(trash, f) for f in os.listdir(trash)]


# ─── US6 #5: a stale duration ────────────────────────────────────────────


def test_a_stale_duration_is_a_media_repair_and_requires_acknowledgment(mlib, server):
    write_aligned(mlib, lambda c: setattr(c[AUDIO_CUE]['Media'], 'duration', '00:00:30.000'))
    with open(mlib.script, 'rb') as fh:
        original = fh.read()
    session = _session(server)

    report = _open(server, session)

    assert report['media_repairs'] == [{
        'cue_id': AUDIO_CUE, 'file_name': 'file.ext', 'field': 'duration',
        'stored': str(CTimecode('00:00:30.000')), 'current': str(CTimecode(ROW_DURATION))}]
    assert report['acknowledgment_required'] is True
    assert report['outcome'] == 'clean' and report['repairs'] == []
    assert report['file_differs_from_loaded'] is True

    refused = _save(server, session, mlib)
    assert [f['type'] for f in refused] == ['repair_save_refused']
    assert refused[0]['value']['report_id'] == report['report_id']
    assert _trash_copies(mlib) == []

    _ack(server, session, report['report_id'])
    saved = _save(server, session, mlib)

    assert saved[0] == {'type': 'project_save', 'value': SCRIPT_ID}
    [copy] = _trash_copies(mlib)
    with open(copy, 'rb') as fh:
        assert fh.read() == original
    assert cues(load(mlib))[AUDIO_CUE]['Media'].duration == CTimecode(ROW_DURATION)


def test_pixel_size_on_an_audio_cue_is_a_media_repair_with_current_null(mlib, server):
    def edit(c):
        c[AUDIO_CUE]['Media'].pixel_width = 640
        c[AUDIO_CUE]['Media'].pixel_height = 480
    write_aligned(mlib, edit)

    report = _open(server, _session(server))

    assert report['media_repairs'] == [{
        'cue_id': AUDIO_CUE, 'file_name': 'file.ext', 'field': 'pixel_size',
        'stored': '640x480', 'current': None}]
    assert report['acknowledgment_required'] is True


# ─── US6 #6, Q6: missing is not stale ────────────────────────────────────


def test_missing_values_are_not_stale(mlib, server):
    session = _session(server)

    report = _open(server, session)

    assert report['media_repairs'] == []
    assert report['acknowledgment_required'] is False
    assert report['file_differs_from_loaded'] is False
    saved = _save(server, session, mlib)
    assert saved[0] == {'type': 'project_save', 'value': SCRIPT_ID}
    assert _trash_copies(mlib) == []
    assert stored(cues(load(mlib))[VIDEO_CUE]) == {k: v for k, v in ROWS['file_video.ext'].items()
                                                   if k in ('pixel_width', 'pixel_height',
                                                            'file_size', 'file_md5')}


def test_an_orphan_is_not_stale(mlib, server):
    def edit(c):
        c[AUDIO_CUE]['Media'].file_name = 'orphan.wav'     # no library row
        c[AUDIO_CUE]['Media'].file_size = 77
        c[AUDIO_CUE]['Media'].duration = '00:00:05.000'
    write_aligned(mlib, edit)

    report = _open(server, _session(server))

    assert report['media_repairs'] == []
    assert report['acknowledgment_required'] is False


def test_an_orphan_keeps_its_values_on_save(mlib):
    """FR-041, on the save path's fill: an orphan's valid values stay as they are.

    Measured at the fill, not through ``project_save``: ``update`` first
    relinks the project's media (``update_media_relations``), which needs a
    ``Media`` row for every file the script names, so a project naming an
    orphan is refused before the fill matters (an existing constraint, not
    this feature's).
    """
    from cuemseditor.CuemsDBProject import (
        db_dimensions_resolver, db_duration_resolver, fix_media_durations_in_contents)

    script = load(mlib)
    media = cues(script)[VIDEO_CUE]['Media']
    media.file_name = 'orphan.mov'
    media.pixel_width, media.pixel_height, media.file_size = 640, 480, 77
    media.file_md5 = 'd' * 32

    stats = fix_media_durations_in_contents(script.cuelist.contents, db_duration_resolver,
                                            db_dimensions_resolver)

    assert stats.orphans == ['orphan.mov']
    assert stored(cues(script)[VIDEO_CUE]) == {'pixel_width': 640, 'pixel_height': 480,
                                               'file_size': 77, 'file_md5': 'd' * 32}


# ─── Edge cases, FR-044, FR-045 ──────────────────────────────────────────


def test_an_invalid_row_value_is_a_media_repair_with_current_null(tmp_path):
    rows = dict(ROWS, **{'file.ext': dict(ROWS['file.ext'], file_size=0)})   # a pre-migration 0
    lib = make_media_lib(str(tmp_path), rows=rows)
    server = _make_server(lib)
    try:
        write_aligned(lib, lambda c: setattr(c[AUDIO_CUE]['Media'], 'file_size', 500))
        session = _session(server)

        report = _open(server, session)
        assert report['media_repairs'] == [{
            'cue_id': AUDIO_CUE, 'file_name': 'file.ext', 'field': 'file_size',
            'stored': '500', 'current': None}]
        _ack(server, session, report['report_id'])
        saved = _save(server, session, lib)
    finally:
        _close(server)
        database.close()

    assert saved[0] == {'type': 'project_save', 'value': SCRIPT_ID}
    assert 'file_size' not in cues(load(lib))[AUDIO_CUE]['Media']


def test_a_row_change_after_acknowledgment_gets_a_new_report(mlib, server):
    write_aligned(mlib, lambda c: setattr(c[AUDIO_CUE]['Media'], 'duration', '00:00:30.000'))
    before = _sha256(mlib.script)
    session = _session(server)
    report = _open(server, session)
    _ack(server, session, report['report_id'])

    Media.update(file_size=501).where(Media.unix_name == 'file.ext').execute()   # a re-upload, say
    frames = _save(server, session, mlib)

    assert [f['type'] for f in frames] == ['repair_save_refused']
    assert frames[0]['value']['reason'] == 'unacknowledged'
    assert frames[0]['value']['report_id'] != report['report_id']
    assert _sha256(mlib.script) == before


def test_media_repairs_is_always_present(mlib, server):
    report = _open(server, _session(server))

    assert 'media_repairs' in report and report['media_repairs'] == []
    assert report['acknowledgment_required'] is False


def test_an_absent_stored_value_reads_as_missing_not_as_unset(mlib):
    """X-4 (cuems-utils 014 `Media.DECLARED_DEFAULTS`): a v2 script without
    ``pixel_width`` / ``file_size`` reads them as absent (``key in media`` is false) and the attribute
    as ``None``, never the library's ``Unset`` marker. The comparison above relies on that to treat a
    merely missing value as "not stale" (Q6). Asserted on the installed library, loaded through
    ``CuemsScript.load`` as the editor does; measured at cuemsutils ``4b336cd`` and ``387598e``."""
    write_aligned(mlib)
    script = load(mlib)
    media = cues(script)[VIDEO_CUE]['Media']
    for key in ('pixel_width', 'pixel_height', 'file_size', 'file_md5'):
        assert key not in media
        assert getattr(media, key) is None
