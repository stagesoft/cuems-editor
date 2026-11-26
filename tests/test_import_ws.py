# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Project import from a zip (ClickUp 1amfwm7kcjp), the WebSocket side: the
guard ``project_import`` on the user session (D3), the one import slot and its
ticket, the ``/upload`` session of an import (D1, D2), the later checks (D4)
and the media upload that must stay as it is.

Design: cuems-RELATIONS Plans/2026-11-24-project-import-from-zip.md (Spec
rev 3), step 1, tests (15) to (18). The interface these tests assume where the
plan names none is listed once, at the top of ``tests/test_import.py``. Until
step 2 lands they fail on the missing ``CuemsWsServer.ImportSlot``,
``CuemsWsUser.request_import_project`` / ``import_refusal`` or
``cuemseditor.CuemsProjectImport``; test (18) is a regression guard and
passes before and after.
"""
import asyncio
import json
import os
import re
import subprocess
import threading
import time
import types
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest
import websockets as ws

from cuemsutils.tools import media_sidecars as ms

import cuemseditor.CuemsDBMedia as m
import cuemseditor.CuemsDBProject as p
import cuemseditor.CuemsWsServer as srv
import cuemseditor.CuemsWsUser as wsu
from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Project
from cuemseditor.CuemsUpload import CuemsUpload

from test_import import (  # noqa: F401  (env, disk, zips, _fresh_marks are fixtures)
    GIB, I1, I2, I3, I4, I5, I6, I7, I8A, MEDIA, TOP, _fresh_marks, _imp, disk, env,
    export_entries, i9_parts, md5, zips)

TICKET = re.compile(r'[0-9a-f]{32}')


# ---------------------------------------------------------------------------
# fakes: the browser's socket, the server, the session that asked
# ---------------------------------------------------------------------------

CLOSE = object()


class FakeSocket:
    """The ``/upload`` socket as the editor sees it: ``recv`` hands out what the
    test queued (``CLOSE`` closes it), ``send`` records each frame with the
    monotonic time it was sent."""

    def __init__(self):
        self.inbox = asyncio.Queue()
        self.sent = []
        self.closed = False

    def put(self, *items):
        for item in items:
            self.inbox.put_nowait(item)

    async def recv(self, *a, **kw):
        if self.closed:
            raise ws.exceptions.ConnectionClosedOK(None, None)
        item = await self.inbox.get()
        if item is CLOSE:
            self.closed = True
            raise ws.exceptions.ConnectionClosedOK(None, None)
        return item

    async def send(self, message):
        if self.closed:
            raise ws.exceptions.ConnectionClosedOK(None, None)
        self.sent.append((time.monotonic(), json.loads(message)))

    async def close(self, *a, **kw):
        self.closed = True
        self.inbox.put_nowait(CLOSE)

    def frames(self):
        return [f for _, f in self.sent]

    async def wait(self, pred, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for frame in self.frames():
                if pred(frame):
                    return frame
            await asyncio.sleep(0.01)
        raise AssertionError(f'no such frame within {timeout} s; last: {self.frames()[-5:]}')


async def until(pred, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if pred():
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f'not true within {timeout} s')


class FakeServer:
    """What ``CuemsUpload`` and the import session use of ``CuemsWsServer``."""

    def __init__(self, env, loop, executor, slot=True):
        self.settings_dict = env.settings
        self.db = env.db
        self.event_loop = loop
        self.executor = executor
        self.users = {}
        self.list_updates = []
        self.engine_words = ['none']
        self.engine_requests = []
        self.engine_communicator = types.SimpleNamespace(send_request=self._engine)
        if slot:
            self.import_slot = srv.ImportSlot()

    async def notify_others_list_changes(self, calling_user, list_type):
        self.list_updates.append((calling_user, list_type))

    async def _engine(self, command):
        self.engine_requests.append(command)
        word = self.engine_words.pop(0) if len(self.engine_words) > 1 else self.engine_words[0]
        return {'action_uuid': command['action_uuid'], 'type': 'project_status',
                'value': {'status': word}}


class FakeOwner:
    """The user session that passed the guard: its ``_engine_status`` answers
    the given words in turn, the last one for ever."""

    def __init__(self, *words):
        self.words = list(words) or ['none']
        self.calls = 0

    async def _engine_status(self):
        self.calls += 1
        return self.words.pop(0) if len(self.words) > 1 else self.words[0]


def first_frame(size, ticket=None, name='show_a.zip', kind='PROJECT'):
    value = {'name': name, 'size': size}
    if kind is not None:
        value['type'] = kind
    if ticket is not None:
        value['ticket'] = ticket
    return json.dumps({'action': 'upload', 'value': value})


def chunks(data, n=500_000):
    return [data[i:i + n] for i in range(0, len(data), n)]


def finished(digest):
    return json.dumps({'action': 'finished', 'value': digest})


def the_zip(env):
    return open(env.zip(export_entries()), 'rb').read()


def is_end(frame):
    return 'close' in frame or 'error' in frame


def run_upload(env, frames, owner=None, size=None, accept_loaded=False, take=True, slot=True,
               end=is_end, wait_s=60, after=None, prepare=None, free_slot=True):
    """One ``/upload`` session from the first frame to the end: the slot's ticket
    is taken for ``size`` (unless ``take`` is false) and put in the first frame
    by ``frames(ticket)``; ``prepare(server, ticket)`` runs before the frames are
    queued, ``after(server, socket, owner)`` once the session runs. Waits for an
    end frame (``end``), closes the socket and, when ``free_slot``, waits for the
    slot to be free. Returns (server, socket, owner)."""
    owner = owner or FakeOwner('none')

    async def main():
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(4)
        server = FakeServer(env, loop, executor, slot=slot)
        try:
            ticket = (server.import_slot.take(size, accept_loaded, owner)
                      if (slot and take) else None)
            if prepare:
                prepare(server, ticket)
            sock = FakeSocket()
            sock.put(*frames(ticket))
            task = asyncio.create_task(CuemsUpload(server, sock).message_handler())
            if after:
                await after(server, sock, owner)
            if end:
                await sock.wait(end, wait_s)
            sock.put(CLOSE)
            await asyncio.wait_for(task, wait_s)
            if slot and free_slot:
                await until(lambda: not server.import_slot.busy, wait_s)
        finally:
            executor.shutdown(wait=True)
        return server, sock

    server, sock = asyncio.run(main())
    return server, sock, owner


def errors(sock):
    return [f for f in sock.frames() if 'error' in f]


# ---------------------------------------------------------------------------
# (15) the guard: the rule of D3, the space, the slot, the ticket
# ---------------------------------------------------------------------------

def _user(server):
    user = object.__new__(wsu.CuemsWsUser)
    user.websocket = mock.Mock()
    user.outgoing = asyncio.Queue()
    user.incoming = asyncio.Queue()
    user.server = server
    return user


def _guard_server(tmp_path, slot=None):
    settings = get_settings()
    settings['library_path'] = str(tmp_path)
    settings['import_folder_name'] = '.import'
    os.makedirs(os.path.join(str(tmp_path), '.import'), mode=0o700, exist_ok=True)
    return types.SimpleNamespace(settings_dict=settings, import_slot=slot or srv.ImportSlot(),
                                 executor=None, event_loop=None, db=mock.Mock(), users={})


def guard(tmp_path, word, *accept, size=3 * GIB, value=None, server=None):
    """One ``project_import`` request against an engine that says ``word``.
    ``accept`` is the acceptance as sent: empty = the key is absent. Returns
    (frames, server, user, the status mock, warning lines)."""
    server = server or _guard_server(tmp_path)
    user = _user(server)
    value = {'size': size, 'name': 'show_a.zip'} if value is None else value

    async def run():
        server.event_loop = asyncio.get_running_loop()
        with mock.patch.object(user, '_engine_status', mock.AsyncMock(return_value=word)) as st, \
                mock.patch.object(wsu.Logger, 'warning') as warning:
            await user.request_import_project(value, 'project_import', *accept)
        frames = []
        while not user.outgoing.empty():
            frames.append(json.loads(await user.outgoing.get()))
        return frames, st, [str(c.args[0]) for c in warning.call_args_list]

    frames, st, warned = asyncio.run(run())
    return frames, server, user, st, warned


def _error(text):
    return {'type': 'error', 'action': 'project_import', 'value': text}


def _ticket_of(frames):
    assert len(frames) == 1 and frames[0]['type'] == 'project_import', frames
    value = frames[0]['value']
    assert set(value) == {'ticket', 'expires_s'} and value['expires_s'] == 60
    assert TICKET.fullmatch(value['ticket']), value
    return value['ticket']


class TestRule:
    @pytest.mark.parametrize('status, accept, want', [
        ('running', None, I3), ('running', True, I3),
        (None, None, I4), (None, True, I4),
        ('loaded', None, I5), ('loaded', False, I5), ('loaded', 'true', I5), ('loaded', 1, I5),
        ('loaded', True, None),
        ('none', None, None), ('none', True, None), ('none', False, None),
    ])
    def test_15_the_rule_of_D3_as_one_function(self, status, accept, want):
        assert wsu.import_refusal(status, accept) == want


class TestGuard:
    @pytest.mark.parametrize('accept', [(), (True,)])
    def test_15_running_is_refused_with_and_without_the_key(self, tmp_path, disk, accept):
        frames, server, user, st, warned = guard(tmp_path, 'running', *accept)
        assert frames == [_error(I3)]
        assert not server.import_slot.busy
        st.assert_awaited_once()
        assert f'import refused: {I3}' in warned

    @pytest.mark.parametrize('accept', [(), (True,)])
    def test_15_no_answer_is_refused_I4(self, tmp_path, disk, accept):
        frames, server, user, st, warned = guard(tmp_path, None, *accept)
        assert frames == [_error(I4)]
        assert not server.import_slot.busy
        assert f'import refused: {I4}' in warned

    @pytest.mark.parametrize('accept', [(), (False,), (None,), ('true',), (1,), ('yes',)])
    def test_15_loaded_without_a_real_true_is_refused_I5(self, tmp_path, disk, accept):
        frames, server, user, st, warned = guard(tmp_path, 'loaded', *accept)
        assert frames == [_error(I5)]
        assert not server.import_slot.busy
        assert f'import refused: {I5}' in warned

    def test_15_loaded_with_accept_loaded_true_gives_a_ticket_and_warns_once(self, tmp_path, disk):
        frames, server, user, st, warned = guard(tmp_path, 'loaded', True)
        ticket = _ticket_of(frames)
        assert warned.count('import accepted while a project is loaded') == 1
        record = server.import_slot.claim(ticket, 3 * GIB)
        assert record is not None and record.accept_loaded is True and record.owner is user
        st.assert_awaited_once()

    @pytest.mark.parametrize('accept', [(), (True,), (False,), (None,), ('true',)])
    def test_15_none_gives_a_ticket_whatever_the_key(self, tmp_path, disk, accept):
        frames, server, user, st, warned = guard(tmp_path, 'none', *accept)
        ticket = _ticket_of(frames)
        assert server.import_slot.busy
        assert not any('refused' in w or 'accepted while' in w for w in warned)
        record = server.import_slot.claim(ticket, 3 * GIB)
        assert record.accept_loaded is (accept == (True,)) and record.size == 3 * GIB

    def test_15_a_second_guard_while_the_slot_is_held_is_I1(self, tmp_path, disk):
        server = _guard_server(tmp_path)
        _ticket_of(guard(tmp_path, 'none', server=server)[0])
        frames, server, user, st, warned = guard(tmp_path, 'none', server=server)
        assert frames == [_error(I1)]
        assert f'import refused: {I1}' in warned

    def test_15_a_held_slot_answers_I1_even_when_the_space_would_not_fit(self, tmp_path, disk):
        """The running import's claim counts in the space check (R3), so the
        space was answered first: "No space", with the free room printed beside
        it, would send the operator deleting media when the answer is to wait
        (the export session's review of R3)."""
        server = _guard_server(tmp_path)
        _ticket_of(guard(tmp_path, 'none', server=server)[0])
        disk.total = 20 * GIB
        disk.free = 1 * GIB                          # nothing would fit
        frames, server, user, st, warned = guard(tmp_path, 'none', server=server)
        assert frames == [_error(I1)]
        assert f'import refused: {I1}' in warned

    def test_15_the_space_at_the_guard_at_its_edge(self, tmp_path, disk):
        disk.total = 20 * GIB
        size = 3 * GIB
        disk.free = size + 5 * GIB - 1
        folder = os.path.join(str(tmp_path), '.import')
        frames, server, user, st, warned = guard(tmp_path, 'none', size=size)
        assert frames == [_error(I2(size, disk.free, folder, 5 * GIB))]
        assert not server.import_slot.busy
        assert folder in disk.paths
        disk.free = size + 5 * GIB
        _ticket_of(guard(tmp_path, 'none', size=size)[0])

    @pytest.mark.parametrize('size', [0, -1, '12', 1.5, True, None])
    def test_15_a_size_that_is_not_a_positive_integer_is_refused(self, tmp_path, disk, size):
        frames, server, user, st, warned = guard(
            tmp_path, 'none', value={'size': size, 'name': 'show_a.zip'})
        assert len(frames) == 1 and frames[0]['type'] == 'error', frames
        assert frames[0]['action'] == 'project_import'
        assert not server.import_slot.busy


class TestSlot:
    @pytest.fixture
    def clock(self, monkeypatch):
        now = [1000.0]
        # raising=False: before step 2 the test, not its setup, reports the gap
        monkeypatch.setattr(srv, 'import_clock', lambda: now[0], raising=False)
        return now

    def test_15_a_ticket_is_used_once(self, clock):
        slot = srv.ImportSlot()
        owner = object()
        ticket = slot.take(100, False, owner)
        assert TICKET.fullmatch(ticket)
        record = slot.claim(ticket, 100)
        assert (record.ticket, record.size, record.accept_loaded, record.owner) == (
            ticket, 100, False, owner)
        assert slot.claim(ticket, 100) is None
        assert slot.busy                                     # held by the import that claimed it

    def test_15_an_unused_ticket_expires_after_60_s_and_frees_the_slot(self, clock):
        assert _imp().TICKET_TTL_S == 60
        slot = srv.ImportSlot()
        ticket = slot.take(100, False, object())
        with pytest.raises(Exception) as ei:
            slot.take(100, False, object())
        assert str(ei.value) == I1
        clock[0] += 61
        assert slot.claim(ticket, 100) is None
        assert not slot.busy
        assert TICKET.fullmatch(slot.take(100, False, object()))

    def test_15_an_unused_ticket_frees_the_slot_for_another_guard(self, clock):
        slot = srv.ImportSlot()
        slot.take(100, False, object())
        clock[0] += 61
        assert TICKET.fullmatch(slot.take(5, False, object()))   # no claim needed first

    def test_15_a_claimed_ticket_holds_the_slot_until_released(self, clock):
        slot = srv.ImportSlot()
        ticket = slot.take(100, False, object())
        slot.claim(ticket, 100)
        clock[0] += 3600
        with pytest.raises(Exception) as ei:
            slot.take(100, False, object())
        assert str(ei.value) == I1
        slot.release('0' * 32)                               # another ticket frees nothing
        assert slot.busy
        slot.release(ticket)
        assert not slot.busy

    def test_15_another_size_or_an_unknown_ticket_claims_nothing(self, clock):
        slot = srv.ImportSlot()
        ticket = slot.take(100, False, object())
        assert slot.claim(ticket, 101) is None
        assert slot.claim('f' * 32, 100) is None


class TestActionMap:
    def _consume(self, frame):
        user = _user(mock.Mock())
        user.request_import_project = mock.AsyncMock()

        async def run():
            await user.incoming.put(json.dumps(frame))
            task = asyncio.create_task(user.consumer())
            for _ in range(100):
                if user.request_import_project.await_count:
                    break
                await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())
        return user.request_import_project

    def test_15_the_frames_accept_loaded_reaches_the_handler(self):
        value = {'size': 10, 'name': 'show_a.zip'}
        handler = self._consume({'action': 'project_import', 'value': value, 'accept_loaded': True})
        handler.assert_awaited_once_with(value, 'project_import', True)

    def test_15_a_frame_without_the_key_reaches_it_as_none(self):
        value = {'size': 10, 'name': 'show_a.zip'}
        handler = self._consume({'action': 'project_import', 'value': value})
        handler.assert_awaited_once_with(value, 'project_import', None)


