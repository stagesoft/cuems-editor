# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Tests for CuemsDBMedia intake None-guard and list() duration payload."""
import os
from unittest import mock

import pytest

from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBMedia import CuemsDBMedia
from cuemseditor.CuemsDBModel import Media, database
from cuemseditor.CuemsErrors import NotTimeCodeError


def _media_mgr(library):
    settings = get_settings()
    settings['library_path'] = library.root
    library.connect()
    return CuemsDBMedia(settings, database)


def test_list_payload_carries_duration(library):
    mgr = _media_mgr(library)
    try:
        entries = mgr.list()
        # each single-key {uuid: {...}} dict must carry a 'duration' key
        for entry in entries:
            (meta,) = entry.values()
            assert 'duration' in meta
        durations = {list(e.values())[0]['unix_name']: list(e.values())[0]['duration']
                     for e in entries}
        assert durations['file.ext'] == '00:00:00.000'
        assert durations['file_video.ext'] is None
    finally:
        database.close()


def test_list_trash_payload_carries_duration(library):
    mgr = _media_mgr(library)
    try:
        entries = mgr.list_trash()
        durations = {list(e.values())[0]['unix_name']: list(e.values())[0]['duration']
                     for e in entries}
        assert durations['tone_c.wav'] == '00:00:03.9'
    finally:
        database.close()


def test_new_none_duration_skips_audio_thumbnail_keeps_waveform(library, tmp_path):
    mgr = _media_mgr(library)
    try:
        upload = tmp_path / 'incoming.wav'
        upload.write_bytes(b'RIFF....')  # bytes irrelevant; probe is mocked

        with mock.patch.object(mgr, 'get_duration',
                               side_effect=NotTimeCodeError('boom')), \
             mock.patch.object(mgr, 'create_audio_thubnail') as thumb, \
             mock.patch.object(mgr, 'create_audio_waveform',
                               return_value='wave.dat') as wave:
            dest = mgr.new(str(upload), 'incoming.wav')

        thumb.assert_not_called()      # no duration -> no waveform *thumbnail*
        wave.assert_called_once()      # waveform data still generated
        row = Media.get(Media.unix_name == dest)
        assert row.duration is None    # row created, duration NULL
        assert row.media_type == 'AUDIO'
    finally:
        database.close()


def test_new_same_name_as_trashed_media_gets_versioned_name(library, tmp_path):
    # 'tone_c.wav' is trashed: its file is in trash/media, but its DB row
    # still holds the unique name, so the upload must not reuse it.
    mgr = _media_mgr(library)
    try:
        upload = tmp_path / 'tone_c.wav'
        upload.write_bytes(b'RIFF....')

        with mock.patch.object(mgr, 'get_duration', return_value=None), \
             mock.patch.object(mgr, 'create_audio_waveform', return_value=None):
            dest = mgr.new(str(upload), 'tone_c.wav')

        assert dest == 'tone_c-001.wav'
        assert os.path.exists(os.path.join(mgr.media_path, dest))
        row = Media.get(Media.unix_name == dest)
        assert row.name == dest and row.in_trash is False
        assert Media.get(Media.unix_name == 'tone_c.wav').in_trash is True
    finally:
        database.close()


def _sidecar_mgr(library):
    # the fixture lacks the sidecar dirs CuemsLibraryMaintenance creates
    mgr = _media_mgr(library)
    for d in (mgr.thumbnail_path, mgr.waveform_path, mgr.thumbnail_trash_path, mgr.waveform_trash_path):
        os.makedirs(d, exist_ok=True)
    return mgr


def _touch(path, data=b''):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(data)


def test_delete_keeps_unix_name_when_trash_holds_stray_file(library):
    # A stray file with the same name in trash/media used to make the move
    # pick 'pic-001.png' while the row kept 'pic.png' (projects use the name).
    mgr = _sidecar_mgr(library)
    try:
        _touch(mgr.get_file_path('pic.png', trash_state=True), b'stray')
        _touch(mgr.get_thumbnail_path('pic.png', trash_state=True), b'stray thumb')
        _touch(mgr.get_thumbnail_path('pic.png'), b'thumb')
        row = Media.get(Media.unix_name == 'pic.png')

        mgr.delete(str(row.uuid))

        row = Media.get(Media.uuid == row.uuid)
        assert row.unix_name == 'pic.png' and row.in_trash is True
        assert not os.path.exists(mgr.get_file_path('pic.png'))
        with open(mgr.get_file_path('pic.png', trash_state=True), 'rb') as f:
            assert f.read() == b''                          # the tracked file
        with open(mgr.get_file_path('pic-001.png', trash_state=True), 'rb') as f:
            assert f.read() == b'stray'                     # the stray, moved aside
        with open(mgr.get_thumbnail_path('pic.png', trash_state=True), 'rb') as f:
            assert f.read() == b'thumb'
    finally:
        database.close()


def test_restore_refuses_when_untracked_live_file_holds_the_name(library):
    mgr = _sidecar_mgr(library)
    try:
        _touch(mgr.get_file_path('tone_c.wav'), b'hand-copied')
        _touch(mgr.get_thumbnail_path('tone_c.wav', trash_state=True), b'thumb')
        row = Media.get(Media.unix_name == 'tone_c.wav')

        with pytest.raises(FileExistsError):
            mgr.restore(str(row.uuid))

        assert Media.get(Media.uuid == row.uuid).in_trash is True
        with open(mgr.get_file_path('tone_c.wav'), 'rb') as f:
            assert f.read() == b'hand-copied'               # live file untouched
        assert os.path.exists(mgr.get_file_path('tone_c.wav', trash_state=True))
        assert os.path.exists(mgr.get_thumbnail_path('tone_c.wav', trash_state=True))
    finally:
        database.close()


def test_restore_moves_files_back_under_the_same_name(library):
    mgr = _sidecar_mgr(library)
    try:
        _touch(mgr.get_thumbnail_path('tone_c.wav', trash_state=True), b'thumb')
        _touch(mgr.get_waveform_path('tone_c.wav', trash_state=True), b'wave')
        row = Media.get(Media.unix_name == 'tone_c.wav')

        mgr.restore(str(row.uuid))

        row = Media.get(Media.uuid == row.uuid)
        assert row.unix_name == 'tone_c.wav' and row.in_trash is False
        assert os.path.exists(mgr.get_file_path('tone_c.wav'))
        assert os.path.exists(mgr.get_thumbnail_path('tone_c.wav'))
        assert os.path.exists(mgr.get_waveform_path('tone_c.wav'))
        assert not os.path.exists(mgr.get_file_path('tone_c.wav', trash_state=True))
    finally:
        database.close()


def test_delete_rolls_back_sidecars_when_media_file_is_missing(library):
    # 'gone.wav' has a live row but no file: the main move fails after the
    # sidecars were moved, and every move must be undone.
    mgr = _sidecar_mgr(library)
    try:
        _touch(mgr.get_thumbnail_path('gone.wav'), b'thumb')
        _touch(mgr.get_waveform_path('gone.wav'), b'wave')
        row = Media.get(Media.unix_name == 'gone.wav')

        with pytest.raises(FileNotFoundError):
            mgr.delete(str(row.uuid))

        assert Media.get(Media.uuid == row.uuid).in_trash is False
        assert os.path.exists(mgr.get_thumbnail_path('gone.wav'))
        assert os.path.exists(mgr.get_waveform_path('gone.wav'))
        assert not os.path.exists(mgr.get_thumbnail_path('gone.wav', trash_state=True))
        assert not os.path.exists(mgr.get_waveform_path('gone.wav', trash_state=True))
    finally:
        database.close()
