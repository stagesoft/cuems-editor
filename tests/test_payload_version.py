# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The payload version is the first frame on connect (FR-047, FR-047a).

``{"type":"payload_version","value":1}`` precedes ``users``, ``session_id``
and every ``initial_*`` frame. A peer that never sends it is version 0, the
wire before 001. The integer is a contract: it may only move together with a
bump row in ``tests/ws-command-responses.txt``. It is not ``doc_version``.
"""

import asyncio
import json
import os
import re
from unittest.mock import MagicMock

import pytest

import cuemseditor.CuemsWsServer as server_module
from cuemseditor.cli import get_mappings, get_settings
from cuemseditor.CuemsWsServer import CuemsWsServer

HERE = os.path.dirname(__file__)
CONF = os.path.join(HERE, 'fixtures', 'conf')
RESPONSES = os.path.join(HERE, 'ws-command-responses.txt')


class _Socket:
    """A connection that is open long enough for the producer to send the
    connect frames, then closes from the client side."""

    def __init__(self):
        self.sent = []
        self.request = MagicMock(path='/')
        self.remote_address = ('127.0.0.1', 0)

    async def send(self, message):
        self.sent.append(json.loads(message))

    def __aiter__(self):
        return self

    async def __anext__(self):
        await asyncio.sleep(0.2)
        raise StopAsyncIteration


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv('CUEMS_CONF_PATH', CONF)
    monkeypatch.setattr(server_module, 'Communicator', MagicMock())
    monkeypatch.setattr(CuemsWsServer, 'nodeconf_available', lambda self: False)
    settings = get_settings()
    settings['tmp_path'] = str(tmp_path)
    server = CuemsWsServer(settings, get_mappings())
    server.event_loop = asyncio.new_event_loop()
    server.executor = None
    yield server
    server.event_loop.close()


def test_payload_version_is_the_first_frame_on_connect(server):
    socket = _Socket()
    server.event_loop.run_until_complete(server.project_manager_session(socket, '/'))

    types = [frame['type'] for frame in socket.sent]
    assert socket.sent[0] == {'type': 'payload_version', 'value': 1}
    assert types.count('payload_version') == 1
    assert {'users', 'session_id', 'initial_mappings', 'node_list'} <= set(types)


def test_the_advertised_version_has_a_bump_row():
    """Changing the integer without recording it in the responses file fails here."""
    with open(RESPONSES, encoding='utf-8') as fh:
        text = fh.read()
    rows = {int(n) for n in re.findall(r'^payload_version (\d+):', text, re.M)}
    assert CuemsWsServer.PAYLOAD_VERSION in rows
    assert max(rows) == CuemsWsServer.PAYLOAD_VERSION
