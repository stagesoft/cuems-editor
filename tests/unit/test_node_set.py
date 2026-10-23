# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``node_set``: the operator's node alias, sent straight to cuems-nodeconf (002 US4, FR-024 to FR-027).

The editor never writes ``network_map.xml``. It sends
``{"action": "node_set", "node_uuid", "alias"}`` to ``/tmp/nodeconf.ipc``
(Q2: not through the engine), relays nodeconf's answer, and on success
refreshes every session's ``node_list``. ``alias`` is the only field the
operator owns (M7); anything else is refused before any IPC. Where nodeconf
does not run, the answer is ``unavailable`` at once (FR-025).

The IPC peer is a fake ``Communicator``; the real handler is gate G4
(``tests/test_upstream_gates.py``).
"""

import asyncio
import concurrent.futures
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

import cuemseditor.CuemsWsUser as ws_user
from cuemseditor.CuemsWsUser import CuemsWsUser

NODE = '4b9b5a1e-0000-4000-8000-0123456789ab'
NODECONF_IPC = '/tmp/nodeconf.ipc'
REQUEST = {'action': 'node_set', 'node_uuid': NODE, 'alias': 'Stage left'}


class FakeCommunicator:
    """Stands in for ``cuemsutils.tools.CommunicatorServices.Communicator``."""

    instances = []
    reply = {'OK': True}
    delay = 0
    raises = None

    def __init__(self, address):
        if FakeCommunicator.raises is not None:
            raise FakeCommunicator.raises
        self.address = address
        self.requests = []
        FakeCommunicator.instances.append(self)

    async def send_request(self, request):
        self.requests.append(request)
        if FakeCommunicator.delay:
            await asyncio.sleep(FakeCommunicator.delay)
        return FakeCommunicator.reply


@pytest.fixture
def user(monkeypatch):
    FakeCommunicator.instances = []
    FakeCommunicator.reply = {'OK': True}
    FakeCommunicator.delay = 0
    FakeCommunicator.raises = None
    monkeypatch.setattr(ws_user, 'Communicator', FakeCommunicator)
    server = MagicMock()
    server.users = {}
    server.NODECONF_IPC = NODECONF_IPC
    server.event_loop = asyncio.new_event_loop()
    server.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    server.nodeconf_available = MagicMock(return_value=True)
    server.notify_all_node_list_update = AsyncMock()
    session = CuemsWsUser(server, MagicMock())
    yield session
    server.executor.shutdown(wait=True)
    server.event_loop.close()


def _call(user, value):
    user.server.event_loop.run_until_complete(user.node_set(value, 'node_set'))
    out = []
    while not user.outgoing.empty():
        out.append(json.loads(user.outgoing.get_nowait()))
    return out


def _refused(node_uuid, reason):
    return lambda frame: (frame['type'] == 'node_set_refused'
                          and frame['value']['node_uuid'] == node_uuid
                          and frame['value']['reason'] == reason
                          and isinstance(frame['value']['message'], str))


def test_node_set_sends_the_alias_and_refreshes_everyone(user):
    frames = _call(user, {'node_uuid': NODE, 'alias': 'Stage left'})

    assert frames == [{'type': 'node_set', 'value': {'node_uuid': NODE, 'alias': 'Stage left'}}]
    [peer] = FakeCommunicator.instances
    assert peer.address == NODECONF_IPC
    assert peer.requests == [REQUEST]
    user.server.notify_all_node_list_update.assert_awaited_once()


def test_a_null_alias_asks_nodeconf_to_remove_it(user):
    frames = _call(user, {'node_uuid': NODE, 'alias': None})

    assert frames == [{'type': 'node_set', 'value': {'node_uuid': NODE, 'alias': None}}]
    assert FakeCommunicator.instances[0].requests == [{'action': 'node_set', 'node_uuid': NODE, 'alias': None}]


def test_unavailable_answers_at_once_and_builds_no_communicator(user):
    user.server.nodeconf_available.return_value = False

    frames = _call(user, {'node_uuid': NODE, 'alias': 'Stage left'})

    assert len(frames) == 1 and _refused(NODE, 'unavailable')(frames[0])
    assert FakeCommunicator.instances == []
    user.server.notify_all_node_list_update.assert_not_awaited()


def test_nodeconf_error_is_relayed_verbatim_without_retry(user):
    FakeCommunicator.reply = {'OK': False, 'error': 'Node x not found'}

    frames = _call(user, {'node_uuid': NODE, 'alias': 'Stage left'})

    assert frames == [{'type': 'node_set_refused', 'value': {
        'node_uuid': NODE, 'reason': 'nodeconf_error', 'message': 'Node x not found'}}]
    assert len(FakeCommunicator.instances) == 1
    assert FakeCommunicator.instances[0].requests == [REQUEST]
    user.server.notify_all_node_list_update.assert_not_awaited()


def test_a_timeout_is_node_set_refused_timeout(user, monkeypatch):
    monkeypatch.setattr(ws_user, 'TIMEOUT', 0.05)
    FakeCommunicator.delay = 1

    frames = _call(user, {'node_uuid': NODE, 'alias': 'Stage left'})

    assert len(frames) == 1 and _refused(NODE, 'timeout')(frames[0])
    assert len(FakeCommunicator.instances[0].requests) == 1


def test_no_reply_is_unavailable(user):
    FakeCommunicator.reply = None          # the NNG requester returns None on a transport error

    frames = _call(user, {'node_uuid': NODE, 'alias': 'Stage left'})

    assert len(frames) == 1 and _refused(NODE, 'unavailable')(frames[0])


@pytest.mark.parametrize('error', [SystemExit(1), PermissionError('/tmp/nodeconf.ipc')])
def test_a_sys_exit_from_communicator_is_unavailable(user, error):
    FakeCommunicator.raises = error

    frames = _call(user, {'node_uuid': NODE, 'alias': 'Stage left'})

    assert len(frames) == 1 and _refused(NODE, 'unavailable')(frames[0])


@pytest.mark.parametrize('field', ['uuid', 'name', 'node_role', 'ip', 'online', 'adopted',
                                   'role_id', 'hostname', 'mac'])
def test_non_operator_fields_are_refused_before_ipc(user, field):
    frames = _call(user, {'node_uuid': NODE, 'alias': 'Stage left', field: 'x'})

    assert len(frames) == 1 and _refused(NODE, 'not_operator_field')(frames[0])
    assert field in frames[0]['value']['message']
    assert FakeCommunicator.instances == []


@pytest.mark.parametrize('node_uuid', [None, '', 'not-a-uuid', 42, '00000000-0000-0000-0000-000000000000'])
def test_an_invalid_node_uuid_is_refused_before_ipc(user, node_uuid):
    frames = _call(user, {'node_uuid': node_uuid, 'alias': 'Stage left'})

    assert len(frames) == 1 and _refused(node_uuid, 'invalid_value')(frames[0])
    assert FakeCommunicator.instances == []


@pytest.mark.parametrize('value', [
    {'node_uuid': NODE, 'alias': ''},
    {'node_uuid': NODE, 'alias': '   '},
    {'node_uuid': NODE, 'alias': 7},
    {'node_uuid': NODE},
])
def test_an_invalid_alias_is_refused_before_ipc(user, value):
    frames = _call(user, value)

    assert len(frames) == 1 and _refused(NODE, 'invalid_value')(frames[0])
    assert FakeCommunicator.instances == []


def test_the_action_is_registered(user):
    message = json.dumps({'action': 'node_set', 'value': {'node_uuid': NODE, 'alias': 'Stage left'}})

    async def dispatch_one():
        await user.incoming.put(message)
        consumer = asyncio.ensure_future(user.consumer())
        while user.outgoing.empty():
            await asyncio.sleep(0.01)
        consumer.cancel()

    user.server.event_loop.run_until_complete(dispatch_one())
    assert json.loads(user.outgoing.get_nowait())['type'] == 'node_set'
