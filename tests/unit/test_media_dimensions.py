# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Stored media dimensions (ClickUp 869fat84r).

The node engine ran ``ffprobe`` for a video file's width and height when it
first armed a cue with that file, under its command lock, so a GO sent right
after a cue selection started up to 400 ms late. The editor already probes a
file at upload for its duration and stores it; it now stores the pixel size
and the file size the same way:

* upload: ``probe_dimensions`` next to ``probe_duration``, new DB columns;
* migration: the columns are added to an existing ``media`` table at start-up
  (``create_tables(safe=True)`` never adds columns), by the editor and by the
  repair tool, which opens the DB itself;
* save: every VideoCue's ``Media`` gets the stored values, server-side, on
  every path that writes a project (``update``, ``new``, ``duplicate``); a
  file without stored values is probed once and stored (D13); values the
  client sent that are not positive integers are stripped everywhere, since
  the parser assigns them raw and the XSD would reject the save;
* repair tool: Pass A re-probes video rows and reports differences, Pass B
  writes the values into every project. (``--strip-dimensions`` was removed by
  D23: the rollback is the XSD-patched utils; plan §8.)

D18: every media type also stores ``file_size`` and ``file_md5`` (the MD5 the
upload already verified); the pixel size stays VideoCue-only. A save never
hashes a file; the repair tool fills and checks the MD5.

Design: cuems-RELATIONS Plans/2026-10-01-engine-late-go-media-probe.md §3.2.
"""
from support.paths import DATA_DIR
import hashlib
import os
import sqlite3
import subprocess
from unittest import mock

import pytest

import cuemseditor.repair_durations as rd
from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Media, Project, database
from cuemsutils.cues import CueList, CuemsScript

DIMS = ('pixel_width', 'pixel_height', 'file_size')
PIXEL = ('pixel_width', 'pixel_height')
ALL = DIMS + ('file_md5',)          # D18: every column / element this change adds
MD5 = 'd41d8cd98f00b204e9800998ecf8427e'
OLD_MEDIA_COLUMNS = ('uuid', 'name', 'unix_name', 'description', 'created',
                     'modified', 'duration', 'media_type', 'in_trash')


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _settings(library):
    settings = get_settings()
    settings['library_path'] = library.root
    return settings


def _columns(db_path):
    con = sqlite3.connect(db_path)
    try:
        return [row[1] for row in con.execute('PRAGMA table_info(media)')]
    finally:
        con.close()


def _make_old_schema(db_path):
    """Rebuild ``media`` as rc1-3 created it: without the new columns."""
    con = sqlite3.connect(db_path)
    try:
        cols = ', '.join(OLD_MEDIA_COLUMNS)
        con.executescript(
            f'CREATE TABLE media_old AS SELECT {cols} FROM media;'
            'DROP TABLE media;'
            'ALTER TABLE media_old RENAME TO media;')
        con.commit()
    finally:
        con.close()
    assert not set(ALL) & set(_columns(db_path))


def _md5(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def _script_path(library, project='proj1'):
    return os.path.join(library.projects_dir, project, 'script.xml')


def _media_blocks(path):
    """[(cue class name, Media)] for every media cue of a project file, read through the library."""
    script, _report = CuemsScript.load_with_report(path)
    out = []

    def walk(contents):
        for cue in contents:
            if isinstance(cue, CueList):
                walk(cue.contents)
            elif cue.get('Media'):
                out.append((type(cue).__name__, cue['Media']))

    walk(script.cuelist.contents)
    return out


def _set_row_dims(library, unix_name, w, h, size):
    library.connect()
    Media.update(pixel_width=w, pixel_height=h, file_size=size).where(
        Media.unix_name == unix_name).execute()
    database.close()


def _row(library, unix_name):
    library.connect()
    try:
        row = Media.get(Media.unix_name == unix_name)
        return row.pixel_width, row.pixel_height, row.file_size
    finally:
        database.close()


def _row_md5(library, unix_name):
    library.connect()
    try:
        return Media.get(Media.unix_name == unix_name).file_md5
    finally:
        database.close()


def _strip_xml(path):
    """Remove the stored values from every Media of a project file."""
    import xml.etree.ElementTree as ET
    ET.register_namespace('cms', 'https://stagelab.coop/cuems/')
    ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')
    tree = ET.parse(path)
    for media in tree.getroot().iter('Media'):
        for key in ALL:
            for el in media.findall(key):
                media.remove(el)
    tree.write(path, encoding='utf-8', xml_declaration=True)


def _project_manager(library):
    from cuemseditor.CuemsDBProject import CuemsDBProject
    library.connect()
    return CuemsDBProject(_settings(library), database)


def _project_uuid(library, unix_name='proj1'):
    library.connect()
    try:
        return str(Project.get(Project.unix_name == unix_name).uuid)
    finally:
        database.close()


def _script_json(library, project='proj1'):
    """The project as the client receives it (the wire), through the editor's own load."""
    uuid = _project_uuid(library, project)
    return _project_manager(library).load(uuid)