# ---------------------------------------------------------------------------
# (16) the upload session of an import
# ---------------------------------------------------------------------------

class TestUploadSession:
    def test_16_a_good_import_answers_ready_progress_imported_then_close(self, env):
        data = the_zip(env)
        parts = chunks(data)
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *parts, finished(md5(data))], size=len(data))
        frames = sock.frames()
        assert errors(sock) == []
        readies = [f for f in frames if f == {'ready': True}]
        assert len(readies) == 1 + len(parts)
        assert frames[:len(readies)] == readies               # nothing else before the data ends
        imported = [f for f in frames if 'imported' in f]
        assert len(imported) == 1
        assert frames[-1] == {'close': True}
        assert frames.index(imported[0]) < len(frames) - 1
        report = imported[0]['imported']
        assert report['project']['unix_name'] == TOP
        assert sorted(report['media']['added']) == sorted(MEDIA)
        for f in frames:
            if 'progress' in f:
                pr = f['progress']
                assert set(pr) == {'phase', 'done', 'total', 'name'}
                assert pr['phase'] in ('check', 'media', 'project')
                assert isinstance(pr['done'], int) and isinstance(pr['total'], int)
                assert 0 <= pr['done'] and 0 <= pr['total']
        assert os.listdir(env.staging_root) == []
        assert (None, 'file_list') in server.list_updates
        assert (None, 'project_list') in server.list_updates
        assert owner.calls >= 1 + len(MEDIA) + 1              # at the end of the upload, per file, project
        assert Project.get(Project.unix_name == TOP)

    @pytest.mark.parametrize('case', ['absent', 'unknown', 'used', 'expired', 'other_size'])
    def test_16_no_valid_ticket_is_I6_and_nothing_is_received(self, env, monkeypatch, case):
        data = the_zip(env)
        now = [1000.0]
        monkeypatch.setattr(srv, 'import_clock', lambda: now[0])
        before = env.state()

        def prepare(server, ticket):
            if case == 'used':                               # another upload claimed it first
                assert server.import_slot.claim(ticket, len(data)) is not None
            elif case == 'expired':
                now[0] += 61

        def frames(ticket):
            ticket = {'absent': None, 'unknown': 'e' * 32}.get(case, ticket)
            size = len(data) + 1 if case == 'other_size' else len(data)
            return [first_frame(size, ticket), *chunks(data), finished(md5(data))]

        server, sock, owner = run_upload(env, frames, size=len(data), prepare=prepare,
                                         take=case not in ('absent', 'unknown'),
                                         free_slot=case not in ('used', 'other_size'))
        sent = sock.frames()
        assert sent and sent[0] == {'error': I6, 'fatal': True}, sent
        assert {'ready': True} not in sent and not any('imported' in f for f in sent)
        assert os.listdir(env.staging_root) == []
        assert env.state() == before
        assert owner.calls == 0

    @pytest.mark.parametrize('case', ['more_bytes', 'fewer_bytes', 'another_md5'])
    def test_16_an_upload_that_is_not_what_was_announced_is_I7(self, env, case):
        data = the_zip(env)
        size = {'more_bytes': len(data) - 10, 'fewer_bytes': len(data) + 10}.get(case, len(data))
        digest = '0' * 32 if case == 'another_md5' else md5(data)
        before = env.state()
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(size, t), *chunks(data), finished(digest)], size=size)
        assert {'error': I7, 'fatal': True} in [{k: f[k] for k in ('error', 'fatal')}
                                                for f in errors(sock)]
        assert not any('imported' in f for f in sock.frames())
        assert os.listdir(env.staging_root) == []
        assert env.state() == before
        assert not server.import_slot.busy

    def test_16_a_stalled_upload_is_I7(self, env, monkeypatch):
        imp = _imp()
        assert imp.UPLOAD_STALL_S == 120
        monkeypatch.setattr(imp, 'UPLOAD_STALL_S', 0.5)
        data = the_zip(env)
        before = env.state()
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), chunks(data)[0]], size=len(data), wait_s=10)
        assert [f['error'] for f in errors(sock)] == [I7]
        assert os.listdir(env.staging_root) == []
        assert env.state() == before

    @pytest.mark.parametrize('frame', ['{"action": "ping"}', 'not json',
                                       '{"action": "finished", "value": 5}'],
                             ids=['another_action', 'not_json', 'finished_without_an_md5'])
    def test_16_a_text_frame_that_is_not_finished_is_I7(self, env, frame):
        """Change review R11: the browser sends nothing but binary frames and
        ``finished`` on this socket; any other text frame ends the import (I7)
        instead of being ignored and holding the one slot."""
        data = the_zip(env)
        parts = chunks(data)
        before = env.state()
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), parts[0], frame, *parts[1:],
                            finished(md5(data))], size=len(data))
        assert [f['error'] for f in errors(sock)] == [I7]
        assert not any('imported' in f for f in sock.frames())
        assert os.listdir(env.staging_root) == []
        assert env.state() == before
        assert not server.import_slot.busy

    def test_16_the_socket_closed_before_finished_drops_the_import(self, env):
        data = the_zip(env)
        before = env.state()
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data)[:2], CLOSE], size=len(data),
            end=None)
        assert os.listdir(env.staging_root) == []
        assert env.state() == before
        assert not server.import_slot.busy
        assert Project.get_or_none(Project.unix_name == TOP) is None

    def test_16_the_socket_closed_after_finished_lets_the_import_end(self, env):
        data = the_zip(env)
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data)), CLOSE],
            size=len(data), end=None)
        assert Project.get(Project.unix_name == TOP)
        assert (None, 'project_list') in server.list_updates
        assert os.listdir(env.staging_root) == []

    def test_16_a_refused_archive_is_I8a_on_the_socket_with_the_library_unchanged(self, env):
        data = open(env.zip([x for x in export_entries() if not x[0].endswith('script.xml')]),
                    'rb').read()
        before = env.state()
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            size=len(data))
        errs = errors(sock)
        assert len(errs) == 1 and errs[0]['error'].startswith(I8A) and errs[0]['fatal'] is True
        assert os.listdir(env.staging_root) == []
        assert env.state() == before
        assert not server.import_slot.busy

    def test_16_a_progress_frame_at_least_every_5_s_while_one_new_lasts_20_s(self, env, monkeypatch):
        imp = _imp()
        assert imp.HEARTBEAT_S <= 5
        real_new = env.media.new
        slow = [True]

        def new(*a, **kw):
            if slow[0]:
                slow[0] = False
                time.sleep(20)                               # one big file's sidecars
            return real_new(*a, **kw)

        monkeypatch.setattr(env.media, 'new', new)
        data = the_zip(env)
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            size=len(data), wait_s=120)
        assert errors(sock) == []
        sent = sock.sent
        last_ready = max(i for i, (_, f) in enumerate(sent) if f == {'ready': True})
        times = [t for t, _ in sent[last_ready:]]
        gaps = [b - a for a, b in zip(times, times[1:])]
        assert times[-1] - times[0] >= 20
        assert max(gaps) <= imp.HEARTBEAT_S + 0.5, gaps
        assert sum(1 for _, f in sent[last_ready:] if 'progress' in f) >= 4


