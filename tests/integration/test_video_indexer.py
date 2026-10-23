# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The video indexer, run for real (003 FR-016a; released in 0.1.0rc1-4).

Integration by the layout's rule: each case starts a real subprocess (a fake ``cuems-videoindexer`` placed on
``PATH``) through ``asyncio.create_subprocess_exec``. The orchestration around it is unit-tested in
``unit/test_media_refresh.py``.
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

    def test_a_replaced_video_is_reindexed_before_the_load(self, lib, tmp_path, monkeypatch):
        _fake_indexer(tmp_path, monkeypatch, 'ok')
        _in_line(lib)
        _add_row(lib, 'clip.mp4', 'MOVIE', duration=tc(90.0), file_size=10,
                 pixel_width=1920, pixel_height=1080)
        _set_xml_media(lib, 'file_video.ext', rename='clip.mp4')
        clip = _write(lib, 'clip.mp4', 10)
        _valid_idx(clip)
        _write(lib, 'clip.mp4', 10, fill=b'z')        # same size, new content
        os.utime(clip, (5, 5))
        with mock.patch.object(p, 'probe_media', FakeProbe({'clip.mp4': probe(90.0, (1920, 1080))})):
            plan = _mgr(lib).plan_media_refresh(_uuid(lib))
            assert {c.file_name: c.state for c in plan.checks}['clip.mp4'] == 'changed'
            report = _refresh(_mgr(lib), _uuid(lib))
        assert report['indexed'] == 1
        assert video_index_state(clip) == INDEX_VALID

    def test_a_video_the_sync_does_not_carry_is_never_work(self, lib):
        _in_line(lib)
        _add_row(lib, 'clip.webm', 'MOVIE', duration=tc(90.0), file_size=10)
        _set_xml_media(lib, 'file_video.ext', rename='clip.webm')
        _write(lib, 'clip.webm', 10)               # no .idx at all
        assert not _mgr(lib).plan_media_refresh(_uuid(lib)).has_work

    def test_an_index_failure_leaves_the_rows_and_is_not_retried(self, lib, tmp_path, monkeypatch):
        _fake_indexer(tmp_path, monkeypatch, 'fail')
        _in_line(lib)
        _add_row(lib, 'clip.mp4', 'MOVIE', duration=tc(90.0), file_size=10)
        _set_xml_media(lib, 'file_video.ext', rename='clip.mp4')
        _write(lib, 'clip.mp4', 10)                # no .idx: index only
        first = _refresh(_mgr(lib), _uuid(lib))
        second = _refresh(_mgr(lib), _uuid(lib), engine='running')
        assert first['index_failed'] == 1
        assert _row(lib, 'clip.mp4').file_size == 10
        assert second['engine_asked'] is False