def _contents(data):
    return data['CuemsScript']['CueList']['contents']


def _video_media(data):
    """The Media dicts of the wire's video cues."""
    return [item['Cue']['Media'] for item in _contents(data)
            if 'Cue' in item and item['Cue'].get('class') == 'video']


# ---------------------------------------------------------------------------
# probe_dimensions
# ---------------------------------------------------------------------------

class TestProbeDimensions:
    def _run(self, stdout=b'1920,1080\n', returncode=0, side_effect=None):
        from cuemseditor import CuemsDBMedia as m
        result = mock.Mock(stdout=stdout, stderr=b'', returncode=returncode)
        with mock.patch.object(m.subprocess, 'run', return_value=result,
                               side_effect=side_effect) as run:
            dims = m.probe_dimensions('/media/clip.mov')
        return dims, run

    def test_same_query_as_the_engine_with_a_short_timeout(self):
        dims, run = self._run()
        assert dims == (1920, 1080)
        cmd = run.call_args.args[0]
        assert cmd[0] == 'ffprobe'
        for part in ('-select_streams', 'v:0', '-show_entries', 'stream=width,height',
                     '-of', 'csv=p=0', '/media/clip.mov'):
            assert part in cmd
        assert run.call_args.kwargs['timeout'] == 5

    @pytest.mark.parametrize('stdout,rc', [(b'', 0), (b'abc,def', 0), (b'0,1080', 0),
                                           (b'1920', 0), (b'1920,1080', 1)])
    def test_bad_output_gives_none(self, stdout, rc):
        assert self._run(stdout=stdout, returncode=rc)[0] == (None, None)

    @pytest.mark.parametrize('error', [subprocess.TimeoutExpired('ffprobe', 5),
                                       OSError('no ffprobe')])
    def test_it_never_raises(self, error):
        assert self._run(side_effect=error)[0] == (None, None)


# ---------------------------------------------------------------------------
# DB migration
# ---------------------------------------------------------------------------

class TestMigration:
    def test_adds_the_columns_once(self, library):
        from cuemseditor.CuemsDBModel import ensure_media_columns
        _make_old_schema(library.db_path)
        library.connect()
        try:
            assert sorted(ensure_media_columns(database)) == sorted(ALL)
            assert ensure_media_columns(database) == []
        finally:
            database.close()
        assert set(ALL) <= set(_columns(library.db_path))

    def test_old_rows_survive_and_an_old_query_still_works(self, library):
        from cuemseditor.CuemsDBModel import ensure_media_columns
        _make_old_schema(library.db_path)
        library.connect()
        ensure_media_columns(database)
        database.close()
        con = sqlite3.connect(library.db_path)
        try:
            rows = con.execute(f'SELECT {", ".join(OLD_MEDIA_COLUMNS)} FROM media').fetchall()
        finally:
            con.close()
        assert len(rows) == 5
        assert _row(library, 'file_video.ext') == (None, None, None)

    def test_the_editor_migrates_at_start(self, library):
        from cuemseditor.CuemsProjectManager import CuemsDBManager
        _make_old_schema(library.db_path)
        CuemsDBManager(_settings(library))
        database.close()
        assert set(ALL) <= set(_columns(library.db_path))

    def test_a_failing_migration_stops_the_editor(self, library):
        from cuemseditor import CuemsProjectManager as pm
        _make_old_schema(library.db_path)
        with mock.patch.object(pm, 'ensure_media_columns',
                               side_effect=RuntimeError('disk full')):
            with pytest.raises(RuntimeError):
                pm.CuemsDBManager(_settings(library))
        if not database.is_closed():
            database.close()


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------