# ---------------------------------------------------------------------------
# (17) a later check that refuses (D4)
# ---------------------------------------------------------------------------

class TestLaterChecks:
    def test_17_a_show_that_starts_at_the_second_file_stops_the_import_I9(self, env, monkeypatch):
        monkeypatch.setattr(_imp(), 'WATCH_S', 3600)         # only the checks before each write
        data = the_zip(env)
        # end of upload; file 1 before its extraction and before its registration (R1);
        # file 2 before its extraction
        owner = FakeOwner('none', 'none', 'none', 'running')
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            owner=owner, size=len(data))
        errs = errors(sock)
        assert len(errs) == 1 and errs[0]['fatal'] is True
        reason, added = i9_parts(errs[0]['error'])
        assert reason == I3 and len(added) == 1
        assert errs[0]['report']['media']['added'] == added
        assert env.row(added[0]) is not None                 # in the library, shown to all
        assert (None, 'file_list') in server.list_updates
        assert Project.get_or_none(Project.unix_name == TOP) is None
        assert not server.import_slot.busy
        assert os.listdir(env.staging_root) == []

    def test_17_a_project_loaded_after_a_guard_that_saw_none_stops_it(self, env):
        data = the_zip(env)
        before = env.state()
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            owner=FakeOwner('loaded'), size=len(data))
        errs = errors(sock)
        assert len(errs) == 1
        reason, added = i9_parts(errs[0]['error'])
        assert (reason, added) == (I5, [])
        assert env.state() == before

    def test_17_loaded_accepted_at_the_guard_goes_on(self, env):
        data = the_zip(env)
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            owner=FakeOwner('loaded'), size=len(data), accept_loaded=True)
        assert errors(sock) == []
        assert Project.get(Project.unix_name == TOP)

    def test_17_the_checks_go_on_after_the_users_socket_is_closed(self, env, monkeypatch):
        """The later checks need no socket of the session that asked (N9): its
        tab goes away while the first file is registered, the import goes on
        asking the engine through the server's communicator and ends."""
        data = the_zip(env)
        closed = {}
        gate = threading.Event()
        real_new = env.media.new

        def new(*a, **kw):
            assert gate.wait(30)                             # held until the user is gone
            return real_new(*a, **kw)

        monkeypatch.setattr(env.media, 'new', new)
        owner = object.__new__(wsu.CuemsWsUser)
        owner.websocket = mock.Mock()
        owner.outgoing = asyncio.Queue()
        owner.incoming = asyncio.Queue()

        def prepare(server, ticket):
            owner.server = server
            server.users[owner] = None

        async def close_the_user(server, sock, _):
            await sock.wait(lambda f: 'progress' in f or 'error' in f, 60)
            server.users.pop(owner, None)
            owner.websocket.send.side_effect = ws.exceptions.ConnectionClosedOK(None, None)
            owner.websocket.recv.side_effect = ws.exceptions.ConnectionClosedOK(None, None)
            closed['at'] = len(server.engine_requests)
            gate.set()

        server, sock, _ = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            owner=owner, size=len(data), prepare=prepare, after=close_the_user)
        assert errors(sock) == []
        assert Project.get(Project.unix_name == TOP)
        asked_after = server.engine_requests[closed['at']:]
        assert len(asked_after) >= len(MEDIA)                # files 2 and 3, and the project
        assert all(r['action'] == 'project_status' for r in server.engine_requests)
        owner.websocket.send.assert_not_called()


