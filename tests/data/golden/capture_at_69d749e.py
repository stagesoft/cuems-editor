"""Capture harness for tests/data/golden/ (not collected: the name does not start with test_): runs the released producer at 69d749e and dumps its frames."""
import json
import os
from unittest import mock

import cuemseditor.CuemsDBProject as p
import cuemseditor.CuemsMediaRefresh as r
from test_media_refresh import (  # noqa: F401  (fixtures and helpers of the released test file)
    FakeProbe, MD5, _fresh_marks, _in_line, _mgr, _refresh, _report, _set_row, _set_xml_media, _uuid, _write, probe, tc,
    asyncio)

OUT = os.environ['GOLDEN_OUT']


def dump(name, value):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name + '.json'), 'w') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def test_all_clear_ready(library):
    _in_line(library)
    dump('media_check_report_all_clear', _refresh(_mgr(library), _uuid(library))['media_report'])


def test_ready_stale_video(library):
    _in_line(library)
    _set_row(library, 'file_video.ext', file_md5=MD5)
    _write(library, 'file_video.ext', 11)
    fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
    with mock.patch.object(p, 'probe_media', fake):
        report = _refresh(_mgr(library), _uuid(library))
    dump('media_check_report_ready', report['media_report'])


def test_open_grouped(library):
    _in_line(library)
    _set_row(library, 'file_video.ext', duration=tc(120.0), file_size=11, pixel_width=1280, pixel_height=720)
    _set_xml_media(library, 'file_video.ext', pixel_width=1920, pixel_height=1080, file_size=10, file_md5=MD5)
    _write(library, 'file_video.ext', 11)
    dump('media_check_report_open', _report(_mgr(library), _uuid(library), 'open'))


def test_save_with_stale_audio_and_video(library):
    _in_line(library)
    _set_row(library, 'file.ext', duration=tc(45.0), file_size=25)
    _set_row(library, 'file_video.ext', duration=tc(120.0), file_size=11, pixel_width=1280, pixel_height=720)
    _write(library, 'file.ext', 25)
    _write(library, 'file_video.ext', 11)
    dump('media_check_report_save', _report(_mgr(library), _uuid(library), 'save'))


def test_copy_in_progress(library):
    _in_line(library)
    path = _write(library, 'file_video.ext', 11)

    def growing(_path):
        with open(path, 'ab') as f:
            f.write(b'more')
        return probe(120.0, (1280, 720))

    with mock.patch.object(p, 'probe_media', FakeProbe({'file_video.ext': growing})):
        report = _refresh(_mgr(library), _uuid(library))
    dump('media_check_report_copy_in_progress', report['media_report'])


def test_engine_running_is_incomplete(library):
    _in_line(library)
    _write(library, 'file_video.ext', 11)
    with mock.patch.object(p, 'probe_media', FakeProbe({})):
        report = _refresh(_mgr(library), _uuid(library), engine='running')
    dump('media_check_report_engine_running', report['media_report'])