class TestUpload:
    def _upload(self, library, tmp_path, name, content=b'x' * 1234, dims=(3840, 2160), md5=None):
        from cuemseditor import CuemsDBMedia as m
        settings = _settings(library)
        library.connect()
        mgr = m.CuemsDBMedia(settings, database)
        upload = tmp_path / name
        upload.write_bytes(content)
        with mock.patch.object(m, 'probe_dimensions', return_value=dims) as probe, \
             mock.patch.object(mgr, 'get_duration', return_value=None), \
             mock.patch.object(mgr, 'create_video_thumbnail', return_value=None), \
             mock.patch.object(mgr, 'create_video_index', return_value=None), \
             mock.patch.object(mgr, 'create_audio_waveform', return_value=None):
            dest = mgr.new(str(upload), name, md5) if md5 else mgr.new(str(upload), name)
        database.close()
        return dest, probe

    def test_a_video_stores_its_dimensions_and_size(self, library, tmp_path):
        dest, probe = self._upload(library, tmp_path, 'clip.mov')
        probe.assert_called_once()
        assert _row(library, dest) == (3840, 2160, 1234)

    def test_audio_stores_its_size_only_and_is_not_probed(self, library, tmp_path):
        dest, probe = self._upload(library, tmp_path, 'song.wav')
        probe.assert_not_called()
        assert _row(library, dest) == (None, None, 1234)

    def test_the_verified_md5_is_stored_lowercase(self, library, tmp_path):
        dest, _ = self._upload(library, tmp_path, 'song2.wav', md5=MD5.upper())
        assert _row_md5(library, dest) == MD5

    def test_without_an_md5_none_is_stored(self, library, tmp_path):
        dest, _ = self._upload(library, tmp_path, 'clip2.mov')
        assert _row_md5(library, dest) is None

    def test_the_upload_session_passes_the_verified_md5(self):
        import inspect
        from cuemseditor.CuemsUpload import CuemsUpload
        src = inspect.getsource(CuemsUpload.upload_done)
        assert 'self.server.db.media.new, self.tmp_file_path(), self.filename, received_md5' in src
        assert src.index('check_file_integrity') < src.index('db.media.new')

    def test_a_failed_probe_stores_nothing_and_the_upload_succeeds(self, library, tmp_path):
        dest, _ = self._upload(library, tmp_path, 'odd.mov', dims=(None, None))
        assert _row(library, dest) == (None, None, 1234)


# ---------------------------------------------------------------------------
# The metadata walk (shared by the save path and the repair tool), on objects (003)
#
# The released tests drove the walk with dict cues. The walk now takes the
# ``CuemsScript``'s cues, and a client's raw values arrive through
# ``CuemsScript.from_json``, which stores them untouched; so the cases below build
# the script from the 013 fixture's wire and put the raw values in the payload.
# ---------------------------------------------------------------------------

import copy

from cuemsutils.helpers import new_uuid

FIXTURE_013 = str(DATA_DIR / 'script_minimal_013.xml')
VIDEO_1 = '1f301cf8-dd03-4b40-ac17-ef0e5e7988be'
AUDIO_1 = 'bb391e70-e65e-47ca-8b29-5a7076bbd250'
VIDEO_2 = '96d6e5de-c29b-4ab2-b828-297d84293304'


def _fixture_wire():
    script, _report = CuemsScript.load_with_report(FIXTURE_013)
    return script.to_wire()


def _wire_cue(data, cue_id):
    for item in _contents(data):
        cue = item.get('Cue')
        if cue and str(cue.get('id')) == cue_id:
            return cue
    raise AssertionError(cue_id)


