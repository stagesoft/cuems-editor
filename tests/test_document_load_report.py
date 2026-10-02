# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The operator is told about a repair, and a repaired file is not overwritten unseen.

FR-019–FR-022, FR-021a, contracts/ws-messages.md, data-model.md. Runs the real
session handlers (``CuemsWsUser``) against a temporary library through the
real ``CuemsDBProject``; only the server around them is a stub.

Fixtures are derived from ``tests/fixtures/script_minimal_013.xml``, saved by
the library as a current (``doc_version="2"``) document so it loads ``clean``,
then edited as text:

* ``repairable`` — one cue's ``target`` names no cue (``target_resolves``,
  repairable: cleared on load and listed);
* ``unrepairable`` — the ActionCue's ``action_target`` names no cue
  (``action_target_resolves``, unrepairable);
* ``too_new`` — ``doc_version="99"``.
"""

import asyncio
import concurrent.futures
import hashlib
import json
import os
import shutil
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Media, Project, ProjectMedia, database
from cuemseditor.CuemsDBProject import CuemsDBProject
from cuemseditor.CuemsWsUser import CuemsWsUser
from cuemsutils.cues import CuemsScript
from cuemsutils.helpers import new_datetime, new_uuid

HERE = os.path.dirname(__file__)
FIXTURE_013 = os.path.join(HERE, 'fixtures', 'script_minimal_013.xml')
SCRIPT_ID = 'ddba3000-7894-4a60-a6c1-e73b9bbed8c0'
ACTION_TARGET = '1f301cf8-dd03-4b40-ac17-ef0e5e7988be'
NOWHERE = '0b0b0b0b-0000-4000-8000-000000000000'
AUDIO_CUE = 'bb391e70-e65e-47ca-8b29-5a7076bbd250'
NEXT_STEPS = ['restore_from_conversion_backup', 'correct_field_by_hand', 'remove_document']


def _sha256(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _write_variant(path, kind):
    script, _report = CuemsScript.load_with_report(FIXTURE_013)
    script.save(path)
    if kind == 'clean':
        return
    with open(path, encoding='utf-8') as fh:
        text = fh.read()
    if kind == 'repairable':
        marker = f'<id>{AUDIO_CUE}</id>'
        head, tail = text.split(marker, 1)
        tail = tail.replace('<target />', f'<target>{NOWHERE}</target>', 1)
        text = head + marker + tail
    elif kind == 'unrepairable':
        text = text.replace(f'<action_target>{ACTION_TARGET}</action_target>',
                            f'<action_target>{NOWHERE}</action_target>', 1)
    elif kind == 'too_new':
        text = text.replace('doc_version="2"', 'doc_version="99"', 1)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(text)


class Lib:
    def __init__(self, root):
        self.root = root
        self.script = os.path.join(root, 'projects', 'minimal', 'script.xml')
        self.trash = os.path.join(root, 'trash', 'projects')


@pytest.fixture
def lib(tmp_path):
    root = str(tmp_path)
    for sub in ('media', 'trash/projects', 'trash/media', 'tmp', 'projects/minimal'):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    database.init(os.path.join(root, 'project-manager.db'))
    database.connect()
    database.create_tables([Project, Media, ProjectMedia], safe=True)
    Project.create(uuid=SCRIPT_ID, name='Test Script', unix_name='minimal',
                   created=new_datetime(), modified=new_datetime(), in_trash=False)
    for name in ('file.ext', 'file_video.ext'):
        Media.create(uuid=str(new_uuid()), name=name, unix_name=name, created=new_datetime(),
                     modified=new_datetime(), duration='00:01:00.000', media_type='AUDIO',
                     in_trash=False)
    settings = get_settings()
    settings['library_path'] = root
    settings['tmp_path'] = os.path.join(root, 'tmp')
    ctx = Lib(root)
    ctx.project = CuemsDBProject(settings, database)
    yield ctx
    database.close()


@pytest.fixture
def server(lib):
    server = MagicMock()
    server.users = {}
    server.sessions = {}
    server.event_loop = asyncio.new_event_loop()
    server.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    server.db.project = lib.project
    server.notify_others_list_changes = AsyncMock()
    server.notify_others_same_project = AsyncMock()
    yield server
    server.executor.shutdown(wait=True)
    server.event_loop.close()


def _session(server):
    """A session as ``CuemsWsServer.register`` leaves it: with a session id."""
    session = CuemsWsUser(server, MagicMock())
    session.session_id = str(new_uuid())
    server.sessions[session.session_id] = {'ws': id(session.websocket)}
    return session


def _run(server, coro):
    return server.event_loop.run_until_complete(coro)


def _drain(session):
    out = []
    while not session.outgoing.empty():
        out.append(json.loads(session.outgoing.get_nowait()))
    return out


def _open(server, session):
    _run(server, session.send_project(SCRIPT_ID, 'project_load'))
    return _drain(session)


# ─── document_load_report (T048) ─────────────────────────────────────────


def test_a_clean_open_still_sends_a_report(lib, server):
    _write_variant(lib.script, 'clean')
    session = _session(server)

    frames = _open(server, session)

    assert [f['type'] for f in frames] == ['project', 'document_load_report']
    report = frames[1]['value']
    assert report['outcome'] == 'clean'
    assert report['file_differs_from_loaded'] is False
    assert report['repairs'] == [] and report['conversions'] == []
    assert report['project_uuid'] == SCRIPT_ID and report['report_id']


def test_a_repaired_open_reports_the_repair_and_writes_nothing(lib, server):
    _write_variant(lib.script, 'repairable')
    before = _sha256(lib.script)
    session = _session(server)

    first = _open(server, session)[1]['value']
    second = _open(server, session)[1]['value']

    assert _sha256(lib.script) == before
    assert first['outcome'] == 'repaired'
    assert first['file_differs_from_loaded'] is True
    assert first['document'] == lib.script
    assert first['repairs'] == [{
        'field_path': f'{AUDIO_CUE}/target',
        'previous_value': NOWHERE,
        'substituted_value': None,
        'rule_name': 'target_resolves',
    }]
    assert second['repairs'] == first['repairs']           # a second open reports it again
    assert second['report_id'] != first['report_id']


def test_a_converted_open_reports_the_conversion(lib, server):
    shutil.copy(FIXTURE_013, lib.script)                   # no doc_version: version 1
    report = _open(server, _session(server))[1]['value']
    assert report['outcome'] == 'converted'
    assert report['file_differs_from_loaded'] is True
    assert report['conversions'][0]['from_version'] == 1
    assert report['conversions'][0]['to_version'] == 2
    assert isinstance(report['conversions'][0]['dropped_elements'], list)


@pytest.mark.parametrize('kind, cue_id, field', [
    ('unrepairable', '58763af8-462c-4831-bd08-d3e978dc4a0a', 'action_target'),
    ('too_new', None, None),
])
def test_an_unrepairable_open_is_document_load_failed(lib, server, kind, cue_id, field):
    _write_variant(lib.script, kind)
    before = _sha256(lib.script)
    session = _session(server)

    frames = _open(server, session)

    assert [f['type'] for f in frames] == ['document_load_failed']
    value = frames[0]['value']
    assert value['project_uuid'] == SCRIPT_ID
    assert value['document'] == lib.script
    assert value['cue_id'] == cue_id
    assert value['field'] == field
    assert value['message']
    assert value['next_steps'] == NEXT_STEPS
    assert _sha256(lib.script) == before

    _run(server, session.list_project('project_list'))     # the session is still usable
    assert _drain(session)[0]['type'] == 'project_list'


# ─── the save gate (T049) ────────────────────────────────────────────────


def _save(server, session):
    payload = json.loads(json.dumps(session_value(server)))
    _run(server, session.received_project(payload, 'project_save'))
    return _drain(session)


def session_value(server):
    return server.db.project.load(SCRIPT_ID)


def _ack(server, session, report_id):
    _run(server, session.repair_acknowledge({'project_uuid': SCRIPT_ID, 'report_id': report_id}, 'repair_acknowledge'))
    return _drain(session)


def _trash_copies(lib):
    return [os.path.join(lib.trash, f) for f in os.listdir(lib.trash) if os.path.isfile(os.path.join(lib.trash, f))]


def test_save_before_acknowledge_is_refused_and_writes_nothing(lib, server):
    _write_variant(lib.script, 'repairable')
    before = _sha256(lib.script)
    session = _session(server)
    report_id = _open(server, session)[1]['value']['report_id']

    frames = _save(server, session)

    assert frames == [{'type': 'repair_save_refused', 'value': {
        'project_uuid': SCRIPT_ID, 'report_id': report_id, 'reason': 'unacknowledged'}}]
    assert _sha256(lib.script) == before
    assert _trash_copies(lib) == []


def test_after_acknowledge_the_original_is_in_trash_and_the_repair_is_saved(lib, server):
    _write_variant(lib.script, 'repairable')
    with open(lib.script, 'rb') as fh:
        original = fh.read()
    session = _session(server)
    report_id = _open(server, session)[1]['value']['report_id']

    assert _ack(server, session, report_id) == [{'type': 'repair_acknowledge', 'value': {
        'project_uuid': SCRIPT_ID, 'report_id': report_id}}]
    frames = _save(server, session)

    assert frames[0] == {'type': 'project_save', 'value': SCRIPT_ID}
    copies = _trash_copies(lib)
    assert len(copies) == 1
    assert 'minimal' in os.path.basename(copies[0])
    with open(copies[0], 'rb') as fh:
        assert fh.read() == original                       # byte-identical original
    saved, report = CuemsScript.load_with_report(lib.script)
    assert report.outcome.value == 'clean'                 # the repaired document is on disk


def test_another_sessions_acknowledgment_does_not_unlock_this_save(lib, server):
    _write_variant(lib.script, 'repairable')
    before = _sha256(lib.script)
    mine, theirs = _session(server), _session(server)
    mine_id = _open(server, mine)[1]['value']['report_id']
    theirs_id = _open(server, theirs)[1]['value']['report_id']

    _ack(server, theirs, theirs_id)
    refused = _ack(server, mine, theirs_id)                 # someone else's report id
    frames = _save(server, mine)

    assert refused[0]['type'] == 'repair_save_refused'
    assert frames[0]['type'] == 'repair_save_refused'
    assert frames[0]['value']['report_id'] == mine_id
    assert _sha256(lib.script) == before


def test_preserve_failure_refuses_and_does_not_save(lib, server):
    _write_variant(lib.script, 'repairable')
    before = _sha256(lib.script)
    session = _session(server)
    report_id = _open(server, session)[1]['value']['report_id']
    _ack(server, session, report_id)

    with patch('cuemseditor.CuemsDBProject.CopyMoveVersioned.move', side_effect=OSError('disk full')), \
         patch.object(CuemsScript, 'save') as save:
        frames = _save(server, session)

    assert frames == [{'type': 'repair_save_refused', 'value': {
        'project_uuid': SCRIPT_ID, 'report_id': report_id, 'reason': 'preserve_failed'}}]
    save.assert_not_called()
    assert _sha256(lib.script) == before


def test_a_clean_open_needs_no_acknowledgment(lib, server):
    _write_variant(lib.script, 'clean')
    session = _session(server)
    _open(server, session)

    frames = _save(server, session)

    assert frames[0] == {'type': 'project_save', 'value': SCRIPT_ID}
    assert _trash_copies(lib) == []


# ─── project_duplicate carries the source report (T054) ──────────────────


@pytest.mark.parametrize('kind, has_report', [('repairable', True), ('clean', False)])
def test_duplicate_reply_carries_the_source_report_when_not_clean(lib, server, kind, has_report):
    _write_variant(lib.script, kind)
    before = _sha256(lib.script)
    session = _session(server)

    _run(server, session.request_duplicate_project(SCRIPT_ID, 'project_duplicate'))
    frame = _drain(session)[0]

    assert frame['type'] == 'project_duplicate'
    assert frame['value']['uuid'] == SCRIPT_ID and frame['value']['new_uuid']
    assert ('report' in frame['value']) is has_report
    if has_report:
        assert frame['value']['report']['outcome'] == 'repaired'
        assert frame['value']['report']['project_uuid'] == SCRIPT_ID
    assert _sha256(lib.script) == before                    # the source is not overwritten
