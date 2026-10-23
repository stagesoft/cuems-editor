# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>

"""Save-time gate for media cues without a usable media block (869fej07m).

The frontend drops a cue's whole ``Media`` block when it cannot match the
file in its library list (e.g. the file is in the media trash). Before this
gate, such a save died inside the atomic transaction with a bare
``KeyError 'file_name'`` (``CueList.get_media``, cuems-utils < rc16) — and
had it not died, it would have written an empty ``<Media/>`` and lost the
cue's media. Pinned here:

* every shape the wire can carry is rejected, with the cue named;
* nested CueLists are walked;
* a trashed-but-known file passes, an unknown one is rejected;
* ``update()`` refuses before writing anything: project row, ProjectMedia
  rows and the XML are byte-identical afterwards (the duration fixer used
  to write Media rows before the fade gate ran);
* the WS layer forwards a ``ValueError`` without the ``<class …>`` prefix.
"""

import os
from unittest import mock

import pytest

from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Media, Project, ProjectMedia, database
from cuemseditor.CuemsDBProject import (
    CuemsDBProject,
    validate_media_cues_in_contents,
)
from cuemseditor.CuemsWsUser import CuemsWsUser


def _audio(media, name='A1', cue_id='a1-uuid'):
    cue = {'name': name, 'id': cue_id}
    if media is not mock.sentinel.absent:
        cue['Media'] = media
    return {'AudioCue': cue}


def _video(media, name='V1', cue_id='v1-uuid'):
    return {'VideoCue': {'name': name, 'id': cue_id, 'Media': media}}


GOOD = {'file_name': 'file.ext', 'id': 'm-1', 'duration': '00:00:01.000', 'regions': []}


# ─── shapes ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    'media, reason',
    [
        (mock.sentinel.absent, 'no media file'),        # the frontend's shape
        (None, 'no media file'),                         # JSON null
        ({}, 'no media file'),                           # the model default
        ({'id': 'm-1'}, 'no media file'),                # no file_name key
        ({'file_name': '', 'id': 'm-1'}, 'no media file'),
        ({'file_name': None, 'id': 'm-1'}, 'no media file'),
        ({'file_name': 'file.ext'}, 'media block has no id'),
    ],
)
def test_every_bad_shape_is_rejected_naming_the_cue(media, reason):
    with pytest.raises(ValueError) as e:
        validate_media_cues_in_contents([_audio(media, name='Intro', cue_id='c-9')])
    text = str(e.value)
    assert "'Intro'" in text and 'c-9' in text and reason in text


def test_good_cues_pass_and_action_cues_are_ignored():
    validate_media_cues_in_contents([
        _audio(GOOD), _video(dict(GOOD, file_name='file_video.ext')),
        {'ActionCue': {'name': 'go', 'id': 'x'}},
        {'FadeCue': {'name': 'f', 'id': 'y'}},
    ])


def test_nested_cuelist_is_walked():
    nested = {'CueList': {'id': 'l', 'contents': [_video(None, name='Deep', cue_id='d-1')]}}
    with pytest.raises(ValueError) as e:
        validate_media_cues_in_contents([_audio(GOOD), nested])
    assert "'Deep'" in str(e.value)


def test_all_offenders_are_listed_once():
    with pytest.raises(ValueError) as e:
        validate_media_cues_in_contents([
            _audio(None, name='One', cue_id='1'),
            _audio(GOOD),
            _video({}, name='Two', cue_id='2'),
        ])
    assert "'One'" in str(e.value) and "'Two'" in str(e.value)
    assert str(e.value).count('(id ') == 2


def test_media_exists_hook_rejects_unknown_files_only():
    known = {'file.ext', 'tone_c.wav'}  # tone_c.wav is in the trash: still known
    validate_media_cues_in_contents(
        [_audio(dict(GOOD, file_name='tone_c.wav'))], media_exists=known.__contains__
    )
    with pytest.raises(ValueError) as e:
        validate_media_cues_in_contents(
            [_audio(dict(GOOD, file_name='nope.wav'), name='Gone')], media_exists=known.__contains__
        )
    assert "'nope.wav' does not exist" in str(e.value)


