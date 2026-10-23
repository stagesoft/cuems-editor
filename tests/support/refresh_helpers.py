# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Helpers of the media-check tests (``unit/test_media_refresh.py``, ``unit/test_media_report.py``,
``integration/test_video_indexer.py``): the temporary library, a fake ffprobe, and the scenario builders.

The fixtures ``lib`` (the 013 library) and ``_fresh_marks`` (the in-memory marks reset around each test) are
imported by name into each test module so pytest finds them there.
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


STORED = ('pixel_width', 'pixel_height', 'file_size', 'file_md5')
MD5 = 'd41d8cd98f00b204e9800998ecf8427e'
ET.register_namespace('cms', 'https://stagelab.coop/cuems/')
ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def lib(library013):
    """The temporary library with a version-2 (013) script as ``proj1`` (the released tests used the pre-013 shape)."""
    return library013


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


def _settings(lib):
    settings = get_settings()
    settings['library_path'] = lib.root
    settings['tmp_path'] = os.path.join(lib.root, 'tmp')
    settings['html_root_path'] = os.path.join(lib.root, 'www')
    return settings


def _mgr(lib):
    lib.connect()
    return p.CuemsDBProject(_settings(lib), database)


def _uuid(lib, unix_name='proj1'):
    lib.connect()
    return str(Project.get(Project.unix_name == unix_name).uuid)


def _script(lib, project='proj1'):
    return os.path.join(lib.projects_dir, project, 'script.xml')


def _write(lib, name, nbytes, fill=b'x'):
    path = os.path.join(lib.root, 'media', name)
    with open(path, 'wb') as f:
        f.write(fill * nbytes)
    return path


def _row(lib, name):
    lib.connect()
    return Media.get(Media.unix_name == name)


def _set_row(lib, name, **fields):
    lib.connect()
    Media.update(**fields).where(Media.unix_name == name).execute()


def _add_row(lib, name, media_type, **fields):
    lib.connect()
    Media.create(uuid=str(new_uuid()), name=name, unix_name=name,
                 created=new_datetime(), modified=new_datetime(),
                 media_type=media_type, in_trash=False, **fields)


def _set_xml_media(lib, name, project='proj1', duration=None, rename=None, **stored):
    """Edit every ``Media`` block that uses *name*: its duration, its stored
    values (replaced by *stored*, in schema order, after ``regions``), and
    optionally its file name."""
    path = _script(lib, project)
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


def _blocks(lib, project='proj1'):
    """[(cue class name, Media)] of the project on disk, read through the library's object load."""
    script, _report = CuemsScript.load_with_report(_script(lib, project))
    out = []

    def walk(contents):
        for cue in contents:
            if isinstance(cue, CueList):
                walk(cue.contents)
            elif cue.get('Media'):
                out.append((type(cue).__name__, cue['Media']))

    walk(script.cuelist.contents)
    return out


def _media_of(lib, name, project='proj1'):
    return [mm for _, mm in _blocks(lib, project) if mm and mm.get('file_name') == name]


def _backups(lib, project='proj1'):
    d = os.path.join(lib.projects_dir, project)
    return sorted(f for f in os.listdir(d) if '.pre-refresh-' in f)


def _in_line(lib, video_seconds=90.0, video_size=10, audio_seconds=30.0, audio_size=20):
    """A lib whose rows match the files and the project: nothing to do."""
    _write(lib, 'file_video.ext', video_size)
    _write(lib, 'file.ext', audio_size)
    _set_row(lib, 'file_video.ext', duration=tc(video_seconds), file_size=video_size,
             pixel_width=1920, pixel_height=1080)
    _set_row(lib, 'file.ext', duration=tc(audio_seconds), file_size=audio_size)
    _set_xml_media(lib, 'file_video.ext', duration=tc(video_seconds))
    _set_xml_media(lib, 'file.ext', duration=tc(audio_seconds))


def _refresh(mgr, uuid, engine='none', clock=time.monotonic):
    async def engine_running():
        return {'none': False, 'loaded': False, 'running': True, 'silent': None}[engine]
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


def _report(mgr, uuid, context='open', reason=None):
    return mgr.media_report(uuid, context, reason)


def _changes(report, file_name):
    for entry in report['files']:
        if entry['file_name'] == file_name:
            return {c['field']: (c['stored'], c['current']) for c in entry['changes']}
    return None


def _bytes(lib, project='proj1'):
    return open(_script(lib, project), 'rb').read()


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
