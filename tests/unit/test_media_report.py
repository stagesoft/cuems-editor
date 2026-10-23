# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``media_check_report`` is the released frame, restored (003, FR-012 to FR-014, FR-020a).

Constitution I: the claim "byte-identical to 0.1.0rc1-4" is checked against payloads
captured from the released producer (``tests/data/golden/``, source and method in its
README), not by inspection. The scenarios are the capture's, run on the object API.
Only the fixture-generated ``project_uuid`` is normalised. Key order is compared too
(``json.dumps`` order), as the constitution counts it as part of the contract.

It is also the projection of the one comparison that feeds ``media_repairs``
(002 FR-043): grouped by file, it names the same stale values, and it never touches
the repair gate.
"""
from support.paths import DATA_DIR
import asyncio
import json
import os
from unittest import mock

import pytest

import cuemseditor.CuemsDBProject as p
import cuemseditor.CuemsMediaRefresh as r
from cuemseditor.CuemsDBProject import media_staleness

from support.refresh_helpers import (  # noqa: F401  (fixtures and helpers shared with the ported suite)
    FakeProbe, MD5, _fresh_marks, _in_line, _mgr, _refresh, _report, _script, _set_row, _set_xml_media,
    _uuid, _write, lib, probe, tc)

GOLDEN = str(DATA_DIR / 'golden')
FRAME_KEYS = ['project_uuid', 'project_name', 'context', 'complete', 'reason', 'files', 'unverified', 'total_files']
FILE_KEYS = ['file_name', 'cues', 'changes']
CHANGE_KEYS = ['field', 'stored', 'current']


def _golden(name):
    with open(os.path.join(GOLDEN, f'media_check_report_{name}.json'), encoding='utf-8') as f:
        return json.load(f)


def _same_as_golden(value, name):
    """Equal to the captured frame, including key order and value types, but for the project uuid."""
    expected = _golden(name)
    assert isinstance(value['project_uuid'], str) and value['project_uuid']
    value = dict(value, project_uuid=expected['project_uuid'])
    assert json.dumps(value) == json.dumps(expected)


def _shape(value):
    assert list(value) == FRAME_KEYS
    for entry in value['files']:
        assert list(entry) == FILE_KEYS
        assert all(list(change) == CHANGE_KEYS for change in entry['changes'])


def test_ready_matches_the_captured_frame(lib):
    _in_line(lib)
    _set_row(lib, 'file_video.ext', file_md5=MD5)
    _write(lib, 'file_video.ext', 11)
    with mock.patch.object(p, 'probe_media', FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})):
        value = _refresh(_mgr(lib), _uuid(lib))['media_report']
    _shape(value)
    _same_as_golden(value, 'ready')


def test_open_matches_the_captured_frame(lib):
    _in_line(lib)
    _set_row(lib, 'file_video.ext', duration=tc(120.0), file_size=11, pixel_width=1280, pixel_height=720)
    _set_xml_media(lib, 'file_video.ext', pixel_width=1920, pixel_height=1080, file_size=10, file_md5=MD5)
    _write(lib, 'file_video.ext', 11)
    value = _report(_mgr(lib), _uuid(lib), 'open')
    _shape(value)
    _same_as_golden(value, 'open')


def test_save_matches_the_captured_frame(lib):
    _in_line(lib)
    _set_row(lib, 'file.ext', duration=tc(45.0), file_size=25)
    _set_row(lib, 'file_video.ext', duration=tc(120.0), file_size=11, pixel_width=1280, pixel_height=720)
    _write(lib, 'file.ext', 25)
    _write(lib, 'file_video.ext', 11)
    value = _report(_mgr(lib), _uuid(lib), 'save')
    _shape(value)
    _same_as_golden(value, 'save')


def test_a_file_growing_during_its_probe_is_copy_in_progress(lib):
    _in_line(lib)
    path = _write(lib, 'file_video.ext', 11)

    def growing(_path):
        with open(path, 'ab') as f:
            f.write(b'more')
        return probe(120.0, (1280, 720))

    with mock.patch.object(p, 'probe_media', FakeProbe({'file_video.ext': growing})):
        value = _refresh(_mgr(lib), _uuid(lib))['media_report']
    _same_as_golden(value, 'copy_in_progress')
    assert (value['complete'], value['reason']) == (False, 'copy_in_progress')


def test_a_running_show_defers_the_probe_and_says_so(lib):
    _in_line(lib)
    _write(lib, 'file_video.ext', 11)
    with mock.patch.object(p, 'probe_media', FakeProbe({})):
        value = _refresh(_mgr(lib), _uuid(lib), engine='running')['media_report']
    _same_as_golden(value, 'engine_running')


def test_a_loaded_but_stopped_engine_does_not_defer_the_probe(lib):
    """``loaded`` is not "no answer": the changed file is measured (003 FR-015)."""
    _in_line(lib)
    _write(lib, 'file_video.ext', 11)
    fake = FakeProbe({'file_video.ext': probe(120.0, (1280, 720))})
    with mock.patch.object(p, 'probe_media', fake):
        value = _refresh(_mgr(lib), _uuid(lib), engine='loaded')['media_report']
    assert fake.calls == ['file_video.ext']
    assert value['reason'] is None and value['complete'] is True


def test_the_all_clear_matches_the_captured_frame(lib):
    _in_line(lib)
    value = _refresh(_mgr(lib), _uuid(lib))['media_report']
    _same_as_golden(value, 'all_clear')
    assert value['complete'] and value['files'] == [] and value['unverified'] == []


def test_the_report_is_the_media_repairs_grouped_by_file(lib):
    """One comparison, two projections (002 M9, 003 FR-013)."""
    _in_line(lib)
    _set_row(lib, 'file_video.ext', duration=tc(120.0), file_size=11, pixel_width=1280, pixel_height=720)
    _set_xml_media(lib, 'file_video.ext', pixel_width=1920, pixel_height=1080, file_size=10, file_md5=MD5)
    mgr = _mgr(lib)
    script, _ = mgr.load_with_report(_uuid(lib))
    repairs, _digest = media_staleness(script)
    value = _report(mgr, _uuid(lib), 'open')
    grouped = {}
    for entry in repairs:
        found = grouped.setdefault(entry['file_name'], [])
        item = (entry['field'], entry['stored'], entry['current'])
        if entry['field'] not in {field for field, _s, _c in found}:     # two cues, one finding
            found.append(item)
    reported = {f['file_name']: [(c['field'], c['stored'], c['current']) for c in f['changes']]
                for f in value['files']}
    assert reported == grouped and reported
    assert {f['file_name']: f['cues'] for f in value['files']} == {
        name: len({e['cue_id'] for e in repairs if e['file_name'] == name}) for name in grouped}


def test_the_report_never_touches_the_repair_gate(lib):
    from cuemseditor.CuemsWsServer import CuemsWsServer
    server = object.__new__(CuemsWsServer)
    server.repair_gates = {}
    _in_line(lib)
    _write(lib, 'file_video.ext', 11)
    _report(_mgr(lib), _uuid(lib), 'open')
    asyncio.run(r.check_media_on_open(_mgr(lib), _uuid(lib), executor=None))
    assert server.repair_gates == {}
