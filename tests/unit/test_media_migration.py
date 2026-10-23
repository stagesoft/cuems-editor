# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The four media columns: migrated at start-up, stored at upload (002 US6, FR-036, FR-037).

Ported from 869fat84r ``0b291d1`` (``83d8460`` pixel and file size,
``cd37792`` size and md5). A database made before the columns existed gets
them at every editor start, additively; a failure stops the start. The repair
tool's dry run never writes the database. An upload stores a movie's pixel
size, the file size and the md5 the upload verified, lowercase; a value that
cannot be read is NULL and never fails the upload.
"""

import hashlib
import os
from unittest.mock import patch

import pytest
from cuemsutils.helpers import new_datetime, new_uuid

import cuemseditor.CuemsDBMedia as db_media
import cuemseditor.CuemsProjectManager as project_manager
import cuemseditor.repair_durations as rd
from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBMedia import CuemsDBMedia
from cuemseditor.CuemsDBModel import MEDIA_ADDED_COLUMNS, Media, Project, ProjectMedia, database
from cuemseditor.CuemsProjectManager import CuemsDBManager


def _sha256(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _columns(db_path):
    database.init(db_path)
    database.connect(reuse_if_open=True)
    try:
        return {column.name for column in database.get_columns('media')}
    finally:
        database.close()


def _make_old_schema(db_path):
    """A database as an editor before 002 made it: ``media`` without the four columns, one row."""
    database.init(db_path)
    database.connect(reuse_if_open=True)
    database.create_tables([Project, Media, ProjectMedia], safe=True)
    Media.insert(uuid=str(new_uuid()), name='old.wav', unix_name='old.wav', created=new_datetime(),
                 modified=new_datetime(), duration='00:00:03.000', media_type='AUDIO',
                 in_trash=False).execute()
    for name in MEDIA_ADDED_COLUMNS:
        database.execute_sql(f'ALTER TABLE "media" DROP COLUMN "{name}"')
    database.close()


def _settings(root):
    settings = get_settings()
    settings['library_path'] = str(root)
    settings['tmp_path'] = str(root / 'tmp')
    for sub in ('tmp', 'projects', 'media/thumbnails', 'media/waveforms',
                'trash/projects', 'trash/media/thumbnails', 'trash/media/waveforms'):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return settings


def test_start_up_adds_the_four_columns_and_keeps_rows(tmp_path):
    settings = _settings(tmp_path)
    db_path = os.path.join(settings['library_path'], settings['database_name'])
    _make_old_schema(db_path)
    assert not set(MEDIA_ADDED_COLUMNS) & _columns(db_path)

    CuemsDBManager(settings)
    try:
        row = Media.get(Media.unix_name == 'old.wav')
        assert (row.duration, row.media_type) == ('00:00:03.000', 'AUDIO')
        assert (row.pixel_width, row.pixel_height, row.file_size, row.file_md5) == (None, None, None, None)
    finally:
        database.close()
    assert set(MEDIA_ADDED_COLUMNS) <= _columns(db_path)

    CuemsDBManager(settings)                                  # idempotent: a second start adds nothing
    database.close()


def test_a_migration_failure_stops_the_start(tmp_path):
    settings = _settings(tmp_path)
    _make_old_schema(os.path.join(settings['library_path'], settings['database_name']))

    with patch.object(project_manager, 'ensure_media_columns', side_effect=RuntimeError('disk is read-only')):
        with pytest.raises(RuntimeError, match='read-only'):
            CuemsDBManager(settings)
    database.close()


def test_repair_tool_dry_run_never_writes_the_database(library, canned_probe):
    database.init(library.db_path)
    database.connect(reuse_if_open=True)
    for name in MEDIA_ADDED_COLUMNS:
        database.execute_sql(f'ALTER TABLE "media" DROP COLUMN "{name}"')
    database.close()
    before = _sha256(library.db_path)

    rd.main(['--library-path', library.root, '--database-name', os.path.basename(library.db_path)])

    assert _sha256(library.db_path) == before
    assert not set(MEDIA_ADDED_COLUMNS) & _columns(library.db_path)


@pytest.fixture
def uploads(tmp_path):
    settings = _settings(tmp_path)
    database.init(os.path.join(settings['library_path'], settings['database_name']))
    database.connect(reuse_if_open=True)
    database.create_tables([Project, Media, ProjectMedia], safe=True)
    media = CuemsDBMedia(settings, database)
    with patch.object(CuemsDBMedia, 'get_duration', return_value=None), \
         patch.object(CuemsDBMedia, 'create_video_thumbnail', return_value=None), \
         patch.object(CuemsDBMedia, 'create_video_index', return_value=None):
        yield tmp_path, media
    database.close()


def _upload(root, media, name, content, md5):
    tmp = root / 'tmp' / name
    tmp.write_bytes(content)
    return Media.get(Media.unix_name == media.new(str(tmp), name, md5))


def test_upload_stores_size_pixels_and_lowercase_md5(uploads):
    root, media = uploads
    content = b'not really a movie, but twelve and more bytes'
    md5 = hashlib.md5(content).hexdigest()

    with patch.object(db_media, 'probe_dimensions', return_value=(1920, 1080)):
        row = _upload(root, media, 'clip.mp4', content, md5.upper())

    assert (row.pixel_width, row.pixel_height) == (1920, 1080)
    assert row.file_size == len(content)
    assert row.file_md5 == md5


def test_a_failed_probe_stores_null_and_does_not_fail_the_upload(uploads):
    root, media = uploads
    content = b'garbage that no prober can read as video'

    with patch.object(db_media, 'probe_dimensions', wraps=db_media.probe_dimensions) as probe:
        row = _upload(root, media, 'broken.mp4', content, 'not-an-md5')

    probe.assert_called_once()
    assert (row.pixel_width, row.pixel_height) == (None, None)
    assert row.file_size == len(content)
    assert row.file_md5 is None
