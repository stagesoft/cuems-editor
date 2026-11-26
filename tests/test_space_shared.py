# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""The disk space shared by running exports and imports (ClickUp 1amfwm7kcjp,
change review R3; the export's side is 1amfwm7kana D14).

An export counted the bytes other running exports had claimed and not yet
written; an import counted nothing, and an export ignored a running import,
so both could pass ``free - need >= reserve`` at once and together need more
than the free space. Now both register in ``cuemseditor.CuemsSpace`` and
both checks count the others on the same filesystem (``st_dev``), the
outstanding bytes only (need less what is on disk, never below zero).

Each test runs a real export and a real import in one library (the import's
``env`` of ``tests/test_import.py``, with an exports folder added). The disk
is the patched ``shutil.disk_usage``: its free space never moves, so the
numbers below make each side fit alone and not both together. The module is
imported inside the tests, so on the code before R3 the cross tests fail on
their assertion (DID NOT RAISE), not on a missing name.
"""
import contextlib
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import cuemseditor.CuemsDBProject as p
from cuemseditor.CuemsDBModel import Project

from test_import import (  # noqa: F401  (env, disk, zips, _fresh_marks are fixtures)
    GIB, I2, MEDIA, NAME, TOP, _fresh_marks, _imp, disk, env, export_entries, md5, zips)
from test_import_ws import (
    chunks, errors, finished, first_frame, guard, is_end, run_upload, the_zip, until)

RESERVE = 5 * GIB          # the reserve of a 20 GiB disk: the larger of 5 GiB and a tenth


def _space():
    from cuemseditor import CuemsSpace
    return CuemsSpace


def held():
    return set(_space()._held)


@pytest.fixture(autouse=True)
def _no_leftover_reservation():
    """A failing test must not leave a claim that refuses the next ones."""
    yield
    try:
        _space()._held.clear()
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# helpers: an exports folder in the import's library, a project to export,
# an export or an import held halfway
# ---------------------------------------------------------------------------

def _exports(env):
    folder = os.path.join(env.settings['html_root_path'], env.settings['export_folder_name'])
    os.makedirs(folder, exist_ok=True)
    conf = os.path.join(env.root, 'cuems-exports.conf')
    open(conf, 'w').close()
    env.settings['export_conf_path'] = conf
    return folder


def _project_to_export(env):
    """Import show_a (MEDIA): the project the export writes. Returns (uuid, the
    bytes its export needs: script.xml and the media)."""
    report = env.run(env.zip(export_entries()))
    script = os.path.join(env.root, 'projects', TOP, 'script.xml')
    return report['project']['uuid'], os.path.getsize(script) + sum(map(len, MEDIA.values()))


def _second_archive(env, size, top='show_b', name='other.wav'):
    """An archive whose one media file (*size* bytes) the library lacks."""
    media = {name: os.urandom(size)}
    return env.zip(export_entries(top=top, media=media), name=f'{top}.zip')


def _tight(disk, a, b):
    """A 20 GiB disk on which *a* bytes fit with the reserve, and *b* bytes fit,
    but not both while either has more than ``min(a, b) / 2`` still to write."""
    disk.total = 20 * GIB
    disk.free = RESERVE + max(a, b) + min(a, b) // 2


def _e2(need, free, folder):
    return (f'No space to export "{NAME}": needs {need / GIB:.1f} GiB, {free / GIB:.1f} GiB '
            f'free in {folder}, {RESERVE / GIB:.1f} GiB kept in reserve')


@contextlib.contextmanager
def export_held(env, uuid, monkeypatch):
    """A real export of *uuid*, in a thread, held in its first copy (the
    script): it has claimed its bytes and written only a few headers."""
    entered, release = threading.Event(), threading.Event()
    real = p._copy_stream
    holder = []

    def hold(src, dst, size):
        if threading.get_ident() in holder:
            entered.set()
            assert release.wait(30)
        return real(src, dst, size)

    monkeypatch.setattr(p, '_copy_stream', hold)

    def run():
        holder.append(threading.get_ident())
        return env.project.export(uuid)

    with ThreadPoolExecutor(1) as pool:
        fut = pool.submit(run)
        if not entered.wait(30):
            raise AssertionError(f'the export did not start: {fut.exception(1)!r}')
        try:
            yield fut
        finally:
            release.set()
            fut.result(60)


@contextlib.contextmanager
def import_held(env, path):
    """A real import of *path*, in a thread, held at its first later check
    (D4), before its first file is extracted: it has claimed its bytes (D6)
    and written none."""
    entered, go = threading.Event(), threading.Event()

    def status():
        entered.set()
        assert go.wait(30)
        return 'none'

    with ThreadPoolExecutor(1) as pool:
        fut = pool.submit(env.run, path, status)
        if not entered.wait(30):
            raise AssertionError(f'the import did not start: {fut.exception(1)!r}')
        try:
            yield fut
        finally:
            go.set()
            fut.result(60)


# ---------------------------------------------------------------------------
# the two cross cases, on one filesystem
# ---------------------------------------------------------------------------

class TestCross:
    def test_r3_a_running_export_refuses_an_import(self, env, disk, monkeypatch):
        folder = _exports(env)
        uuid, need = _project_to_export(env)
        path = _second_archive(env, need)
        _tight(disk, need, need)
        with export_held(env, uuid, monkeypatch) as export:
            # after the checks (D6): the files to add against the library
            error, text = env.refused(path)
            assert text == I2(need, disk.free, env.media_dir, RESERVE)   # free is the disk's own
            # and at the guard: the zip against the staging folder
            assert _imp().space_refusal(env.staging_root, need) == I2(
                need, disk.free, env.staging_root, RESERVE)
        assert export.result() == 'exports/show_a.zip'
        assert os.path.isfile(os.path.join(folder, 'show_a.zip'))
        assert held() == set()
        report = env.run(path)                       # alone, the same import fits
        assert report['media']['added'] == ['other.wav']

    def test_r3_a_running_import_refuses_an_export(self, env, disk, monkeypatch):
        folder = _exports(env)
        uuid, need = _project_to_export(env)
        path = _second_archive(env, need)
        _tight(disk, need, need)
        with import_held(env, path) as imported:
            with pytest.raises(Exception) as ei:
                env.project.export(uuid)
            assert str(ei.value) == _e2(need, disk.free, folder)
            assert not os.listdir(folder)            # nothing written, no .part left
        assert imported.result()['media']['added'] == ['other.wav']
        assert held() == set()
        assert env.project.export(uuid) == 'exports/show_a.zip'   # alone, it fits

    def test_r3_a_running_export_refuses_an_upload_that_starts_after_the_guard(
            self, env, disk, monkeypatch):
        """The guard registers nothing (its ticket may never be used): the
        zip is claimed when the upload starts, and refused there (I2) when an
        export took the room since the guard."""
        _exports(env)
        uuid, need = _project_to_export(env)
        data = the_zip(env)
        _tight(disk, need, len(data))
        staged = os.listdir(env.staging_root)        # show_a's, which env.run leaves
        with export_held(env, uuid, monkeypatch):
            server, sock, owner = run_upload(
                env, lambda t: [first_frame(len(data), t), *chunks(data), finished(md5(data))],
                size=len(data))
        sent = sock.frames()
        assert sent[0] == {'error': I2(len(data), disk.free, env.staging_root, RESERVE),
                           'fatal': True}, sent
        assert {'ready': True} not in sent
        assert not server.import_slot.busy
        assert os.listdir(env.staging_root) == staged    # the upload's folder is gone
        assert held() == set()


# ---------------------------------------------------------------------------
# two filesystems: neither counts the other
# ---------------------------------------------------------------------------

class TestFilesystems:
    def test_r3_an_export_and_an_import_on_two_filesystems_do_not_count_each_other(
            self, env, disk, monkeypatch):
        folder = _exports(env)
        uuid, need = _project_to_export(env)
        monkeypatch.setattr(_space(), 'device_of', lambda path: (
            'exports-disk' if os.fspath(path).startswith(folder) else 'library-disk'))
        _tight(disk, need, need)                     # what refuses both on one filesystem
        with export_held(env, uuid, monkeypatch):
            report = env.run(_second_archive(env, need))
        assert report['media']['added'] == ['other.wav']
        with import_held(env, _second_archive(env, need, top='show_c', name='third.wav')):
            assert env.project.export(uuid) == 'exports/show_a.zip'
        assert held() == set()


# ---------------------------------------------------------------------------
# what the import claims, and how it shrinks as the files land
# ---------------------------------------------------------------------------

def _sizes():
    return [len(MEDIA[n]) for n in MEDIA]          # the order the script names them


class TestImportClaim:
    def test_r3_one_filesystem_a_file_counts_once_extracted_and_its_move_is_free(self, env):
        seen = []

        def status():
            seen.append(sorted((r.need, r.outstanding()) for r in held()))
            return 'none'

        env.run(env.zip(export_entries()), status)
        a, b, c = _sizes()
        total = a + b + c
        # asked before each extraction, before each registration (new(), a
        # rename here) and before the project: the claim shrinks by a file
        # when it is extracted, not again when it is moved into media/
        assert seen == [[(total, total)], [(total, b + c)], [(total, b + c)], [(total, c)],
                        [(total, c)], [(total, 0)], [(total, 0)]]
        assert held() == set()

    def test_r3_two_filesystems_the_library_claim_shrinks_as_each_file_is_registered(
            self, env, monkeypatch):
        monkeypatch.setattr(_space(), 'device_of', lambda path: (
            'staging' if os.fspath(path).startswith(env.staging_root) else 'library'))
        seen = []

        def status():
            seen.append({r.device: (r.need, r.outstanding()) for r in held()})
            return 'none'

        env.run(env.zip(export_entries()), status)
        a, b, c = _sizes()
        total, largest = a + b + c, max(a, b, c)
        library = [s['library'] for s in seen]
        assert library == [(total, total), (total, total), (total, b + c), (total, b + c),
                           (total, c), (total, c), (total, 0)]
        assert {s['staging'] for s in seen} == {(largest, largest)}
        assert held() == set()

    def test_r3_the_upload_claims_the_zip_and_shrinks_as_it_arrives(self, env, disk):
        data = the_zip(env)
        parts = chunks(data, 100_000)
        disk.total = 20 * GIB
        disk.free = RESERVE + len(data)              # the zip fits alone, at its edge
        seen = {}

        async def after(server, sock, owner):
            await until(lambda: sock.frames().count({'ready': True}) >= 2, 20)
            seen['held'] = [(r.need, r.outstanding()) for r in held()]
            # a guard asked now counts what this upload still has to receive
            seen['guard'] = _imp().space_refusal(env.staging_root, len(data))
            sock.put(*parts[1:], finished(md5(data)))

        server, sock, owner = run_upload(env, lambda t: [first_frame(len(data), t), parts[0]],
                                         size=len(data), after=after)
        assert errors(sock) == [], sock.frames()
        [(need, outstanding)] = seen['held']
        assert need == len(data)
        assert len(data) - len(parts[0]) <= outstanding < len(data)
        assert seen['guard'] == I2(len(data), disk.free, env.staging_root, RESERVE)
        assert Project.get(Project.unix_name == TOP)
        assert held() == set()


# ---------------------------------------------------------------------------
# released on every exit path
# ---------------------------------------------------------------------------

class TestRelease:
    @pytest.mark.parametrize('case', ['no_space', 'new_fails', 'show_starts'])
    def test_r3_a_failed_import_releases_its_claim(self, env, disk, monkeypatch, case):
        path = env.zip(export_entries())
        status = None
        if case == 'no_space':
            disk.total = 20 * GIB
            disk.free = RESERVE
        elif case == 'new_fails':
            def boom(*a, **kw):
                raise RuntimeError('disk on fire')
            monkeypatch.setattr(env.media, 'new', boom)
        else:
            status = lambda: 'running'               # noqa: E731
        claimed = []
        real = _space().claim

        def spy(*a, **kw):
            claimed.append(real(*a, **kw))
            return claimed[-1]

        monkeypatch.setattr(_space(), 'claim', spy)
        env.refused(path, status=status)
        assert len(claimed) == (0 if case == 'no_space' else 1)
        assert held() == set()

    @pytest.mark.parametrize('case', ['dropped', 'stalled', 'not_what_was_announced'])
    def test_r3_an_upload_that_ends_early_releases_its_claim(self, env, monkeypatch, case):
        data = the_zip(env)
        parts = chunks(data)
        if case == 'stalled':
            monkeypatch.setattr(_imp(), 'UPLOAD_STALL_S', 0.5)
        claimed = []

        async def after(server, sock, owner):
            await until(lambda: sock.frames().count({'ready': True}) >= 2, 20)
            claimed.extend(held())
            if case == 'not_what_was_announced':
                sock.put(*parts[1:], finished('0' * 32))
            # dropped: run_upload closes the socket now; stalled: nothing comes

        server, sock, owner = run_upload(
            env, lambda t: [first_frame(len(data), t), parts[0]], size=len(data), after=after,
            end=None if case == 'dropped' else is_end, wait_s=20)
        assert [r.need for r in claimed] == [len(data)]   # it was claimed ...
        assert held() == set()                            # ... and let go
        assert not server.import_slot.busy
        assert os.listdir(env.staging_root) == []

    def test_r3_the_guard_claims_nothing_so_an_unused_ticket_leaks_nothing(self, tmp_path, disk):
        frames, server, user, st, warned = guard(tmp_path, 'none')
        assert frames[0]['type'] == 'project_import'      # a ticket was given
        assert held() == set()

    @pytest.mark.parametrize('case', ['no_space', 'copy_fails'])
    def test_r3_a_failed_export_releases_its_claim(self, env, disk, monkeypatch, case):
        _exports(env)
        uuid, need = _project_to_export(env)
        if case == 'no_space':
            disk.total = 20 * GIB
            disk.free = RESERVE + need - 1
        else:
            def boom(src, dst, size):
                raise OSError(28, 'No space left on device')
            monkeypatch.setattr(p, '_copy_stream', boom)
        with pytest.raises(Exception):
            env.project.export(uuid)
        assert held() == set()


# ---------------------------------------------------------------------------
# the registry itself
# ---------------------------------------------------------------------------

class TestReservation:
    def test_r3_outstanding_is_never_below_zero_and_an_unreadable_size_counts_whole(self):
        space = _space()
        assert space.Reservation('d', 100, lambda: 150).outstanding() == 0
        assert space.Reservation('d', 100, lambda: 30).outstanding() == 70

        def unreadable():
            raise OSError('gone')

        assert space.Reservation('d', 100, unreadable).outstanding() == 100
        assert space.Reservation('d', 100).outstanding() == 100

    def test_r3_check_and_claim_count_only_the_same_device(self, tmp_path, monkeypatch):
        import collections
        space = _space()
        usage = collections.namedtuple('usage', 'total used free')
        monkeypatch.setattr(space.shutil, 'disk_usage', lambda path: usage(20 * GIB, 0, 10 * GIB))
        devices = {str(tmp_path / 'a'): 1, str(tmp_path / 'b'): 2}
        monkeypatch.setattr(space, 'device_of', lambda path: devices[os.fspath(path)])

        def reserve(u):
            return RESERVE

        first = space.claim(str(tmp_path / 'a'), 4 * GIB, reserve)
        with pytest.raises(space.NoSpace) as ei:
            space.check(str(tmp_path / 'a'), 2 * GIB, reserve)
        assert (ei.value.free, ei.value.reserve) == (10 * GIB, RESERVE)
        space.check(str(tmp_path / 'b'), 2 * GIB, reserve)         # another disk: not counted
        space.release(first, None)
        space.check(str(tmp_path / 'a'), 2 * GIB, reserve)
        assert held() == set()