def _object_cue(script, cue_id):
    def walk(contents):
        for cue in contents:
            if isinstance(cue, CueList):
                found = walk(cue.contents)
                if found is not None:
                    return found
            elif str(cue.get('id')) == cue_id:
                return cue
        return None

    return walk(script.cuelist.contents)


def _walk(script, dims_by_file, known=('file.ext', 'file_video.ext')):
    from cuemseditor.CuemsDBProject import fix_media_durations_in_contents

    def durations(name):
        if name not in known:
            raise KeyError(name)
        return None

    def dimensions(name):
        if name not in known:
            raise KeyError(name)
        value = dims_by_file.get(name)
        if isinstance(value, Exception):
            raise value
        return value

    return fix_media_durations_in_contents(script.cuelist.contents, durations, dimensions)


STORED = {'pixel_width': 1920, 'pixel_height': 1080, 'file_size': 4096, 'file_md5': MD5}


def _media(script, cue_id):
    return _object_cue(script, cue_id)['Media']


def _stored_of(media):
    return {k: media[k] for k in ALL if k in media}


class TestFill:
    def test_video_cues_get_everything_audio_cues_size_and_md5(self):
        script = CuemsScript.from_json(_fixture_wire())
        _walk(script, {'file_video.ext': STORED, 'file.ext': STORED})
        assert _stored_of(_media(script, VIDEO_1)) == STORED
        audio = _media(script, AUDIO_1)
        assert _stored_of(audio) == {'file_size': 4096, 'file_md5': MD5}
        assert not set(PIXEL) & set(audio)

    def test_an_md5_is_stored_lowercase(self):
        data = _fixture_wire()
        _wire_cue(data, AUDIO_1)['Media'].update(file_name='orphan.wav', file_md5=MD5.upper())
        script = CuemsScript.from_json(data)
        _walk(script, {}, known=())
        assert _media(script, AUDIO_1)['file_md5'] == MD5

    def test_the_stored_values_replace_what_the_client_sent(self):
        data = _fixture_wire()
        _wire_cue(data, VIDEO_1)['Media'].update(pixel_width=10, pixel_height=10, file_size=10)
        script = CuemsScript.from_json(data)
        _walk(script, {'file_video.ext': STORED})
        assert _stored_of(_media(script, VIDEO_1)) == STORED

    def test_unknown_values_remove_what_the_client_sent(self):
        data = _fixture_wire()
        _wire_cue(data, VIDEO_1)['Media'].update(pixel_width=10, pixel_height=10)
        script = CuemsScript.from_json(data)
        _walk(script, {'file_video.ext': None})
        assert not set(ALL) & set(_media(script, VIDEO_1))

    @pytest.mark.parametrize('bad', [None, 0, -5, 'abc', '', 1.5, True])
    def test_invalid_client_values_are_stripped_everywhere(self, bad):
        data = _fixture_wire()
        _wire_cue(data, VIDEO_1)['Media'].update(file_name='orphan.mov', pixel_width=bad)
        _wire_cue(data, AUDIO_1)['Media'].update(file_size=bad, file_md5=bad)
        _wire_cue(data, VIDEO_2)['Media'].update(pixel_height=bad)
        script = CuemsScript.from_json(data)
        _walk(script, {'file_video.ext': None})
        for cue_id in (VIDEO_1, AUDIO_1, VIDEO_2):
            assert not set(ALL) & set(_media(script, cue_id)), cue_id

    def test_an_orphan_keeps_valid_values(self):
        data = _fixture_wire()
        _wire_cue(data, VIDEO_1)['Media'].update(file_name='orphan.mov', **STORED)
        script = CuemsScript.from_json(data)
        stats = _walk(script, {})
        assert _stored_of(_media(script, VIDEO_1)) == STORED
        assert stats.orphans == ['orphan.mov']

    def test_one_bad_cue_does_not_stop_the_others(self):
        data = _fixture_wire()
        _wire_cue(data, VIDEO_1)['Media'].update(file_name='file.ext')
        script = CuemsScript.from_json(data)
        stats = _walk(script, {'file.ext': RuntimeError('db'), 'file_video.ext': STORED})
        assert _stored_of(_media(script, VIDEO_2)) == STORED
        assert 'file.ext' in stats.errors

    def test_nested_cuelists_are_walked(self):
        data = _fixture_wire()
        root = data['CuemsScript']['CueList']
        inner = copy.deepcopy({k: v for k, v in root.items() if k != 'contents'})
        inner['id'] = str(new_uuid())
        moved = [item for item in root['contents'] if item.get('Cue', {}).get('id') is not None
                 and str(item['Cue']['id']) == VIDEO_1]
        root['contents'] = [item for item in root['contents'] if item not in moved]
        inner['contents'] = moved
        root['contents'].append({'CueList': inner})
        script = CuemsScript.from_json(data)
        _walk(script, {'file_video.ext': STORED})
        assert _media(script, VIDEO_1)['pixel_width'] == 1920

    def test_without_a_dimensions_resolver_only_invalid_values_go(self):
        from cuemseditor.CuemsDBProject import fix_media_durations_in_contents
        data = _fixture_wire()
        _wire_cue(data, VIDEO_1)['Media'].update(pixel_width=0, pixel_height=1080)
        script = CuemsScript.from_json(data)
        fix_media_durations_in_contents(script.cuelist.contents, lambda name: None)
        media = _media(script, VIDEO_1)
        assert 'pixel_width' not in media and media['pixel_height'] == 1080