# ---------------------------------------------------------------------------
# (D19) a GO stops the import also during the upload and the check, and the
# import works at the lowest priority
# ---------------------------------------------------------------------------

class SaysNow(FakeOwner):
    """An engine whose word the test changes while the session runs."""

    def __init__(self, word='none'):
        super().__init__(word)
        self.word = word
        self.said = []

    async def _engine_status(self):
        self.calls += 1
        self.said.append(self.word)
        return self.word


def _watching(monkeypatch, every=0.05):
    imp = _imp()
    monkeypatch.setattr(imp, 'WATCH_S', every)
    return imp


async def _asked_again(owner):
    seen = owner.calls
    await until(lambda: owner.calls >= seen + 2, 10)


class TestStopsOnGo:
    def test_d19_the_engine_is_asked_every_second(self):
        assert 0 < _imp().WATCH_S <= 1
        assert 0 < _imp().KILL_S <= 0.2

    @pytest.mark.parametrize('word,accept,reason', [('running', False, I3), ('running', True, I3),
                                                    ('loaded', False, I5)],
                             ids=['go', 'go_though_loaded_was_accepted', 'loaded_not_accepted'])
    def test_d19_a_show_during_the_upload_stops_it_without_waiting_for_its_end(
            self, env, monkeypatch, word, accept, reason):
        _watching(monkeypatch)
        data = the_zip(env)
        parts = chunks(data, 1000)
        before = env.state()

        async def go(server, sock, owner):
            await sock.wait(lambda f: f == {'ready': True}, 10)
            owner.word = word
            await until(lambda: word in owner.said, 10)       # asked while the upload goes on
            await asyncio.sleep(0.1)
            sock.put(parts[1])                                # no ``finished`` ever comes

        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), parts[0]], size=len(data),
            owner=SaysNow(), accept_loaded=accept, after=go, wait_s=20)
        errs = errors(sock)
        assert len(errs) == 1 and errs[0]['fatal'] is True
        assert i9_parts(errs[0]['error']) == (reason, [])
        assert env.state() == before
        assert os.listdir(env.staging_root) == []
        assert not server.import_slot.busy

    @pytest.mark.parametrize('word,accept', [(None, False), ('loaded', True), ('none', False)],
                             ids=['no_answer', 'loaded_and_accepted', 'nothing_loaded'])
    def test_d19_these_answers_during_the_upload_stop_nothing(self, env, monkeypatch, word, accept):
        _watching(monkeypatch)
        data = the_zip(env)
        parts = chunks(data, 1000)

        async def go_on(server, sock, owner):
            await sock.wait(lambda f: f == {'ready': True}, 10)
            owner.word = word
            await _asked_again(owner)
            owner.word = 'loaded' if accept else 'none'       # the checks after the upload
            sock.put(*parts[1:], finished(md5(data)))

        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), parts[0]], size=len(data),
            owner=SaysNow(), accept_loaded=accept, after=go_on)
        assert errors(sock) == []
        assert Project.get(Project.unix_name == TOP)

    def test_d19_a_show_during_the_check_of_the_archive_stops_it(self, env, monkeypatch):
        imp = _watching(monkeypatch)
        real_check = imp._check
        owner = SaysNow()
        before = env.state()

        def check(*a, **kw):
            owner.word = 'running'
            deadline = time.monotonic() + 10
            while 'running' not in owner.said:
                assert time.monotonic() < deadline, 'nobody asks the engine during the check'
                time.sleep(0.02)
            time.sleep(0.05)
            return real_check(*a, **kw)

        monkeypatch.setattr(imp, '_check', check)
        data = the_zip(env)
        before = env.state()
        server, sock, _ = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            size=len(data), owner=owner, wait_s=30)
        errs = errors(sock)
        assert len(errs) == 1
        assert i9_parts(errs[0]['error']) == (I3, [])
        assert env.state() == before
        assert os.listdir(env.staging_root) == []


