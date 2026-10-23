# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``schema_descriptor`` serves the library's descriptor; ``config_save`` refuses what it must (FR-045).

The descriptor is ``ConfigManager.get_schema_descriptor(SchemaName)`` and
nothing else; this checks the editor carries it to the wire intact, not what
the library puts in it. ``config_save`` must refuse ``script`` (that is
``project_save``), ``hardware_outputs`` (no model bindings), anything that is
not a ``SchemaName``, and any write of ``default_mappings.xml``.

All four domains persist through ``ConfigManager.from_json`` (cuemsutils 014,
UR-5). ``project_mappings``/``project_settings`` additionally need
``value["project_uuid"]``, resolved to a ``unix_name`` the same way
``project_ready`` resolves one. Pending cuems-utils UR-6, a project's
``config_save`` still fails before the target file has ever been saved —
``ConfigManager.project_path`` raises ``FileNotFoundError`` for it (gate G1).

Since 002 every ``config_save`` carries ``base_revision`` (Q3) and is answered
with an object, not ``"OK"`` (M3), and ``network_map`` is refused (FR-019).
The config round trip itself is ``tests/test_config_round_trip.py``.
"""

from support.paths import DATA_DIR
import asyncio
import concurrent.futures
import hashlib
import json
import os
import shutil
from unittest.mock import AsyncMock, MagicMock

import pytest

from cuemseditor.CuemsErrors import NonExistentItemError
from cuemseditor.CuemsWsUser import CuemsWsUser
from cuemsutils.tools.ConfigManager import ConfigManager, SchemaName

CONF = str(DATA_DIR / 'conf')
FIELD_KEYS = ['name', 'xsd_type', 'required', 'repeated', 'order', 'kind',
              'enum_values', 'default', 'repairability']


@pytest.fixture
def conf(tmp_path, monkeypatch):
    target = tmp_path / 'conf'
    shutil.copytree(CONF, target)
    # config_save backs up into <library_path>/trash/config: keep it in tmp_path,
    # where project_dir points ConfigManager.library_path too.
    settings = target / 'settings.xml'
    settings.write_text(settings.read_text(encoding='utf-8').replace(
        '<library_path>/opt/cuems_library</library_path>',
        f'<library_path>{tmp_path}</library_path>'), encoding='utf-8')
    monkeypatch.setenv('CUEMS_CONF_PATH', str(target))
    return target


@pytest.fixture
def user(conf):
    server = MagicMock()
    server.users = {}
    server.repair_gates = {}
    server.file_locks = {}
    server.notify_others_config_changed = AsyncMock()
    server.event_loop = asyncio.new_event_loop()
    server.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    session = CuemsWsUser(server, MagicMock())
    yield session
    server.executor.shutdown(wait=True)
    server.event_loop.close()


def _md5(path):
    with open(path, 'rb') as fh:
        return hashlib.md5(fh.read()).hexdigest()


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


@pytest.mark.parametrize('schema', ['script', 'hardware_outputs', 'network_map', 'default_mappings', 'outputs', None])
def test_config_save_refuses(user, conf, schema):
    before = {p.name: p.read_bytes() for p in conf.iterdir()}
    base_revision = _md5(conf / 'network_map.xml') if schema == 'network_map' else None
    frames = _call(user, user.config_save(
        {'schema': schema, 'document': {}, 'base_revision': base_revision}, 'config_save'))

    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_save'
    assert {p.name: p.read_bytes() for p in conf.iterdir()} == before


def test_config_save_of_settings_persists_through_save_settings(user, conf):
    manager = ConfigManager(load_all=False)
    document = manager.to_wire('settings')
    frames = _call(user, user.config_save(
        {'schema': 'settings', 'document': document, 'base_revision': _md5(conf / 'settings.xml')}, 'config_save'))
    assert [f['type'] for f in frames] == ['config_save']
    assert frames[0]['value']['schema'] == 'settings'
    assert frames[0]['value']['revision'] == _md5(conf / 'settings.xml')


# ─── project_mappings / project_settings need a project_uuid ─────────────


@pytest.fixture
def project_dir(monkeypatch, tmp_path):
    """Redirects ``ConfigManager.library_path`` at a scratch directory, so the
    real, unmodified ``project_path`` resolves under it instead of under
    ``/opt/cuems_library`` (``tests/data/conf/settings.xml``'s value — a
    real path this sandbox must not touch, and which happens to exist on some
    dev machines via a sibling repo's fixtures). ``project_path``'s existence
    check — the thing cuems-utils UR-6 is petitioning to relax — runs for
    real here, unlike cuems-utils' own ``project_config_manager`` fixture
    (``tests/integration/test_config_manager_save_accessors.py``), which
    monkeypatches ``project_path`` itself and so never exercises it.
    """
    directory = tmp_path / 'projects' / 'test_project'
    directory.mkdir(parents=True)
    monkeypatch.setattr(ConfigManager, 'library_path', property(lambda self: str(tmp_path)))
    return directory


@pytest.mark.parametrize('schema', ['project_mappings', 'project_settings'])
def test_config_save_of_a_project_schema_needs_a_project_uuid(user, conf, schema):
    frames = _call(user, user.config_save({'schema': schema, 'document': {}, 'base_revision': None}, 'config_save'))
    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_save'
    assert 'project_uuid' in frames[0]['value']


@pytest.mark.parametrize('schema', ['project_mappings', 'project_settings'])
def test_config_save_of_a_project_schema_refuses_an_unknown_project(user, conf, schema):
    user.server.db.project.get_project_unix_name.side_effect = NonExistentItemError(
        "item with uuid: bogus does not exist")
    frames = _call(user, user.config_save(
        {'schema': schema, 'document': {}, 'project_uuid': 'bogus', 'base_revision': None}, 'config_save'))
    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_save'


def test_first_config_save_of_project_settings_round_trips(user, conf, project_dir):
    """Gate G1 (closed): a project's first ``config_save`` (no file, ``base_revision`` null).

    cuems-utils 015 gave ``project_path``/``conf_path`` a keyword-only
    ``must_exist``; the write site passes ``must_exist=False`` and creates the
    file with no backup. The value is checked in the written file, so this
    gate stays independent of G2's ``config_load``. The marker is off and the
    assertion stays (S6).
    """
    user.server.db.project.get_project_unix_name.return_value = 'test_project'
    document = {'setting': [{'name': 'example', 'value': '1'}]}
    frames = _call(user, user.config_save(
        {'schema': 'project_settings', 'document': document, 'project_uuid': 'irrelevant-here',
         'base_revision': None}, 'config_save'))
    assert [f['type'] for f in frames] == ['config_save']
    saved = (project_dir / 'settings.xml').read_text(encoding='utf-8')
    assert '<name>example</name>' in saved and '<value>1</value>' in saved


def test_config_save_of_project_settings_persists_once_the_file_exists(user, conf, project_dir):
    (project_dir / 'settings.xml').write_text(
        "<?xml version='1.0' encoding='utf-8'?>"
        '<cms:CuemsProjectSettings xmlns:cms="https://stagelab.coop/cuems/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xsi:schemaLocation="https://stagelab.coop/cuems/ project_settings.xsd">'
        '<setting><name>previous</name><value>0</value></setting>'
        '</cms:CuemsProjectSettings>', encoding='utf-8')
    user.server.db.project.get_project_unix_name.return_value = 'test_project'
    document = {'setting': [{'name': 'example', 'value': '1'}]}

    frames = _call(user, user.config_save(
        {'schema': 'project_settings', 'document': document, 'project_uuid': 'some-uuid',
         'base_revision': _md5(project_dir / 'settings.xml')}, 'config_save'))

    assert frames == [{'type': 'config_save', 'value': {
        'schema': 'project_settings', 'project_uuid': 'some-uuid',
        'revision': _md5(project_dir / 'settings.xml'), 'restart': []}}]
    saved = (project_dir / 'settings.xml').read_text(encoding='utf-8')
    assert '<name>example</name>' in saved and '<value>1</value>' in saved
    assert 'previous' not in saved
