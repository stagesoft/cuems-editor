# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Project export, written in one pass and protected from a running show
(ClickUp 1amfwm7kana).

``CuemsDBProject.export`` writes the zip straight from the library into the
exports folder, stored, under a private ``.<unix_name>.XXXX.part`` name, and
publishes it with ``os.link``. ``CuemsWsUser.request_export_project`` asks the
engine first: ``running`` is refused, ``loaded`` needs the operator's
``accept_loaded: true``, no answer is refused, ``none`` goes on.

Design: cuems-RELATIONS Plans/2026-11-24-project-export-served-and-cleaned-1amfwm7kana.md
(step 2: the test list is numbered there; the numbers below are the plan's).

Seams used by the tests: ``cuemseditor.CuemsDBProject.prefetch`` (called by the
old and the new ``export()`` before the media is touched) and, for the new
writer only, ``cuemseditor.CuemsDBProject._copy_stream(src, dst)``.
"""
import asyncio
import collections
import errno
import json
import os
import re
import stat
import threading
import warnings
import zipfile
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

import pytest

import cuemseditor.CuemsDBProject as p
import cuemseditor.CuemsWsUser as wsu
from cuemseditor.CuemsDBModel import Media, Project, ProjectMedia
from cuemseditor.cli import ensure_directories, get_settings
from cuemseditor.CuemsErrors import EngineError

GIB = 1024 ** 3

# The texts the plan fixes (D17, D20, D25; step 2). One line each.
E1_CONF = ('Export is not served on this box: the apache conf cuems-exports is '
           'not enabled (cuems-common installs it)')
E3 = 'A show is running: stop it before exporting a project'
E4 = ('Cannot check whether a show is running (the engine does not answer): '
      'nothing was exported')
E5 = ('A project is loaded and waiting for GO: an export reads the whole project '
      'from disk and can make the next GO late. Accept the warning in the export '
      'dialog to go on')


def E1_FOLDER(folder):
    return f'Export folder {folder} is missing or not writable (cuems-common installs it)'


def E6(name):
    return f'Media file {name} changed while it was exported: export again'


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

#: file name -> content. Sizes cross the 1 MiB chunk; pic.png is empty.
FILES = {
    'file.ext': os.urandom(300_000),
    'file_video.ext': os.urandom(2_500_000),
    'pic.png': b'',
}


class Disk:
    """What the patched ``shutil.disk_usage`` answers."""

    def __init__(self):
        self.total = 1024 * GIB
        self.free = 1024 * GIB
        self.paths = []

    def __call__(self, path):
        self.paths.append(path)
        return collections.namedtuple('usage', 'total used free')(
            self.total, self.total - self.free, self.free)


@pytest.fixture
def disk(monkeypatch):
    """A roomy disk by default; the reserve tests set ``total`` and ``free``."""
    d = Disk()
    monkeypatch.setattr(p.shutil, 'disk_usage', d)
    return d


class Env:
    def __init__(self, library, folder, conf, mgr, uuid):
        self.library = library
        self.folder = folder          # the exports folder
        self.conf = conf              # the enabled conf (D21)
        self.mgr = mgr
        self.uuid = uuid
        self.media_dir = os.path.join(library.root, 'media')
        self.tmp = os.path.join(library.root, 'tmp')
        self.script = os.path.join(library.projects_dir, 'proj1', 'script.xml')

    def export(self, uuid=None):
        return self.mgr.export(uuid or self.uuid)

    def listing(self):
        return sorted(os.listdir(self.folder))

    def need(self, names=None):
        """What the export will write: script.xml plus the media files."""
        names = list(FILES) if names is None else names
        return os.path.getsize(self.script) + sum(
            os.path.getsize(os.path.join(self.media_dir, n)) for n in names)


@pytest.fixture
def env(library, tmp_path, disk):
    from cuemseditor.CuemsDBModel import database

    library.connect()
    for name, data in FILES.items():
        with open(os.path.join(library.root, 'media', name), 'wb') as f:
            f.write(data)
    proj = Project.get(Project.unix_name == 'proj1')
    for name in FILES:
        ProjectMedia.create(project=proj, media=Media.get(Media.unix_name == name),
                            media_filename=name)

    root = os.path.join(library.root, 'varlib')          # stands for /var/lib/cuems
    folder = os.path.join(root, 'exports')
    os.makedirs(folder)
    conf = os.path.join(library.root, 'cuems-exports.conf')
    open(conf, 'w').close()

    settings = get_settings()
    settings['library_path'] = library.root
    settings['tmp_path'] = os.path.join(library.root, 'tmp')
    settings['html_root_path'] = root
    settings['export_conf_path'] = conf
    mgr = p.CuemsDBProject(settings, database)
    return Env(library, folder, conf, mgr, str(proj.uuid))


def _read_zip(path):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        return {i.filename: (i.compress_type, z.read(i)) for i in z.infolist()}


def _assert_complete(zip_path, env, names=None):
    """The zip holds exactly the folders, script.xml and the media: stored and
    equal byte for byte (AC3; ``testzip()`` alone is not this check, P4)."""
    names = list(FILES) if names is None else names
    got = _read_zip(zip_path)
    want = {'proj1/', 'proj1/script.xml', 'proj1/media/'}
    want |= {f'proj1/media/{n}' for n in names}
    assert sorted(got) == sorted(want)
    for name, (method, data) in got.items():
        assert method == zipfile.ZIP_STORED, name
        if name == 'proj1/script.xml':
            assert data == open(env.script, 'rb').read()
        elif name.startswith('proj1/media/') and not name.endswith('/'):
            assert data == FILES[name.rsplit('/', 1)[1]], name


def _leftovers(folder):
    return [n for n in os.listdir(folder) if n.endswith('.part')]


# ---------------------------------------------------------------------------
# (1) the zip, (11) the returned value
# ---------------------------------------------------------------------------

class TestTheZip:
    def test_1_entries_stored_and_equal_to_the_library(self, env):
        value = env.export()
        _assert_complete(os.path.join(env.folder, 'proj1.zip'), env)
        assert value == 'exports/proj1.zip'

    def test_11_returned_value_is_relative_without_a_leading_slash(self, env):
        value = env.export()
        assert value.startswith('exports/') and not value.startswith('/')
        assert re.fullmatch(r'exports/proj1(-\d{3})?\.zip', value)
        assert os.path.isfile(os.path.join(os.path.dirname(env.folder), value))

    def test_9_zip64_records_read_back(self, env, monkeypatch):
        # a 2.5 MB file crosses a limit lowered to 1 MiB: the zip64 path
        monkeypatch.setattr(zipfile, 'ZIP64_LIMIT', 1 << 20)
        env.export()
        path = os.path.join(env.folder, 'proj1.zip')
        with zipfile.ZipFile(path) as z:
            info = z.getinfo('proj1/media/file_video.ext')
            assert info.file_size == len(FILES['file_video.ext'])
            assert info.extra            # the zip64 extra field is there
        _assert_complete(path, env)

    def test_the_settings_point_at_the_exports_parent(self):
        s = get_settings()
        assert s['html_root_path'] == '/var/lib/cuems'
        assert s['export_folder_name'] == 'exports'
        assert s['export_conf_path'] == '/etc/apache2/conf-enabled/cuems-exports.conf'


# ---------------------------------------------------------------------------
# (2) two exports at once, (3) nothing in tmp / no .part, (7) modes
# ---------------------------------------------------------------------------

def _two_at_once(env, monkeypatch, seam, name):
    """Run two exports of one project that meet at a barrier patched into
    ``seam`` (``prefetch``, or the writer's copy)."""
    barrier = threading.Barrier(2, timeout=10)
    real = getattr(p, seam)
    seen = set()

    def gate(*a, **kw):
        me = threading.get_ident()
        if me not in seen:                 # once per export
            seen.add(me)
            barrier.wait()
        return real(*a, **kw)

    monkeypatch.setattr(p, seam, gate)
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(env.export) for _ in range(2)]
        return [f.result(timeout=30) for f in futures]


class TestTwoAtOnce:
    def test_2_two_exports_meeting_at_prefetch_both_complete(self, env, monkeypatch):
        values = _two_at_once(env, monkeypatch, 'prefetch', 'prefetch')
        assert sorted(values) == ['exports/proj1-001.zip', 'exports/proj1.zip']
        assert env.listing() == ['proj1-001.zip', 'proj1.zip']
        for n in env.listing():
            _assert_complete(os.path.join(env.folder, n), env)

    def test_2b_two_exports_held_in_mid_copy_both_complete(self, env, monkeypatch):
        values = _two_at_once(env, monkeypatch, '_copy_stream', '_copy_stream')
        assert sorted(values) == ['exports/proj1-001.zip', 'exports/proj1.zip']
        for n in env.listing():
            _assert_complete(os.path.join(env.folder, n), env)
        assert _leftovers(env.folder) == []


class TestNothingLeftBehind:
    def test_3_nothing_under_tmp_path_and_no_part_after_success(self, env):
        env.export()
        assert not os.path.exists(env.tmp)
        assert env.listing() == ['proj1.zip']

    def test_3_no_part_and_nothing_published_after_a_failure_in_mid_copy(self, env, monkeypatch):
        real = p._copy_stream
        calls = []

        def boom(src, dst):
            calls.append(src.name)
            if len(calls) == 2:
                raise OSError(errno.EIO, 'disk error')
            return real(src, dst)

        monkeypatch.setattr(p, '_copy_stream', boom)
        with pytest.raises(OSError):
            env.export()
        assert len(calls) == 2
        assert env.listing() == []
        assert not os.path.exists(env.tmp)

    def test_7_part_is_0600_while_written_and_0644_once_published(self, env, monkeypatch):
        real = p._copy_stream
        seen = []

        def look(src, dst):
            parts = [n for n in os.listdir(env.folder) if n.endswith('.part')]
            assert len(parts) == 1
            assert re.fullmatch(r'\.proj1\..+\.part', parts[0])
            seen.append(stat.S_IMODE(os.stat(os.path.join(env.folder, parts[0])).st_mode))
            return real(src, dst)

        monkeypatch.setattr(p, '_copy_stream', look)
        env.export()
        assert seen and set(seen) == {0o600}
        assert stat.S_IMODE(os.stat(os.path.join(env.folder, 'proj1.zip')).st_mode) == 0o644


# ---------------------------------------------------------------------------
# (4) E1
# ---------------------------------------------------------------------------

class TestExportsFolderAndConf:
    def test_4_folder_missing_is_E1_and_is_not_created(self, env):
        os.rmdir(env.folder)
        with mock.patch.object(p.Logger, 'error') as error:
            with pytest.raises(Exception) as ei:
                env.export()
        assert str(ei.value) == E1_FOLDER(env.folder)
        assert not os.path.exists(env.folder)
        assert not os.path.exists(env.tmp)
        assert any(E1_FOLDER(env.folder) in str(c.args[0]) for c in error.call_args_list)

    def test_4_folder_that_is_a_file_is_E1(self, env):
        os.rmdir(env.folder)
        open(env.folder, 'w').close()
        with pytest.raises(Exception) as ei:
            env.export()
        assert str(ei.value) == E1_FOLDER(env.folder)

    @pytest.mark.skipif(os.geteuid() == 0, reason='root writes anywhere')
    def test_4_folder_not_writable_is_E1(self, env):
        os.chmod(env.folder, 0o555)
        try:
            with pytest.raises(Exception) as ei:
                env.export()
            assert str(ei.value) == E1_FOLDER(env.folder)
            assert os.listdir(env.folder) == []
        finally:
            os.chmod(env.folder, 0o755)

    def test_4_conf_missing_is_E1_and_nothing_is_created(self, env):
        os.remove(env.conf)
        with mock.patch.object(p.Logger, 'error') as error:
            with pytest.raises(Exception) as ei:
                env.export()
        assert str(ei.value) == E1_CONF
        assert env.listing() == []
        assert not os.path.exists(env.conf)
        assert not os.path.exists(env.tmp)
        assert any(E1_CONF in str(c.args[0]) for c in error.call_args_list)

    def test_4_a_dangling_link_for_the_conf_is_E1(self, env):
        os.remove(env.conf)
        os.symlink(os.path.join(env.library.root, 'nowhere.conf'), env.conf)
        with pytest.raises(Exception) as ei:
            env.export()
        assert str(ei.value) == E1_CONF


# ---------------------------------------------------------------------------
# (5) the reserve (D14), E2
# ---------------------------------------------------------------------------

class TestReserve:
    @pytest.mark.parametrize('total_gib, reserve_gib', [(20, 5), (200, 20)])
    def test_5_the_reserve_at_its_two_edges(self, env, disk, total_gib, reserve_gib):
        need = env.need()
        reserve = reserve_gib * GIB
        disk.total = total_gib * GIB

        disk.free = need + reserve - 1
        with mock.patch.object(p.Logger, 'error') as error:
            with pytest.raises(Exception) as ei:
                env.export()
        text = str(ei.value)
        assert text.startswith('No space to export "Proj One": needs ')
        assert f'{reserve_gib:.1f} GiB kept in reserve' in text
        assert text.endswith('kept in reserve') and '\n' not in text
        assert env.folder in text
        assert env.listing() == []
        assert any('No space to export' in str(c.args[0]) for c in error.call_args_list)

        disk.free = need + reserve
        assert env.export() == 'exports/proj1.zip'
        assert env.folder in disk.paths           # the exports filesystem is the one measured

    def test_5_an_export_in_progress_counts(self, env, disk, monkeypatch):
        need = env.need()
        reserve = 5 * GIB
        disk.total = 20 * GIB
        disk.free = need + reserve
        entered = threading.Event()
        release = threading.Event()
        real = p._copy_stream
        holder = []

        def hold(src, dst):
            if threading.get_ident() in holder:
                entered.set()
                assert release.wait(20)
            return real(src, dst)

        monkeypatch.setattr(p, '_copy_stream', hold)

        def first():
            holder.append(threading.get_ident())
            return env.export()

        with ThreadPoolExecutor(1) as pool:
            fut = pool.submit(first)
            assert entered.wait(20)
            try:
                # the first export has most of its bytes still to write: it
                # takes room, so a second one of the same size no longer fits
                # on a disk that would take it alone
                with pytest.raises(Exception) as ei:
                    env.export()
                assert str(ei.value).startswith('No space to export "Proj One"')
                # ... and does when the disk has room for both and the reserve
                disk.free = 2 * need + reserve + 8192
                second = env.export()
            finally:
                release.set()
            first_value = fut.result(timeout=30)
        assert sorted([first_value, second]) == ['exports/proj1-001.zip', 'exports/proj1.zip']
        # nothing stays booked once both are done
        disk.free = need + reserve
        assert env.export().startswith('exports/proj1')

    def test_12_two_rows_for_one_file_count_once_in_need(self, env, disk):
        proj = Project.get(Project.unix_name == 'proj1')
        ProjectMedia.create(project=proj, media=Media.get(Media.unix_name == 'file.ext'),
                            media_filename='file.ext')
        disk.total = 20 * GIB
        disk.free = env.need() + 5 * GIB          # exactly enough for one copy of each file
        with warnings.catch_warnings():
            warnings.simplefilter('error')        # zipfile's 'Duplicate name' is a UserWarning
            assert env.export() == 'exports/proj1.zip'
        _assert_complete(os.path.join(env.folder, 'proj1.zip'), env)


# ---------------------------------------------------------------------------
# (6) naming, (8) no link, (12) rows, (13) a file that changes
# ---------------------------------------------------------------------------

class TestPublishing:
    def test_6_the_next_free_name_is_taken(self, env):
        for n in ('proj1.zip', 'proj1-001.zip'):
            with open(os.path.join(env.folder, n), 'wb') as f:
                f.write(b'older')
        assert env.export() == 'exports/proj1-002.zip'
        assert open(os.path.join(env.folder, 'proj1.zip'), 'rb').read() == b'older'
        assert open(os.path.join(env.folder, 'proj1-001.zip'), 'rb').read() == b'older'
        _assert_complete(os.path.join(env.folder, 'proj1-002.zip'), env)

    def test_6_sixteen_threads_publishing_get_sixteen_names_each_intact(self, env):
        with ThreadPoolExecutor(16) as pool:
            values = [f.result(timeout=60) for f in [pool.submit(env.export) for _ in range(16)]]
        assert len(set(values)) == 16
        names = env.listing()
        assert len(names) == 16 and _leftovers(env.folder) == []
        for n in names:
            _assert_complete(os.path.join(env.folder, n), env)

    def test_8_without_hard_links_a_name_is_still_never_overwritten(self, env, monkeypatch):
        with open(os.path.join(env.folder, 'proj1.zip'), 'wb') as f:
            f.write(b'older')

        def refuse(*a, **kw):
            raise OSError(errno.EPERM, 'no hard links here')

        monkeypatch.setattr(os, 'link', refuse)
        assert env.export() == 'exports/proj1-001.zip'
        assert open(os.path.join(env.folder, 'proj1.zip'), 'rb').read() == b'older'
        path = os.path.join(env.folder, 'proj1-001.zip')
        _assert_complete(path, env)
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o644
        assert _leftovers(env.folder) == []

    def test_8_without_hard_links_sixteen_threads_still_get_sixteen_names(self, env, monkeypatch):
        def refuse(*a, **kw):
            raise OSError(errno.EOPNOTSUPP, 'no hard links here')

        monkeypatch.setattr(os, 'link', refuse)
        with ThreadPoolExecutor(16) as pool:
            values = [f.result(timeout=60) for f in [pool.submit(env.export) for _ in range(16)]]
        assert len(set(values)) == 16
        for n in env.listing():
            _assert_complete(os.path.join(env.folder, n), env)

    def test_the_info_line_names_the_file_its_size_and_the_seconds(self, env):
        with mock.patch.object(p.Logger, 'info') as info:
            env.export()
        lines = [str(c.args[0]) for c in info.call_args_list]
        size = os.path.getsize(os.path.join(env.folder, 'proj1.zip'))
        assert any(re.fullmatch(
            rf'exported proj1 -> exports/proj1\.zip \({size} bytes, [0-9.]+ s\)', l)
            for l in lines), lines


class TestTheRows:
    def test_12_a_file_deleted_for_good_is_skipped_as_today(self, env):
        proj = Project.get(Project.unix_name == 'proj1')
        ProjectMedia.create(project=proj, media=None, media_filename='gone.wav')
        with mock.patch.object(p.Logger, 'warning') as warning:
            assert env.export() == 'exports/proj1.zip'
        _assert_complete(os.path.join(env.folder, 'proj1.zip'), env)
        assert any('gone.wav' in str(c.args[0]) and 'no longer in the library' in str(c.args[0])
                   for c in warning.call_args_list)

    def test_12_two_rows_for_one_file_give_one_entry(self, env):
        proj = Project.get(Project.unix_name == 'proj1')
        ProjectMedia.create(project=proj, media=Media.get(Media.unix_name == 'file.ext'),
                            media_filename='file.ext')
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            env.export()
        path = os.path.join(env.folder, 'proj1.zip')
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
        assert len(names) == len(set(names))
        _assert_complete(path, env)


class TestAFileThatChanges:
    def _wrapped(self, monkeypatch, name, before):
        real = p._copy_stream

        def wrapper(src, dst):
            if os.path.basename(src.name) == name:
                before(src.name)
            return real(src, dst)

        monkeypatch.setattr(p, '_copy_stream', wrapper)

    def test_13_a_file_that_grows_is_E6_and_nothing_is_published(self, env, monkeypatch):
        def grow(path):
            with open(path, 'ab') as f:
                f.write(b'more' * 1000)

        self._wrapped(monkeypatch, 'file.ext', grow)
        with mock.patch.object(p.Logger, 'error') as error:
            with pytest.raises(Exception) as ei:
                env.export()
        assert str(ei.value) == E6('file.ext')
        assert env.listing() == []
        assert any(E6('file.ext') in str(c.args[0]) for c in error.call_args_list)

    def test_13_a_file_that_is_truncated_is_E6_and_nothing_is_published(self, env, monkeypatch):
        self._wrapped(monkeypatch, 'file_video.ext', lambda path: os.truncate(path, 300_000))
        with pytest.raises(Exception) as ei:
            env.export()
        assert str(ei.value) == E6('file_video.ext')
        assert env.listing() == []

    def test_13_a_file_that_grows_across_the_zip64_limit_is_E6_too(self, env, monkeypatch):
        # zipfile raises RuntimeError itself there: the export maps it to E6
        monkeypatch.setattr(zipfile, 'ZIP64_LIMIT', 1_500_000)
        path = os.path.join(env.media_dir, 'file.ext')
        with open(path, 'wb') as f:
            f.write(b'x' * 1_000_000)

        def grow(path):
            with open(path, 'ab') as f:
                f.write(b'y' * 1_000_000)

        self._wrapped(monkeypatch, 'file.ext', grow)
        with pytest.raises(Exception) as ei:
            env.export()
        assert str(ei.value) == E6('file.ext')
        assert env.listing() == []

    def test_13_a_file_replaced_by_name_ends_with_the_old_file(self, env, monkeypatch):
        def replace(path):
            new = path + '.new'
            with open(new, 'wb') as f:
                f.write(b'\x00' * os.path.getsize(path))
            os.replace(new, path)

        self._wrapped(monkeypatch, 'file.ext', replace)
        assert env.export() == 'exports/proj1.zip'
        _assert_complete(os.path.join(env.folder, 'proj1.zip'), env)   # the old bytes
        assert _leftovers(env.folder) == []


# ---------------------------------------------------------------------------
# (10) the start-up sweep
# ---------------------------------------------------------------------------

class TestSweep:
    def _settings(self, tmp_path):
        s = get_settings()
        s['tmp_path'] = str(tmp_path / 'tmp-upload')
        s['html_root_path'] = str(tmp_path / 'varlib')
        return s

    def test_10_removes_part_files_dotted_or_not_and_creates_nothing(self, tmp_path):
        import tempfile
        s = self._settings(tmp_path)
        folder = tmp_path / 'varlib' / 'exports'
        folder.mkdir(parents=True)
        fd, mk = tempfile.mkstemp(dir=str(folder), prefix='.proj1.', suffix='.part')
        os.close(fd)
        assert os.path.basename(mk).startswith('.')          # a glob would not see it
        (folder / 'plain.part').write_bytes(b'x')
        for keep in ('proj1.zip', '.hidden', 'notes.txt', 'proj1.part.zip'):
            (folder / keep).write_bytes(b'keep')
        before = set(os.listdir(tmp_path / 'varlib'))
        ensure_directories(s)
        assert sorted(os.listdir(folder)) == ['.hidden', 'notes.txt', 'proj1.part.zip', 'proj1.zip']
        assert set(os.listdir(tmp_path / 'varlib')) == before

    def test_10_never_creates_the_exports_folder(self, tmp_path):
        s = self._settings(tmp_path)
        ensure_directories(s)
        assert not os.path.exists(tmp_path / 'varlib')
        (tmp_path / 'varlib').mkdir()
        ensure_directories(s)
        assert os.listdir(tmp_path / 'varlib') == []


# ---------------------------------------------------------------------------
# (14)-(20) the show is protected always (D17, D20)
# ---------------------------------------------------------------------------

def _user(project_db):
    user = object.__new__(wsu.CuemsWsUser)
    user.websocket = mock.Mock()
    user.outgoing = asyncio.Queue()
    user.incoming = asyncio.Queue()
    user.server = mock.Mock()
    user.server.executor = None
    user.server.db.project = project_db
    return user


def _drive(reply, *accept):
    """One ``project_export`` request against an engine that answers ``reply``
    (a value, or an exception to raise). ``accept`` is the acceptance as sent:
    empty = the key is absent. Returns (frames, project_db, engine commands,
    warning lines)."""
    project_db = mock.Mock()
    project_db.export.return_value = 'exports/x.zip'
    user = _user(project_db)
    commands = []

    async def engine(action, action_uuid, command, query_mode=False):
        commands.append(command)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def run():
        user.server.event_loop = asyncio.get_running_loop()
        with mock.patch.object(user, 'comunicate_with_engine', side_effect=engine), \
                mock.patch.object(wsu.Logger, 'warning') as warning:
            await user.request_export_project('u1', 'project_export', *accept)
        frames = []
        while not user.outgoing.empty():
            frames.append(json.loads(await user.outgoing.get()))
        return frames, [str(c.args[0]) for c in warning.call_args_list]

    frames, warned = asyncio.run(run())
    return frames, project_db, commands, warned


def _error(text):
    return {'type': 'error', 'uuid': 'u1', 'action': 'project_export', 'value': text}


ACCEPTANCES = [(), (True,), (False,), (None,), ('true',), (1,)]


class TestShowIsProtected:
    @pytest.mark.parametrize('accept', [(), (True,)])
    def test_14_running_is_refused_with_and_without_the_key(self, accept):
        frames, project_db, commands, warned = _drive({'status': 'running'}, *accept)
        assert frames == [_error(E3)]
        project_db.export.assert_not_called()
        assert [c['action'] for c in commands] == ['project_status']   # only the question
        assert any(w.startswith('export of u1 refused:') for w in warned)

    @pytest.mark.parametrize('accept', [(), (True,)])
    @pytest.mark.parametrize('reply', [
        EngineError('Timeout: Engine did not respond in 25s'),
        RuntimeError('boom'),
        'OK',
        None,
        {'status': 'weird'},
        {'nostatus': 1},
    ])
    def test_15_no_usable_answer_is_refused_E4(self, reply, accept):
        frames, project_db, commands, warned = _drive(reply, *accept)
        assert frames == [_error(E4)]
        project_db.export.assert_not_called()
        assert [c['action'] for c in commands] == ['project_status']
        assert any(w.startswith('export of u1 refused:') for w in warned)

    @pytest.mark.parametrize('accept', [(), (False,), (None,), ('true',), (1,), ('yes',)])
    def test_16_loaded_without_a_real_true_is_refused_E5(self, accept):
        frames, project_db, commands, warned = _drive({'status': 'loaded'}, *accept)
        assert frames == [_error(E5)]
        project_db.export.assert_not_called()
        assert [c['action'] for c in commands] == ['project_status']
        assert any(w.startswith('export of u1 refused:') for w in warned)

    def test_17_loaded_with_accept_loaded_true_exports_and_warns_once(self):
        frames, project_db, commands, warned = _drive({'status': 'loaded'}, True)
        assert frames == [{'type': 'project_export', 'value': 'exports/x.zip'}]
        project_db.export.assert_called_once_with('u1')
        accepted = [w for w in warned if w == 'export of u1 accepted while a project is loaded']
        assert len(accepted) == 1
        assert [c['action'] for c in commands] == ['project_status']

    @pytest.mark.parametrize('accept', ACCEPTANCES)
    def test_18_none_exports_whatever_the_key(self, accept):
        frames, project_db, commands, warned = _drive({'status': 'none'}, *accept)
        assert frames == [{'type': 'project_export', 'value': 'exports/x.zip'}]
        project_db.export.assert_called_once_with('u1')
        assert not any('refused' in w or 'accepted while' in w for w in warned)

    def test_the_error_of_an_export_that_fails_is_still_sent_as_it_is(self):
        project_db = mock.Mock()
        project_db.export.side_effect = RuntimeError('No space to export "x"')
        user = _user(project_db)

        async def engine(*a, **kw):
            return {'status': 'none'}

        async def run():
            user.server.event_loop = asyncio.get_running_loop()
            with mock.patch.object(user, 'comunicate_with_engine', side_effect=engine):
                await user.request_export_project('u1', 'project_export')
            return json.loads(await user.outgoing.get())

        assert asyncio.run(run()) == _error('No space to export "x"')


class TestActionMap:
    def _consume(self, frame):
        user = _user(mock.Mock())
        user.request_export_project = mock.AsyncMock()

        async def run():
            await user.incoming.put(json.dumps(frame))
            task = asyncio.create_task(user.consumer())
            for _ in range(100):
                if user.request_export_project.await_count:
                    break
                await asyncio.sleep(0.01)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(run())
        return user.request_export_project

    def test_19_the_frames_accept_loaded_reaches_the_handler(self):
        handler = self._consume({'action': 'project_export', 'value': 'u1', 'accept_loaded': True})
        handler.assert_awaited_once_with('u1', 'project_export', True)

    def test_19_a_frame_without_the_key_reaches_it_as_none(self):
        handler = self._consume({'action': 'project_export', 'value': 'u1'})
        handler.assert_awaited_once_with('u1', 'project_export', None)


class TestEngineStatus:
    def _ask(self, method, value):
        user = _user(mock.Mock())

        async def engine(action, action_uuid, command, query_mode=False):
            assert (command['action'], query_mode) == ('project_status', True)
            if isinstance(value, Exception):
                raise value
            return value

        async def run():
            with mock.patch.object(user, 'comunicate_with_engine', side_effect=engine):
                return await getattr(user, method)()

        return asyncio.run(run())

    @pytest.mark.parametrize('word', ['running', 'loaded', 'none'])
    def test_status_returns_the_three_words(self, word):
        assert self._ask('_engine_status', {'status': word, 'project_uuid': 'x'}) == word

    @pytest.mark.parametrize('value', [
        RuntimeError('timeout'), 'OK', None, {'status': 'other'}, {'status': None}, {}, 7])
    def test_status_is_none_for_anything_else(self, value):
        assert self._ask('_engine_status', value) is None

    def test_20_engine_running_keeps_its_answers(self):
        # the pin of tests/test_media_refresh.py:850-865, plus 'loaded' (N10, D19)
        assert self._ask('_engine_running', {'status': 'running'}) is True
        assert self._ask('_engine_running', {'status': 'none'}) is False
        assert self._ask('_engine_running', {'status': 'loaded'}) is None
        assert self._ask('_engine_running', RuntimeError('timeout')) is None
        assert self._ask('_engine_running', 'OK') is None