# A GO while a file is being added: what the import waits for is ended at once and
# nothing of that file stays (D19, "a GO has total priority").

def _sleeper(pids):
    """A builder that takes a minute, as a real program of the calling thread."""
    proc = subprocess.Popen(['sleep', '60'])
    pids.append(proc.pid)
    try:
        return proc.wait()
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


def _alive(pid):
    try:
        with open(f'/proc/{pid}/stat') as f:
            return f.read().rsplit(')', 1)[1].split()[0] != 'Z'
    except FileNotFoundError:
        return False


class TestAGoCutsTheFileInHand:
    @pytest.mark.parametrize('word,accept,reason', [('running', True, I3), ('loaded', False, I5)],
                             ids=['go', 'loaded_not_accepted'])
    def test_d19_its_programs_are_killed_and_nothing_of_it_stays(self, env, monkeypatch, word,
                                                                 accept, reason):
        _watching(monkeypatch)
        owner = SaysNow()
        names = list(MEDIA)
        pids, codes = [], []
        cut_name = []

        def thumbnail(filename, duration=None):
            env.builders.thumbnail(filename)                  # what a real one has half written
            if len(env.media_files_added) == 1 and not cut_name:
                cut_name.append(filename)
                index = ms.video_index_path(env.media.get_file_path(filename))
                env.builders._write(index)
                env.builders._write(index + '.tmp')
                owner.word = word                             # the GO, with a program in hand
                codes.append(_sleeper(pids))                  # the thumbnail
                codes.append(_sleeper(pids))                  # and the one that follows it
            env.media_files_added.append(filename)

        env.media_files_added = []
        monkeypatch.setattr(env.media, 'create_video_thumbnail', thumbnail)
        monkeypatch.setattr(env.media, 'create_audio_thubnail', thumbnail)
        # another thread's builder, as a media upload running beside the import has
        other = subprocess.Popen(['sleep', '60'])
        data = the_zip(env)
        started = time.monotonic()
        try:
            server, sock, _ = run_upload(
                env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
                size=len(data), owner=owner, accept_loaded=accept, wait_s=40)
            took = time.monotonic() - started
            assert other.poll() is None, 'a program the import did not start was killed'
        finally:
            other.kill()
            other.wait()
        errs = errors(sock)
        assert len(errs) == 1 and errs[0]['fatal'] is True
        said, added = i9_parts(errs[0]['error'])
        assert said == reason
        assert codes == [-9, -9] and not any(_alive(pid) for pid in pids)
        assert took < 20, took
        assert cut_name and len(added) == 1 and cut_name[0] not in added
        assert env.row(cut_name[0]) is None
        left = [os.path.join(base, n) for base, _, found in os.walk(env.media_dir) for n in found
                if n.startswith(cut_name[0])]
        assert left == []
        assert env.row(added[0]) is not None                  # what was in before stays (D12)
        assert Project.get_or_none(Project.unix_name == TOP) is None
        assert os.listdir(env.staging_root) == []
        assert not server.import_slot.busy
        assert len(MEDIA) == len(names)

    @pytest.mark.parametrize('call', [1, 2, 3, 4, 5])
    def test_d19_a_registration_given_up_at_any_step_leaves_nothing(self, env, call):
        before = env.state()
        calls = []

        class GivenUp(Exception):
            pass

        def stop():
            calls.append(1)
            if len(calls) == call:
                raise GivenUp()

        for name, data in MEDIA.items():
            calls.clear()
            tmp = os.path.join(env.zips, 'incoming')
            with open(tmp, 'wb') as f:
                f.write(data)
            with pytest.raises(GivenUp):
                env.media.new(tmp, name, md5(data), stop=stop)
        files, rows = env.state()
        assert rows == before[1]
        assert [f[0] for f in files] == [f[0] for f in before[0]]

    def test_d19_a_go_while_a_file_is_extracted_ends_before_its_registration(self, env, monkeypatch):
        imp = _imp()
        cut = imp._Cut()
        registered = []
        monkeypatch.setattr(env.media, 'new', lambda *a, **kw: registered.append(a))
        before = env.state()

        def progress(phase, done, total, name):
            if phase == 'media':                              # right before the extraction
                cut.reason = I3

        with pytest.raises(Exception) as ei:
            imp.import_archive(env.zip(export_entries()), env.db, env.stage(),
                               status=lambda: 'none', progress=progress, cut=cut)
        assert i9_parts(str(ei.value)) == (I3, [])
        assert registered == [] and env.state() == before

    def test_d19_a_go_while_the_project_is_prepared_creates_no_project(self, env, monkeypatch):
        imp = _imp()
        cut = imp._Cut()
        real_fill = env.project._fix_media_durations

        def fill(data, **kw):
            real_fill(data, **kw)
            cut.reason = I3

        monkeypatch.setattr(env.project, '_fix_media_durations', fill)
        with pytest.raises(Exception) as ei:
            imp.import_archive(env.zip(export_entries()), env.db, env.stage(),
                               status=lambda: 'none', cut=cut)
        said, added = i9_parts(str(ei.value))
        assert said == I3 and len(added) == len(MEDIA)
        assert Project.get_or_none(Project.unix_name == TOP) is None
        assert not os.path.exists(os.path.join(env.project.projects_path, TOP))

    def test_d19_a_go_after_the_project_exists_changes_nothing(self, env):
        imp = _imp()
        cut = imp._Cut()

        def told(kind):
            if kind == 'project_list':
                cut.reason = I3

        report = imp.import_archive(env.zip(export_entries()), env.db, env.stage(),
                                    status=lambda: 'none', list_update=told, cut=cut)
        assert report['project']['unix_name'] == TOP
        assert Project.get(Project.unix_name == TOP)


