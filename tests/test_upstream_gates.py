# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Upstream gates of the ``xml-refactor-merge-candidate`` tag (002 S6, S7, FR-032).

Each test asserts what the editor will do once another repository fixes a
gap, and is a strict xfail until then: the day it passes it XPASSes, which
fails the suite, and its marker comes off. Every reason names the gate as
``<repo> UR-<n>``. The tag is not cut while any of them is xfailed
(specs/002-config-round-trip/tag-readiness.md).

Gate G1 lives in ``tests/test_schema_descriptor.py``
(``test_first_config_save_of_project_settings_round_trips``).
"""

import asyncio
import hashlib
import json
import shutil
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cuemsutils.helpers import new_uuid
from cuemsutils.tools.ConfigManager import ConfigManager, SchemaName

from test_config_round_trip import PROJECT, _load, _root_instance, _save, env, user  # noqa: F401  (fixtures)
from test_document_load_report import SCRIPT_ID, _drain, _run, _session, _write_variant, lib  # noqa: F401
from test_repair_gate_durable import _close, _make_server

NODECONF = Path(__file__).resolve().parent.parent.parent / 'cuems-nodeconf'
NODE = '4b9b5a1e-0000-4000-8000-0123456789ab'

PROJECT_SETTINGS = (
    "<?xml version='1.0' encoding='utf-8'?>"
    '<cms:CuemsProjectSettings xmlns:cms="https://stagelab.coop/cuems/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="https://stagelab.coop/cuems/ project_settings.xsd">'
    '<setting><name>previous</name><value>0</value></setting>'
    '</cms:CuemsProjectSettings>')


# ─── G2: cuems-editor UR-7 ───────────────────────────────────────────────


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="cuems-editor UR-7: project_settings has no public read projection (gate G2)")
def test_config_load_project_settings_round_trips(env, user):
    (env.project / 'settings.xml').write_text(PROJECT_SETTINGS, encoding='utf-8')

    frames = _load(user, 'project_settings', PROJECT)

    assert [f['type'] for f in frames] == ['config_load']
    value = frames[0]['value']
    assert value['exists'] is True
    assert value['document'] == {'setting': [{'name': 'previous', 'value': '0'}]}


# ─── G3: cuems-frontend UR-1 ─────────────────────────────────────────────

G3 = "cuems-frontend UR-1: the descriptor instance is not in to_wire() shape and has null required defaults (gate G3)"


def _script_instance(name):
    types = ConfigManager(load_all=False).get_schema_descriptor(SchemaName('script'))
    return json.loads(json.dumps(next(t for t in types if t.key.name == name).instance, default=str))


@pytest.mark.xfail(strict=True, raises=AssertionError, reason=G3)
def test_a_cue_built_from_the_descriptor_instance_saves_through_project_save(lib, monkeypatch):
    """Gate G3 (a): a client builds a new audio cue from the descriptor's instances.

    Only what an operator chooses is filled in: the cue's id, its media file
    and its output's name. Everything else is the instance as served.
    """
    monkeypatch.setenv('CUEMS_CONF_PATH', str(Path(__file__).resolve().parent / 'fixtures' / 'conf'))
    _write_variant(lib.script, 'clean')
    cue = _script_instance('AudioCueType')
    cue['id'] = str(new_uuid())
    cue['Media']['file_name'] = 'file.ext'
    cue['Media']['id'] = str(new_uuid())
    output = _script_instance('AudioCueOutputsType')
    output['output_name'] = 'system:playback_1'
    cue['outputs'] = {'CueOutput': [output]}
    payload = json.loads(json.dumps(lib.project.load(SCRIPT_ID)))
    payload['CuemsScript']['CueList']['contents'] = [{'Cue': cue}]

    server = _make_server(lib)
    try:
        session = _session(server)
        _run(server, session.received_project(payload, 'project_save'))
        frames = _drain(session)
    finally:
        _close(server)

    assert frames[:1] == [{'type': 'project_save', 'value': SCRIPT_ID}]


# Gate G3 (b) flipped when cuems-utils feature 015 made every root instance
# saveable; the marker is off and the assertion stays (tag-readiness S6).
@pytest.mark.parametrize('schema', ['settings', 'project_mappings', 'project_settings'])
def test_a_config_root_instance_saves_through_config_save(env, user, schema):
    """Gate G3 (b): a config root-type instance, saved over an existing file.

    The file exists and ``base_revision`` is its md5, so neither G1 (a first
    save) nor a conflict is in the way: only the instance is.
    """
    if schema == 'settings':
        target, project_uuid = env.settings, None
    elif schema == 'project_mappings':
        target, project_uuid = env.mappings, PROJECT
        shutil.copy(env.conf / 'default_mappings.xml', target)
    else:
        target, project_uuid = env.project / 'settings.xml', PROJECT
        target.write_text(PROJECT_SETTINGS, encoding='utf-8')
    revision = hashlib.md5(target.read_bytes()).hexdigest()

    frames = _save(user, schema, _root_instance(schema), revision, project_uuid)

    assert [f['type'] for f in frames] == ['config_save']


# ─── G4: cuems-editor UR-8 ───────────────────────────────────────────────


class _Replies:
    """nodeconf's ``communications_thread``, reduced to the reply path, on a loop of its own."""

    def __init__(self):
        self.event_loop = asyncio.new_event_loop()
        self.replies = []
        self.answered = threading.Event()
        self.thread = threading.Thread(target=self.event_loop.run_forever, daemon=True)
        self.thread.start()

    async def respond_to_engine(self, message, context):
        self.replies.append(message)
        self.answered.set()

    def stop(self):
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join(timeout=5)
        self.event_loop.close()


