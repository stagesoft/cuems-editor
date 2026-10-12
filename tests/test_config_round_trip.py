# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``config_load`` and the revision-checked ``config_save`` (002 US2, FR-012 to FR-023, FR-015a).

The UI reads a configuration file's real values with its md5 (``revision``),
edits them, and saves the whole document with that revision as
``base_revision``. A stale save is ``config_conflict``; a document the library
refuses is ``config_save_refused`` with the violation's location; the file
replaced is backed up into ``<library>/trash/config/`` first.

Fixtures: a copy of ``tests/fixtures/conf`` as ``CUEMS_CONF_PATH``, its
``settings.xml``'s ``<library_path>`` rewritten to a temporary library that
holds ``projects/test_project/``. ``get_project_unix_name`` is mocked to
``test_project``. Nothing under ``/opt/cuems_library`` is touched.
"""

import asyncio
import concurrent.futures
import copy
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import cuemseditor.CuemsWsUser as ws_user
from cuemseditor.CuemsErrors import NonExistentItemError
from cuemseditor.CuemsWsUser import CuemsWsUser
from cuemsutils.tools.ConfigManager import ConfigManager, SchemaName

HERE = Path(__file__).resolve().parent
CONF = HERE / 'fixtures' / 'conf'
PACKAGE = HERE.parent / 'src' / 'cuemseditor'
PRE_013_SETTINGS = HERE.parent.parent / 'cuems-utils' / 'tests' / 'data' / 'corpus' / 'pre-013' / 'settings.xml'
PROJECT = 'c0ffee00-0000-4000-8000-000000000002'
RESTART_SETTINGS = [{'service': 'cuems-controller-engine', 'where_active': False},
                    {'service': 'cuems-node-engine', 'where_active': True}]


class Env:
    def __init__(self, conf, library):
        self.conf = conf
        self.library = library
        self.project = library / 'projects' / 'test_project'
        self.settings = conf / 'settings.xml'
        self.mappings = self.project / 'mappings.xml'
        self.backups = library / 'trash' / 'config'


@pytest.fixture
def env(tmp_path, monkeypatch):
    conf = tmp_path / 'conf'
    shutil.copytree(CONF, conf)
    library = tmp_path / 'library'
    (library / 'projects' / 'test_project').mkdir(parents=True)
    settings = conf / 'settings.xml'
    settings.write_text(settings.read_text(encoding='utf-8').replace(
        '<library_path>/opt/cuems_library</library_path>',
        f'<library_path>{library}</library_path>'), encoding='utf-8')
    monkeypatch.setenv('CUEMS_CONF_PATH', str(conf))
    return Env(conf, library)


@pytest.fixture
def user(env):
    server = MagicMock()
    server.users = {}
    server.sessions = {}
    server.repair_gates = {}
    server.file_locks = {}
    server.event_loop = asyncio.new_event_loop()
    server.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    server.db.project.get_project_unix_name = MagicMock(return_value='test_project')
    server.notify_others_config_changed = AsyncMock()
    server.notify_all_node_list_update = AsyncMock()
    session = CuemsWsUser(server, MagicMock())
    session.session_id = 'saver'
    server.users[session] = None
    yield session
    server.executor.shutdown(wait=True)
    server.event_loop.close()


def _drain(user):
    out = []
    while not user.outgoing.empty():
        out.append(json.loads(user.outgoing.get_nowait()))
    return out


def _call(user, coro):
    user.server.event_loop.run_until_complete(coro)
    return _drain(user)


def _load(user, schema, project_uuid=None):
    value = {'schema': schema}
    if project_uuid is not None:
        value['project_uuid'] = project_uuid
    return _call(user, user.config_load(value, 'config_load'))


def _save(user, schema, document, base_revision, project_uuid=None):
    value = {'schema': schema, 'document': document, 'base_revision': base_revision}
    if project_uuid is not None:
        value['project_uuid'] = project_uuid
    return _call(user, user.config_save(value, 'config_save'))


def _md5(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _root_instance(schema):
    types = ConfigManager(load_all=False).get_schema_descriptor(SchemaName(schema))
    root = next(t for t in types if t.key.is_path and '/' not in t.key.name)
    return json.loads(json.dumps(root.instance, default=str))


def _mappings_wire():
    manager = ConfigManager(load_all=False)
    manager.load_net_and_node_mappings()
    manager.load_project_mappings('test_project')
    return manager.to_wire('project_mappings')


def _with_mappings(env):
    shutil.copy(env.conf / 'default_mappings.xml', env.mappings)


# ─── config_load (FR-012, FR-013, FR-014) ────────────────────────────────


def test_config_load_settings_serves_the_file(env, user):
    frames = _load(user, 'settings')

    assert [f['type'] for f in frames] == ['config_load']
    value = frames[0]['value']
    assert value['schema'] == 'settings'
    assert value['project_uuid'] is None
    assert value['exists'] is True
    assert value['revision'] == _md5(env.settings)
    assert value['document'] == ConfigManager(load_all=False).to_wire('settings')


def test_config_load_network_map_is_read_only_and_loaded(env, user):
    frames = _load(user, 'network_map')

    value = frames[0]['value']
    assert frames[0]['type'] == 'config_load'
    assert value['exists'] is True
    assert value['revision'] == _md5(env.conf / 'network_map.xml')
    assert list(value['document']) == ['node_list']
    manager = ConfigManager(load_all=False)
    manager.load_network_map()
    assert value['document'] == json.loads(json.dumps(manager.to_wire('network_map')))


def test_config_load_project_mappings_with_its_uuid(env, user):
    _with_mappings(env)

    frames = _load(user, 'project_mappings', PROJECT)

    value = frames[0]['value']
    assert frames[0]['type'] == 'config_load'
    assert value['project_uuid'] == PROJECT
    assert value['exists'] is True
    assert value['revision'] == _md5(env.mappings)
    assert value['document'] == json.loads(json.dumps(_mappings_wire()))
    user.server.db.project.get_project_unix_name.assert_called_once_with(PROJECT)


def test_config_load_without_a_file_is_exists_false_with_the_root_instance(env, user):
    frames = _load(user, 'project_mappings', PROJECT)

    assert [f['type'] for f in frames] == ['config_load']
    value = frames[0]['value']
    assert value['exists'] is False
    assert value['revision'] is None
    assert value['document'] == _root_instance('project_mappings')


@pytest.mark.parametrize('schema', ['project_mappings', 'project_settings'])
def test_config_load_of_a_project_domain_needs_a_project_uuid(env, user, schema):
    frames = _load(user, schema)
    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_load'


def test_config_load_of_an_unknown_project_is_the_error_frame(env, user):
    user.server.db.project.get_project_unix_name.side_effect = NonExistentItemError(
        'item with uuid: bogus does not exist')
    frames = _load(user, 'project_mappings', 'bogus')
    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_load'


@pytest.mark.parametrize('schema', ['outputs', 'default_mappings', None, 'script', 'hardware_outputs'])
def test_config_load_of_a_non_domain_is_the_error_frame(env, user, schema):
    frames = _load(user, schema)
    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_load'


def test_config_load_of_project_settings_is_refused_naming_ur7(env, user):
    frames = _load(user, 'project_settings', PROJECT)
    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_load'
    assert 'cuems-editor UR-7' in frames[0]['value']


def test_a_pre_013_settings_is_config_load_failed(env, user):
    env.settings.write_text(PRE_013_SETTINGS.read_text(encoding='utf-8').replace(
        '/opt/cuems_library', str(env.library)), encoding='utf-8')

    frames = _load(user, 'settings')

    assert [f['type'] for f in frames] == ['config_load_failed']
    value = frames[0]['value']
    assert value['schema'] == 'settings' and value['project_uuid'] is None
    assert 'pre-013 device shape' in value['message']
    assert value['field'] is None and value['location'] is None and value['rule'] is None


# ─── config_save: the round trip (FR-015, FR-016, SC-004) ────────────────


def test_round_trip_settings(env, user):
    loaded = _load(user, 'settings')[0]['value']
    document = copy.deepcopy(loaded['document'])
    document['editor_url'] = 'stage.local'

    frames = _save(user, 'settings', document, loaded['revision'])

    assert frames == [{'type': 'config_save', 'value': {
        'schema': 'settings', 'project_uuid': None, 'revision': _md5(env.settings),
        'restart': RESTART_SETTINGS}}]
    again = _load(user, 'settings')[0]['value']
    assert again['revision'] == frames[0]['value']['revision'] != loaded['revision']
    assert again['document'] == document


def test_round_trip_project_mappings(env, user):
    _with_mappings(env)
    loaded = _load(user, 'project_mappings', PROJECT)[0]['value']
    document = copy.deepcopy(loaded['document'])
    document['defaults'][0]['default']['&'] = '0367f391-ebf4-48b2-9f26-000000000001_system:capture_2'

    frames = _save(user, 'project_mappings', document, loaded['revision'], PROJECT)

    assert frames == [{'type': 'config_save', 'value': {
        'schema': 'project_mappings', 'project_uuid': PROJECT, 'revision': _md5(env.mappings),
        'restart': []}}]
    again = _load(user, 'project_mappings', PROJECT)[0]['value']
    assert again['revision'] == frames[0]['value']['revision'] != loaded['revision']
    assert again['document'] == document


def test_a_stale_base_revision_is_config_conflict_and_writes_nothing(env, user):
    loaded = _load(user, 'settings')[0]['value']
    stale = 'f' * 32
    before = _sha256(env.settings)

    frames = _save(user, 'settings', loaded['document'], stale)

    assert frames == [{'type': 'config_conflict', 'value': {
        'schema': 'settings', 'project_uuid': None,
        'revision': loaded['revision'], 'document': loaded['document']}}]
    assert _sha256(env.settings) == before
    assert not env.backups.exists()
    user.server.notify_others_config_changed.assert_not_awaited()


def test_two_simultaneous_saves_write_once_and_conflict_once(env, user):
    loaded = _load(user, 'settings')[0]['value']
    first, second = copy.deepcopy(loaded['document']), copy.deepcopy(loaded['document'])
    first['editor_url'] = 'first.local'
    second['editor_url'] = 'second.local'

    def save(document):
        return user.config_save({'schema': 'settings', 'document': document,
                                 'base_revision': loaded['revision']}, 'config_save')

    async def both():
        await asyncio.gather(save(first), save(second))

    frames = _call(user, both())

    assert sorted(f['type'] for f in frames) == ['config_conflict', 'config_save']
    saved = next(f for f in frames if f['type'] == 'config_save')['value']
    conflict = next(f for f in frames if f['type'] == 'config_conflict')['value']
    assert conflict['revision'] == saved['revision'] == _md5(env.settings)
    assert len(list(env.backups.iterdir())) == 1


# ─── config_save: refusals (Q3, FR-019, FR-020, SC-006) ──────────────────


def test_missing_base_revision_is_refused(env, user):
    loaded = _load(user, 'settings')[0]['value']
    before = _sha256(env.settings)

    frames = _call(user, user.config_save({'schema': 'settings', 'document': loaded['document']}, 'config_save'))

    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_save'
    assert 'base_revision' in frames[0]['value']
    assert _sha256(env.settings) == before


def test_null_base_revision_with_an_existing_file_conflicts(env, user):
    loaded = _load(user, 'settings')[0]['value']
    before = _sha256(env.settings)

    frames = _save(user, 'settings', loaded['document'], None)

    assert [f['type'] for f in frames] == ['config_conflict']
    assert frames[0]['value']['revision'] == loaded['revision']
    assert _sha256(env.settings) == before


def test_network_map_save_is_refused_and_names_node_set(env, user):
    loaded = _load(user, 'network_map')[0]['value']
    path = env.conf / 'network_map.xml'
    before = _sha256(path)

    frames = _save(user, 'network_map', loaded['document'], loaded['revision'])

    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_save'
    assert 'node_set' in frames[0]['value'] and 'cuems-nodeconf' in frames[0]['value']
    assert _sha256(path) == before
    user.server.notify_all_node_list_update.assert_not_awaited()


def test_no_source_path_writes_network_map():
    assert 'network_map' not in ws_user.CONFIG_SAVE_TARGETS
    offenders = [f'{p.name}:{n}' for p in sorted(PACKAGE.glob('*.py'))
                 for n, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1)
                 if 'save_network_map' in line]
    assert offenders == []


def _library_refusal(document):
    """The library's own refusal of *document*, to compare the frame with verbatim."""
    try:
        ConfigManager(load_all=False).from_json(SchemaName('project_mappings'), document).save(os.devnull)
    except Exception as error:
        return error
    raise AssertionError('the library accepted the document')