# ---------------------------------------------------------------------------
# Every path that writes a project
# ---------------------------------------------------------------------------

def _patched_probe(dims=(1280, 720)):
    from cuemseditor import CuemsDBProject as p
    return mock.patch.object(p, 'probe_dimensions', return_value=dims)


class TestSavePaths:
    def test_update_writes_the_stored_values_into_video_cues(self, library013):
        library = library013
        _set_row_dims(library, 'file_video.ext', 3840, 2160, 777)
        data = _script_json(library)
        mgr = _project_manager(library)
        with _patched_probe() as probe:
            mgr.update(_project_uuid(library), data)
        if not database.is_closed():
            database.close()
        probe.assert_not_called()
        blocks = _media_blocks(_script_path(library))
        videos = [m for t, m in blocks if t == 'VideoCue']
        audios = [m for t, m in blocks if t == 'AudioCue']
        assert videos and all((m['pixel_width'], m['pixel_height'], m['file_size'])
                              == (3840, 2160, 777) for m in videos)
        assert audios and all(not set(PIXEL) & set(m) for m in audios)

    def test_update_probes_and_stores_a_file_without_values(self, library013):
        # A row with no stored size is verified by the one probe that reads
        # the duration and the pixel size together (D20, plan §7.9.4).
        library = library013
        from cuemseditor import CuemsDBProject as p
        from cuemseditor.CuemsDBMedia import MediaProbe, PROBE_OK
        from cuemsutils.tools.CTimecode import CTimecode
        with open(os.path.join(library.root, 'media', 'file_video.ext'), 'wb') as f:
            f.write(b'y' * 55)
        data = _script_json(library)
        mgr = _project_manager(library)
        result = MediaProbe(duration=CTimecode(start_seconds=90.0), duration_state=PROBE_OK,
                            width=1280, height=720, picture_state=PROBE_OK)
        with mock.patch.object(p, 'probe_media', return_value=result) as probe:
            mgr.update(_project_uuid(library), data)
        if not database.is_closed():
            database.close()
        assert probe.call_count == 1          # once per file, not per cue
        assert _row(library, 'file_video.ext') == (1280, 720, 55)
        videos = [m for t, m in _media_blocks(_script_path(library)) if t == 'VideoCue']
        assert all(m['pixel_width'] == 1280 for m in videos)

    def test_a_failed_probe_never_fails_the_save(self, library013):
        library = library013
        data = _script_json(library)
        for media in _video_media(data):
            media['pixel_width'] = 0   # client junk
        mgr = _project_manager(library)
        with _patched_probe((None, None)):
            mgr.update(_project_uuid(library), data)
        if not database.is_closed():
            database.close()
        videos = [m for t, m in _media_blocks(_script_path(library)) if t == 'VideoCue']
        assert videos and all(not set(PIXEL) & set(m) for m in videos)

    def test_new_fills_the_values(self, library013):
        library = library013
        _set_row_dims(library, 'file_video.ext', 3840, 2160, 777)
        data = _script_json(library)
        data['CuemsScript']['name'] = 'Proj New'
        data['CuemsScript']['id'] = str(new_uuid())
        mgr = _project_manager(library)
        with _patched_probe():
            mgr.new(data, 'projnew')
        if not database.is_closed():
            database.close()
        videos = [m for t, m in _media_blocks(_script_path(library, 'projnew'))
                  if t == 'VideoCue']
        assert videos and all(m['pixel_width'] == 3840 for m in videos)

    def test_duplicate_fills_the_values(self, library013):
        library = library013
        _set_row_dims(library, 'file_video.ext', 3840, 2160, 777)
        mgr = _project_manager(library)
        with _patched_probe():
            mgr.duplicate(_project_uuid(library))
        if not database.is_closed():
            database.close()
        dup = [d for d in os.listdir(library.projects_dir) if d != 'proj1']
        assert dup
        videos = [m for t, m in _media_blocks(_script_path(library, dup[0]))
                  if t == 'VideoCue']
        assert videos and all(m['pixel_width'] == 3840 for m in videos)