def test_nodeconf_engine_callback_accepts_node_set(monkeypatch, tmp_path):
    """Gate G4 (closed): nodeconf's real handler, given the exact request the editor sends.

    Imports ``cuemsnodeconf.CuemsNodeConf`` from the sibling ``../cuems-nodeconf``
    working tree (``feat/xml-refactor`` at ``3d3601d`` or later, on cuems-utils
    ``38d2ede`` or later), with its OS-facing modules stubbed. The map holds
    ``NODE`` and is written for real to ``tmp_path``, so the alias is checked
    on disk. An import failure errors; it is not a skip.
    """
    if not NODECONF.is_dir():
        pytest.skip('../cuems-nodeconf is not checked out here (a deployed host)')
    monkeypatch.syspath_prepend(str(NODECONF))
    for module in ('netifaces', 'systemd', 'systemd.daemon', 'dbus', 'zeroconf'):
        monkeypatch.setitem(sys.modules, module, MagicMock())
    for module in [m for m in sys.modules if m == 'cuemsnodeconf' or m.startswith('cuemsnodeconf.')]:
        monkeypatch.delitem(sys.modules, module)
    from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf
    from cuemsutils.config.network_map import CuemsNetworkMapType
    from cuemsutils.tools.NodeList import NodeIndex, NodeRole, node as Node

    nodeconf = CuemsNodeConf()
    nodeconf._ready = True
    nodeconf._document = CuemsNetworkMapType()
    nodeconf.network_map = NodeIndex()
    nodeconf.map_path = str(tmp_path / 'network_map.xml')
    nodeconf.network_map['aabbccddee01'] = Node(
        uuid=NODE, mac='aabbccddee01', name='aabbccddee01._cuems_nodeconf._tcp.local.',
        node_role=NodeRole.node, ip='169.254.0.9', adopted=True, online=True,
    )
    nodeconf._save_network_map()
    nodeconf.communications_thread = replies = _Replies()
    try:
        nodeconf.engine_callback({'action': 'node_set', 'node_uuid': NODE, 'alias': 'Stage left'}, context=None)
        assert replies.answered.wait(timeout=5), 'engine_callback did not answer'
    finally:
        replies.stop()

    assert replies.replies == [{'OK': True}]
    assert '<alias>Stage left</alias>' in Path(nodeconf.map_path).read_text()