def test_a_library_refusal_is_config_save_refused_with_its_location(env, user):
    _with_mappings(env)
    loaded = _load(user, 'project_mappings', PROJECT)[0]['value']
    document = copy.deepcopy(loaded['document'])
    document['defaults'][0]['default']['direction'] = 'sideways'
    before = _sha256(env.mappings)

    frames = _save(user, 'project_mappings', document, loaded['revision'], PROJECT)

    assert frames == [{'type': 'config_save_refused', 'value': {
        'schema': 'project_mappings', 'project_uuid': PROJECT,
        'field': 'default', 'location': [None, 'default'], 'rule': 'XsdEnumerationFacets',
        'message': str(_library_refusal(document))}}]
    assert _sha256(env.mappings) == before
    assert not env.backups.exists() or list(env.backups.iterdir()) == []
    user.server.notify_others_config_changed.assert_not_awaited()


def test_an_unknown_top_level_key_is_config_save_refused_without_location(env, user):
    _with_mappings(env)
    revision = _md5(env.mappings)
    before = _sha256(env.mappings)

    frames = _save(user, 'project_mappings', {'bogus': 1}, revision, PROJECT)

    assert [f['type'] for f in frames] == ['config_save_refused']
    value = frames[0]['value']
    assert value['field'] is None and value['location'] is None and value['rule'] is None
    assert 'expected a project_mappings document' in value['message']
    assert _sha256(env.mappings) == before