def _priority_of(tid):
    io = subprocess.run(['ionice', '-p', str(tid)], capture_output=True, text=True).stdout.strip()
    return os.getpriority(os.PRIO_PROCESS, tid), io


class TestLowestPriority:
    def test_d19_the_registration_and_its_programs_run_at_the_lowest_priority(self, env, monkeypatch):
        mine = _priority_of(threading.get_native_id())
        seen = []
        real_new = env.media.new

        def new(*a, **kw):
            child = subprocess.run(['sh', '-c', 'nice; ionice -p $$'], capture_output=True, text=True)
            seen.append((_priority_of(threading.get_native_id()), child.stdout.split('\n')[:2],
                         threading.current_thread()))
            return real_new(*a, **kw)

        monkeypatch.setattr(env.media, 'new', new)
        data = the_zip(env)
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            size=len(data))
        assert errors(sock) == []
        assert len(seen) == len(MEDIA)
        for own, child, thread in seen:
            assert own == (19, 'best-effort: prio 7')
            assert child == ['19', 'best-effort: prio 7']
        # the editor's own threads keep theirs, and the niced thread does not outlive the import
        assert _priority_of(threading.get_native_id()) == mine
        threads = {thread for _, _, thread in seen}
        for thread in threads:
            thread.join(10)
            assert not thread.is_alive()


