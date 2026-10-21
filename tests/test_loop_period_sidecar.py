# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""The loop period sidecar (``indexes/<name>.period``) the editor writes
(plan 869ejxng3 + 1amfwm7e6cw rev 3.14, §4.1, D14).

* at upload: every MOVIE and AUDIO file gets one, next to the ``.idx``; a
  failure is a WARNING, never a failed upload; a rolled-back upload leaves none;
* before a load (the media refresh): a project file without a valid sidecar
  (a library from before this release, a file replaced by hand) gets one within
  the refresh's deadline, so the load's media sync carries it to the nodes; a
  file whose period fails is not retried until it changes.

The period itself is computed by ``cuemsutils.tools.media_sidecars`` (tested
there); here it is faked.
"""
import os
from unittest import mock

import pytest

import cuemseditor.CuemsDBProject as p
import cuemseditor.CuemsMediaRefresh as r
from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBMedia import CuemsDBMedia
from cuemseditor.CuemsDBModel import Media, database
from cuemsutils.tools import media_sidecars as ms


@pytest.fixture(autouse=True)
def _fresh_marks():
    p.reset_refresh_marks()
    r.reset_refresh_state()
    yield
    p.reset_refresh_marks()
    r.reset_refresh_state()


def _fake_period(path, budget_s=None):
    st = os.stat(path)
    return ms.Period(num=48000, den=48000, rate=48000, real_frames=None, fps=None, rule='walk',
                     frames_rule=None, vfr=False, size=st.st_size, mtime=int(st.st_mtime),
                     ffprobe='fake')


def _media_mgr(library):
    settings = get_settings()
    settings['library_path'] = library.root
    library.connect()
    return CuemsDBMedia(settings, database)


def _sidecar(library, name):
    return os.path.join(library.root, 'media', 'indexes', name + '.period')


# --------------------------------------------------------------------------- upload

@pytest.mark.parametrize('name,kind', [('clip.mp4', 'MOVIE'), ('take.wav', 'AUDIO')])
def test_upload_writes_the_period_of_movies_and_audio(library, tmp_path, name, kind):
    mgr = _media_mgr(library)
    try:
        upload = tmp_path / name
        upload.write_bytes(b'bytes')
        with mock.patch.object(mgr, 'get_duration', return_value=None), \
             mock.patch.object(mgr, 'create_video_thumbnail', return_value=None), \
             mock.patch.object(mgr, 'create_video_index', return_value=None), \
             mock.patch.object(mgr, 'create_audio_waveform', return_value=None), \
             mock.patch.object(ms, 'loop_period', side_effect=_fake_period) as lp:
            dest = mgr.new(str(upload), name)
        assert lp.call_count == 1
        assert ms.read_period(os.path.join(library.root, 'media', dest)).num == 48000
        assert Media.get(Media.unix_name == dest).media_type == kind
    finally:
        database.close()


def test_upload_of_an_image_writes_no_period(library, tmp_path):
    mgr = _media_mgr(library)
    try:
        upload = tmp_path / 'still.png'
        upload.write_bytes(b'png')
        with mock.patch.object(mgr, 'create_video_thumbnail', return_value=None), \
             mock.patch.object(ms, 'loop_period', side_effect=_fake_period) as lp:
            dest = mgr.new(str(upload), 'still.png')
        lp.assert_not_called()
        assert not os.path.exists(_sidecar(library, dest))
    finally:
        database.close()


def test_a_failed_period_never_fails_the_upload(library, tmp_path):
    mgr = _media_mgr(library)
    try:
        upload = tmp_path / 'broken.mp3'
        upload.write_bytes(b'not audio')
        with mock.patch.object(mgr, 'get_duration', return_value=None), \
             mock.patch.object(mgr, 'create_audio_waveform', return_value=None), \
             mock.patch.object(ms, 'loop_period', side_effect=ms.PeriodError('no audio')):
            dest = mgr.new(str(upload), 'broken.mp3')
        assert Media.get(Media.unix_name == dest)           # the row exists
        assert not os.path.exists(_sidecar(library, dest))
    finally:
        database.close()


def test_a_rolled_back_upload_leaves_no_period(library, tmp_path):
    mgr = _media_mgr(library)
    try:
        upload = tmp_path / 'clip.mov'
        upload.write_bytes(b'bytes')
        with mock.patch.object(mgr, 'get_duration', return_value=None), \
             mock.patch.object(mgr, 'create_video_thumbnail', return_value=None), \
             mock.patch.object(mgr, 'create_video_index', return_value=None), \
             mock.patch.object(ms, 'loop_period', side_effect=_fake_period), \
             mock.patch.object(Media, 'create', side_effect=RuntimeError('db down')):
            with pytest.raises(RuntimeError):
                mgr.new(str(upload), 'clip.mov')
        assert not os.path.exists(_sidecar(library, 'clip.mov'))
    finally:
        database.close()


def test_create_video_index_goes_through_the_shared_caller(library):
    mgr = _media_mgr(library)
    try:
        with mock.patch.object(ms, 'ensure_video_index', return_value=[]) as ev:
            mgr.create_video_index('clip.mp4')
        ev.assert_called_once_with(os.path.join(library.root, 'media', 'clip.mp4'), timeout_s=300)
    finally:
        database.close()


# --------------------------------------------------------------------------- before a load
# (the helpers of the media refresh's own tests: a library "in line" with its
# project, then one cue pointed at a real movie/audio name)

import test_media_refresh as t  # noqa: E402  (pytest puts tests/ on sys.path)


def _project_with(library, name, kind, nbytes=10):
    t._in_line(library)
    t._add_row(library, name, kind, duration=t.tc(10.0), file_size=nbytes)
    t._set_xml_media(library, 'file_video.ext', rename=name)
    return t._write(library, name, nbytes), t._uuid(library)


def test_a_file_without_a_period_gets_one_before_the_load(library):
    path, uuid = _project_with(library, 'take.wav', 'AUDIO')
    with mock.patch.object(ms, 'loop_period', side_effect=_fake_period):
        report = t._refresh(t._mgr(library), uuid)
        assert report['periods'] == 1 and report['engine_asked'] is True
        assert ms.read_period(path) is not None
        again = t._refresh(t._mgr(library), uuid, engine='running')   # nothing left to do
    assert again['engine_asked'] is False and again['periods'] == 0


def test_no_period_is_computed_while_a_show_runs(library):
    path, uuid = _project_with(library, 'take.wav', 'AUDIO')
    with mock.patch.object(ms, 'loop_period', side_effect=_fake_period) as lp:
        report = t._refresh(t._mgr(library), uuid, engine='running')
    lp.assert_not_called()
    assert report['skipped'] == 'running' and ms.read_period(path) is None


def test_a_failed_period_is_not_retried_until_the_file_changes(library):
    path, uuid = _project_with(library, 'take.wav', 'AUDIO')
    with mock.patch.object(ms, 'loop_period', side_effect=ms.PeriodError('broken')) as lp:
        first = t._refresh(t._mgr(library), uuid)
        second = t._refresh(t._mgr(library), uuid, engine='running')
    assert first['period_failed'] == 1
    assert lp.call_count == 1 and second['engine_asked'] is False


def test_the_deadline_leaves_periods_for_the_next_load(library):
    path, uuid = _project_with(library, 'take.wav', 'AUDIO')
    with mock.patch.object(ms, 'loop_period', side_effect=ms.PeriodTimeout('budget')):
        report = t._refresh(t._mgr(library), uuid)
    assert report['period_not_reached'] == 1 and report['period_failed'] == 0
    assert ms.read_period(path) is None


def test_write_loop_periods_respects_the_deadline():
    with mock.patch.object(ms, 'loop_period') as lp:
        out = p.write_loop_periods(['/a.wav', '/b.wav'], deadline=100.2, clock=lambda: 100.0)
    lp.assert_not_called()
    assert out == {'periods': 0, 'period_failed': 0, 'period_not_reached': 2}


def test_write_loop_periods_budget_per_file_is_capped(tmp_path):
    a = tmp_path / 'a.wav'
    a.write_bytes(b'a')
    seen = []

    def lp(path, budget_s=None):
        seen.append(budget_s)
        return _fake_period(path)
    with mock.patch.object(ms, 'loop_period', side_effect=lp):
        out = p.write_loop_periods([str(a)], deadline=1000.0, clock=lambda: 0.0)
    assert out['periods'] == 1 and seen == [p.LOOP_PERIOD_LOAD_BUDGET_S]
