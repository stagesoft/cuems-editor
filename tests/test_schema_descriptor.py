# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``schema_descriptor`` serves the library's descriptor; ``config_save`` refuses what it must (FR-045).

The descriptor is ``ConfigManager.get_schema_descriptor(SchemaName)`` and
nothing else; this checks the editor carries it to the wire intact, not what
the library puts in it. ``config_save`` must refuse ``script`` (that is
``project_save``), ``hardware_outputs`` (no model bindings), anything that is
not a ``SchemaName``, and any write of ``default_mappings.xml``.

Persisting ``settings``/``network_map`` goes through ``ConfigManager.from_json``
(cuemsutils 014, UR-5). ``project_mappings``/``project_settings`` still have
no project identifier on this action's wire shape, so ``config_save`` of
either still answers an error.
"""

import asyncio
import concurrent.futures
import json
import os
import shutil
from unittest.mock import MagicMock

import pytest

from cuemseditor.CuemsWsUser import CuemsWsUser
from cuemsutils.tools.ConfigManager import ConfigManager, SchemaName

HERE = os.path.dirname(__file__)
CONF = os.path.join(HERE, 'fixtures', 'conf')
FIELD_KEYS = ['name', 'xsd_type', 'required', 'repeated', 'order', 'kind',
              'enum_values', 'default', 'repairability']


@pytest.fixture
def conf(tmp_path, monkeypatch):
    target = tmp_path / 'conf'
    shutil.copytree(CONF, target)
    monkeypatch.setenv('CUEMS_CONF_PATH', str(target))
    return target


@pytest.fixture
def user(conf):
    server = MagicMock()
    server.users = {}
    server.event_loop = asyncio.new_event_loop()
    server.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    session = CuemsWsUser(server, MagicMock())
    yield session
    server.executor.shutdown(wait=True)
    server.event_loop.close()


def _call(user, coro):
    user.server.event_loop.run_until_complete(coro)
    out = []
    while not user.outgoing.empty():
        out.append(json.loads(user.outgoing.get_nowait()))
    return out


@pytest.mark.parametrize('schema', [s.value for s in SchemaName])
def test_schema_descriptor_carries_the_library_descriptor(user, schema):
    frames = _call(user, user.schema_descriptor(schema, 'schema_descriptor'))

    assert len(frames) == 1 and frames[0]['type'] == 'schema_descriptor'
    value = frames[0]['value']
    assert value['schema'] == schema
    library = ConfigManager(load_all=False).get_schema_descriptor(SchemaName(schema))
    assert [t['key'] for t in value['types']] == [str(t.key) for t in library]
    for served, own in zip(value['types'], library):
        assert set(served) == {'key', 'fields', 'instance'}
        assert [f['name'] for f in served['fields']] == [f.name for f in own.fields]
        for field in served['fields']:
            assert list(field) == FIELD_KEYS


def test_schema_descriptor_of_an_unknown_schema_is_an_error(user):
    frames = _call(user, user.schema_descriptor('outputs', 'schema_descriptor'))
    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'schema_descriptor'


@pytest.mark.parametrize('schema', ['script', 'hardware_outputs', 'default_mappings', 'outputs', None])
def test_config_save_refuses(user, conf, schema):
    before = {p.name: p.read_bytes() for p in conf.iterdir()}
    frames = _call(user, user.config_save({'schema': schema, 'document': {}}, 'config_save'))

    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_save'
    assert {p.name: p.read_bytes() for p in conf.iterdir()} == before


def test_config_save_of_settings_persists_through_save_settings(user, conf):
    manager = ConfigManager(load_all=False)
    document = manager.to_wire('settings')
    frames = _call(user, user.config_save({'schema': 'settings', 'document': document}, 'config_save'))
    assert frames == [{'type': 'config_save', 'value': 'OK'}]
