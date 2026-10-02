# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``alive`` and ``online`` stay two facts; engine errors are relayed as sent (FR-033, FR-036).

``node_status`` relays the engine's ``cluster_status``: ``alive`` is the
sub-second ping/pong set. ``online`` on each node is nodeconf's discovery
view (~30 s). Nothing in the editor copies one onto the other.
``nodelist_modify`` forwards the engine's error text verbatim, including
nodeconf's readiness-window ``Node <uuid> not found``, and does not retry.
"""

import ast
import asyncio
import concurrent.futures
import json
import os
from unittest.mock import MagicMock, patch

import pytest

from cuemseditor.CuemsErrors import EngineError
from cuemseditor.CuemsWsUser import CuemsWsUser

SRC = os.path.join(os.path.dirname(__file__), '..', 'src', 'cuemseditor')
NODE = '4b9b5a1e-0000-4000-8000-0123456789ab'


@pytest.fixture
def user():
    server = MagicMock()
    server.users = {}
    server.event_loop = asyncio.new_event_loop()
    server.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    server.mappings_dict = {'nodes': [{'node': {'uuid': NODE, 'online': 'False'}}], 'new_nodes': []}
    session = CuemsWsUser(server, MagicMock())
    yield session
    server.executor.shutdown(wait=False)
    server.event_loop.close()


def _drain(user):
    out = []
    while not user.outgoing.empty():
        out.append(json.loads(user.outgoing.get_nowait()))
    return out


def test_node_status_relays_cluster_status_and_leaves_online_alone(user):
    engine = {'alive': [NODE], 'adopted': [NODE], 'controller': NODE, 'age_s': 0.1}
    before = json.dumps(user.server.mappings_dict)
    with patch.object(user, 'comunicate_with_engine', return_value=engine) as call:
        user.server.event_loop.run_until_complete(user.node_status('node_status'))

    assert call.call_args[0][2]['action'] == 'cluster_status'
    assert _drain(user) == [{'type': 'node_status', 'value': engine}]
    assert json.dumps(user.server.mappings_dict) == before   # alive did not become online


def test_no_source_assigns_online_from_alive():
    """Structural: no assignment whose target is ``online`` reads ``alive``."""
    for name in os.listdir(SRC):
        if not name.endswith('.py'):
            continue
        with open(os.path.join(SRC, name), encoding='utf-8') as fh:
            tree = ast.parse(fh.read())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                targets = ast.dump(node.targets[0])
                if "'online'" in targets or "attr='online'" in targets:
                    assert 'alive' not in ast.dump(node.value), f'{name}:{node.lineno}'


@pytest.mark.parametrize('message', [
    f'Node {NODE} not found',
    'cuems-nodeconf did not respond',
])
def test_nodelist_modify_relays_the_engine_error_unchanged_without_retry(user, message):
    with patch.object(user, 'comunicate_with_engine', side_effect=EngineError(message)) as call:
        user.server.event_loop.run_until_complete(
            user.nodelist_modify(NODE, 'nodelist_modify', 'ADD'))

    assert call.call_count == 1
    frames = _drain(user)
    assert frames == [{'type': 'error', 'action': 'nodelist_modify', 'value': message}]
    user.server.notify_all_node_list_update.assert_not_called()