# ---------------------------------------------------------------------------
# (D19) after the external change review (X2 to X5)
# ---------------------------------------------------------------------------

def _spied(monkeypatch, module, name, calls, then=None):
    """*name* of *module* noted in *calls* when it runs; ``then()`` after it."""
    real = getattr(module, name)

    def spy(*a, **kw):
        calls.append(name)
        out = real(*a, **kw)
        if then:
            then()
        return out

    monkeypatch.setattr(module, name, spy)


class TestAGoBetweenTheStepsOfTheScript:
    """X2: the step in hand ends; the next one never starts."""

    def test_d19_a_go_before_the_script_is_copied_ends_before_it_is_read(self, env, monkeypatch):
        imp = _imp()
        cut = imp._Cut()
        cut.reason = I3
        calls = []
        _spied(monkeypatch, imp, '_read_script', calls)
        before = env.state()
        with pytest.raises(Exception) as ei:
            imp.import_archive(env.zip(export_entries()), env.db, env.stage(),
                               status=lambda: 'none', cut=cut)
        assert i9_parts(str(ei.value)) == (I3, [])
        assert calls == [] and env.state() == before

    @pytest.mark.parametrize('after', ['read', 'parse', 'validate'])
    def test_d19_no_step_of_the_check_starts_after_a_go(self, env, monkeypatch, after):
        imp = _imp()
        cut = imp._Cut()
        done = []

        def go(step):
            def then():
                done.append(step)
                if step == after:
                    cut.reason = I3
            return then

        real_reader = imp.XmlReaderWriter

        class Reader(real_reader):
            def read(self, **kw):
                out = super().read(**kw)
                go('read')()
                return out

            def validate_object(self, project_object):
                out = super().validate_object(project_object)
                go('validate')()
                return out

        class Parser(imp.CuemsParser):
            def parse(self):
                out = super().parse()
                go('parse')()
                return out

        monkeypatch.setattr(imp, 'XmlReaderWriter', Reader)
        monkeypatch.setattr(imp, 'CuemsParser', Parser)
        gates = []
        _spied(monkeypatch, imp, '_gate_warnings', gates)
        before = env.state()
        with pytest.raises(Exception) as ei:
            imp.import_archive(env.zip(export_entries()), env.db, env.stage(),
                               status=lambda: 'none', cut=cut)
        assert i9_parts(str(ei.value)) == (I3, [])
        steps = ['read', 'parse', 'validate']
        assert done == steps[:steps.index(after) + 1]
        assert gates == [] and env.state() == before

    @pytest.mark.parametrize('during', ['parse', 'relations'])
    def test_d19_a_go_inside_the_creation_writes_no_script_and_creates_nothing(
            self, env, monkeypatch, during):
        imp = _imp()
        cut = imp._Cut()
        saved, errors_logged = [], []
        real_parser = p.CuemsParser

        class Parser(real_parser):
            def parse(self):
                out = super().parse()
                if during == 'parse':
                    cut.reason = I3
                return out

        real_relations = env.project.add_media_relations

        def relations(*a, **kw):
            real_relations(*a, **kw)
            if during == 'relations':
                cut.reason = I3

        monkeypatch.setattr(p, 'CuemsParser', Parser)
        monkeypatch.setattr(env.project, 'add_media_relations', relations)
        monkeypatch.setattr(env.project, 'save_xml', lambda *a: saved.append(a))
        monkeypatch.setattr(p.Logger, 'error', lambda text, *a, **kw: errors_logged.append(text))
        with pytest.raises(Exception) as ei:
            imp.import_archive(env.zip(export_entries()), env.db, env.stage(),
                               status=lambda: 'none', cut=cut)
        said, added = i9_parts(str(ei.value))
        assert said == I3 and len(added) == len(MEDIA)
        assert saved == []
        assert Project.get_or_none(Project.unix_name == TOP) is None
        assert not os.path.exists(os.path.join(env.project.projects_path, TOP))
        assert not [e for e in errors_logged if 'trying to import' in e], errors_logged


