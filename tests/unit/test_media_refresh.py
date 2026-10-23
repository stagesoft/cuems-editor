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
  sync carries), re-probes what changed, corrects the DB rows and re-indexes
  a changed video. It never rewrites the project (D21): it reports the stale
  values in ``media_check_report``, which the UI shows (D22), and the next
  save writes them.
* At ``project_load`` a read-only check reports too, after the project frame;
  after a save, a report clears the warning on every session of the project.
* D13: a save that meets a legacy row or a changed file measures it first.
* Q2: a re-upload after a permanent deletion only relinks.
* Saving: an atomic write that keeps the file's mode.

Design: cuems-RELATIONS Plans/2026-10-01-engine-late-go-media-probe.md §7, §8.
"""
import asyncio
import json
import os
import shutil
import stat
import struct
import sys
import time
import xml.etree.ElementTree as ET  # test helper only: edits the fixture script on disk
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
from cuemsutils.cues import CueList, CuemsScript
from support.refresh_helpers import (  # noqa: F401  (fixtures are used by name)
    FakeProbe,
    MD5,
    STORED,
    _add_row,
    _backups,
    _blocks,
    _bytes,
    _changes,
    _fake_indexer,
    _fresh_marks,
    _idx_header,
    _in_line,
    _media_of,
    _mgr,
    _refresh,
    _report,
    _row,
    _script,
    _set_row,
    _set_xml_media,
    _settings,
    _uuid,
    _valid_idx,
    _write,
    _write_idx,
    lib,
    probe,
    tc)



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
# Step 1: read and compare, without writing anything
# ---------------------------------------------------------------------------


class TestPlan:
    def test_an_unchanged_library_has_no_work(self, lib):
        _in_line(lib)
        mgr = _mgr(lib)
        fake = FakeProbe({})
        with mock.patch.object(p, 'probe_media', fake):
            plan = mgr.plan_media_refresh(_uuid(lib))
            report = _refresh(mgr, _uuid(lib), engine='running')  # never asked
        assert not plan.has_work and not plan.has_stale_values
        assert fake.calls == []
        assert report['engine_asked'] is False
        mr = report['media_report']
        assert mr['complete'] is True and mr['files'] == [] and mr['unverified'] == []

    def test_a_replaced_file_is_changed(self, lib):
        _in_line(lib)
        _write(lib, 'file_video.ext', 11)
        plan = _mgr(lib).plan_media_refresh(_uuid(lib))
        states = {c.file_name: c.state for c in plan.checks}
        assert states == {'file_video.ext': 'changed', 'file.ext': 'unchanged'}
        assert plan.has_work

    def test_a_row_without_a_size_is_legacy(self, lib):
        _in_line(lib)
        _set_row(lib, 'file.ext', file_size=None)
        plan = _mgr(lib).plan_media_refresh(_uuid(lib))
        assert {c.file_name: c.state for c in plan.checks}['file.ext'] == 'legacy'

    def test_a_missing_or_empty_file_and_an_orphan_are_skipped(self, lib):
        _in_line(lib)
        os.remove(os.path.join(lib.root, 'media', 'file.ext'))
        _write(lib, 'file_video.ext', 0)
        _set_xml_media(lib, 'file_video.ext', rename='nobody.ext')
        plan = _mgr(lib).plan_media_refresh(_uuid(lib))
        assert all(c.state == 'skipped' for c in plan.checks)
        assert not plan.has_work

    def test_missing_values_are_not_stale(self, lib):
        _in_line(lib)                     # the XML has no stored values at all
        assert not _mgr(lib).plan_media_refresh(_uuid(lib)).has_stale_values

    def test_matching_values_read_as_strings_are_not_stale(self, lib):
        _in_line(lib)
        _set_row(lib, 'file_video.ext', file_md5=MD5)
        _set_xml_media(lib, 'file_video.ext', pixel_width=1920, pixel_height=1080,
                       file_size=10, file_md5=MD5)
        assert not _mgr(lib).plan_media_refresh(_uuid(lib)).has_stale_values

    def test_a_present_wrong_duration_is_stale_but_no_work(self, lib):
        _in_line(lib)
        _set_xml_media(lib, 'file_video.ext', duration=tc(80))
        plan = _mgr(lib).plan_media_refresh(_uuid(lib))
        assert plan.has_stale_values
        assert not plan.has_work                # nothing to measure: no engine query

    def test_a_null_db_duration_is_never_stale(self, lib):
        _in_line(lib)
        _set_row(lib, 'file_video.ext', duration=None)
        assert not _mgr(lib).plan_media_refresh(_uuid(lib)).has_stale_values

    def test_a_stored_value_the_db_does_not_have_is_stale(self, lib):
        _in_line(lib)
        _set_xml_media(lib, 'file_video.ext', file_size=10, file_md5=MD5)   # row: no md5
        assert _mgr(lib).plan_media_refresh(_uuid(lib)).has_stale_values

    def test_pixel_keys_on_an_audio_cue_are_stale(self, lib):
        _in_line(lib)
        _set_xml_media(lib, 'file.ext', pixel_width=10, pixel_height=10)
        assert _mgr(lib).plan_media_refresh(_uuid(lib)).has_stale_values

    def test_a_trashed_project_is_not_planned(self, lib):
        _in_line(lib)
        _mgr(lib).delete(_uuid(lib))
        with pytest.raises(Exception):
            _mgr(lib).plan_media_refresh(_uuid(lib))


# ---------------------------------------------------------------------------
# The report (media_check_report's value)
# ---------------------------------------------------------------------------

class TestReport:
    def test_changes_are_grouped_by_file_with_the_cues_counted(self, lib):
        _in_line(lib)
        _set_row(lib, 'file_video.ext', duration=tc(120.0), file_size=11,
                 pixel_width=1280, pixel_height=720)
        _set_xml_media(lib, 'file_video.ext', pixel_width=1920, pixel_height=1080,
                       file_size=10, file_md5=MD5)
        _write(lib, 'file_video.ext', 11)
        mr = _report(_mgr(lib), _uuid(lib), 'open')
        assert mr['context'] == 'open' and mr['project_name'] == 'Proj One'
        assert [f['file_name'] for f in mr['files']] == ['file_video.ext']
        assert mr['files'][0]['cues'] == 2                 # two VideoCues use it
        assert _changes(mr, 'file_video.ext') == {
            'duration': (tc(90.0), tc(120.0)),
            'pixel_size': ('1920x1080', '1280x720'),
            'file_size': ('10', '11'),
            'file_md5': (MD5, None)}
        assert mr['complete'] is True and mr['total_files'] == 1

    def test_a_changed_file_not_yet_measured_is_unverified(self, lib):
        _in_line(lib)
        _write(lib, 'file_video.ext', 11)              # row still says 10
        mr = _report(_mgr(lib), _uuid(lib), 'open')
        assert mr['unverified'] == ['file_video.ext']
        assert mr['files'] == []

    def test_a_legacy_row_is_not_unverified(self, lib):
        _in_line(lib)
        _set_row(lib, 'file.ext', file_size=None)
        assert _report(_mgr(lib), _uuid(lib))['unverified'] == []

    def test_a_reason_makes_it_incomplete(self, lib):
        _in_line(lib)
        mr = _report(_mgr(lib), _uuid(lib), 'ready', 'engine_running')
        assert (mr['complete'], mr['reason']) == (False, 'engine_running')

    def test_a_file_whose_probe_failed_makes_it_incomplete(self, lib):
        _in_line(lib)
        _write(lib, 'file_video.ext', 11)
        fake = FakeProbe({'file_video.ext': probe(duration_state=PROBE_FAILED,
                                                  picture_state=PROBE_FAILED)})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(lib), _uuid(lib))
        mr = _report(_mgr(lib), _uuid(lib))
        assert (mr['complete'], mr['reason']) == (False, 'probe_failed')

    def test_the_files_are_capped(self):
        entries = [{'file_name': f'f{i:02d}.mov', 'cues': 1,
                    'changes': [{'field': 'duration', 'stored': '1', 'current': '2'}]}
                   for i in range(30)]
        files, total = p.cap_report_files(entries)
        assert len(files) == p.REPORT_FILES_MAX == 20 and total == 30


# ---------------------------------------------------------------------------
# L1 at project_ready (steps 0-3, then the report)
# ---------------------------------------------------------------------------

class TestRefresh:
    def test_a_replaced_file_corrects_the_row_and_reports_the_project(self, lib):
        _in_line(lib)
        _set_row(lib, 'file_video.ext', file_md5=MD5)
        _write(lib, 'file_video.ext', 11)
        before = _bytes(lib)
        mgr = _mgr(lib)
        fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake), \
                mock.patch.object(p.Logger, 'warning') as warning:
            report = _refresh(mgr, _uuid(lib))
        row = _row(lib, 'file_video.ext')
        assert (row.duration, row.pixel_width, row.pixel_height, row.file_size, row.file_md5) \
            == (tc(120.0), 1280, 720, 11, None)
        assert _bytes(lib) == before                  # D21: never rewritten at load
        assert _backups(lib) == []
        mr = report['media_report']
        assert mr['context'] == 'ready' and mr['complete'] is True
        assert _changes(mr, 'file_video.ext')['duration'] == (tc(90.0), tc(120.0))
        assert any('Proj One' in str(c) and 'stale' in str(c) for c in warning.call_args_list)

    def test_the_second_load_measures_nothing_and_still_reports(self, lib):
        _in_line(lib)
        _write(lib, 'file_video.ext', 11)
        mgr = _mgr(lib)
        fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(mgr, _uuid(lib))
            report = _refresh(mgr, _uuid(lib), engine='running')
        assert fake.calls == ['file_video.ext']
        assert report['engine_asked'] is False          # stale values alone are no work
        assert _changes(report['media_report'], 'file_video.ext')['duration'] == (tc(90.0), tc(120.0))

    def test_a_copy_in_progress_is_skipped_and_incomplete(self, lib):
        _in_line(lib)
        path = _write(lib, 'file_video.ext', 11)

        def growing(_path):
            with open(path, 'ab') as f:
                f.write(b'more')
            return probe(120.0, (1280, 720))

        with mock.patch.object(p, 'probe_media', FakeProbe({'file_video.ext': growing})):
            report = _refresh(_mgr(lib), _uuid(lib))
        row = _row(lib, 'file_video.ext')
        assert (row.duration, row.file_size) == (tc(90.0), 10)
        mr = report['media_report']
        assert (mr['complete'], mr['reason']) == (False, 'copy_in_progress')

    def test_a_legacy_row_is_verified_and_marked(self, lib):
        _in_line(lib)
        _set_row(lib, 'file.ext', file_size=None)
        before = _bytes(lib)
        with mock.patch.object(p, 'probe_media', FakeProbe({'file.ext': probe(30.0)})):
            report = _refresh(_mgr(lib), _uuid(lib))
        assert _row(lib, 'file.ext').file_size == 20
        assert _bytes(lib) == before
        mr = report['media_report']
        assert mr['complete'] and mr['files'] == [] and mr['unverified'] == []

    def test_a_legacy_row_with_the_old_rounding_is_corrected_and_reported(self, lib):
        _in_line(lib)
        _set_row(lib, 'file.ext', file_size=None, duration='00:05:32.009')
        _set_xml_media(lib, 'file.ext', duration='00:05:32.009')
        before = _bytes(lib)
        with mock.patch.object(p, 'probe_media', FakeProbe({'file.ext': probe(332.9)})), \
                mock.patch.object(p.Logger, 'warning') as warning:
            report = _refresh(_mgr(lib), _uuid(lib))
        assert _row(lib, 'file.ext').duration == '00:05:32.900'
        assert _bytes(lib) == before
        assert _changes(report['media_report'], 'file.ext')['duration'] == ('00:05:32.009', '00:05:32.900')
        assert any('00:05:32.009' in str(c) and '00:05:32.900' in str(c)
                   for c in warning.call_args_list)

    def test_an_audio_only_movie_is_marked_and_not_probed_again(self, lib):
        _in_line(lib)
        _set_row(lib, 'file_video.ext', file_size=None, pixel_width=None, pixel_height=None)
        fake = FakeProbe({'file_video.ext': probe(90.0)})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(lib), _uuid(lib))
            _refresh(_mgr(lib), _uuid(lib))
        row = _row(lib, 'file_video.ext')
        assert (row.file_size, row.pixel_width) == (10, None)
        assert fake.calls == ['file_video.ext']

    def test_a_failed_duration_probe_leaves_the_row_backs_off_and_is_incomplete(self, lib):
        _in_line(lib)
        _write(lib, 'file_video.ext', 11)
        fake = FakeProbe({'file_video.ext': probe(duration_state=PROBE_FAILED,
                                                  picture_state=PROBE_FAILED)})
        with mock.patch.object(p, 'probe_media', fake):
            first = _refresh(_mgr(lib), _uuid(lib))
            second = _refresh(_mgr(lib), _uuid(lib))
        row = _row(lib, 'file_video.ext')
        assert (row.duration, row.file_size) == (tc(90.0), 10)
        assert fake.calls == ['file_video.ext']          # not retried until it changes
        for report in (first, second):
            assert (report['media_report']['complete'], report['media_report']['reason']) \
                == (False, 'probe_failed')
        _write(lib, 'file_video.ext', 12)
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(lib), _uuid(lib))
        assert fake.calls == ['file_video.ext', 'file_video.ext']

    def test_a_failed_pixel_probe_still_writes_the_duration_and_the_mark(self, lib):
        _in_line(lib)
        _write(lib, 'file_video.ext', 11)
        fake = FakeProbe({'file_video.ext': probe(120.0, picture_state=PROBE_FAILED)})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(lib), _uuid(lib))
        row = _row(lib, 'file_video.ext')
        assert (row.duration, row.file_size, row.pixel_width) == (tc(120.0), 11, None)

    def test_an_image_needs_no_duration(self, lib):
        _in_line(lib)
        _write(lib, 'pic.png', 7)
        _set_xml_media(lib, 'file_video.ext', rename='pic.png')
        with mock.patch.object(p, 'probe_media', FakeProbe({'pic.png': probe(dims=(640, 480))})):
            _refresh(_mgr(lib), _uuid(lib))
            report = _refresh(_mgr(lib), _uuid(lib), engine='running')
        row = _row(lib, 'pic.png')
        assert (row.duration, row.pixel_width, row.file_size) == (None, 640, 7)
        assert report['engine_asked'] is False

    def test_an_audio_file_with_cover_art_gets_no_pixel_size(self, lib):
        _in_line(lib)
        _write(lib, 'file.ext', 21)
        with mock.patch.object(p, 'probe_media', FakeProbe({'file.ext': probe(31.0, (600, 600))})):
            _refresh(_mgr(lib), _uuid(lib))
        row = _row(lib, 'file.ext')
        assert (row.duration, row.pixel_width, row.file_size) == (tc(31.0), None, 21)

    def test_shared_media_is_reported_in_every_project(self, lib):
        _in_line(lib)
        shutil.copytree(os.path.join(lib.projects_dir, 'proj1'),
                        os.path.join(lib.projects_dir, 'proj2'))
        lib.connect()
        Project.create(uuid=str(new_uuid()), name='Proj Two', unix_name='proj2',
                       created=new_datetime(), modified=new_datetime(), in_trash=False)
        _write(lib, 'file_video.ext', 11)
        before = _bytes(lib, 'proj2')
        fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake):
            _refresh(_mgr(lib), _uuid(lib, 'proj1'))
            report = _refresh(_mgr(lib), _uuid(lib, 'proj2'))
        assert fake.calls == ['file_video.ext']             # B causes no probe
        assert _bytes(lib, 'proj2') == before
        assert _changes(report['media_report'], 'file_video.ext')['duration'] == (tc(90.0), tc(120.0))

    def test_audio_cue_pixel_keys_are_reported(self, lib):
        _in_line(lib)
        _set_xml_media(lib, 'file.ext', pixel_width=10, pixel_height=10)
        report = _refresh(_mgr(lib), _uuid(lib), engine='running')
        assert report['engine_asked'] is False
        assert _changes(report['media_report'], 'file.ext') == {'pixel_size': ('10x10', None)}

    def test_a_running_show_or_a_silent_engine_means_no_write_and_incomplete(self, lib):
        for engine, reason in (('running', 'engine_running'), ('silent', 'engine_silent')):
            _in_line(lib)
            _write(lib, 'file_video.ext', 11)
            before = _bytes(lib)
            fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
            with mock.patch.object(p, 'probe_media', fake):
                report = _refresh(_mgr(lib), _uuid(lib), engine=engine)
            assert report['engine_asked'] is True and report['skipped'] == engine
            assert fake.calls == []
            assert _row(lib, 'file_video.ext').file_size == 10
            assert _bytes(lib) == before
            mr = report['media_report']
            assert (mr['complete'], mr['reason']) == (False, reason)
            assert mr['unverified'] == ['file_video.ext']

    def test_the_deadline_stops_reports_incomplete_and_the_next_load_continues(self, lib):
        _in_line(lib)
        _set_row(lib, 'file_video.ext', file_size=None)
        _set_row(lib, 'file.ext', file_size=None)
        now = [0.0]

        def slow(seconds):
            def run(_path):
                now[0] += 30.0                               # past the 20 s deadline
                return probe(seconds)
            return run

        fake = FakeProbe({'file_video.ext': slow(90.0), 'file.ext': slow(30.0)})
        with mock.patch.object(p, 'probe_media', fake):
            first = _refresh(_mgr(lib), _uuid(lib), clock=lambda: now[0])
            assert len(fake.calls) == 1
            assert (first['media_report']['complete'], first['media_report']['reason']) \
                == (False, 'deadline')
            _refresh(_mgr(lib), _uuid(lib), clock=lambda: now[0])
        assert len(fake.calls) == 2 and fake.calls[1] != fake.calls[0]

    def test_any_exception_in_l1_is_swallowed(self, lib):
        mgr = _mgr(lib)
        with mock.patch.object(mgr, 'plan_media_refresh', side_effect=RuntimeError('boom')), \
                mock.patch.object(r.Logger, 'error') as error:
            report = _refresh(mgr, _uuid(lib))
        assert report is None
        assert error.called


class TestOneRefreshPerProject:
    def test_a_second_request_joins_the_running_one(self):
        calls = []

        class SlowDB:
            def plan_media_refresh(self, uuid):
                calls.append(uuid)
                time.sleep(0.3)
                return mock.Mock(has_work=False)

            def media_report(self, uuid, context, reason=None):
                return {'project_uuid': uuid, 'context': context}

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


# ---------------------------------------------------------------------------
# The check at open, and after a save
# ---------------------------------------------------------------------------

class TestOpenAndSave:
    def test_the_open_check_is_read_only(self, lib):
        _in_line(lib)
        _write(lib, 'file_video.ext', 11)
        fake = FakeProbe({})
        with mock.patch.object(p, 'probe_media', fake):
            mr = asyncio.run(r.check_media_on_open(_mgr(lib), _uuid(lib), executor=None))
        assert fake.calls == []
        assert _row(lib, 'file_video.ext').file_size == 10
        assert mr['context'] == 'open' and mr['unverified'] == ['file_video.ext']

    def test_simultaneous_opens_share_one_check(self):
        calls = []

        class SlowDB:
            def media_report(self, uuid, context, reason=None):
                calls.append(uuid)
                time.sleep(0.3)
                return {'project_uuid': uuid, 'context': context}

        async def three():
            return await asyncio.gather(*(r.check_media_on_open(SlowDB(), 'u1', executor=None)
                                          for _ in range(3)))

        results = asyncio.run(three())
        assert calls == ['u1'] and results[0] == results[1] == results[2]

    def test_a_failing_open_check_returns_nothing(self):
        class BrokenDB:
            def media_report(self, uuid, context, reason=None):
                raise RuntimeError('boom')

        with mock.patch.object(r.Logger, 'error') as error:
            assert asyncio.run(r.check_media_on_open(BrokenDB(), 'u1', executor=None)) is None
        assert error.called

    def test_a_save_measures_a_changed_file_and_writes_its_real_values(self, lib):
        _in_line(lib)
        _write(lib, 'file_video.ext', 11)               # replaced, never loaded since
        data = _mgr(lib).load(_uuid(lib))
        fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake):
            _mgr(lib).update(_uuid(lib), data)
        assert fake.calls == ['file_video.ext']
        assert all(str(mm['duration']) == tc(120.0) and mm['file_size'] == 11
                   for mm in _media_of(lib, 'file_video.ext'))
        mr = _report(_mgr(lib), _uuid(lib), 'save')
        assert mr['complete'] and mr['files'] == [] and mr['unverified'] == []


class TestSessions:
    def _server(self, users):
        from cuemseditor.CuemsWsServer import CuemsWsServer
        server = object.__new__(CuemsWsServer)
        server.users = users
        return server

    def _session(self):
        s = mock.Mock()
        s.outgoing = asyncio.Queue()
        return s

    def test_a_report_reaches_every_session_on_the_project_once(self):
        a, b, c = self._session(), self._session(), self._session()

        async def run():
            server = self._server({a: 'p1', b: 'p1', c: 'p2'})
            await server.send_to_project_sessions('p1', 'FRAME', skip=a)
            return a.outgoing.qsize(), b.outgoing.qsize(), c.outgoing.qsize()

        assert asyncio.run(run()) == (0, 1, 0)


class TestProjectReady:
    def _user(self, project_db, users=None):
        from cuemseditor.CuemsWsUser import CuemsWsUser
        user = object.__new__(CuemsWsUser)
        user.websocket = mock.Mock()
        user.outgoing = asyncio.Queue()
        user.server = mock.Mock()
        user.server.executor = None
        user.server.db.project = project_db
        user.server.send_to_project_sessions = mock.AsyncMock()
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

    def test_the_report_follows_the_reply_and_reaches_the_project_sessions(self):
        project_db = mock.Mock()
        project_db.get_project_unix_name.return_value = 'proj1'
        project_db.plan_media_refresh.return_value = mock.Mock(has_work=False)
        project_db.media_report.return_value = {'project_uuid': 'u1', 'context': 'ready',
                                                'complete': True, 'files': [], 'unverified': []}
        user = self._user(project_db)

        async def engine(action, action_uuid, command, query_mode=False):
            return 'OK'

        async def run():
            user.server.event_loop = asyncio.get_running_loop()
            with mock.patch.object(user, 'comunicate_with_engine', side_effect=engine):
                await user.project_ready('u1', 'project_ready')
            frames = []
            while not user.outgoing.empty():
                frames.append(json.loads(await user.outgoing.get()))
            return frames

        frames = asyncio.run(run())
        assert [f['type'] for f in frames] == ['project_ready', 'media_check_report']
        user.server.send_to_project_sessions.assert_awaited_once()
        assert user.server.send_to_project_sessions.await_args.kwargs.get('skip') is user

    def test_the_project_frame_goes_first_at_open(self):
        from cuemseditor import CuemsWsUser as ws_user
        project_db = mock.Mock()
        # 002: a load is ``open`` (project, library report, md5, media_repairs, rows digest)
        project_db.open.return_value = ({'CuemsScript': {}}, mock.Mock(), 'md5', [], 'digest')
        project_db.media_report.return_value = {'project_uuid': 'u1', 'context': 'open',
                                                'complete': True, 'files': [], 'unverified': []}
        user = self._user(project_db)
        user.server.users = {}
        user.server.sessions = {'s': {}}
        user.server.repair_gates = {}
        user.session_id = 's'

        async def run():
            user.server.event_loop = asyncio.get_running_loop()
            with mock.patch.object(ws_user, 'derive_gate', return_value={'report_id': 'r', 'media_repairs': []}), \
                    mock.patch.object(ws_user, 'load_report_value', return_value={}):
                await user.send_project('u1', 'project_load')
            await asyncio.sleep(0.3)                      # the background check
            frames = []
            while not user.outgoing.empty():
                frames.append(json.loads(await user.outgoing.get()))
            return frames

        frames = asyncio.run(run())
        # the library's load report (002) sits between the project frame and the media report
        assert [f['type'] for f in frames] == ['project', 'document_load_report', 'media_check_report']

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


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------

class TestSaving:
    # Retired (003, FR-023): "a failed write leaves the old file and no temporary" and "an
    # unwritable directory falls back to writing in place" tested the editor's own atomic writer
    # (a temp file, os.replace, XmlReaderWriter). The script is now written by the library's
    # CuemsScript.save, which owns atomicity, so the editor no longer carries that code. The first
    # property is the library's (utils CuemsScript.save: "answers atomically"); the second is a
    # behaviour that did not survive: the library raises when it cannot create its temporary file,
    # where the released editor wrote in place. Reported to cuems-utils (upstream-reports).

    def test_a_save_keeps_the_old_mode(self, lib):
        _in_line(lib)
        os.chmod(_script(lib), 0o604)
        data = _mgr(lib).load(_uuid(lib))
        _mgr(lib).update(_uuid(lib), data)
        assert stat.S_IMODE(os.stat(_script(lib)).st_mode) == 0o604

    def test_no_project_lock_and_no_backups_any_more(self):
        assert not hasattr(p.CuemsDBProject, 'project_lock')
        assert not hasattr(p.CuemsDBProject, 'rewrite_project_media')
        assert not hasattr(p.CuemsDBProject, '_backup_script')

    def test_a_duplicate_does_not_copy_leftover_backups(self, lib):
        _in_line(lib)
        open(_script(lib) + '.pre-refresh-20261005T000000Z', 'w').write('old')
        _mgr(lib).duplicate(_uuid(lib))
        dup = [d for d in os.listdir(lib.projects_dir) if d != 'proj1'][0]
        assert _backups(lib, dup) == []


# ---------------------------------------------------------------------------
# D13: a save that meets a legacy row
# ---------------------------------------------------------------------------

class TestSaveVerifiesLegacyRows:
    def test_a_save_verifies_a_legacy_rows_duration_too(self, lib):
        _write(lib, 'file_video.ext', 55)
        _set_row(lib, 'file_video.ext', duration='00:00:00.000')
        data = _mgr(lib).load(_uuid(lib))
        fake = FakeProbe({'file_video.ext': probe(90.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake):
            _mgr(lib).update(_uuid(lib), data)
        row = _row(lib, 'file_video.ext')
        assert (row.duration, row.pixel_width, row.file_size) == (tc(90.0), 1280, 55)
        assert fake.calls == ['file_video.ext']
        assert all(str(mm['duration']) == tc(90.0) for mm in _media_of(lib, 'file_video.ext'))

    def test_a_save_stops_verifying_at_the_deadline(self, lib):
        _write(lib, 'file_video.ext', 55)
        data = _mgr(lib).load(_uuid(lib))
        fake = FakeProbe({'file_video.ext': probe(90.0, (1280, 720))})
        with mock.patch.object(p, 'probe_media', fake), \
                mock.patch.object(p, 'REFRESH_DEADLINE_S', 0):
            _mgr(lib).update(_uuid(lib), data)
        assert fake.calls == []
        assert _row(lib, 'file_video.ext').file_size is None


# ---------------------------------------------------------------------------
# Q2: re-upload after a permanent deletion
# ---------------------------------------------------------------------------

def _dangling(lib, project_unix, name):
    lib.connect()
    project = Project.get(Project.unix_name == project_unix)
    ProjectMedia.create(project=project, media=None, media_filename=name)


class TestReupload:
    def test_the_cleanup_deletes_only_the_reuploaded_files_rows(self, lib):
        _dangling(lib, 'proj1', 'x.wav')
        _dangling(lib, 'proj1', 'y.wav')
        _mgr(lib).deletele_mising_media_references('x.wav')
        lib.connect()
        names = sorted(pm.media_filename for pm in ProjectMedia.select())
        assert names == ['y.wav']

    def test_a_reupload_only_relinks_and_trashed_projects_are_skipped(self, lib):
        _in_line(lib)
        shutil.copytree(os.path.join(lib.projects_dir, 'proj1'),
                        os.path.join(lib.projects_dir, 'proj2'))
        lib.connect()
        Project.create(uuid=str(new_uuid()), name='Proj Two', unix_name='proj2',
                       created=new_datetime(), modified=new_datetime(), in_trash=False)
        mgr = _mgr(lib)
        mgr.delete(_uuid(lib, 'proj2'))                # trashed
        _set_row(lib, 'file_video.ext', duration=tc(120.0), file_size=11)
        before = _bytes(lib)
        mgr.update_projects_existed_media(_uuid(lib, 'proj1'), 'file_video.ext')
        mgr.update_projects_existed_media(_uuid(lib, 'proj2'), 'file_video.ext')
        assert _bytes(lib) == before                   # relink only: D21
        mr = _report(_mgr(lib), _uuid(lib, 'proj1'))
        assert _changes(mr, 'file_video.ext')['duration'] == (tc(90.0), tc(120.0))

    def test_one_failing_project_does_not_fail_the_upload(self, lib):
        from cuemseditor.CuemsUpload import CuemsUpload
        upload = object.__new__(CuemsUpload)
        upload.server = mock.Mock()
        upload.server.db.media.check_if_media_existed_in_projects.return_value = [
            mock.Mock(project_id='a'), mock.Mock(project_id='b')]
        upload.server.db.project.update_projects_existed_media.side_effect = [
            RuntimeError('broken project'), None]
        upload.check_if_media_existed('file.ext')
        assert upload.server.db.project.update_projects_existed_media.call_count == 2

    def test_export_skips_a_dangling_row(self, lib):
        _in_line(lib)
        _dangling(lib, 'proj1', 'gone-forever.wav')
        os.makedirs(os.path.join(lib.root, 'www', 'exports'), exist_ok=True)
        os.makedirs(os.path.join(lib.root, 'tmp'), exist_ok=True)
        assert _mgr(lib).export(_uuid(lib)).endswith('.zip')
