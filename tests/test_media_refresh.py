# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""A media file that changed after its values were stored (ClickUp 869fat84r, D20).

A project stores each file's duration, pixel size, size and MD5. A file
replaced by hand on the controller (same name), or re-uploaded after its old
media was permanently deleted, leaves those values stale: the cue ends at the
old length and an Auto follow fires at the old end.

* L1: at ``project_ready``, before the engine is asked, the editor re-checks
  each file the project uses (size, and the ``.idx`` header of a video the
  sync carries), re-probes what changed, corrects the DB rows, re-indexes a
  changed video, and rewrites the project only when a value present in it
  is wrong.
* D13: a save that meets a legacy row (no stored size) verifies it the same
  way, duration included.
* Q2: a re-upload after a permanent deletion rewrites the relinked projects.
* Saving safely: one re-entrant lock per project taken first by every
  writer, an atomic write that keeps the file's mode, timestamped backups.

Design: cuems-RELATIONS Plans/2026-10-01-engine-late-go-media-probe.md §7.
"""
import asyncio
import os
import re
import shutil
import stat
import struct
import sys
import threading
import time
import xml.etree.ElementTree as ET
from unittest import mock

import pytest

import cuemseditor.CuemsDBProject as p
import cuemseditor.CuemsMediaRefresh as r
from cuemseditor import CuemsDBMedia as m
from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBMedia import (
    INDEX_MISSING, INDEX_STALE, INDEX_VALID, PROBE_FAILED, PROBE_NO_STREAM,
    PROBE_OK, MediaProbe, video_index_path, video_index_state)
from cuemseditor.CuemsDBModel import Media, Project, ProjectMedia, database
from cuemsutils.helpers import new_datetime, new_uuid
from cuemsutils.tools.CTimecode import CTimecode
from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter

STORED = ('pixel_width', 'pixel_height', 'file_size', 'file_md5')
MD5 = 'd41d8cd98f00b204e9800998ecf8427e'
ET.register_namespace('cms', 'https://stagelab.coop/cuems/')
ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _fresh_marks():
    p.reset_refresh_marks()
    r.reset_refresh_state()
    yield
    p.reset_refresh_marks()
    r.reset_refresh_state()


def tc(seconds):
    return str(CTimecode(start_seconds=seconds))


def probe(seconds=None, dims=None, duration_state=None, picture_state=None):
    """A ``MediaProbe`` as ffprobe would report it."""
    return MediaProbe(
        duration=CTimecode(start_seconds=seconds) if seconds is not None else None,
        duration_state=duration_state or (PROBE_OK if seconds is not None else PROBE_NO_STREAM),
        width=dims[0] if dims else None,
        height=dims[1] if dims else None,
        picture_state=picture_state or (PROBE_OK if dims else PROBE_NO_STREAM))


class FakeProbe:
    """Stands in for ``probe_media``: {file name: MediaProbe or callable}."""

    def __init__(self, table):
        self.table = table
        self.calls = []

    def __call__(self, path, timeout=None):
        name = os.path.basename(path)
        self.calls.append(name)
        result = self.table[name]
        return result(path) if callable(result) else result


def _settings(library):
    settings = get_settings()
    settings['library_path'] = library.root
    settings['tmp_path'] = os.path.join(library.root, 'tmp')
    settings['html_root_path'] = os.path.join(library.root, 'www')
    return settings


def _mgr(library):
    library.connect()
    return p.CuemsDBProject(_settings(library), database)


def _uuid(library, unix_name='proj1'):
    library.connect()
    return str(Project.get(Project.unix_name == unix_name).uuid)


def _script(library, project='proj1'):
    return os.path.join(library.projects_dir, project, 'script.xml')


def _write(library, name, nbytes, fill=b'x'):
    path = os.path.join(library.root, 'media', name)
    with open(path, 'wb') as f:
        f.write(fill * nbytes)
    return path


def _row(library, name):
    library.connect()
    return Media.get(Media.unix_name == name)


def _set_row(library, name, **fields):
    library.connect()
    Media.update(**fields).where(Media.unix_name == name).execute()


def _add_row(library, name, media_type, **fields):
    library.connect()
    Media.create(uuid=str(new_uuid()), name=name, unix_name=name,
                 created=new_datetime(), modified=new_datetime(),
                 media_type=media_type, in_trash=False, **fields)


def _set_xml_media(library, name, project='proj1', duration=None, rename=None, **stored):
    """Edit every ``Media`` block that uses *name*: its duration, its stored
    values (replaced by *stored*, in schema order, after ``regions``), and
    optionally its file name."""
    path = _script(library, project)
    tree = ET.parse(path)
    for media in tree.getroot().iter('Media'):
        if media.findtext('file_name') != name:
            continue
        if duration is not None:
            media.find('duration').text = duration
        if stored:
            for key in STORED:
                for el in media.findall(key):
                    media.remove(el)
            for key in STORED:
                if stored.get(key) is not None:
                    ET.SubElement(media, key).text = str(stored[key])
        if rename:
            media.find('file_name').text = rename
    tree.write(path, encoding='utf-8', xml_declaration=True)


def _blocks(library, project='proj1'):
    """[(cue_type, Media dict)] as the editor reads the project."""
    data = XmlReaderWriter(schema_name='script', xmlfile=_script(library, project)).read()
    out = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ('AudioCue', 'VideoCue') and isinstance(value, dict):
                    out.append((key, value.get('Media')))
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(data)
    return out


def _media_of(library, name, project='proj1'):
    return [mm for _, mm in _blocks(library, project) if mm and mm.get('file_name') == name]


def _backups(library, project='proj1'):
    d = os.path.join(library.projects_dir, project)
    return sorted(f for f in os.listdir(d) if '.pre-refresh-' in f)


def _in_line(library, video_seconds=90.0, video_size=10, audio_seconds=30.0, audio_size=20):
    """A library whose rows match the files and the project: nothing to do."""
    _write(library, 'file_video.ext', video_size)
    _write(library, 'file.ext', audio_size)
    _set_row(library, 'file_video.ext', duration=tc(video_seconds), file_size=video_size,
             pixel_width=1920, pixel_height=1080)
    _set_row(library, 'file.ext', duration=tc(audio_seconds), file_size=audio_size)
    _set_xml_media(library, 'file_video.ext', duration=tc(video_seconds))
    _set_xml_media(library, 'file.ext', duration=tc(audio_seconds))


def _refresh(mgr, uuid, engine='none', clock=time.monotonic):
    async def engine_running():
        return {'none': False, 'running': True, 'silent': None}[engine]
    return asyncio.run(r.refresh_media_before_load(mgr, uuid, executor=None,
                                                   engine_running=engine_running, clock=clock))


def _idx_header(size, mtime, frames=10, version=1, magic=b'CXID'):
    return struct.pack('<4sIqqq', magic, version, size, mtime, frames) + b'\0' * 64


def _write_idx(video_path, header):
    path = video_index_path(video_path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(header)
    return path


def _valid_idx(video_path):
    st = os.stat(video_path)
    return _write_idx(video_path, _idx_header(st.st_size, int(st.st_mtime)))


# ---------------------------------------------------------------------------
# probe_media and the .idx header
# ---------------------------------------------------------------------------

class TestProbeMedia:
    def _run(self, stdout, rc=0):
        done = mock.Mock(returncode=rc, stdout=stdout.encode(), stderr=b'')
        with mock.patch.object(m.subprocess, 'run', return_value=done) as run:
            result = m.probe_media('/x/file.mov')
        return result, run

    def test_one_ffprobe_gives_the_duration_and_the_pixel_size(self):
        result, run = self._run('{"streams": [{"width": 1920, "height": 1080}],'
                                ' "format": {"duration": "332.900000"}}')
        assert run.call_count == 1
        assert (result.duration_state, str(result.duration)) == (PROBE_OK, '00:05:32.900')
        assert (result.picture_state, result.width, result.height) == (PROBE_OK, 1920, 1080)

    def test_the_duration_string_is_the_one_probe_duration_stores(self):
        result, _ = self._run('{"streams": [], "format": {"duration": "90.000000"}}')
        assert str(result.duration) == str(CTimecode(start_seconds=90.0))

    def test_an_audio_file_has_no_picture(self):
        result, _ = self._run('{"streams": [], "format": {"duration": "12.5"}}')
        assert result.duration_state == PROBE_OK
        assert result.picture_state == PROBE_NO_STREAM

    def test_an_image_has_no_duration(self):
        result, _ = self._run('{"streams": [{"width": 640, "height": 480}], "format": {}}')
        assert result.duration_state == PROBE_NO_STREAM
        assert result.picture_state == PROBE_OK

    def test_a_failed_ffprobe_is_failed_not_no_stream(self):
        result, _ = self._run('', rc=1)
        assert result.duration_state == PROBE_FAILED
        assert result.picture_state == PROBE_FAILED

    def test_a_timeout_is_failed(self):
        with mock.patch.object(m.subprocess, 'run',
                               side_effect=m.subprocess.TimeoutExpired('ffprobe', 5)):
            result = m.probe_media('/x/file.mov')
        assert (result.duration_state, result.picture_state) == (PROBE_FAILED, PROBE_FAILED)

    def test_garbage_is_failed(self):
        result, _ = self._run('{"streams": [{"width": 0}], "format": {"duration": "nan"}}')
        assert (result.duration_state, result.picture_state) == (PROBE_FAILED, PROBE_FAILED)


class TestVideoIndexState:
    def test_the_index_path_is_the_videocomposers(self, tmp_path):
        assert video_index_path('/lib/media/a.mp4') == '/lib/media/indexes/a.mp4.idx'

    def test_valid(self, tmp_path):
        video = tmp_path / 'a.mp4'
        video.write_bytes(b'v' * 100)
        _valid_idx(str(video))
        assert video_index_state(str(video)) == INDEX_VALID

    def test_a_replaced_file_makes_the_header_stale(self, tmp_path):
        video = tmp_path / 'a.mp4'
        video.write_bytes(b'v' * 100)
        _valid_idx(str(video))
        video.write_bytes(b'w' * 100)                       # same size
        os.utime(video, (1, 1))                             # another mtime
        assert video_index_state(str(video)) == INDEX_STALE

    def test_missing_unknown_version_bad_magic_or_no_frames(self, tmp_path):
        video = tmp_path / 'a.mp4'
        video.write_bytes(b'v' * 100)
        assert video_index_state(str(video)) == INDEX_MISSING
        st = os.stat(video)
        for header in (_idx_header(st.st_size, int(st.st_mtime), version=2),
                       _idx_header(st.st_size, int(st.st_mtime), magic=b'XXXX'),
                       _idx_header(st.st_size, int(st.st_mtime), frames=0),
                       b'CXID'):
            _write_idx(str(video), header)
            assert video_index_state(str(video)) == INDEX_MISSING


# ---------------------------------------------------------------------------
# L1 step 1: read and compare, without writing anything
# ---------------------------------------------------------------------------

class TestPlan:
    def test_an_unchanged_library_has_no_work(self, library):
        _in_line(library)
        mgr = _mgr(library)
        before = open(_script(library), 'rb').read()
        fake = FakeProbe({})
        with mock.patch.object(p, 'probe_media', fake):
            plan = mgr.plan_media_refresh(_uuid(library))
            report = _refresh(mgr, _uuid(library), engine='running')  # never asked
        assert not plan.has_work
        assert fake.calls == []
        assert report['engine_asked'] is False
        assert open(_script(library), 'rb').read() == before
        assert _backups(library) == []

    def test_a_replaced_file_is_changed(self, library):
        _in_line(library)
        _write(library, 'file_video.ext', 11)
        plan = _mgr(library).plan_media_refresh(_uuid(library))
        states = {c.file_name: c.state for c in plan.checks}
        assert states == {'file_video.ext': 'changed', 'file.ext': 'unchanged'}
        assert plan.has_work

    def test_a_row_without_a_size_is_legacy(self, library):
        _in_line(library)
        _set_row(library, 'file.ext', file_size=None)
        plan = _mgr(library).plan_media_refresh(_uuid(library))
        assert {c.file_name: c.state for c in plan.checks}['file.ext'] == 'legacy'

    def test_a_missing_or_empty_file_and_an_orphan_are_skipped(self, library):
        _in_line(library)
        os.remove(os.path.join(library.root, 'media', 'file.ext'))
        _write(library, 'file_video.ext', 0)
        _set_xml_media(library, 'file_video.ext', rename='nobody.ext')
        plan = _mgr(library).plan_media_refresh(_uuid(library))
        assert plan.checks == [] or all(c.state == 'skipped' for c in plan.checks)
        assert not plan.has_work

    def test_missing_values_are_not_a_reason_to_rewrite(self, library):
        _in_line(library)                     # the XML has no stored values at all
        assert not _mgr(library).plan_media_refresh(_uuid(library)).needs_rewrite

    def test_matching_values_read_as_strings_are_not_wrong(self, library):
        _in_line(library)
        _set_row(library, 'file_video.ext', file_md5=MD5)
        _set_xml_media(library, 'file_video.ext', pixel_width=1920, pixel_height=1080,
                       file_size=10, file_md5=MD5)
        assert not _mgr(library).plan_media_refresh(_uuid(library)).needs_rewrite

    def test_a_present_wrong_duration_is_a_reason_to_rewrite(self, library):
        _in_line(library)
        _set_xml_media(library, 'file_video.ext', duration=tc(80))
        assert _mgr(library).plan_media_refresh(_uuid(library)).needs_rewrite

    def test_a_null_db_duration_is_never_a_reason_to_rewrite(self, library):
        _in_line(library)
        _set_row(library, 'file_video.ext', duration=None)
        assert not _mgr(library).plan_media_refresh(_uuid(library)).needs_rewrite

    def test_a_stored_value_the_db_does_not_have_is_wrong(self, library):
        _in_line(library)
        _set_xml_media(library, 'file_video.ext', file_size=10, file_md5=MD5)   # row: no md5
        assert _mgr(library).plan_media_refresh(_uuid(library)).needs_rewrite

    def test_pixel_keys_on_an_audio_cue_are_wrong(self, library):
        _in_line(library)
        _set_xml_media(library, 'file.ext', pixel_width=10, pixel_height=10)
        assert _mgr(library).plan_media_refresh(_uuid(library)).needs_rewrite

    def test_a_trashed_project_is_not_planned(self, library):
        _in_line(library)
        _mgr(library).delete(_uuid(library))
        with pytest.raises(Exception):
            _mgr(library).plan_media_refresh(_uuid(library))


# ---------------------------------------------------------------------------
# L1 end to end (steps 0-6)
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_a_replaced_file_corrects_the_row_and_the_project(self, library):
        _in_line(library)
        _set_row(library, 'file_video.ext', file_md5=MD5)
        _write(library, 'file_video.ext', 11)
        mgr = _mgr(library)
        fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake), \
                mock.patch.object(p.Logger, 'warning') as warning:
            report = _refresh(mgr, _uuid(library))
        row = _row(library, 'file_video.ext')
        assert (row.duration, row.pixel_width, row.pixel_height, row.file_size, row.file_md5) \
            == (tc(120.0), 1280, 720, 11, None)
        videos = _media_of(library, 'file_video.ext')
        assert videos and all(mm['duration'] == tc(120.0) and mm['file_size'] == 11
                              and mm['pixel_width'] == 1280 and 'file_md5' not in mm
                              for mm in videos)
        assert sum('file_video.ext' in str(c) for c in warning.call_args_list) == 1
        assert report['rewritten'] is True
        assert len(_backups(library)) == 1

    def test_the_second_load_does_nothing(self, library):
        _in_line(library)
        _write(library, 'file_video.ext', 11)
        mgr = _mgr(library)
        fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(mgr, _uuid(library))
            before = open(_script(library), 'rb').read()
            report = _refresh(mgr, _uuid(library), engine='running')
        assert fake.calls == ['file_video.ext']
        assert report['engine_asked'] is False
        assert open(_script(library), 'rb').read() == before

    def test_a_copy_in_progress_is_skipped(self, library):
        _in_line(library)
        path = _write(library, 'file_video.ext', 11)

        def growing(_path):
            with open(path, 'ab') as f:
                f.write(b'more')
            return probe(120.0, (1280, 720))

        with mock.patch.object(p, 'probe_media', FakeProbe({'file_video.ext': growing})):
            _refresh(_mgr(library), _uuid(library))
        row = _row(library, 'file_video.ext')
        assert (row.duration, row.file_size) == (tc(90.0), 10)

    def test_a_legacy_row_is_verified_and_marked(self, library):
        _in_line(library)
        _set_row(library, 'file.ext', file_size=None)
        with mock.patch.object(p, 'probe_media', FakeProbe({'file.ext': probe(30.0)})):
            report = _refresh(_mgr(library), _uuid(library))
        assert _row(library, 'file.ext').file_size == 20
        assert report['rewritten'] is False          # missing values are not wrong
        assert _backups(library) == []

    def test_a_legacy_row_with_the_old_rounding_is_corrected(self, library):
        _in_line(library)
        _set_row(library, 'file.ext', file_size=None, duration='00:05:32.009')
        _set_xml_media(library, 'file.ext', duration='00:05:32.009')
        with mock.patch.object(p, 'probe_media', FakeProbe({'file.ext': probe(332.9)})), \
                mock.patch.object(p.Logger, 'warning') as warning:
            report = _refresh(_mgr(library), _uuid(library))
        assert _row(library, 'file.ext').duration == '00:05:32.900'
        assert all(mm['duration'] == '00:05:32.900' for mm in _media_of(library, 'file.ext'))
        assert report['rewritten'] is True
        assert any('00:05:32.009' in str(c) and '00:05:32.900' in str(c)
                   for c in warning.call_args_list)

    def test_an_audio_only_movie_is_marked_and_not_probed_again(self, library):
        _in_line(library)
        _set_row(library, 'file_video.ext', file_size=None, pixel_width=None, pixel_height=None)
        fake = FakeProbe({'file_video.ext': probe(90.0)})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(library), _uuid(library))
            _refresh(_mgr(library), _uuid(library))
        row = _row(library, 'file_video.ext')
        assert (row.file_size, row.pixel_width) == (10, None)
        assert fake.calls == ['file_video.ext']

    def test_a_failed_duration_probe_leaves_the_row_and_backs_off(self, library):
        _in_line(library)
        _write(library, 'file_video.ext', 11)
        fake = FakeProbe({'file_video.ext': probe(duration_state=PROBE_FAILED,
                                                  picture_state=PROBE_FAILED)})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(library), _uuid(library))
            _refresh(_mgr(library), _uuid(library))
        row = _row(library, 'file_video.ext')
        assert (row.duration, row.file_size) == (tc(90.0), 10)
        assert fake.calls == ['file_video.ext']          # not retried until it changes
        _write(library, 'file_video.ext', 12)
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(library), _uuid(library))
        assert fake.calls == ['file_video.ext', 'file_video.ext']

    def test_a_failed_pixel_probe_still_writes_the_duration_and_the_mark(self, library):
        _in_line(library)
        _write(library, 'file_video.ext', 11)
        fake = FakeProbe({'file_video.ext': probe(120.0, picture_state=PROBE_FAILED)})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(library), _uuid(library))
        row = _row(library, 'file_video.ext')
        assert (row.duration, row.file_size, row.pixel_width) == (tc(120.0), 11, None)

    def test_an_image_needs_no_duration(self, library):
        _in_line(library)
        _write(library, 'pic.png', 7)
        _set_xml_media(library, 'file_video.ext', rename='pic.png')
        with mock.patch.object(p, 'probe_media', FakeProbe({'pic.png': probe(dims=(640, 480))})):
            _refresh(_mgr(library), _uuid(library))
            report = _refresh(_mgr(library), _uuid(library), engine='running')
        row = _row(library, 'pic.png')
        assert (row.duration, row.pixel_width, row.file_size) == (None, 640, 7)
        assert report['engine_asked'] is False

    def test_an_audio_file_with_cover_art_gets_no_pixel_size(self, library):
        _in_line(library)
        _write(library, 'file.ext', 21)
        with mock.patch.object(p, 'probe_media', FakeProbe({'file.ext': probe(31.0, (600, 600))})):
            _refresh(_mgr(library), _uuid(library))
        row = _row(library, 'file.ext')
        assert (row.duration, row.pixel_width, row.file_size) == (tc(31.0), None, 21)

    def test_shared_media_is_corrected_in_every_project_at_its_own_load(self, library):
        _in_line(library)
        shutil.copytree(os.path.join(library.projects_dir, 'proj1'),
                        os.path.join(library.projects_dir, 'proj2'))
        library.connect()
        Project.create(uuid=str(new_uuid()), name='Proj Two', unix_name='proj2',
                       created=new_datetime(), modified=new_datetime(), in_trash=False)
        _write(library, 'file_video.ext', 11)
        fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(library), _uuid(library, 'proj1'))
            report = _refresh(_mgr(library), _uuid(library, 'proj2'))
        assert fake.calls == ['file_video.ext']             # B causes no probe
        assert report['rewritten'] is True
        assert all(mm['duration'] == tc(120.0)
                   for mm in _media_of(library, 'file_video.ext', 'proj2'))

    def test_audio_cue_pixel_keys_are_removed_once(self, library):
        _in_line(library)
        _set_xml_media(library, 'file.ext', pixel_width=10, pixel_height=10)
        first = _refresh(_mgr(library), _uuid(library))
        second = _refresh(_mgr(library), _uuid(library), engine='running')
        assert first['rewritten'] is True
        assert second['engine_asked'] is False
        assert all('pixel_width' not in mm for mm in _media_of(library, 'file.ext'))

    def test_a_running_show_or_a_silent_engine_means_no_write(self, library):
        for engine in ('running', 'silent'):
            _in_line(library)
            _write(library, 'file_video.ext', 11)
            before = open(_script(library), 'rb').read()
            fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
            with mock.patch.object(p, 'probe_media', fake):
                report = _refresh(_mgr(library), _uuid(library), engine=engine)
            assert report['engine_asked'] is True and report['skipped'] == engine
            assert fake.calls == []
            assert _row(library, 'file_video.ext').file_size == 10
            assert open(_script(library), 'rb').read() == before

    def test_the_deadline_stops_and_the_next_load_starts_where_it_stopped(self, library):
        _in_line(library)
        _set_row(library, 'file_video.ext', file_size=None)
        _set_row(library, 'file.ext', file_size=None)
        now = [0.0]

        def slow(seconds):
            def run(_path):
                now[0] += 30.0                               # past the 20 s deadline
                return probe(seconds)
            return run

        fake = FakeProbe({'file_video.ext': slow(90.0), 'file.ext': slow(30.0)})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(library), _uuid(library), clock=lambda: now[0])
            assert len(fake.calls) == 1
            first = fake.calls[0]
            _refresh(_mgr(library), _uuid(library), clock=lambda: now[0])
        assert len(fake.calls) == 2 and fake.calls[1] != first

    def test_any_exception_in_l1_is_swallowed(self, library):
        mgr = _mgr(library)
        with mock.patch.object(mgr, 'plan_media_refresh', side_effect=RuntimeError('boom')), \
                mock.patch.object(r.Logger, 'error') as error:
            report = _refresh(mgr, _uuid(library))
        assert report is None
        assert error.called

    def test_l1_does_not_change_the_projects_modified_date(self, library):
        _in_line(library)
        library.connect()
        before = Project.get(Project.unix_name == 'proj1').modified
        _set_xml_media(library, 'file_video.ext', duration=tc(80))
        _refresh(_mgr(library), _uuid(library))
        library.connect()
        assert Project.get(Project.unix_name == 'proj1').modified == before


class TestOneRefreshPerProject:
    def test_a_second_request_joins_the_running_one(self):
        calls = []

        class SlowDB:
            def plan_media_refresh(self, uuid):
                calls.append(uuid)
                time.sleep(0.3)
                return mock.Mock(has_work=False)

        async def both():
            async def engine_running():
                return False
            return await asyncio.gather(
                r.refresh_media_before_load(SlowDB(), 'u1', executor=None,
                                            engine_running=engine_running),
                r.refresh_media_before_load(SlowDB(), 'u1', executor=None,
                                            engine_running=engine_running))

        first, second = asyncio.run(both())
        assert calls == ['u1']
        assert first == second


class TestProjectReady:
    def _user(self, project_db):
        from cuemseditor.CuemsWsUser import CuemsWsUser
        user = object.__new__(CuemsWsUser)
        user.websocket = mock.Mock()
        user.outgoing = asyncio.Queue()
        user.server = mock.Mock()
        user.server.executor = None
        user.server.db.project = project_db
        return user

    def test_the_load_request_reaches_the_engine_whatever_l1_does(self):
        project_db = mock.Mock()
        project_db.get_project_unix_name.return_value = 'proj1'
        project_db.plan_media_refresh.side_effect = RuntimeError('boom')
        user = self._user(project_db)
        sent = []

        async def engine(action, action_uuid, command, query_mode=False):
            sent.append(command['action'])
            return 'OK'

        async def run():
            user.server.event_loop = asyncio.get_running_loop()
            with mock.patch.object(user, 'comunicate_with_engine', side_effect=engine):
                await user.project_ready('u1', 'project_ready')

        asyncio.run(run())
        assert sent == ['project_ready']

    def test_the_status_query_maps_the_engines_reply(self):
        user = self._user(mock.Mock())

        async def ask(value):
            async def engine(action, action_uuid, command, query_mode=False):
                assert (command['action'], query_mode) == ('project_status', True)
                if isinstance(value, Exception):
                    raise value
                return value
            with mock.patch.object(user, 'comunicate_with_engine', side_effect=engine):
                return await user._engine_running()

        assert asyncio.run(ask({'status': 'running', 'project_uuid': 'x'})) is True
        assert asyncio.run(ask({'status': 'none', 'project_uuid': ''})) is False
        assert asyncio.run(ask(RuntimeError('timeout'))) is None
        assert asyncio.run(ask('OK')) is None


# ---------------------------------------------------------------------------
# L1 step 3: video indexes
# ---------------------------------------------------------------------------

def _fake_indexer(tmp_path, monkeypatch, mode='ok', sleep=0.0):
    """A ``cuems-videoindexer`` on PATH: 'ok' writes a valid header, 'fail'
    exits 1, 'stale' exits 0 and writes a header that does not match."""
    bindir = tmp_path / 'bin'
    bindir.mkdir(exist_ok=True)
    script = bindir / 'cuems-videoindexer'
    script.write_text(f'''#!{sys.executable}
import os, struct, sys, time
time.sleep({sleep})
path = sys.argv[1]
if {mode!r} == 'fail':
    sys.exit(1)
st = os.stat(path)
size = st.st_size if {mode!r} == 'ok' else st.st_size + 1
d = os.path.join(os.path.dirname(path), 'indexes')
os.makedirs(d, exist_ok=True)
with open(os.path.join(d, os.path.basename(path) + '.idx'), 'wb') as f:
    f.write(struct.pack('<4sIqqq', b'CXID', 1, size, int(st.st_mtime), 5) + bytes(64))
''')
    script.chmod(0o755)
    monkeypatch.setenv('PATH', f'{bindir}{os.pathsep}{os.environ.get("PATH", "")}')
    return script


class TestVideoIndexer:
    def _video(self, tmp_path):
        video = tmp_path / 'media' / 'clip.mp4'
        video.parent.mkdir(exist_ok=True)
        video.write_bytes(b'v' * 64)
        return str(video)

    def test_success_is_the_exit_code_and_a_matching_header(self, tmp_path, monkeypatch):
        _fake_indexer(tmp_path, monkeypatch, 'ok')
        video = self._video(tmp_path)
        assert asyncio.run(m.run_video_indexer(video)) is True
        assert video_index_state(video) == INDEX_VALID

    def test_a_failure_or_a_header_that_still_does_not_match_is_a_failure(self, tmp_path, monkeypatch):
        for mode in ('fail', 'stale'):
            _fake_indexer(tmp_path, monkeypatch, mode)
            assert asyncio.run(m.run_video_indexer(self._video(tmp_path))) is False

    def test_a_missing_indexer_is_a_failure(self, tmp_path, monkeypatch):
        monkeypatch.setenv('PATH', str(tmp_path / 'empty'))
        assert asyncio.run(m.run_video_indexer(self._video(tmp_path))) is False

    def test_a_busy_indexer_is_not_waited_for(self, tmp_path, monkeypatch):
        _fake_indexer(tmp_path, monkeypatch, 'ok', sleep=0.5)
        video = self._video(tmp_path)
        other = str(tmp_path / 'media' / 'other.mp4')
        open(other, 'wb').write(b'o' * 32)

        async def both():
            far = time.monotonic() + 60
            return await asyncio.gather(r._index_videos([video], far),
                                        r._index_videos([other], far))

        start = time.monotonic()
        first, second = asyncio.run(both())
        assert first['indexed'] == 1
        assert second['index_busy'] == 1 and second['indexed'] == 0
        assert time.monotonic() - start < 2.0

    def test_a_replaced_video_is_reindexed_before_the_load(self, library, tmp_path, monkeypatch):
        _fake_indexer(tmp_path, monkeypatch, 'ok')
        _in_line(library)
        _add_row(library, 'clip.mp4', 'MOVIE', duration=tc(90.0), file_size=10,
                 pixel_width=1920, pixel_height=1080)
        _set_xml_media(library, 'file_video.ext', rename='clip.mp4')
        clip = _write(library, 'clip.mp4', 10)
        _valid_idx(clip)
        _write(library, 'clip.mp4', 10, fill=b'z')        # same size, new content
        os.utime(clip, (5, 5))
        with mock.patch.object(p, 'probe_media', FakeProbe({'clip.mp4': probe(90.0, (1920, 1080))})):
            plan = _mgr(library).plan_media_refresh(_uuid(library))
            assert {c.file_name: c.state for c in plan.checks}['clip.mp4'] == 'changed'
            report = _refresh(_mgr(library), _uuid(library))
        assert report['indexed'] == 1
        assert video_index_state(clip) == INDEX_VALID

    def test_a_video_the_sync_does_not_carry_is_never_work(self, library):
        _in_line(library)
        _add_row(library, 'clip.webm', 'MOVIE', duration=tc(90.0), file_size=10)
        _set_xml_media(library, 'file_video.ext', rename='clip.webm')
        _write(library, 'clip.webm', 10)               # no .idx at all
        assert not _mgr(library).plan_media_refresh(_uuid(library)).has_work

    def test_an_index_failure_leaves_the_rows_and_is_not_retried(self, library, tmp_path, monkeypatch):
        _fake_indexer(tmp_path, monkeypatch, 'fail')
        _in_line(library)
        _add_row(library, 'clip.mp4', 'MOVIE', duration=tc(90.0), file_size=10)
        _set_xml_media(library, 'file_video.ext', rename='clip.mp4')
        _write(library, 'clip.mp4', 10)                # no .idx: index only
        first = _refresh(_mgr(library), _uuid(library))
        second = _refresh(_mgr(library), _uuid(library), engine='running')
        assert first['index_failed'] == 1
        assert _row(library, 'clip.mp4').file_size == 10
        assert second['engine_asked'] is False


# ---------------------------------------------------------------------------
# Saving safely
# ---------------------------------------------------------------------------

class TestSavingSafely:
    def test_the_project_lock_is_reentrant(self, library):
        mgr = _mgr(library)
        done = []

        def nested():
            with mgr.project_lock('u'):
                with mgr.project_lock('u'):
                    done.append(True)

        t = threading.Thread(target=nested)
        t.start()
        t.join(5)
        assert done == [True]

    def test_update_holding_its_transaction_and_l1_do_not_deadlock(self, library):
        _in_line(library)
        _set_xml_media(library, 'file_video.ext', duration=tc(80))   # L1 has work
        mgr = _mgr(library)
        uuid = _uuid(library)
        data = XmlReaderWriter(schema_name='script', xmlfile=_script(library)).read()
        data['CuemsScript']['name'] = 'Edited By Update'
        inside, release = threading.Event(), threading.Event()
        errors = []
        real = mgr.update_media_relations

        def slow_relations(*a, **k):
            inside.set()
            release.wait(5)
            return real(*a, **k)

        def run(fn, *args):
            try:
                fn(*args)
            except Exception as e:          # noqa: BLE001
                errors.append(e)

        with mock.patch.object(mgr, 'update_media_relations', side_effect=slow_relations):
            t1 = threading.Thread(target=run, args=(mgr.update, uuid, data))
            t1.start()
            assert inside.wait(5)
            t2 = threading.Thread(target=run, args=(mgr.rewrite_project_media, uuid))
            t2.start()
            time.sleep(0.3)
            assert t2.is_alive()             # waits for the project lock, not SQLite
            release.set()
            t1.join(10)
            t2.join(10)
        assert not t1.is_alive() and not t2.is_alive()
        assert errors == []
        saved = XmlReaderWriter(schema_name='script', xmlfile=_script(library)).read()
        assert saved['CuemsScript']['name'] == 'Edited By Update'

    def test_duplicate_takes_the_source_lock_before_its_transaction(self, library):
        mgr = _mgr(library)
        order = []
        real_lock, real_atomic = mgr.project_lock, mgr.db.atomic

        def lock(uuid):
            order.append('lock')
            return real_lock(uuid)

        def atomic(*a, **k):
            order.append('atomic')
            return real_atomic(*a, **k)

        with mock.patch.object(mgr, 'project_lock', side_effect=lock), \
                mock.patch.object(mgr.db, 'atomic', side_effect=atomic):
            mgr.duplicate(_uuid(library))
        assert order[:2] == ['lock', 'atomic']

    def test_a_failed_write_leaves_the_old_file_and_no_temporary(self, library):
        mgr = _mgr(library)
        before = open(_script(library), 'rb').read()
        obj = mock.Mock()
        with mock.patch.object(p.XmlReaderWriter, 'write_from_object', side_effect=ValueError('bad')):
            with pytest.raises(ValueError):
                mgr.save_xml('proj1', obj)
        assert open(_script(library), 'rb').read() == before
        assert [f for f in os.listdir(os.path.dirname(_script(library))) if f.endswith('.tmp')] == []

    def test_the_new_file_keeps_the_old_mode(self, library):
        _in_line(library)
        os.chmod(_script(library), 0o604)
        _set_xml_media(library, 'file_video.ext', duration=tc(80))
        _refresh(_mgr(library), _uuid(library))
        assert stat.S_IMODE(os.stat(_script(library)).st_mode) == 0o604

    @pytest.mark.skipif(os.geteuid() == 0, reason='root ignores directory permissions')
    def test_an_unwritable_directory_falls_back_to_writing_in_place(self, library):
        _in_line(library)
        _set_xml_media(library, 'file_video.ext', duration=tc(80))
        d = os.path.dirname(_script(library))
        os.chmod(_script(library), 0o666)
        os.chmod(d, 0o555)
        try:
            report = _refresh(_mgr(library), _uuid(library))
        finally:
            os.chmod(d, 0o755)
        assert report['rewritten'] is True
        assert all(mm['duration'] == tc(90.0) for mm in _media_of(library, 'file_video.ext'))

    def test_backups_only_when_writing_and_the_last_three_kept(self, library):
        _in_line(library)
        for seconds in (81, 82, 83, 84):
            _set_xml_media(library, 'file_video.ext', duration=tc(seconds))
            _refresh(_mgr(library), _uuid(library))
            time.sleep(0.01)
        _refresh(_mgr(library), _uuid(library))           # nothing to do: no backup
        assert len(_backups(library)) == 3

    def test_a_duplicate_does_not_inherit_the_backups(self, library):
        _in_line(library)
        _set_xml_media(library, 'file_video.ext', duration=tc(80))
        _refresh(_mgr(library), _uuid(library))
        assert _backups(library)
        _mgr(library).duplicate(_uuid(library))
        dup = [d for d in os.listdir(library.projects_dir) if d != 'proj1'][0]
        assert _backups(library, dup) == []


# ---------------------------------------------------------------------------
# D13: a save that meets a legacy row
# ---------------------------------------------------------------------------

class TestSaveVerifiesLegacyRows:
    def test_a_save_verifies_a_legacy_rows_duration_too(self, library):
        _write(library, 'file_video.ext', 55)
        _set_row(library, 'file_video.ext', duration='00:00:00.000')
        data = XmlReaderWriter(schema_name='script', xmlfile=_script(library)).read()
        fake = FakeProbe({'file_video.ext': probe(90.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake):
            _mgr(library).update(_uuid(library), data)
        row = _row(library, 'file_video.ext')
        assert (row.duration, row.pixel_width, row.file_size) == (tc(90.0), 1280, 55)
        assert fake.calls == ['file_video.ext']
        assert all(mm['duration'] == tc(90.0) for mm in _media_of(library, 'file_video.ext'))

    def test_a_save_stops_verifying_at_the_deadline(self, library):
        _write(library, 'file_video.ext', 55)
        data = XmlReaderWriter(schema_name='script', xmlfile=_script(library)).read()
        fake = FakeProbe({'file_video.ext': probe(90.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake), \
                mock.patch.object(p, 'REFRESH_DEADLINE_S', 0):
            _mgr(library).update(_uuid(library), data)
        assert fake.calls == []
        assert _row(library, 'file_video.ext').file_size is None


# ---------------------------------------------------------------------------
# Q2: re-upload after a permanent deletion
# ---------------------------------------------------------------------------

def _dangling(library, project_unix, name):
    library.connect()
    project = Project.get(Project.unix_name == project_unix)
    ProjectMedia.create(project=project, media=None, media_filename=name)


class TestReupload:
    def test_the_cleanup_deletes_only_the_reuploaded_files_rows(self, library):
        _dangling(library, 'proj1', 'x.wav')
        _dangling(library, 'proj1', 'y.wav')
        _mgr(library).deletele_mising_media_references('x.wav')
        library.connect()
        names = sorted(pm.media_filename for pm in ProjectMedia.select())
        assert names == ['y.wav']

    def test_relinked_live_projects_are_rewritten_and_trashed_ones_skipped(self, library):
        _in_line(library)
        shutil.copytree(os.path.join(library.projects_dir, 'proj1'),
                        os.path.join(library.projects_dir, 'proj2'))
        library.connect()
        Project.create(uuid=str(new_uuid()), name='Proj Two', unix_name='proj2',
                       created=new_datetime(), modified=new_datetime(), in_trash=False)
        mgr = _mgr(library)
        mgr.delete(_uuid(library, 'proj2'))                # trashed
        _set_row(library, 'file_video.ext', duration=tc(120.0), file_size=11)
        mgr.update_projects_existed_media(_uuid(library, 'proj1'), 'file_video.ext')
        mgr.update_projects_existed_media(_uuid(library, 'proj2'), 'file_video.ext')
        assert all(mm['duration'] == tc(120.0) for mm in _media_of(library, 'file_video.ext'))

    def test_one_failing_project_does_not_fail_the_upload(self, library):
        from cuemseditor.CuemsUpload import CuemsUpload
        upload = object.__new__(CuemsUpload)
        upload.server = mock.Mock()
        upload.server.db.media.check_if_media_existed_in_projects.return_value = [
            mock.Mock(project_id='a'), mock.Mock(project_id='b')]
        upload.server.db.project.update_projects_existed_media.side_effect = [
            RuntimeError('broken project'), None]
        upload.check_if_media_existed('file.ext')
        assert upload.server.db.project.update_projects_existed_media.call_count == 2

    def test_export_skips_a_dangling_row(self, library):
        _in_line(library)
        _dangling(library, 'proj1', 'gone-forever.wav')
        os.makedirs(os.path.join(library.root, 'www', 'exports'), exist_ok=True)
        os.makedirs(os.path.join(library.root, 'tmp'), exist_ok=True)
        assert _mgr(library).export(_uuid(library)).endswith('.zip')