# ---------------------------------------------------------------------------
# Repair tool
# ---------------------------------------------------------------------------

class TestRepairTool:
    def test_dry_run_on_an_unmigrated_db_changes_nothing(self, library013, canned_probe):
        library = library013
        _make_old_schema(library.db_path)
        db_before = _md5(library.db_path)
        xml_before = _md5(_script_path(library))
        rd.main(['--library-path', library.root])
        assert _md5(library.db_path) == db_before
        assert not set(ALL) & set(_columns(library.db_path))
        assert _md5(_script_path(library)) == xml_before

    def test_apply_migrates_and_fills_the_db_but_writes_no_script(self, library013, canned_probe, capsys):
        library = library013
        _make_old_schema(library.db_path)
        with open(os.path.join(library.root, 'media', 'file_video.ext'), 'wb') as f:
            f.write(b'v' * 321)
        xml_before = _md5(_script_path(library))
        rd.main(['--library-path', library.root, '--apply'])
        assert _row(library, 'file_video.ext') == (1920, 1080, 321)
        assert _row_md5(library, 'file_video.ext') == hashlib.md5(b'v' * 321).hexdigest()
        # 002 FR-027a: the script changes only when an operator saves it in the editor.
        assert _md5(_script_path(library)) == xml_before
        assert 'NEEDS_SAVE' in capsys.readouterr().out

    def test_no_mode_writes_a_script(self, library013):
        # The released --xml-only (Pass B) was an explicit bulk save; on this line the tool lists
        # the projects that need a save (002 FR-027a).
        with pytest.raises(SystemExit):
            rd.main(['--library-path', library013.root, '--apply', '--xml-only'])

    def test_pass_a_reports_a_replaced_file(self, library013, canned_probe, capsys):
        library = library013
        _set_row_dims(library, 'file_video.ext', 640, 480, 1)
        rd.main(['--library-path', library.root])
        out = capsys.readouterr().out
        assert 'DIMS_CHANGED' in out and 'file_video.ext' in out

    def test_pass_a_reports_a_changed_md5_as_dirty(self, library013, canned_probe, capsys):
        library = library013
        library.connect()
        Media.update(file_md5=MD5).where(Media.unix_name == 'file.ext').execute()
        database.close()
        with open(os.path.join(library.root, 'media', 'file.ext'), 'wb') as f:
            f.write(b'changed')
        rd.main(['--library-path', library.root])
        out = capsys.readouterr().out
        assert 'MD5_CHANGED' in out and 'file.ext' in out

    def test_no_md5_skips_the_hashing(self, library013, canned_probe):
        library = library013
        rd.main(['--library-path', library.root, '--apply', '--no-md5'])
        assert _row_md5(library, 'file_video.ext') is None

    def test_strip_dimensions_is_no_longer_an_option(self, library):
        # D23 (plan §8): the rollback is the XSD-patched utils debs.
        with pytest.raises(SystemExit):
            rd.main(['--library-path', library.root, '--apply', '--strip-dimensions'])
