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

003 adaptation (T011): since cuems-utils 013 the wire carries a media cue as
``{'Cue': {'class': 'audio' | 'video', ...}}``, not as ``{'AudioCue': ...}``.
The released gate only knew the old wrappers, so on the current wire it would
find no media cue at all and refuse nothing (constitution IV gate 4: a
caller that still resolves but now computes the wrong answer). The shape
tests below use the current wire; one test keeps the old wrappers, because a
deployed frontend may still send them. The update tests save a version-2
(013) script, which is what ``CuemsScript.load`` accepts.
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
    cue = {'name': name, 'id': cue_id, 'class': 'audio'}
    if media is not mock.sentinel.absent:
        cue['Media'] = media
    return {'Cue': cue}


def _video(media, name='V1', cue_id='v1-uuid'):
    return {'Cue': {'name': name, 'id': cue_id, 'class': 'video', 'Media': media}}


def _media_cues_of(data):
    """The media cues of a wire payload (class audio or video), nested lists walked."""
    found = []

    def walk(contents):
        for item in contents:
            if 'CueList' in item:
                walk(item['CueList'].get('contents', []))
            elif 'Cue' in item and item['Cue'].get('class') in ('audio', 'video'):
                found.append(item['Cue'])

    walk(data['CuemsScript']['CueList']['contents'])
    return found


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


@pytest.mark.parametrize('key', ['AudioCue', 'VideoCue'])
def test_the_pre_013_wrappers_are_still_gated(key):
    """A deployed frontend may still send ``{'AudioCue': ...}``: keep accepting it (Principle I)."""
    with pytest.raises(ValueError) as e:
        validate_media_cues_in_contents([{key: {'name': 'Old', 'id': 'o-1'}}])
    assert "'Old'" in str(e.value) and 'no media file' in str(e.value)


def test_a_hardware_cue_of_another_class_is_not_a_media_cue():
    validate_media_cues_in_contents([{'Cue': {'name': 'dmx', 'id': 'd-1', 'class': 'dmx'}}])


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


def test_update_refuses_a_media_less_cue_and_writes_nothing(library013):
    library = library013
    _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    database.close()
    # Link the fixture's media so the ProjectMedia snapshot is non-trivial.
    mgr2 = _manager(library)
    mgr2.update(uuid, mgr2.load(uuid))
    database.close()
    before_db, before_xml = _snapshot(library), _xml(library)

    # The frontend's shape: the audio cue arrives with no Media key at all.
    bad = _manager(library).load(uuid)
    audio = [c for c in _media_cues_of(bad) if c['class'] == 'audio']
    assert audio, 'the 013 fixture holds an audio cue'
    audio[0]['name'] = 'renamed'
    del audio[0]['Media']
    with pytest.raises(ValueError) as e:
        _manager(library).update(uuid, bad)
    if not database.is_closed():
        database.close()

    assert "'renamed'" in str(e.value) and 'no media file' in str(e.value)
    assert _snapshot(library) == before_db
    assert _xml(library) == before_xml


def test_update_refuses_a_deleted_media_file(library013):
    library = library013
    mgr = _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    data = mgr.load(uuid)
    for cue in _media_cues_of(data):
        if cue['class'] == 'audio':
            cue['Media']['file_name'] = 'vanished.wav'
    with pytest.raises(ValueError) as e:
        mgr.update(uuid, data)
    if not database.is_closed():
        database.close()
    assert "'vanished.wav' does not exist" in str(e.value)


def test_update_accepts_a_trashed_media_file(library013):
    """Trashed is fine: the file can be restored; the save must not block."""
    # The fixture's only trashed file carries a malformed duration on purpose
    # (for the repair-durations tests); the duration fixer would copy it into
    # the XML and the XSD would reject the save for that unrelated reason.
    library = library013
    library.connect()
    Media.update(duration='00:00:03.900').where(Media.unix_name == 'tone_c.wav').execute()
    database.close()
    mgr = _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    data = mgr.load(uuid)
    for cue in _media_cues_of(data):
        if cue['class'] == 'audio':
            cue['Media']['file_name'] = 'tone_c.wav'
    mgr.update(uuid, data)
    if not database.is_closed():
        database.close()
    assert b'tone_c.wav' in _xml(library)


# ─── the WS layer forwards the message as is ──────────────────────────────


def test_value_error_text_has_no_class_prefix():
    assert CuemsWsUser._error_text(ValueError('Media cue without a usable media file: x')) == \
        'Media cue without a usable media file: x'
    assert CuemsWsUser._error_text(KeyError('file_name')).startswith("<class 'KeyError'>")


# ─── the library's own guard, if the gate is bypassed (FR-009, utils 017 §1) ─


@pytest.mark.xfail(
    strict=True,
    reason="cuems-utils 4b336cd (the candidate tag) raises KeyError('file_name') from CueList.get_media; "
           "rc16's ValueError guard is only in utils 387598e and later (utils 017). "
           "See specs/003-release-line-reconciliation/upstream-reports/cuems-utils.md. "
           "Turns XPASS (red) on the re-cut: drop this marker then.")
def test_the_librarys_media_error_reaches_the_client_unprefixed(library013):
    """Without the gate, ``CueList.get_media`` raises a ``ValueError`` naming the cue.

    It must still be a ``ValueError`` (so ``_error_text`` forwards it as is), never a
    ``KeyError 'file_name'`` as in cuems-utils < rc16.
    """
    library = library013
    mgr = _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    data = mgr.load(uuid)
    audio = [c for c in _media_cues_of(data) if c['class'] == 'audio'][0]
    audio['name'] = 'Bypassed'
    audio['Media'] = {}
    with mock.patch('cuemseditor.CuemsDBProject.validate_media_cues_in_contents'):
        with pytest.raises(Exception) as e:
            mgr.update(uuid, data)
    if not database.is_closed():
        database.close()
    assert isinstance(e.value, ValueError), repr(e.value)
    assert not CuemsWsUser._error_text(e.value).startswith('<class')


def test_new_refuses_a_media_less_cue_before_writing_anything(library013):
    library = library013
    mgr = _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    data = mgr.load(uuid)
    audio = [c for c in _media_cues_of(data) if c['class'] == 'audio'][0]
    audio['name'] = 'NoMedia'
    del audio['Media']
    data['CuemsScript']['id'] = '00000000-0000-4000-8000-000000000001'
    with pytest.raises(ValueError) as e:
        mgr.new(data, 'proj_new')
    if not database.is_closed():
        database.close()
    assert "'NoMedia'" in str(e.value)
    assert not os.path.exists(os.path.join(library.projects_dir, 'proj_new'))
