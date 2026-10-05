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
  writes the values into every project, ``--strip-dimensions`` removes them.

D18: every media type also stores ``file_size`` and ``file_md5`` (the MD5 the
upload already verified); the pixel size stays VideoCue-only. A save never
hashes a file; the repair tool fills and checks the MD5.

Design: cuems-RELATIONS Plans/2026-10-01-engine-late-go-media-probe.md §3.2.
"""
import hashlib
import os
import sqlite3
import subprocess
from unittest import mock

import pytest

import cuemseditor.repair_durations as rd
from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Media, Project, database
from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter

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
    """[(cue_type, Media dict)] for every media cue in a project XML."""
    data = XmlReaderWriter(schema_name='script', xmlfile=path).read()
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
    return XmlReaderWriter(schema_name='script', xmlfile=_script_path(library, project)).read()


def _contents(data):
    return data['CuemsScript']['CueList']['contents']


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
# The metadata walk (shared by the save path and the repair tool)
# ---------------------------------------------------------------------------

def _walk(contents, dims_by_file, known=('file.ext', 'file_video.ext')):
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

    return fix_media_durations_in_contents(contents, durations, dimensions)


def _cue(cue_type, file_name, **media):
    return {cue_type: {'Media': {'file_name': file_name, 'duration': '00:00:01.000',
                                 **media}}}


STORED = {'pixel_width': 1920, 'pixel_height': 1080, 'file_size': 4096, 'file_md5': MD5}


class TestFill:
    def test_video_cues_get_everything_audio_cues_size_and_md5(self):
        contents = [_cue('VideoCue', 'file_video.ext'), _cue('AudioCue', 'file.ext')]
        stats = _walk(contents, {'file_video.ext': STORED, 'file.ext': STORED})
        video, audio = contents[0]['VideoCue']['Media'], contents[1]['AudioCue']['Media']
        assert {k: video[k] for k in ALL} == STORED
        assert {k: audio[k] for k in ('file_size', 'file_md5')} == {'file_size': 4096, 'file_md5': MD5}
        assert not set(PIXEL) & set(audio)
        assert stats.dimension_changes == 2

    def test_an_md5_is_stored_lowercase(self):
        contents = [_cue('AudioCue', 'file.ext', file_md5=MD5.upper())]
        _walk(contents, {'file.ext': None}, known=())
        assert contents[0]['AudioCue']['Media']['file_md5'] == MD5

    def test_the_stored_values_replace_what_the_client_sent(self):
        contents = [_cue('VideoCue', 'file_video.ext', pixel_width=10, pixel_height=10,
                         file_size=10)]
        _walk(contents, {'file_video.ext': STORED})
        assert {k: contents[0]['VideoCue']['Media'][k] for k in ALL} == STORED

    def test_unknown_values_remove_what_the_client_sent(self):
        contents = [_cue('VideoCue', 'file_video.ext', pixel_width=10, pixel_height=10)]
        stats = _walk(contents, {'file_video.ext': None})
        assert not set(ALL) & set(contents[0]['VideoCue']['Media'])
        assert stats.dimension_changes == 1

    @pytest.mark.parametrize('bad', [None, 0, -5, 'abc', '', 1.5, True])
    def test_invalid_client_values_are_stripped_everywhere(self, bad):
        contents = [
            _cue('VideoCue', 'orphan.mov', pixel_width=bad),
            _cue('AudioCue', 'file.ext', file_size=bad),
            _cue('VideoCue', 'file_video.ext', pixel_height=bad),
            _cue('AudioCue', 'orphan.wav', file_md5=bad),
        ]
        _walk(contents, {'file_video.ext': None})
        for item in contents:
            (cue,) = item.values()
            assert not set(ALL) & set(cue['Media'])

    def test_an_orphan_keeps_valid_values(self):
        contents = [_cue('VideoCue', 'orphan.mov', **STORED)]
        stats = _walk(contents, {})
        assert {k: contents[0]['VideoCue']['Media'][k] for k in ALL} == STORED
        assert stats.orphans == ['orphan.mov']

    def test_one_bad_cue_does_not_stop_the_others(self):
        contents = [_cue('VideoCue', 'file.ext'), _cue('VideoCue', 'file_video.ext')]
        _walk(contents, {'file.ext': RuntimeError('db'), 'file_video.ext': STORED})
        assert {k: contents[1]['VideoCue']['Media'][k] for k in ALL} == STORED

    def test_nested_cuelists_are_walked(self):
        inner = [_cue('VideoCue', 'file_video.ext')]
        contents = [{'CueList': {'contents': inner}}]
        _walk(contents, {'file_video.ext': STORED})
        assert inner[0]['VideoCue']['Media']['pixel_width'] == 1920

    def test_without_a_dimensions_resolver_only_invalid_values_go(self):
        from cuemseditor.CuemsDBProject import fix_media_durations_in_contents
        contents = [_cue('VideoCue', 'file_video.ext', pixel_width=0, pixel_height=1080)]
        fix_media_durations_in_contents(contents, lambda name: None)
        media = contents[0]['VideoCue']['Media']
        assert 'pixel_width' not in media and media['pixel_height'] == 1080


# ---------------------------------------------------------------------------
# Every path that writes a project
# ---------------------------------------------------------------------------

def _patched_probe(dims=(1280, 720)):
    from cuemseditor import CuemsDBProject as p
    return mock.patch.object(p, 'probe_dimensions', return_value=dims)


class TestSavePaths:
    def test_update_writes_the_stored_values_into_video_cues(self, library):
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

    def test_update_probes_and_stores_a_file_without_values(self, library):
        # A row with no stored size is verified by the one probe that reads
        # the duration and the pixel size together (D20, plan §7.9.4).
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

    def test_a_failed_probe_never_fails_the_save(self, library):
        data = _script_json(library)
        for item in _contents(data):
            if 'VideoCue' in item:
                item['VideoCue']['Media']['pixel_width'] = 0   # client junk
        mgr = _project_manager(library)
        with _patched_probe((None, None)):
            mgr.update(_project_uuid(library), data)
        if not database.is_closed():
            database.close()
        videos = [m for t, m in _media_blocks(_script_path(library)) if t == 'VideoCue']
        assert videos and all(not set(PIXEL) & set(m) for m in videos)

    def test_new_fills_the_values(self, library):
        _set_row_dims(library, 'file_video.ext', 3840, 2160, 777)
        data = _script_json(library)
        data['CuemsScript']['name'] = 'Proj New'
        mgr = _project_manager(library)
        with _patched_probe():
            mgr.new(data, 'projnew')
        if not database.is_closed():
            database.close()
        videos = [m for t, m in _media_blocks(_script_path(library, 'projnew'))
                  if t == 'VideoCue']
        assert videos and all(m['pixel_width'] == 3840 for m in videos)

    def test_duplicate_fills_the_values(self, library):
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
    def test_dry_run_on_an_unmigrated_db_changes_nothing(self, library, canned_probe):
        _make_old_schema(library.db_path)
        db_before = _md5(library.db_path)
        xml_before = _md5(_script_path(library))
        rd.main(['--library-path', library.root])
        assert _md5(library.db_path) == db_before
        assert not set(ALL) & set(_columns(library.db_path))
        assert _md5(_script_path(library)) == xml_before

    def test_apply_migrates_fills_the_db_and_the_projects(self, library, canned_probe):
        _make_old_schema(library.db_path)
        with open(os.path.join(library.root, 'media', 'file_video.ext'), 'wb') as f:
            f.write(b'v' * 321)
        rd.main(['--library-path', library.root, '--apply'])
        assert _row(library, 'file_video.ext') == (1920, 1080, 321)
        assert _row_md5(library, 'file_video.ext') == hashlib.md5(b'v' * 321).hexdigest()
        videos = [m for t, m in _media_blocks(_script_path(library)) if t == 'VideoCue']
        assert videos and all(m['pixel_width'] == 1920 for m in videos)

    def test_pass_b_writes_values_into_a_project_whose_durations_are_right(
            self, library, canned_probe):
        rd.main(['--library-path', library.root, '--apply'])   # durations fixed
        # Wipe the dimensions from the XML only: durations are now correct.
        rd.main(['--library-path', library.root, '--apply', '--strip-dimensions'])
        assert all(not set(ALL) & set(m) for _, m in _media_blocks(_script_path(library)))
        rd.main(['--library-path', library.root, '--apply', '--xml-only'])
        videos = [m for t, m in _media_blocks(_script_path(library)) if t == 'VideoCue']
        assert videos and all(m['pixel_width'] == 1920 for m in videos)

    def test_pass_a_reports_a_replaced_file(self, library, canned_probe, capsys):
        _set_row_dims(library, 'file_video.ext', 640, 480, 1)
        rd.main(['--library-path', library.root])
        out = capsys.readouterr().out
        assert 'DIMS_CHANGED' in out and 'file_video.ext' in out

    def test_pass_a_reports_a_changed_md5_as_dirty(self, library, canned_probe, capsys):
        library.connect()
        Media.update(file_md5=MD5).where(Media.unix_name == 'file.ext').execute()
        database.close()
        with open(os.path.join(library.root, 'media', 'file.ext'), 'wb') as f:
            f.write(b'changed')
        rd.main(['--library-path', library.root])
        out = capsys.readouterr().out
        assert 'MD5_CHANGED' in out and 'file.ext' in out

    def test_no_md5_skips_the_hashing(self, library, canned_probe):
        rd.main(['--library-path', library.root, '--apply', '--no-md5'])
        assert _row_md5(library, 'file_video.ext') is None

    def test_strip_dimensions_touches_only_the_projects(self, library, canned_probe):
        rd.main(['--library-path', library.root, '--apply'])
        rows_before = _row(library, 'file_video.ext')
        rd.main(['--library-path', library.root, '--apply', '--strip-dimensions'])
        assert all(not set(ALL) & set(m) for _, m in _media_blocks(_script_path(library)))
        assert _row(library, 'file_video.ext') == rows_before