# ─── config_save: restart notice, broadcast, backup (FR-016, FR-017, FR-015a)


def test_settings_save_names_the_engines_to_restart(env, user):
    _with_mappings(env)
    settings = _load(user, 'settings')[0]['value']
    mappings = _load(user, 'project_mappings', PROJECT)[0]['value']

    saved_settings = _save(user, 'settings', settings['document'], settings['revision'])
    saved_mappings = _save(user, 'project_mappings', mappings['document'], mappings['revision'], PROJECT)

    assert saved_settings[0]['value']['restart'] == RESTART_SETTINGS
    assert saved_mappings[0]['value']['restart'] == []


def test_other_sessions_get_config_changed(env, user):
    loaded = _load(user, 'settings')[0]['value']

    frames = _save(user, 'settings', loaded['document'], loaded['revision'])

    assert [f['type'] for f in frames] == ['config_save']
    user.server.notify_others_config_changed.assert_awaited_once_with(user, {
        'schema': 'settings', 'project_uuid': None, 'revision': frames[0]['value']['revision']})


def test_notify_others_config_changed_skips_the_saver():
    from cuemseditor.CuemsWsServer import CuemsWsServer

    server = MagicMock()
    saver, other = MagicMock(), MagicMock()
    saver.outgoing.put = AsyncMock()
    other.outgoing.put = AsyncMock()
    server.users = {saver: None, other: PROJECT}
    value = {'schema': 'settings', 'project_uuid': None, 'revision': 'a' * 32}

    asyncio.new_event_loop().run_until_complete(
        CuemsWsServer.notify_others_config_changed(server, saver, value))

    saver.outgoing.put.assert_not_awaited()
    other.outgoing.put.assert_awaited_once_with(json.dumps({'type': 'config_changed', 'value': value}))


