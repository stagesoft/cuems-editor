# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The editor's node merge and the ``initial_mappings`` wire form (FR-028–FR-036a).

Pins what this repository does with the library's nodes: the merge into the
mapping nodes, the string form the UI reads, where the shared state is
assigned, and what happens when the map has a duplicate identity. It does not
test the node model itself (``NodeRole``, ``Uuid``): that is the library's
(FR-030).

Nodes come from ``tests/fixtures/conf`` through ``ConfigManager`` and
``partition_by_adoption``, the same public path the server uses.
"""

import asyncio
import copy
import json
import os
import shutil
from unittest.mock import MagicMock, patch

import pytest

import cuemseditor.CuemsWsServer as server_module
from cuemseditor.cli import get_mappings, get_settings
from cuemseditor.CuemsWsServer import CuemsWsServer
from cuemsutils.tools.ConfigManager import ConfigManager

HERE = os.path.dirname(__file__)
CONF = os.path.join(HERE, 'fixtures', 'conf')
CAPTURE = os.path.join(
    HERE, '..', 'specs', '001-cuems-utils-migration', 'evidence', 'initial-mappings.json')

CONTROLLER = '0367f391-ebf4-48b2-9f26-000000000001'   # adopted; mapping node has devices
NEW_NODE = '0367f391-ebf4-48b2-9f26-000000000003'     # not adopted; mapping node has none


def _library_nodes(conf=CONF):
    """``(adopted, unadopted)`` as the server obtains them."""
    from cuemsutils.tools.NodeList import partition_by_adoption
    with patch.dict(os.environ, {'CUEMS_CONF_PATH': conf}):
        manager = ConfigManager(load_all=False)
        manager.load_network_map()
        return partition_by_adoption(manager.network_map)


def _mapping_nodes():
    with patch.dict(os.environ, {'CUEMS_CONF_PATH': CONF}):
        mappings = get_mappings()
    wire = mappings.to_wire()
    return wire['nodes'] + wire['new_nodes']


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv('CUEMS_CONF_PATH', CONF)
    monkeypatch.setattr(server_module, 'Communicator', MagicMock())
    monkeypatch.setattr(CuemsWsServer, 'nodeconf_available', lambda self: False)
    settings = get_settings()
    settings['tmp_path'] = str(tmp_path)
    return CuemsWsServer(settings, get_mappings())


# ─── the merge (T033) ────────────────────────────────────────────────────


def test_a_converted_node_keeps_node_role_through_the_merge():
    adopted, _unadopted = _library_nodes()
    assert 'node_role' in adopted[0].to_wire() and 'node_type' not in adopted[0].to_wire()

    server = CuemsWsServer.__new__(CuemsWsServer)
    merged = server.merge_node_data(_mapping_nodes(), adopted)

    assert [item['node']['uuid'] for item in merged] == [CONTROLLER]
    assert merged[0]['node']['node_role'] == adopted[0].to_wire()['node_role']


def test_a_node_the_mappings_do_not_know_is_its_own_wire_form():
    adopted, unadopted = _library_nodes()
    server = CuemsWsServer.__new__(CuemsWsServer)
    merged = server.merge_node_data([], adopted + unadopted)
    assert merged == [{'node': node.to_wire()} for node in adopted + unadopted]


# ─── the wire form (T034) ────────────────────────────────────────────────


def _capture_value():
    with open(CAPTURE, encoding='utf-8') as fh:
        return json.load(fh)['value']


def apply_mapping_deltas(captured, library_wire, mapping_uuids):
    """The pre-001 frame moved through the enumerated deltas, and nothing else.

    (m1) ``nodeconf_available`` is present, last. The pre-001 frame lost it:
         ``json.dumps`` of the library mappings object drops undeclared keys.
    (m2) a merged node's status fields are ``to_wire()``'s: ``adopted`` and
         ``online`` are ``"True"`` / ``"False"`` (were JSON booleans), and
         ``node_role`` follows ``name``. The mapping node's own keys, output
         blocks included, keep their place and value.
    (m3) a node only in the map is its own ``to_wire()``, key for key
         (none in this fixture; ``test_a_node_the_mappings_do_not_know_is_its_own_wire_form``).
    """
    value = copy.deepcopy(captured)
    for key in ('nodes', 'new_nodes'):
        moved = []
        for item in value[key]:
            node = item['node']
            wire = library_wire[node['uuid']]
            if node['uuid'] in mapping_uuids:                       # (m2)
                merged = dict(node)
                for field in ('online', 'adopted', 'ip', 'name', 'node_role', 'mac',
                              'role_id', 'alias', 'hostname'):
                    if field in wire:
                        merged[field] = wire[field]
                moved.append({'node': merged})
            else:                                                   # (m3)
                moved.append({'node': wire})
        value[key] = moved
    value['nodeconf_available'] = False                             # (m1)
    return value


def test_initial_mappings_differs_from_the_capture_only_by_the_listed_deltas(server):
    adopted, unadopted = _library_nodes()
    library_wire = {str(n.to_wire()['uuid']): n.to_wire() for n in adopted + unadopted}

    mapping_uuids = {item['node']['uuid'] for item in _mapping_nodes()}
    frame = json.loads(server.initial_setting_message())

    assert frame['type'] == 'initial_mappings'
    expected = apply_mapping_deltas(_capture_value(), library_wire, mapping_uuids)
    assert json.dumps(frame['value']) == json.dumps(expected)


def test_merged_nodes_carry_the_string_wire_form(server):
    frame = json.loads(server.initial_setting_message())
    for key in ('nodes', 'new_nodes'):
        for item in frame['value'][key]:
            node = item['node']
            assert isinstance(node['uuid'], str)
            assert node['adopted'] in ('True', 'False')
            assert node['online'] in ('True', 'False')
            assert 'node_role' in node
            assert 'node_type' not in node


def test_mapping_output_blocks_survive_the_merge_including_an_unnamed_class(server):
    """A merge that only copied audio / video / dmx would lose ``lighting``."""
    frame = json.loads(server.initial_setting_message())
    controller = next(item['node'] for item in frame['value']['nodes']
                      if item['node']['uuid'] == CONTROLLER)
    classes = [d['device']['class'] for d in controller['devices']]
    assert classes == ['audio', 'video', 'dmx', 'lighting']
    assert [d['default']['class'] for d in frame['value']['defaults']] == \
        ['audio', 'audio', 'video', 'video', 'dmx', 'dmx']


# ─── where the shared state is assigned (T038) ───────────────────────────


def test_the_executor_read_does_not_touch_shared_state(server):
    before = copy.deepcopy(server.mappings_dict)
    result = server.reload_network_map_nodes(assign=False)
    assert result
    assert server.mappings_dict == before


def test_both_paths_sample_nodeconf_available_fresh(server):
    with patch.object(CuemsWsServer, 'nodeconf_available', return_value=True):
        assert json.loads(server.initial_setting_message())['value']['nodeconf_available'] is True

    server.users = {}
    server.event_loop = asyncio.new_event_loop()
    server.executor = None   # run_in_executor(None, ...) uses the loop's default
    try:
        with patch.object(CuemsWsServer, 'nodeconf_available', return_value=True):
            server.event_loop.run_until_complete(server.notify_all_node_list_update())
        assert server.mappings_dict['nodeconf_available'] is True
        with patch.object(CuemsWsServer, 'nodeconf_available', return_value=False):
            server.event_loop.run_until_complete(server.notify_all_node_list_update())
        assert server.mappings_dict['nodeconf_available'] is False
    finally:
        server.event_loop.close()


# ─── a duplicate node identity (T039) ────────────────────────────────────


class _Session:
    def __init__(self):
        self.outgoing = asyncio.Queue()

    def drain(self):
        out = []
        while not self.outgoing.empty():
            out.append(json.loads(self.outgoing.get_nowait()))
        return out


def _duplicate_conf(tmp_path):
    conf = tmp_path / 'conf'
    shutil.copytree(CONF, conf)
    text = (conf / 'network_map.xml').read_text()
    (conf / 'network_map.xml').write_text(text.replace(NEW_NODE, CONTROLLER))
    return conf


def test_a_duplicate_identity_is_not_retried_and_is_broadcast(server, tmp_path, monkeypatch):
    conf = _duplicate_conf(tmp_path)
    last_good = copy.deepcopy(server.mappings_dict['nodes'])
    one, two = _Session(), _Session()
    server.users = {one: None, two: None}
    server.event_loop = asyncio.new_event_loop()
    server.executor = None
    sleeps = []
    monkeypatch.setattr(server_module.time, 'sleep', lambda s: sleeps.append(s))
    monkeypatch.setenv('CUEMS_CONF_PATH', str(conf))
    try:
        server.event_loop.run_until_complete(server.notify_all_node_list_update())

        assert all(s < 0.1 for s in sleeps), f'retried with back-off: {sleeps}'
        assert server.mappings_dict['nodes'] == last_good
        for session in (one, two):
            frames = session.drain()
            assert frames == [{'type': 'network_map_error', 'value': {
                'kind': 'duplicate_identity',
                'identity': CONTROLLER,
                'file': str(conf / 'network_map.xml'),
            }}]

        # A session that connects while the error stands is told too.
        late = _Session()
        server.event_loop.run_until_complete(server.send_initial_frames(late))
        assert {'type': 'network_map_error', 'value': {
            'kind': 'duplicate_identity', 'identity': CONTROLLER,
            'file': str(conf / 'network_map.xml')}} in late.drain()

        # The map is fixed: clear, then the usual refresh.
        shutil.copy(os.path.join(CONF, 'network_map.xml'), conf / 'network_map.xml')
        server.event_loop.run_until_complete(server.notify_all_node_list_update())
        for session in (one, two):
            frames = session.drain()
            assert [f['type'] for f in frames] == ['network_map_error', 'initial_mappings']
            assert frames[0]['value'] is None
    finally:
        server.event_loop.close()
