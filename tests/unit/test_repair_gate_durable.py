# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The repair gate outlives the connection (002 US1, FR-005 to FR-011; Q1, Q4).

The gate is per project (``server.repair_gates``), each session acknowledges
for itself, and a project the process holds no state for is re-derived from
the file on disk. Runs the real ``CuemsWsUser`` handlers against a temporary
library through the real ``CuemsDBProject``; only the server is a stub.

The library, the fixture variants and the helpers come from
``tests/test_document_load_report.py``.
"""

import asyncio
import concurrent.futures
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from test_document_load_report import (  # noqa: F401  (lib is a fixture)
    SCRIPT_ID,
    _ack,
    _drain,
    _open,
    _run,
    _save,
    _session,
    _sha256,
    _trash_copies,
    _write_variant,
    lib,
)

import cuemseditor.CuemsWsUser as ws_user
from cuemseditor.CuemsWsUser import CuemsWsUser


def _make_server(lib):
    """A server stub as ``CuemsWsServer.__init__`` leaves its session tables."""
    server = MagicMock()
    server.users = {}
    server.sessions = {}
    server.repair_gates = {}
    server.file_locks = {}
    server.event_loop = asyncio.new_event_loop()
    server.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    server.db.project = lib.project
    server.notify_others_list_changes = AsyncMock()
    server.notify_others_same_project = AsyncMock()
    return server


def _close(server):
    server.executor.shutdown(wait=True)
    server.event_loop.close()


@pytest.fixture
def server(lib):
    server = _make_server(lib)
    yield server
    _close(server)


def _reconnect(server, session):
    """A new connection that re-uses *session*'s ``session_id`` (``check_session``)."""
    again = CuemsWsUser(server, MagicMock())
    again.session_id = session.session_id
    server.sessions[again.session_id]['ws'] = id(again.websocket)
    return again


def _refusal(report_id, reason='unacknowledged'):
    return {'type': 'repair_save_refused', 'value': {
        'project_uuid': SCRIPT_ID, 'report_id': report_id, 'reason': reason}}


# ─── US1 #1: a reconnect keeps the gate (FR-005, written first) ──────────


def test_a_reconnect_with_the_same_session_id_keeps_the_gate(lib, server):
    _write_variant(lib.script, 'repairable')
    before = _sha256(lib.script)
    a = _session(server)
    report_id = _open(server, a)[1]['value']['report_id']

    frames = _save(server, _reconnect(server, a))

    assert frames == [_refusal(report_id)]
    assert _sha256(lib.script) == before
    assert _trash_copies(lib) == []


# ─── US1 #2, #5: re-acknowledge after a reconnect, one preserve ──────────


def test_a_reacknowledge_after_reconnect_is_echoed_then_the_save_preserves(lib, server):
    _write_variant(lib.script, 'repairable')
    with open(lib.script, 'rb') as fh:
        original = fh.read()
    a = _session(server)
    report_id = _open(server, a)[1]['value']['report_id']
    again = _reconnect(server, a)

    assert _ack(server, again, report_id) == [{'type': 'repair_acknowledge', 'value': {
        'project_uuid': SCRIPT_ID, 'report_id': report_id}}]
    first = _save(server, again)
    second = _save(server, again)

    assert first[0] == {'type': 'project_save', 'value': SCRIPT_ID}
    assert second[0] == {'type': 'project_save', 'value': SCRIPT_ID}
    copies = _trash_copies(lib)
    assert len(copies) == 1                                 # one preserve per stale file
    with open(copies[0], 'rb') as fh:
        assert fh.read() == original


# ─── US1 #3: a session that never loaded the project ─────────────────────


def test_a_session_that_never_loaded_the_project_is_refused(lib, server):
    _write_variant(lib.script, 'repairable')
    before = _sha256(lib.script)
    a = _session(server)
    report_id = _open(server, a)[1]['value']['report_id']
    _ack(server, a, report_id)                               # a's acknowledgment, not b's

    frames = _save(server, _session(server))

    assert frames == [_refusal(report_id)]
    assert _sha256(lib.script) == before
    assert _trash_copies(lib) == []


# ─── US1 #4: an editor restart (FR-009) ──────────────────────────────────


def test_after_an_editor_restart_the_gate_is_rederived_from_the_file(lib, server):
    _write_variant(lib.script, 'repairable')
    before = _sha256(lib.script)
    a = _session(server)
    _open(server, a)

    restarted = _make_server(lib)                            # a new process: empty tables
    try:
        tab = _session(restarted)
        tab.session_id = a.session_id                        # the tab reconnects with its old id
        frames = _save(restarted, tab)
    finally:
        _close(restarted)

    assert [f['type'] for f in frames] == ['repair_save_refused']
    assert frames[0]['value']['reason'] == 'unacknowledged'
    assert _sha256(lib.script) == before
    assert _trash_copies(lib) == []


# ─── FR-009a: a file changed after acknowledgment ────────────────────────


def test_a_file_changed_after_acknowledgment_gets_a_new_report(lib, server):
    _write_variant(lib.script, 'repairable')
    a = _session(server)
    report_id = _open(server, a)[1]['value']['report_id']
    _ack(server, a, report_id)

    with open(lib.script, 'a', encoding='utf-8') as fh:      # other bytes, still repaired
        fh.write('\n<!-- edited by hand -->\n')
    before = _sha256(lib.script)
    frames = _save(server, a)

    assert [f['type'] for f in frames] == ['repair_save_refused']
    assert frames[0]['value']['reason'] == 'unacknowledged'
    assert frames[0]['value']['report_id'] != report_id
    assert _sha256(lib.script) == before
    assert _trash_copies(lib) == []


# ─── Q4: a clean project gains no step ───────────────────────────────────


def test_a_clean_project_save_adds_no_load(lib, server):
    _write_variant(lib.script, 'clean')
    a = _session(server)
    _open(server, a)

    with patch.object(lib.project, 'inspect', wraps=lib.project.inspect) as inspect, \
         patch.object(ws_user, 'bytes_md5', wraps=ws_user.bytes_md5) as md5:
        frames = _save(server, _reconnect(server, a))

    assert frames[0] == {'type': 'project_save', 'value': SCRIPT_ID}
    inspect.assert_not_called()
    md5.assert_not_called()
    assert _trash_copies(lib) == []


# ─── FR-010 and R8.5 ─────────────────────────────────────────────────────


def test_unload_drops_this_sessions_acknowledgment(lib, server):
    _write_variant(lib.script, 'repairable')
    before = _sha256(lib.script)
    a = _session(server)
    report_id = _open(server, a)[1]['value']['report_id']
    _ack(server, a, report_id)

    with patch.object(CuemsWsUser, 'comunicate_with_engine', AsyncMock(return_value='OK')):
        _run(server, a.project_unload('project_unload'))
    assert _drain(a) == [{'type': 'project_unload', 'value': 'OK'}]
    frames = _save(server, a)

    assert [f['type'] for f in frames] == ['repair_save_refused']
    assert _sha256(lib.script) == before


def test_project_load_by_another_session_keeps_the_report_id(lib, server):
    _write_variant(lib.script, 'repairable')
    a, b = _session(server), _session(server)

    first = _open(server, a)[1]['value']['report_id']
    second = _open(server, b)[1]['value']['report_id']

    assert second == first