@pytest.mark.parametrize('schema, scope, stem', [
    ('settings', 'controller', 'settings'),
    ('project_mappings', 'test_project', 'mappings'),
])
def test_the_replaced_file_is_backed_up_first(env, user, schema, scope, stem):
    _with_mappings(env)
    project_uuid = PROJECT if schema == 'project_mappings' else None
    target = env.settings if schema == 'settings' else env.mappings
    original = target.read_bytes()
    loaded = _load(user, schema, project_uuid)[0]['value']

    frames = _save(user, schema, loaded['document'], loaded['revision'], project_uuid)

    assert frames[0]['type'] == 'config_save'
    backups = list(env.backups.iterdir())
    assert len(backups) == 1
    assert re.fullmatch(rf'{scope}_{stem}_\d{{8}}T\d{{6}}\.xml', backups[0].name)
    assert backups[0].read_bytes() == original


def test_a_failed_backup_saves_nothing(env, user):
    loaded = _load(user, 'settings')[0]['value']
    env.backups.parent.mkdir(parents=True)
    env.backups.write_text('a file where the backup directory belongs')
    before = _sha256(env.settings)

    frames = _save(user, 'settings', loaded['document'], loaded['revision'])

    assert frames[0]['type'] == 'error' and frames[0]['action'] == 'config_save'
    assert _sha256(env.settings) == before
    user.server.notify_others_config_changed.assert_not_awaited()