# ─── update() refuses before writing ──────────────────────────────────────


def _settings(library):
    settings = get_settings()
    settings['library_path'] = library.root
    return settings


def _manager(library):
    library.connect()
    return CuemsDBProject(_settings(library), database)


def _snapshot(library):
    library.connect()
    try:
        p = Project.get(Project.unix_name == 'proj1')
        rows = sorted(
            (str(pm.media.uuid), pm.media_filename)
            for pm in ProjectMedia.select().where(ProjectMedia.project == p)
        )
        return (p.name, str(p.modified), str(p.description), rows)
    finally:
        database.close()


def _xml(library):
    with open(os.path.join(library.projects_dir, 'proj1', 'script.xml'), 'rb') as f:
        return f.read()


def test_update_refuses_a_media_less_cue_and_writes_nothing(library):
    mgr = _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    data = mgr.load(uuid)
    database.close()
    # Link the fixture's media so the ProjectMedia snapshot is non-trivial.
    mgr2 = _manager(library)
    with mock.patch('cuemseditor.CuemsDBProject.probe_dimensions', return_value=(1, 1)):
        mgr2.update(uuid, mgr2.load(uuid))
    database.close()
    before_db, before_xml = _snapshot(library), _xml(library)

    # The frontend's shape: the AudioCue arrives with no Media key at all.
    bad = mgr.load(uuid) if not database.is_closed() else _manager(library).load(uuid)
    for item in bad['CuemsScript']['CueList']['contents']:
        if 'AudioCue' in item:
            item['AudioCue']['name'] = 'renamed'
            del item['AudioCue']['Media']
    with pytest.raises(ValueError) as e:
        _manager(library).update(uuid, bad)
    if not database.is_closed():
        database.close()

    assert "'renamed'" in str(e.value) and 'no media file' in str(e.value)
    assert _snapshot(library) == before_db
    assert _xml(library) == before_xml


def test_update_refuses_a_deleted_media_file(library):
    mgr = _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    data = mgr.load(uuid)
    for item in data['CuemsScript']['CueList']['contents']:
        if 'AudioCue' in item:
            item['AudioCue']['Media']['file_name'] = 'vanished.wav'
    with pytest.raises(ValueError) as e:
        mgr.update(uuid, data)
    if not database.is_closed():
        database.close()
    assert "'vanished.wav' does not exist" in str(e.value)


def test_update_accepts_a_trashed_media_file(library):
    """Trashed is fine: the file can be restored; the save must not block."""
    # The fixture's only trashed file carries a malformed duration on purpose
    # (for the repair-durations tests); the duration fixer would copy it into
    # the XML and the XSD would reject the save for that unrelated reason.
    library.connect()
    Media.update(duration='00:00:03.900').where(Media.unix_name == 'tone_c.wav').execute()
    database.close()
    mgr = _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    data = mgr.load(uuid)
    for item in data['CuemsScript']['CueList']['contents']:
        if 'AudioCue' in item:
            item['AudioCue']['Media']['file_name'] = 'tone_c.wav'
    with mock.patch('cuemseditor.CuemsDBProject.probe_dimensions', return_value=(1, 1)):
        mgr.update(uuid, data)
    if not database.is_closed():
        database.close()
    assert b'tone_c.wav' in _xml(library)


# ─── the WS layer forwards the message as is ──────────────────────────────


def test_value_error_text_has_no_class_prefix():
    assert CuemsWsUser._error_text(ValueError('Media cue without a usable media file: x')) == \
        'Media cue without a usable media file: x'
    assert CuemsWsUser._error_text(KeyError('file_name')).startswith("<class 'KeyError'>")