class TestAGoDuringTheProbesOfThePreparation:
    """X3: the probe the cut killed is not the library file's failure."""

    def test_d19_a_killed_probe_marks_no_file_and_no_other_file_is_probed(self, env, monkeypatch):
        imp = _imp()
        cut = imp._Cut()
        for n, data in MEDIA.items():
            env.put_media(n, data, with_size=False)          # legacy rows: the preparation probes them
        p.reset_refresh_marks()
        probed, logged = [], []

        def killed(path, timeout=None):
            probed.append(os.path.basename(path))
            cut.reason = I3                                  # the GO; its kill is what the probe sees
            return m.MediaProbe()

        monkeypatch.setattr(p, 'probe_media', killed)
        monkeypatch.setattr(p.Logger, 'error', lambda text, *a, **kw: logged.append(text))
        before = env.state()
        with pytest.raises(Exception) as ei:
            imp.import_archive(env.zip(export_entries()), env.db, env.stage(),
                               status=lambda: 'none', cut=cut)
        assert i9_parts(str(ei.value)) == (I3, [])
        assert len(probed) == 1, probed
        assert not p._FAILED_MARKS, p._FAILED_MARKS
        assert not [e for e in logged if 'could not read the duration' in e], logged
        assert env.state() == before                         # no row was written, no project

    def test_d19_without_a_go_a_failed_probe_is_still_marked(self, env, monkeypatch):
        for n, data in MEDIA.items():
            env.put_media(n, data, with_size=False)
        p.reset_refresh_marks()
        monkeypatch.setattr(p, 'probe_media', lambda path, timeout=None: m.MediaProbe())
        report = env.run(env.zip(export_entries()))
        assert report['project']['unix_name'] == TOP
        assert p._FAILED_MARKS


class TestThePriorityOfTheUpload:
    """X4: the whole import works at the lowest priority, the upload included."""

    def test_d19_the_upload_is_written_in_the_imports_own_thread_at_the_lowest_priority(
            self, env, monkeypatch):
        imp = _imp()
        mine = _priority_of(threading.get_native_id())
        writes, registrations = [], []
        real_write, real_new = imp._write_chunk, env.media.new

        def write(*a):
            writes.append((_priority_of(threading.get_native_id()), threading.current_thread()))
            return real_write(*a)

        def new(*a, **kw):
            registrations.append(threading.current_thread())
            return real_new(*a, **kw)

        monkeypatch.setattr(imp, '_write_chunk', write)
        monkeypatch.setattr(env.media, 'new', new)
        data = the_zip(env)
        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            size=len(data))
        assert errors(sock) == []
        assert writes and registrations
        assert {own for own, _ in writes} == {(19, 'best-effort: prio 7')}
        assert {t for _, t in writes} == set(registrations)  # one thread for the whole import
        assert _priority_of(threading.get_native_id()) == mine
        thread = writes[0][1]
        thread.join(10)
        assert not thread.is_alive()


class TestTheHeartbeatToTheEnd:
    """X5: a question still out when the work ends keeps the progress frames coming."""

    def test_progress_goes_on_while_the_last_question_is_answered(self, env, monkeypatch):
        imp = _watching(monkeypatch)
        monkeypatch.setattr(imp, 'HEARTBEAT_S', 0.25)
        real_import = imp.import_archive
        ended = {}

        class SlowAtTheEnd(FakeOwner):
            slow = False
            stuck = False

            async def _engine_status(self):
                self.calls += 1
                if self.slow:
                    self.stuck = True
                    await asyncio.sleep(2)
                return 'none'

        owner = SlowAtTheEnd()

        def archive(*a, **kw):
            report = real_import(*a, **kw)
            owner.slow = True
            deadline = time.monotonic() + 10
            while not owner.stuck:                           # the watcher's question is out
                assert time.monotonic() < deadline
                time.sleep(0.01)
            ended['at'] = time.monotonic()
            return report

        monkeypatch.setattr(imp, 'import_archive', archive)
        data = the_zip(env)
        server, sock, _ = run_upload(
            env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
            size=len(data), owner=owner)
        assert errors(sock) == []
        report_at = next(at for at, f in sock.sent if 'imported' in f)
        assert report_at - ended['at'] > 1.5                 # the answer was waited for
        times = [ended['at']] + [at for at, f in sock.sent
                                 if 'progress' in f and ended['at'] < at < report_at] + [report_at]
        assert max(b - a for a, b in zip(times, times[1:])) < 0.8, times


# ---------------------------------------------------------------------------
# (18) a first frame without type: PROJECT is a media upload as before
# ---------------------------------------------------------------------------

class TestMediaUploadAsBefore:
    @pytest.mark.parametrize('extra', [{}, {'type': 'AUDIO'}, {'type': 'project'}])
    def test_18_a_media_upload_is_unchanged(self, env, extra):
        data = os.urandom(700_000)
        value = {'name': 'song.wav', 'size': len(data), **extra}

        def frames(_):
            return [json.dumps({'action': 'upload', 'value': value}), *chunks(data),
                    finished(md5(data))]

        server, sock, owner = run_upload(env, frames, slot=False)
        sent = sock.frames()
        assert sent == [{'ready': True}] * (1 + len(chunks(data))) + [{'close': True}], sent
        row = env.row('song.wav')
        assert row is not None and row.file_md5 == md5(data)
        assert open(os.path.join(env.media_dir, 'song.wav'), 'rb').read() == data
        assert server.list_updates == [(None, 'file_list')]
        assert os.listdir(env.staging_root) == []
        assert owner.calls == 0
