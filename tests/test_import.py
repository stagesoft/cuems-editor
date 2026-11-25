# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Project import from a zip made by Export (ClickUp 1amfwm7kcjp), the
archive side: what the reader checks, what it does per media file, the
project it creates, and what a failure leaves.

Design: cuems-RELATIONS Plans/2026-11-24-project-import-from-zip.md (Spec
rev 3), step 1. The numbers in the test names are the plan's step-1 numbers;
(15) to (18) are in ``tests/test_import_ws.py``. These tests are written
before the code (AC1): until step 2 lands they fail on the missing module
``cuemseditor.CuemsProjectImport`` or on the missing names below. The module
is imported inside each test (``_imp()``), after its fixtures ran, so a
fixture defect shows up as its own error and not as the expected ImportError.

Interface chosen by step 1 (where the plan fixes no name or signature; step 2
implements exactly this):

* ``cuemseditor.CuemsProjectImport.import_archive(zip_path, db, staging, *,
  status, accept_loaded=False, progress=None, list_update=None) -> report``,
  synchronous (the session runs it in the executor). ``db`` has ``.project``
  (``CuemsDBProject``) and ``.media`` (``CuemsDBMedia``); ``staging`` is this
  import's own existing folder, the only place it writes outside the
  library's writers; the caller removes it. ``status()`` returns the engine's
  word (``'running'``, ``'loaded'``, ``'none'`` or ``None``) and is called
  before each file is registered and before the project is created (D4);
  ``progress(phase, done, total, name)``; ``list_update(list_type)`` with
  ``'file_list'`` after each file registered (failure path included) and
  ``'project_list'`` at the end and after a relink changed a project.
* ``cuemseditor.CuemsProjectImport.open_archive(zip_path) -> zipfile.ZipFile``:
  bounds the directory's bytes from the end record and counts its records
  before ``ZipFile`` is built; raises ``ProjectImportError`` (I8a).
* Module constants, read at call time (tests patch them): ``MAX_SCRIPT_BYTES``
  (64 MiB), ``MAX_DIRECTORY_BYTES`` (4 MiB), ``MAX_ENTRIES`` (10 000),
  ``HEARTBEAT_S`` (5), ``UPLOAD_STALL_S`` (120), ``TICKET_TTL_S`` (60).
* ``cuemseditor.CuemsErrors.ProjectImportError(text, report=None)``: ``str()``
  is the one-line text I1 to I9; ``.report`` the report so far (or ``None``).
* The report is the dict of "The messages". Names in ``added`` and ``reused``
  are the library names the imported script uses; ``renamed`` lists every
  archive name whose library name differs, added or reused,
  ``{"from": <archive name>, "to": <library name>}``; ``missing`` and
  ``from_library`` hold script names; ``project.renamed`` is a bool;
  ``relinked`` items are ``{"project": <that project's display name>, "name":
  <file>}``; ``sidecars_failed`` items are ``{"name": <file>, "what": one of
  "thumbnail", "waveform", "index", "period"}``; ``ignored`` holds entry
  names. The order of the lists is free (the tests sort).
* I8a's ``<reason>`` names the offending entry or media name when there is one;
  the entity-bearing script is I8a (the defused parser refuses it before the
  schema runs); a script the schema refuses is I8b, whose version is
  ``cuemsutils.__version__`` and whose reason is the validator's, on one line.
* I2 is formatted as the export's E2: ``{:.1f}`` GiB; at the guard it names the
  staging root ``<library_path>/<import_folder_name>``, after the checks the
  media folder. The post-check counts the bytes of the files to be added.
* I9's list of media added is ``", ".join(<library names>)`` or ``none``.
* ``CuemsDBProject.import_project(data, unix_name, name) -> (uuid, unix_name,
  name)``: the pair it chose. ``add_media_relations(project, project_object,
  allow_missing=False)``.
* ``cli.get_settings()['import_folder_name'] == '.import'``; the staging root
  is ``<library_path>/.import``. ``ensure_directories`` makes it 0700, removes
  only children matching ``^import-[0-9a-f]+$`` (logging each with
  ``Logger.info``), never follows a link, and when the root is a symlink it
  leaves it alone, logs ``Logger.error`` naming it and does not raise.
* WebSocket side (``tests/test_import_ws.py``): ``CuemsWsServer.ImportSlot()``
  with ``take(size, accept_loaded, owner) -> ticket`` (raises
  ``ProjectImportError`` I1 while held), ``claim(ticket, size) -> record or
  None`` (one use; ``None`` when unknown, used, expired or of another size;
  ``record`` has ``ticket``, ``size``, ``accept_loaded``, ``owner``, ``stamp``),
  ``release(ticket)`` and ``busy``; its clock is the module-level
  ``CuemsWsServer.import_clock`` (``time.monotonic``); an unclaimed ticket
  older than ``TICKET_TTL_S`` frees the slot, a claimed one holds it until
  released. The server holds one as ``server.import_slot``. The guard is
  ``CuemsWsUser.request_import_project(value, action, accept_loaded=None)``
  and the rule of D3 is ``CuemsWsUser.import_refusal(status,
  accept_loaded) -> text or None``. On ``/upload`` the first frame carries
  ``type`` and ``ticket`` inside ``value``:
  ``{"action":"upload","value":{"name","size","type":"PROJECT","ticket"}}``.
  The later checks call ``owner._engine_status()`` of the session that took
  the ticket. A bad ``size`` at the guard is refused with an action error
  whose text is free.
"""
import collections
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import struct
import subprocess
import sys
import types
import uuid
import warnings
import zipfile
from unittest import mock
from xml.sax.saxutils import escape

import pytest

import cuemseditor.CuemsDBMedia as m
import cuemseditor.CuemsDBProject as p
import cuemseditor.cli as cli
from cuemseditor.CuemsDBModel import Media, Project, ProjectMedia, database
from cuemsutils.helpers import new_datetime
from cuemsutils.tools import media_sidecars as ms
from cuemsutils.tools.CTimecode import CTimecode

GIB = 1024 ** 3


def _imp():
    """The module under test (step 2): imported late, see the docstring."""
    import cuemseditor.CuemsProjectImport as imp
    return imp


def _error_class():
    from cuemseditor.CuemsErrors import ProjectImportError
    return ProjectImportError


# ---------------------------------------------------------------------------
# The texts the plan fixes ("The messages", I1 to I9). One line each.
# ---------------------------------------------------------------------------

I1 = 'Another import is in progress: wait for it to end'
I3 = 'A show is running: stop it before importing a project'
I4 = ('Cannot check whether a show is running (the engine does not answer): '
      'nothing was imported')
I5 = ('A project is loaded and waiting for GO: an import writes the whole project to '
      'disk and builds its previews, and can make the next GO late. Accept the warning '
      'in the import dialog to go on')
I6 = 'Import refused: start it again from the project list'
I7 = 'The upload is not complete or does not match: import again'
I8A = 'Not a project archive made by Export: '
I9 = 'Import interrupted: '
I9_TAIL = '. Nothing that existed was changed; media added: '


def I2(need, free, folder, reserve):
    return (f'No space to import: needs {need / GIB:.1f} GiB, {free / GIB:.1f} GiB free '
            f'in {folder}, {reserve / GIB:.1f} GiB kept in reserve')


def I8B_HEAD():
    import cuemsutils
    return (f"This project's script is not valid for this controller "
            f"(cuems-utils {cuemsutils.__version__}): ")


I8B_TAIL = '. If the archive comes from a newer version, update this controller first'


def i9_parts(text):
    """(reason, [names added]) of an I9 text."""
    assert text.startswith(I9), text
    reason, _, names = text[len(I9):].rpartition(I9_TAIL)
    assert _ == I9_TAIL, text
    return reason, ([] if names == 'none' else names.split(', '))


# ---------------------------------------------------------------------------
# The show: three media of three types, a fade; names as the export writes them
# ---------------------------------------------------------------------------

TOP = 'show_a'
NAME = 'Show A'
DESCRIPTION = 'Imported test show'
SCRIPT_ID = 'a0d6d6a5-3b9f-4c41-9d0c-1f2e3d4c5b6a'
TC0 = '<CTimecode>00:00:00.000</CTimecode>'
TC3 = str(CTimecode(start_seconds=3.0))     # what the fake prober says for movie and audio

#: name -> bytes. clip.mp4 crosses the 1 MiB chunk; cançó.wav carries an accent.
MEDIA = {
    'clip.mp4': os.urandom(1_300_000),
    'cançó.wav': os.urandom(200_000),
    'still.png': os.urandom(5_000),
}
MOVIE_EXT = ('.mp4', '.mov', '.mkv', '.avi')
IMAGE_EXT = ('.png', '.jpg')


def md5(data):
    return hashlib.md5(data).hexdigest()


def _uuid4(seed):
    """A fixed uuid of version 4 (the schema's ``UuidType`` accepts no other)."""
    return str(uuid.UUID(bytes=uuid.uuid5(uuid.NAMESPACE_URL, seed).bytes, version=4))


def cue_id(name):
    return _uuid4('cue:' + name)


def media_id(name):
    """The Media block id the source project carries for ``name``."""
    return _uuid4('media:' + name)


FADE_ID = _uuid4('cue:the-fade')
NOMEDIA_ID = _uuid4('cue:no-media')

_NS = ('xmlns:cms="https://stagelab.coop/cuems/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
       'xsi:schemaLocation="https://stagelab.coop/cuems/ script.xsd"')
_UI = ('<ui_properties><icon>icon.png</icon><color>#ffffff</color><timeline_position><x>0</x>'
       '<y>0</y></timeline_position><warning>0</warning></ui_properties>')


def _common(cid, ui='<ui_properties />'):
    return (f'<autoload>False</autoload><description /><enabled>True</enabled><id>{cid}</id>'
            f'<loop>0</loop><name>cue</name><offset>{TC0}</offset><post_go>pause</post_go>'
            f'<postwait>{TC0}</postwait><prewait>{TC0}</prewait><target /><timecode>False</timecode>{ui}')


def _media_block(name, content=None, mid=None):
    duration = TC3 if not name.lower().endswith(IMAGE_EXT) else '00:00:00.000'
    extra = ''
    if content is not None:
        if content:
            extra += f'<file_size>{len(content)}</file_size>'
        extra += f'<file_md5>{md5(content)}</file_md5>'
    return (f'<Media><file_name>{escape(name)}</file_name><id>{mid or media_id(name)}</id>'
            f'<duration>{duration}</duration><regions><Region><id>0</id><loop>2</loop>'
            f'<in_time>{TC0}</in_time><out_time>{TC0}</out_time></Region></regions>{extra}</Media>')


def _cue(name, content=None, mid=None):
    block = _media_block(name, content, mid)
    if name.lower().endswith(MOVIE_EXT + IMAGE_EXT):
        return f'<VideoCue>{_common(cue_id(name))}{block}<outputs /></VideoCue>'
    return (f'<AudioCue>{_common(cue_id(name))}{block}<outputs />'
            f'<master_vol>66</master_vol></AudioCue>')


def _fade(target, duration='00:00:02.000'):
    return (f'<FadeCue>{_common(FADE_ID, ui=_UI)}<action_target>{target}</action_target>'
            f'<action_type>fade_action</action_type><curve_type>linear</curve_type>'
            f'<duration><CTimecode>{duration}</CTimecode></duration>'
            f'<target_value>0</target_value></FadeCue>')


def script_bytes(names=None, contents=None, name=NAME, fade='00:00:02.000', extra_cues='',
                 script_id=SCRIPT_ID, ids=None):
    """A script that names ``names`` (default: the keys of MEDIA), one cue each,
    plus a FadeCue on the first audio cue. ``contents`` gives each named file's
    bytes: its Media block then carries ``file_size`` and ``file_md5``, as a
    project saved by an rc15+ editor does. ``ids`` overrides a Media block's id."""
    names = list(MEDIA) if names is None else list(names)
    contents = MEDIA if contents is None else contents
    cues = [_cue(n, contents.get(n), (ids or {}).get(n)) for n in names]
    audio = [n for n in names if not n.lower().endswith(MOVIE_EXT + IMAGE_EXT)]
    if audio and fade is not None:
        cues.append(_fade(cue_id(audio[0]), fade))
    if not cues and not extra_cues:
        cues.append(f'<ActionCue>{_common(NOMEDIA_ID, ui=_UI)}<action_target>{NOMEDIA_ID}'
                    f'</action_target><action_type>play</action_type></ActionCue>')
    return (f"<?xml version='1.0' encoding='utf-8'?>\n<cms:CuemsProject {_NS}><CuemsScript><CueList>"
            f'<autoload>False</autoload><description /><enabled>True</enabled>'
            f'<id>{_uuid4("root:" + script_id)}</id><loop>1</loop>'
            f'<name>root</name><offset>{TC0}</offset><post_go>pause</post_go><postwait>{TC0}</postwait>'
            f'<prewait>{TC0}</prewait><target /><timecode>False</timecode><ui_properties />'
            f'<contents>{"".join(cues)}{extra_cues}</contents></CueList><created>2026-04-21T18:07:48</created>'
            f'<description>{DESCRIPTION}</description><id>{script_id}</id>'
            f'<modified>2026-04-21T18:07:48</modified><name>{escape(name)}</name>'
            f'<ui_properties><icon>icon.png</icon><color>#000000</color></ui_properties>'
            f'</CuemsScript></cms:CuemsProject>').encode('utf-8')


# ---------------------------------------------------------------------------
# Archives
# ---------------------------------------------------------------------------

def export_entries(top=TOP, script=None, media=None):
    """The one-pass export's entries, in its order (docs/project-archive.md s2)."""
    media = MEDIA if media is None else media
    script = script_bytes(list(media), media) if script is None else script
    return ([(f'{top}/', None), (f'{top}/script.xml', script), (f'{top}/media/', None)]
            + [(f'{top}/media/{n}', b) for n, b in media.items()])


def write_zip(path, entries, compression=zipfile.ZIP_STORED, comment_bytes=0):
    """Write ``entries`` [(name, bytes | None for a directory) or (ZipInfo, bytes)]."""
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')                 # 'Duplicate name'
        with zipfile.ZipFile(path, 'w', compression=compression, allowZip64=True) as z:
            for name, data in entries:
                if isinstance(name, zipfile.ZipInfo):
                    z.writestr(name, data)
                    continue
                info = zipfile.ZipInfo(name, date_time=(2026, 11, 24, 12, 0, 0))
                info.compress_type = compression
                if data is None:
                    info.external_attr = (0o40755 << 16) | 0x10
                    data = b''
                if comment_bytes:
                    info.comment = b'c' * comment_bytes
                z.writestr(info, data)
    return path


def _eocd(buf):
    i = buf.rfind(b'PK\x05\x06')
    assert i >= 0
    return i


def _central_records(buf):
    """[(offset of the record, name bytes, offset of the local header)] of a
    small (not zip64) archive."""
    i = _eocd(buf)
    size_cd, offset_cd = struct.unpack('<II', buf[i + 12:i + 20])
    pos, out = offset_cd, []
    while buf[pos:pos + 4] == b'PK\x01\x02':
        n, e, c = struct.unpack('<HHH', buf[pos + 28:pos + 34])
        local = struct.unpack('<I', buf[pos + 42:pos + 46])[0]
        out.append((pos, buf[pos + 46:pos + 46 + n], local))
        pos += 46 + n + e + c
    return out


def patch_zip(path, name, how):
    """Edit one entry of a written archive in place (``how``: 'encrypt',
    'damage', 'oversize')."""
    buf = bytearray(open(path, 'rb').read())
    hits = [r for r in _central_records(buf) if r[1] == name.encode('utf-8')]
    assert hits, name
    pos, raw, local = hits[0]
    if how == 'encrypt':
        buf[pos + 8] |= 0x01
        buf[local + 6] |= 0x01
    elif how == 'damage':
        n, e = struct.unpack('<HH', buf[local + 26:local + 30])
        data = local + 30 + n + e
        buf[data + 100] ^= 0xFF
    elif how == 'oversize':
        struct.pack_into('<I', buf, pos + 20, len(buf) + 1)
    else:
        raise ValueError(how)
    open(path, 'wb').write(bytes(buf))
    return path


def declare_entries(path, count):
    """Make the end record declare ``count`` entries (both of its counts)."""
    buf = bytearray(open(path, 'rb').read())
    i = _eocd(buf)
    struct.pack_into('<HH', buf, i + 8, count, count)
    open(path, 'wb').write(bytes(buf))
    return path


def craft_directory(path, records, declared, name=b'show_a/x'):
    """An archive of one empty local entry and ``records`` central records that
    all point at it; the end record declares ``declared`` entries. Written in
    pieces: a hostile directory of tens of MB without a ZipInfo in sight."""
    local = struct.pack('<4sHHHHHIIIHH', b'PK\x03\x04', 20, 0, 0, 0, 0, 0, 0, 0,
                        len(name), 0) + name
    rec = struct.pack('<4sHHHHHHIIIHHHHHII', b'PK\x01\x02', 20, 20, 0, 0, 0, 0, 0, 0, 0,
                      len(name), 0, 0, 0, 0, 0, 0) + name
    with open(path, 'wb') as f:
        f.write(local)
        left = records
        while left:
            k = min(left, 100_000)
            f.write(rec * k)
            left -= k
        size_cd = records * len(rec)
        f.write(struct.pack('<4sHHHHIIH', b'PK\x05\x06', 0, 0, declared & 0xFFFF,
                            declared & 0xFFFF, size_cd, len(local), 0))
    return path


def symlink_info(name):
    info = zipfile.ZipInfo(name, date_time=(2026, 11, 24, 12, 0, 0))
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    return info


# ---------------------------------------------------------------------------
# The library: the destination of every import
# ---------------------------------------------------------------------------

class Disk:
    """What the patched ``shutil.disk_usage`` answers; per path prefix when
    ``by_prefix`` is set (two filesystems)."""

    Usage = collections.namedtuple('usage', 'total used free')

    def __init__(self):
        self.total = 1024 * GIB
        self.free = 1024 * GIB
        self.by_prefix = {}
        self.paths = []

    def __call__(self, path):
        path = os.fspath(path)
        self.paths.append(path)
        for prefix, (total, free) in sorted(self.by_prefix.items(), key=lambda kv: -len(kv[0])):
            if path == prefix or path.startswith(prefix.rstrip('/') + '/'):
                return self.Usage(total, total - free, free)
        return self.Usage(self.total, self.total - self.free, self.free)


@pytest.fixture
def disk(monkeypatch):
    d = Disk()
    monkeypatch.setattr(shutil, 'disk_usage', d)
    return d


@pytest.fixture(autouse=True)
def _fresh_marks():
    p.reset_refresh_marks()
    yield
    p.reset_refresh_marks()


_IDX = struct.Struct('<4sIqqq')


class FakeBuilders:
    """Stand-ins for ffprobe, ffmpeg, audiowaveform, the indexer and the loop
    period, on one ``CuemsDBMedia``: each writes the sidecar a real one would
    (a valid ``.idx`` and ``.period`` included), unless ``(name, what)`` is in
    ``skip``. ``new_hook(name)`` runs before ``new()`` returns (tests use it to
    slow it down or to fail it)."""

    def __init__(self, media):
        self.media = media
        self.skip = set()

    def install(self, mp):
        mp.setattr(self.media, 'get_duration', lambda filename: CTimecode(start_seconds=3.0))
        mp.setattr(self.media, 'create_video_thumbnail', self.thumbnail)
        mp.setattr(self.media, 'create_audio_thubnail', self.thumbnail)
        mp.setattr(self.media, 'create_audio_waveform', self.waveform)
        mp.setattr(self.media, 'create_video_index', self.index)
        mp.setattr(self.media, 'create_loop_period', self.period)

    def _write(self, path, data=b'sidecar'):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def thumbnail(self, filename, duration=None):
        if (filename, 'thumbnail') not in self.skip:
            return self._write(self.media.get_thumbnail_path(filename))

    def waveform(self, filename):
        if (filename, 'waveform') not in self.skip:
            return self._write(self.media.get_waveform_path(filename))

    def index(self, filename):
        if (filename, 'index') not in self.skip:
            path = self.media.get_file_path(filename)
            st = os.stat(path)
            self._write(ms.video_index_path(path),
                        _IDX.pack(b'CXID', 1, st.st_size, st.st_mtime_ns // 1_000_000_000, 100))

    def period(self, filename):
        if (filename, 'period') not in self.skip:
            path = self.media.get_file_path(filename)
            st = os.stat(path)
            ms.write_period(path, ms.Period(num=48000, den=48000, rate=48000, real_frames=None,
                                            fps=None, rule='walk', frames_rule=None, vfr=False,
                                            size=st.st_size, mtime=int(st.st_mtime), ffprobe='fake'))


class FakeProbe:
    """``probe_media`` of the save path: a 3 s file with no picture."""

    def __init__(self):
        self.calls = []
        self.hook = None

    def __call__(self, path, timeout=None):
        self.calls.append(os.path.basename(path))
        if self.hook:
            self.hook(path)
        return m.MediaProbe(duration=CTimecode(start_seconds=3.0), duration_state=m.PROBE_OK,
                            picture_state=m.PROBE_NO_STREAM)


class Env:
    def __init__(self, library, settings, db, builders, probe, zips):
        self.library = library
        self.root = library.root
        self.settings = settings
        self.db = db
        self.media = db.media
        self.project = db.project
        self.builders = builders
        self.probe = probe
        self.zips = zips
        self.media_dir = os.path.join(library.root, 'media')
        self.staging_root = os.path.join(library.root, '.import')
        self.progress = []
        self.lists = []
        self.status_calls = 0

    def stage(self):
        """A fresh ``import-<hex>`` folder, as the session makes one per import."""
        path = os.path.join(self.staging_root, 'import-' + uuid.uuid4().hex)
        os.mkdir(path, 0o700)
        return path

    def zip(self, entries, name='show_a.zip', **kw):
        return write_zip(os.path.join(self.zips, name), entries, **kw)

    def run(self, zip_path, status=None, accept_loaded=False, staging=None):
        imp = _imp()
        words = status if callable(status) else (lambda: status or 'none')

        def ask():
            self.status_calls += 1
            return words()

        return imp.import_archive(
            zip_path, self.db, staging or self.stage(), status=ask, accept_loaded=accept_loaded,
            progress=lambda *a: self.progress.append(a), list_update=self.lists.append)

    def refused(self, zip_path, **kw):
        with pytest.raises(_error_class()) as ei:
            self.run(zip_path, **kw)
        text = str(ei.value)
        assert '\n' not in text, text
        return ei.value, text

    # --- the library as it is now
    def put_media(self, name, data, trash=False, with_md5=True, with_size=True, media_type=None):
        folder = os.path.join(self.root, 'trash', 'media') if trash else self.media_dir
        with open(os.path.join(folder, name), 'wb') as f:
            f.write(data)
        ext = os.path.splitext(name)[1].lower()
        media_type = media_type or ('MOVIE' if ext in MOVIE_EXT else 'IMAGE' if ext in IMAGE_EXT
                                    else 'AUDIO')
        row = Media.create(uuid=str(uuid.uuid4()), name=name, unix_name=name,
                           created=new_datetime(), modified=new_datetime(),
                           duration=None if media_type == 'IMAGE' else TC3,
                           media_type=media_type, in_trash=trash,
                           file_size=len(data) if (with_size and data) else None,
                           file_md5=md5(data) if with_md5 else None)
        return str(row.uuid)

    def add_project(self, unix_name, name, script, dangling=()):
        os.makedirs(os.path.join(self.library.projects_dir, unix_name))
        with open(os.path.join(self.library.projects_dir, unix_name, 'script.xml'), 'wb') as f:
            f.write(script)
        proj = Project.create(uuid=str(uuid.uuid4()), name=name, unix_name=unix_name,
                              created=new_datetime(), modified=new_datetime(), in_trash=False)
        for n in dangling:
            ProjectMedia.create(project=proj, media=None, media_filename=n)
        return str(proj.uuid)

    def state(self):
        """The library state of the acceptance rows: files (path, size, mtime)
        without the staging folder and the database, and the three tables'
        rows, sorted, without the surrogate ``projectmedia.id``."""
        files = []
        for base, dirs, names in os.walk(self.root):
            rel = os.path.relpath(base, self.root)
            if rel == '.import' or rel.startswith('.import' + os.sep) or rel == 'tmp':
                dirs[:] = []
                continue
            for n in names:
                if n.startswith('project-manager.db'):
                    continue
                st = os.lstat(os.path.join(base, n))
                files.append((os.path.normpath(os.path.join(rel, n)), st.st_size, st.st_mtime_ns))
        rows = (sorted(tuple(str(v) for v in r) for r in Project.select().tuples()),
                sorted(tuple(str(v) for v in r) for r in Media.select().tuples()),
                sorted((str(r.project_id), str(r.media_id), r.media_filename)
                       for r in ProjectMedia.select()))
        return sorted(files), rows

    def script_of(self, unix_name):
        return self.project.load_xml(unix_name)

    def links(self, project_uuid):
        """{media_filename: media uuid or None} of a project's rows."""
        return {r.media_filename: (str(r.media_id) if r.media_id else None)
                for r in ProjectMedia.select().where(ProjectMedia.project == project_uuid)}

    def row(self, name):
        return Media.get_or_none(Media.unix_name == name)

    def sha(self, name, trash=False):
        folder = os.path.join(self.root, 'trash', 'media') if trash else self.media_dir
        return hashlib.sha256(open(os.path.join(folder, name), 'rb').read()).hexdigest()


@pytest.fixture
def zips(tmp_path_factory):
    return str(tmp_path_factory.mktemp('zips'))


@pytest.fixture
def env(library, monkeypatch, disk, zips):
    library.connect()
    settings = cli.get_settings()
    settings['library_path'] = library.root
    settings['tmp_path'] = os.path.join(library.root, 'tmp')
    settings['html_root_path'] = os.path.join(library.root, 'www')
    settings['import_folder_name'] = '.import'     # what step 2 adds to get_settings()
    os.makedirs(settings['tmp_path'], exist_ok=True)
    media = m.CuemsDBMedia(settings, database)
    for d in (media.thumbnail_path, media.waveform_path, media.thumbnail_trash_path,
              media.waveform_trash_path, os.path.join(media.media_path, 'indexes')):
        os.makedirs(d, exist_ok=True)
    project = p.CuemsDBProject(settings, database)
    builders = FakeBuilders(media)
    builders.install(monkeypatch)
    monkeypatch.setattr(m, 'probe_dimensions', lambda path: (None, None))
    monkeypatch.setattr(p, 'probe_dimensions', lambda path: (None, None))
    probe = FakeProbe()
    monkeypatch.setattr(p, 'probe_media', probe)
    os.mkdir(os.path.join(library.root, '.import'), 0o700)
    db = types.SimpleNamespace(project=project, media=media)
    return Env(library, settings, db, builders, probe, zips)


def assert_report_shape(report):
    assert set(report) == {'project', 'media', 'sidecars_failed', 'relinked', 'ignored',
                           'warnings'}, report
    assert set(report['project']) == {'uuid', 'name', 'unix_name', 'renamed'}
    assert set(report['media']) == {'added', 'reused', 'renamed', 'missing', 'from_library'}
    json.dumps(report)                                  # it goes on the wire as it is


def comparable(data):
    """A script dict without what an import changes: the project id, the two
    dates and each Media block's id (AC2's comparer)."""
    data = json.loads(json.dumps(data, default=str))
    script = data['CuemsScript']
    for key in ('id', 'created', 'modified'):
        script.pop(key, None)

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get('Media'), dict):
                node['Media'].pop('id', None)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(script)
    return data


def media_ids_in(data):
    """{file_name: Media id} of a script dict."""
    out = {}

    def walk(node):
        if isinstance(node, dict):
            block = node.get('Media')
            if isinstance(block, dict) and block.get('file_name'):
                out[block['file_name']] = str(block.get('id'))
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return out


def export_with_the_export(tmp_root, media=None, top=TOP, name=NAME):
    """A zip made by ``CuemsDBProject.export`` (the export's own code) from a
    separate source library; returns (zip path, the source script dict, the
    source project uuid). The global database is left closed: the caller
    connects its own library again."""
    media = MEDIA if media is None else media
    if not database.is_closed():
        database.close()
    root = str(tmp_root)
    for sub in ('media', 'trash/media', f'projects/{top}', 'trash/projects', 'www/exports', 'tmp'):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    conf = os.path.join(root, 'cuems-exports.conf')
    open(conf, 'w').close()
    database.init(os.path.join(root, 'project-manager.db'))
    database.connect()
    database.create_tables([Project, Media, ProjectMedia], safe=True)
    try:
        settings = cli.get_settings()
        settings.update(library_path=root, tmp_path=os.path.join(root, 'tmp'),
                        html_root_path=os.path.join(root, 'www'), export_conf_path=conf)
        mgr = p.CuemsDBProject(settings, database)
        source_uuid = str(uuid.uuid4())
        with open(os.path.join(root, 'projects', top, 'script.xml'), 'wb') as f:
            f.write(script_bytes(list(media), media, name=name, script_id=source_uuid))
        # the library writes its scripts through save_xml: so does the source
        from cuemsutils.xml.Parsers import CuemsParser
        mgr.save_xml(top, CuemsParser(mgr.load_xml(top)).parse())
        proj = Project.create(uuid=source_uuid, name=name, unix_name=top, description=DESCRIPTION,
                              created=new_datetime(), modified=new_datetime(), in_trash=False)
        for n, data in media.items():
            with open(os.path.join(root, 'media', n), 'wb') as f:
                f.write(data)
            ext = os.path.splitext(n)[1].lower()
            row = Media.create(uuid=media_id(n), name=n, unix_name=n, created=new_datetime(),
                               modified=new_datetime(),
                               duration=None if ext in IMAGE_EXT else TC3,
                               media_type='MOVIE' if ext in MOVIE_EXT else
                               'IMAGE' if ext in IMAGE_EXT else 'AUDIO',
                               in_trash=False, file_size=len(data), file_md5=md5(data))
            ProjectMedia.create(project=proj, media=row, media_filename=n)
        value = mgr.export(source_uuid)
        source = mgr.load_xml(top)
        return os.path.join(root, 'www', value), source, source_uuid
    finally:
        database.close()


# ---------------------------------------------------------------------------
# The kit itself (these pass before step 2: they guard the fixtures above)
# ---------------------------------------------------------------------------

class TestKit:
    def test_kit_scripts_are_valid_for_this_box(self, env):
        from cuemsutils.xml.Parsers import CuemsParser
        from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter
        for data in (script_bytes(), script_bytes([], {}), script_bytes(['i̇.wav'], {}),
                     script_bytes(fade='00:00:00.000'), script_bytes(name='X' * 60)):
            path = os.path.join(env.zips, 'probe.xml')
            open(path, 'wb').write(data)
            parsed = CuemsParser(XmlReaderWriter(schema_name='script', xmlfile=path).read()).parse()
            assert parsed is not None

    def test_kit_hostile_directories_are_what_they_claim(self, env):
        path = env.zip(export_entries() + [(f'{TOP}/noise/{i}', b'') for i in range(9_995)])
        declare_entries(path, 1)
        buf = open(path, 'rb').read()
        i = _eocd(buf)
        assert struct.unpack('<HH', buf[i + 8:i + 12]) == (1, 1)
        with zipfile.ZipFile(path) as z:                  # zipfile believes the records
            assert len(z.infolist()) == 10_001
        big = env.zip(export_entries() + [(f'{TOP}/c/{i}', b'') for i in range(80)],
                      name='big.zip', comment_bytes=60_000)
        buf = open(big, 'rb').read()
        assert struct.unpack('<I', buf[_eocd(buf) + 12:_eocd(buf) + 16])[0] > 4 * 1024 ** 2

    def test_kit_every_hostile_archive_builds(self, env):
        for ident, build, _ in HOSTILE:
            path = build(env)
            assert os.path.getsize(path) > 0, ident
            os.rename(path, os.path.join(env.zips, f'kit-{ident}.zip'))

    def test_kit_the_export_makes_what_the_contract_says(self, env, tmp_path_factory):
        zip_path, source, _ = export_with_the_export(tmp_path_factory.mktemp('source'))
        env.library.connect()
        with zipfile.ZipFile(zip_path) as z:
            names = [i.filename for i in z.infolist()]
            assert all(i.compress_type == zipfile.ZIP_STORED for i in z.infolist())
        assert names == [n for n, _ in export_entries()]
        assert sorted(media_ids_in(source)) == sorted(MEDIA)

    def test_kit_the_released_form_builds(self, env):
        TestReleasedForm()._released(env, MEDIA)

    def test_kit_the_library_helpers(self, env):
        before = env.state()
        env.put_media('clip.mp4', b'abc')
        env.add_project('other', 'Other Show', script_bytes(['clip.mp4'], {}), dangling=('x.wav',))
        assert env.state() != before
        assert env.row('clip.mp4').file_md5 == md5(b'abc')
        other = str(Project.get(Project.unix_name == 'other').uuid)
        assert env.links(other) == {'x.wav': None}
        assert media_ids_in(env.script_of('other')) == {'clip.mp4': media_id('clip.mp4')}
        assert os.path.isdir(env.stage())

    def test_kit_patched_entries_are_detected_by_zipfile(self, env):
        path = patch_zip(env.zip(export_entries()), f'{TOP}/media/still.png', 'damage')
        with zipfile.ZipFile(path) as z, pytest.raises(zipfile.BadZipFile):
            z.read(f'{TOP}/media/still.png')
        path = patch_zip(env.zip(export_entries(), name='e.zip'), f'{TOP}/media/clip.mp4', 'encrypt')
        with zipfile.ZipFile(path) as z:
            assert z.getinfo(f'{TOP}/media/clip.mp4').flag_bits & 1


# ---------------------------------------------------------------------------
# (1) the round trip of an archive made by the export's own code
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_1_round_trip_of_the_exports_own_zip(self, env, tmp_path_factory):
        zip_path, source, source_uuid = export_with_the_export(tmp_path_factory.mktemp('source'))
        env.library.connect()
        before = new_datetime()
        report = env.run(zip_path)

        assert_report_shape(report)
        assert sorted(report['media']['added']) == sorted(MEDIA)
        for key in ('reused', 'renamed', 'missing', 'from_library'):
            assert report['media'][key] == [], key
        assert report['sidecars_failed'] == [] and report['relinked'] == []
        assert set(report['ignored']) <= {f'{TOP}/', f'{TOP}/media/'}
        assert report['project']['unix_name'] == TOP and report['project']['name'] == NAME
        assert report['project']['renamed'] is False

        # the project row: a new uuid, the source's names, the dates of now
        proj = Project.get(Project.unix_name == TOP)
        assert str(proj.uuid) == report['project']['uuid'] != source_uuid
        assert (proj.name, proj.description, proj.in_trash) == (NAME, DESCRIPTION, False)
        assert str(proj.created) >= before and str(proj.modified) >= str(proj.created)

        # the script: equal but for the id, the dates and each Media id
        got = env.script_of(TOP)
        assert str(got['CuemsScript']['id']) == str(proj.uuid)
        assert comparable(got) == comparable(source)

        # every media file: same bytes, a row of its own, its sidecars
        ids = media_ids_in(got)
        for n, data in MEDIA.items():
            assert open(os.path.join(env.media_dir, n), 'rb').read() == data, n
            row = env.row(n)
            assert row is not None and not row.in_trash
            assert (row.file_size, row.file_md5) == (len(data), md5(data))
            assert ids[n] == str(row.uuid)                    # D10: Media id = the row's uuid
            assert os.path.exists(env.media.get_thumbnail_path(n)), n
        assert os.path.exists(env.media.get_waveform_path('cançó.wav'))
        assert ms.video_index_state(os.path.join(env.media_dir, 'clip.mp4')) == ms.INDEX_VALID
        for n in ('clip.mp4', 'cançó.wav'):
            assert ms.read_period(os.path.join(env.media_dir, n)) is not None, n
        assert env.links(str(proj.uuid)) == {n: str(env.row(n).uuid) for n in MEDIA}

        # the other sessions are told; progress was reported
        assert 'file_list' in env.lists and 'project_list' in env.lists
        phases = {a[0] for a in env.progress}
        assert phases <= {'check', 'media', 'project'} and 'media' in phases
        assert any(a[0] == 'media' and a[2] == len(MEDIA) for a in env.progress)

    def test_1_the_engine_is_asked_before_each_file_and_before_the_project(self, env, monkeypatch):
        events = []
        real_new = env.media.new
        monkeypatch.setattr(env.media, 'new',
                            lambda *a, **kw: (events.append('new'), real_new(*a, **kw))[1])
        real_ip = env.project.import_project
        monkeypatch.setattr(env.project, 'import_project',
                            lambda *a, **kw: (events.append('project'), real_ip(*a, **kw))[1])
        env.run(env.zip(export_entries()), status=lambda: (events.append('ask'), 'none')[1])
        assert events.count('new') == len(MEDIA) and events.count('project') == 1
        for i, e in enumerate(events):
            if e in ('new', 'project'):
                assert events[i - 1] == 'ask', events     # each write right after a question


# ---------------------------------------------------------------------------
# (2) the released form (0.1.0rc1-8): Deflated, and no media/ without media
# ---------------------------------------------------------------------------

class TestReleasedForm:
    def _released(self, env, media):
        """The released code's own steps: a copy into <tmp>/<unix_name>/, then
        shutil.make_archive (docs/project-archive.md s3)."""
        tmp = os.path.join(env.zips, 'released')
        folder = os.path.join(tmp, TOP)
        os.makedirs(folder)
        with open(os.path.join(folder, 'script.xml'), 'wb') as f:
            f.write(script_bytes(list(media), media))
        if media:
            os.makedirs(os.path.join(folder, 'media'))
            for n, data in media.items():
                with open(os.path.join(folder, 'media', n), 'wb') as f:
                    f.write(data)
        base = shutil.make_archive(os.path.join(env.zips, TOP), 'zip', tmp, TOP)
        with zipfile.ZipFile(base) as z:
            infos = z.infolist()
        assert all(i.compress_type == zipfile.ZIP_DEFLATED for i in infos if not i.is_dir())
        assert (f'{TOP}/media/' in [i.filename for i in infos]) == bool(media)
        return base

    def test_2_released_form_with_media_imports(self, env):
        report = env.run(self._released(env, MEDIA))
        assert sorted(report['media']['added']) == sorted(MEDIA)
        for n, data in MEDIA.items():
            assert open(os.path.join(env.media_dir, n), 'rb').read() == data
        assert Project.get(Project.unix_name == TOP).name == NAME

    def test_2_released_form_without_media_imports(self, env):
        before = sorted(os.listdir(env.media_dir))
        report = env.run(self._released(env, {}))
        assert report['media'] == {'added': [], 'reused': [], 'renamed': [], 'missing': [],
                                   'from_library': []}
        proj = Project.get(Project.unix_name == TOP)
        assert env.links(str(proj.uuid)) == {}
        assert sorted(os.listdir(env.media_dir)) == before


# ---------------------------------------------------------------------------
# (3) reuse, (4) another file under the name, (5) a row with no file_md5
# ---------------------------------------------------------------------------

class TestPerFile:
    def test_3_an_identical_file_is_reused_and_nothing_is_written(self, env):
        uuids = {n: env.put_media(n, data) for n, data in MEDIA.items()}
        before = {n: os.stat(os.path.join(env.media_dir, n)) for n in MEDIA}
        report = env.run(env.zip(export_entries()))
        assert sorted(report['media']['reused']) == sorted(MEDIA)
        assert report['media']['added'] == [] and report['media']['renamed'] == []
        for n in MEDIA:
            st = os.stat(os.path.join(env.media_dir, n))
            assert (st.st_ino, st.st_mtime_ns) == (before[n].st_ino, before[n].st_mtime_ns)
            assert str(env.row(n).uuid) == uuids[n]
        assert sorted(f for f in os.listdir(env.media_dir) if '-0' in f) == []
        ids = media_ids_in(env.script_of(TOP))
        assert ids == {n: uuids[n] for n in MEDIA}
        assert 'file_list' not in env.lists                 # nothing was registered

    def test_3_importing_again_gives_a_second_project_and_reuses_all(self, env):
        path = env.zip(export_entries())
        first = env.run(path)
        files_before = env.state()[0]
        second = env.run(path)
        assert second['project']['unix_name'] == f'{TOP}-001'
        assert second['project']['name'] == f'{NAME} (1)'
        assert second['project']['renamed'] is True
        assert sorted(second['media']['reused']) == sorted(MEDIA)
        assert second['media']['added'] == []
        assert second['project']['uuid'] != first['project']['uuid']
        grown = sorted(set(env.state()[0]) - set(files_before))
        assert [f[0] for f in grown] == [os.path.join('projects', f'{TOP}-001', 'script.xml')]

    def test_4a_other_content_under_the_name_is_registered_as_001(self, env):
        other = os.urandom(1000)
        own_uuid = env.put_media('clip.mp4', other)
        report = env.run(env.zip(export_entries()))
        assert {'from': 'clip.mp4', 'to': 'clip-001.mp4'} in report['media']['renamed']
        assert 'clip-001.mp4' in report['media']['added']
        assert open(os.path.join(env.media_dir, 'clip-001.mp4'), 'rb').read() == MEDIA['clip.mp4']
        # the library's own file keeps its bytes, its row and its uuid
        assert open(os.path.join(env.media_dir, 'clip.mp4'), 'rb').read() == other
        assert str(env.row('clip.mp4').uuid) == own_uuid
        ids = media_ids_in(env.script_of(TOP))
        assert 'clip.mp4' not in ids
        assert ids['clip-001.mp4'] == str(env.row('clip-001.mp4').uuid)
        proj = Project.get(Project.unix_name == TOP)
        assert set(env.links(str(proj.uuid))) == {'clip-001.mp4', 'cançó.wav', 'still.png'}

    def test_4b_a_name_only_in_the_trash_is_not_taken_back(self, env):
        trashed = os.urandom(800)
        own_uuid = env.put_media('clip.mp4', trashed, trash=True)
        report = env.run(env.zip(export_entries()))
        assert {'from': 'clip.mp4', 'to': 'clip-001.mp4'} in report['media']['renamed']
        assert env.row('clip.mp4').in_trash is True and str(env.row('clip.mp4').uuid) == own_uuid
        assert env.sha('clip.mp4', trash=True) == hashlib.sha256(trashed).hexdigest()
        assert not os.path.exists(os.path.join(env.media_dir, 'clip.mp4'))
        assert 'clip-001.mp4' in media_ids_in(env.script_of(TOP))

    def test_4c_the_same_archive_again_reuses_the_001_and_makes_no_002(self, env):
        env.put_media('clip.mp4', os.urandom(1000))
        path = env.zip(export_entries())
        env.run(path)
        report = env.run(path)
        assert 'clip-001.mp4' in report['media']['reused']
        assert {'from': 'clip.mp4', 'to': 'clip-001.mp4'} in report['media']['renamed']
        assert not os.path.exists(os.path.join(env.media_dir, 'clip-002.mp4'))
        assert env.row('clip-002.mp4') is None
        assert 'clip-001.mp4' in media_ids_in(env.script_of(f'{TOP}-001'))

    def test_5_a_row_with_no_md5_is_compared_by_hashing_its_file(self, env):
        uuid_ = env.put_media('clip.mp4', MEDIA['clip.mp4'], with_md5=False, with_size=False)
        st = os.stat(os.path.join(env.media_dir, 'clip.mp4'))
        report = env.run(env.zip(export_entries()))
        assert 'clip.mp4' in report['media']['reused']
        st2 = os.stat(os.path.join(env.media_dir, 'clip.mp4'))
        assert (st2.st_ino, st2.st_mtime_ns) == (st.st_ino, st.st_mtime_ns)   # read only
        assert str(env.row('clip.mp4').uuid) == uuid_
        assert not os.path.exists(os.path.join(env.media_dir, 'clip-001.mp4'))

    def test_5_a_row_with_no_md5_and_other_bytes_is_not_reused(self, env):
        env.put_media('clip.mp4', os.urandom(len(MEDIA['clip.mp4'])), with_md5=False)
        report = env.run(env.zip(export_entries()))
        assert {'from': 'clip.mp4', 'to': 'clip-001.mp4'} in report['media']['renamed']


# ---------------------------------------------------------------------------
# (6) missing everywhere, (7) missing in the archive, present in the library
# ---------------------------------------------------------------------------

class TestMissing:
    def test_6_a_missing_file_is_imported_as_a_row_with_no_media_and_healed_by_an_upload(self, env):
        names = list(MEDIA) + ['lost.wav']
        script = script_bytes(names, MEDIA)                  # lost.wav: named, not carried
        report = env.run(env.zip(export_entries(script=script)))
        assert report['media']['missing'] == ['lost.wav']
        assert sorted(report['media']['added']) == sorted(MEDIA)
        proj_uuid = report['project']['uuid']
        assert env.links(proj_uuid)['lost.wav'] is None
        assert media_ids_in(env.script_of(TOP))['lost.wav'] == media_id('lost.wav')  # kept

        # the heal: an upload of that name, through the upload's own relink
        from cuemseditor.CuemsUpload import CuemsUpload
        data = os.urandom(3000)
        tmp = os.path.join(env.settings['tmp_path'], 'lost.wav.tmp1')
        open(tmp, 'wb').write(data)
        dest = env.media.new(tmp, 'lost.wav', md5(data))
        assert dest == 'lost.wav'
        upload = object.__new__(CuemsUpload)
        upload.server = types.SimpleNamespace(db=env.db)
        upload.check_if_media_existed(dest)
        assert env.links(proj_uuid)['lost.wav'] == str(env.row('lost.wav').uuid)

    def test_7_missing_in_the_archive_but_in_the_library_is_linked_and_flagged(self, env):
        names = list(MEDIA) + ['pic.png']                    # pic.png: the library fixture's
        script = script_bytes(names, MEDIA)
        report = env.run(env.zip(export_entries(script=script)))
        assert report['media']['from_library'] == ['pic.png']
        assert report['media']['missing'] == []
        pic = env.row('pic.png')
        assert env.links(report['project']['uuid'])['pic.png'] == str(pic.uuid)
        assert media_ids_in(env.script_of(TOP))['pic.png'] == str(pic.uuid)


# ---------------------------------------------------------------------------
# (8) the name pair (D10), through import_project
# ---------------------------------------------------------------------------

def _data(name=NAME):
    """A script dict with no media, as the import hands it to import_project."""
    from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter
    import tempfile
    fd, path = tempfile.mkstemp(suffix='.xml')
    with os.fdopen(fd, 'wb') as f:
        f.write(script_bytes([], {}, name=name))
    try:
        return XmlReaderWriter(schema_name='script', xmlfile=path).read()
    finally:
        os.remove(path)


class TestNamePair:
    @pytest.mark.parametrize('setup, unix_name, name, want', [
        ('free', 'show_a', 'Show A', ('show_a', 'Show A')),
        ('live', 'proj1', 'Proj One', ('proj1-001', 'Proj One (1)')),
        ('live', 'proj1', 'Another Name', ('proj1-001', 'Another Name (1)')),
        ('live', 'other_dir', 'Proj One', ('other_dir-001', 'Proj One (1)')),
        ('trash', 'old', 'Old Show', ('old-001', 'Old Show (1)')),
        ('folder', 'ghost', 'Ghost', ('ghost-001', 'Ghost (1)')),
        ('free', 'long', 'X' * 60, ('long', 'X' * 60)),
        ('long', 'long', 'X' * 60, ('long-001', 'X' * 56 + ' (1)')),
    ])
    def test_8_the_name_pair(self, env, setup, unix_name, name, want):
        if setup == 'trash':
            Project.create(uuid=str(uuid.uuid4()), name='Old Show', unix_name='old',
                           created=new_datetime(), modified=new_datetime(), in_trash=True)
        elif setup == 'folder':
            os.makedirs(os.path.join(env.library.projects_dir, 'ghost'))
        elif setup == 'long':
            Project.create(uuid=str(uuid.uuid4()), name='X' * 60, unix_name='long',
                           created=new_datetime(), modified=new_datetime(), in_trash=False)
        data = _data(name)
        before = new_datetime()
        got_uuid, got_unix, got_name = env.project.import_project(data, unix_name, name)
        assert (got_unix, got_name) == want
        assert len(got_name) <= 60
        proj = Project.get(Project.uuid == got_uuid)
        assert (proj.unix_name, proj.name) == want
        assert got_uuid != SCRIPT_ID
        assert str(proj.created) >= before and str(proj.modified) >= str(proj.created)
        script = env.script_of(got_unix)                     # valid for the schema: it read back
        assert str(script['CuemsScript']['id']) == got_uuid
        assert script['CuemsScript']['name'] == got_name

    def test_8_add_media_relations_accepts_a_missing_file_only_when_asked(self, env):
        from cuemsutils.xml.Parsers import CuemsParser
        from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter
        path = os.path.join(env.zips, 'm.xml')
        open(path, 'wb').write(script_bytes(['nowhere.wav'], {}))
        obj = CuemsParser(XmlReaderWriter(schema_name='script', xmlfile=path).read()).parse()
        proj = Project.get(Project.unix_name == 'proj1')
        with pytest.raises(Exception):
            env.project.add_media_relations(proj, obj)                 # as today
        env.project.add_media_relations(proj, obj, allow_missing=True)
        assert env.links(str(proj.uuid))['nowhere.wav'] is None


# ---------------------------------------------------------------------------
# (9) archives that are not what Export makes, (10) the script
# ---------------------------------------------------------------------------

def _base(media=None, top=TOP):
    return export_entries(top=top, media=media)


def _one(name, data=b'x' * 4000):
    """An archive whose script names one file ``name``, carried as given."""
    return export_entries(script=script_bytes([name], {name: data}), media={name: data})


def _names(*names):
    """An archive whose script names each of ``names``, each carried with bytes of its own."""
    media = {n: os.urandom(3000) for n in names}
    return export_entries(script=script_bytes(names, media), media=media)


#: (id, build(env) -> zip path, needle that the reason must contain, or None)
HOSTILE = [
    ('dotdot', lambda e: e.zip(_base() + [(f'{TOP}/media/../../evil.mp4', b'x')]), 'evil.mp4'),
    ('absolute', lambda e: e.zip(_base() + [('/abs.mp4', b'x')]), 'abs.mp4'),
    ('backslash', lambda e: e.zip(_base() + [(f'{TOP}\\media\\x.mp4', b'x')]), 'x.mp4'),
    ('symlink', lambda e: e.zip(
        [x for x in _base() if x[0] != f'{TOP}/media/clip.mp4']
        + [(symlink_info(f'{TOP}/media/clip.mp4'), b'/etc/passwd')]), 'clip.mp4'),
    ('encrypted', lambda e: patch_zip(e.zip(_base()), f'{TOP}/media/clip.mp4', 'encrypt'),
     'clip.mp4'),
    ('method_bzip2', lambda e: e.zip(
        [x for x in _base() if x[0] != f'{TOP}/media/clip.mp4']
        + [(_info(f'{TOP}/media/clip.mp4', zipfile.ZIP_BZIP2), MEDIA['clip.mp4'])]), 'clip.mp4'),
    ('used_media_twice', lambda e: e.zip(_base() + [(f'{TOP}/media/clip.mp4', MEDIA['clip.mp4'])]),
     'clip.mp4'),
    ('script_twice', lambda e: e.zip(_base() + [(f'{TOP}/script.xml', script_bytes())]),
     'script.xml'),
    ('two_top_folders', lambda e: e.zip(_base() + [('other/readme.txt', b'hello')]), None),
    ('no_top_folder', lambda e: e.zip([('script.xml', script_bytes())]
                                      + [(f'media/{n}', b) for n, b in MEDIA.items()]), None),
    ('top_the_sanitiser_changes', lambda e: e.zip(_base(top='Show A')), 'Show A'),
    ('no_script', lambda e: e.zip([x for x in _base() if not x[0].endswith('script.xml')]), None),
    # Ion, 2026-11-25: a capital is not refused, the sanitiser names it (TestSanitisedNames);
    # what is refused is two used names that become one, or a name that becomes nothing.
    ('media_names_that_sanitise_to_one', lambda e: e.zip(_names('A.wav', 'a.wav')),
     "'A.wav' and 'a.wav'"),
    # The sanitiser drops every '?' and keeps nothing; '€' goes and '.' stays (read on .111).
    ('media_name_that_sanitises_to_empty', lambda e: e.zip(_one('???')),
     "'???' is refused (empty once sanitised)"),
    ('media_name_that_sanitises_to_a_dot', lambda e: e.zip(_one('€.')),
     "'€.' is refused ('.' or '..' once sanitised)"),
    ('media_name_tab', lambda e: e.zip(_one('a\tb.mp4')), None),
    ('media_name_slash', lambda e: e.zip(_one('sub/clip.mp4')), 'sub/clip.mp4'),
    ('media_name_backslash', lambda e: e.zip(_one('a\\b.mp4')), None),
    ('media_name_256_bytes', lambda e: e.zip(_one('a' * 252 + '.mp4')), None),
    ('media_name_256_bytes_in_utf8', lambda e: e.zip(_one('ç' * 126 + '.mp4')), None),
    ('named_file_without_a_media_type', lambda e: e.zip(_one('notes.txt')), 'notes.txt'),
    ('more_entries_than_the_cap', lambda e: e.zip(
        _base() + [(f'{TOP}/noise/{i}', b'') for i in range(10_001 - 6)]), None),
    ('more_entries_than_the_cap_declared_1', lambda e: declare_entries(e.zip(
        _base() + [(f'{TOP}/noise/{i}', b'') for i in range(10_001 - 6)]), 1), None),
    ('directory_above_the_byte_bound', lambda e: e.zip(
        _base() + [(f'{TOP}/c/{i}', b'') for i in range(80)], comment_bytes=60_000), None),
    ('damaged_last_entry', lambda e: patch_zip(e.zip(_base()), f'{TOP}/media/still.png', 'damage'),
     'still.png'),
    ('sizes_add_up_to_more_than_the_zip',
     lambda e: patch_zip(e.zip(_base()), f'{TOP}/media/clip.mp4', 'oversize'), None),
    ('script_with_an_entity', lambda e: e.zip(export_entries(script=script_bytes().replace(
        b"<?xml version='1.0' encoding='utf-8'?>\n",
        b"<?xml version='1.0' encoding='utf-8'?>\n<!DOCTYPE x [<!ENTITY a \"Show\">]>\n").replace(
        b'<name>Show A</name>', b'<name>&a; A</name>'))), None),
]


def _info(name, compression):
    info = zipfile.ZipInfo(name, date_time=(2026, 11, 24, 12, 0, 0))
    info.compress_type = compression
    return info


class TestHostileArchives:
    @pytest.mark.parametrize('build, needle', [(b, n) for _, b, n in HOSTILE],
                             ids=[i for i, _, _ in HOSTILE])
    def test_9_refused_with_its_reason_and_the_library_unchanged(self, env, build, needle):
        path = build(env)
        before = env.state()
        error, text = env.refused(path)
        assert text.startswith(I8A) and len(text) > len(I8A), text
        if needle:
            assert needle in text, text
        assert env.state() == before
        assert env.lists == []                                    # nothing was registered

    @pytest.mark.parametrize('rows, declared', [
        ('directory_above_the_byte_bound', None),
        ('more_entries_than_the_cap_declared_1', 1),
    ])
    def test_9_the_directory_is_refused_before_any_zipinfo_is_built(self, env, monkeypatch, rows,
                                                                     declared):
        build = {i: b for i, b, _ in HOSTILE}[rows]
        path = build(env)
        built = []
        real = zipfile.ZipInfo.__init__

        def counting(self, *a, **kw):
            built.append(1)
            return real(self, *a, **kw)

        monkeypatch.setattr(zipfile.ZipInfo, '__init__', counting)
        error, text = env.refused(path)
        assert text.startswith(I8A)
        assert built == []

    def test_9_a_hostile_directory_is_refused_under_an_address_space_limit(self, env):
        """Two million records whose end record declares one: zipfile itself
        would build two million ZipInfo objects (hundreds of MB). In a child
        process whose address space is limited to what it uses plus 256 MiB,
        ``open_archive`` must refuse it with I8a, not die of MemoryError."""
        path = craft_directory(os.path.join(env.zips, 'hostile.zip'), 2_000_000, 1)
        code = r'''
import json, resource, sys
import cuemseditor.CuemsProjectImport as imp
from cuemseditor.CuemsErrors import ProjectImportError
vm = [l for l in open('/proc/self/status') if l.startswith('VmSize:')][0].split()[1]
limit = int(vm) * 1024 + 256 * 1024 ** 2
resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
try:
    imp.open_archive(sys.argv[1])
    print(json.dumps({'error': None}))
except ProjectImportError as e:
    print(json.dumps({'error': 'ProjectImportError', 'text': str(e)}))
except MemoryError:
    print(json.dumps({'error': 'MemoryError'}))
'''
        env_vars = dict(os.environ, PYTHONPATH=os.pathsep.join(p for p in sys.path if p))
        run = subprocess.run([sys.executable, '-c', code, path], capture_output=True, text=True,
                             env=env_vars, timeout=120)
        assert run.returncode == 0, run.stderr[-2000:]
        result = json.loads(run.stdout.strip().splitlines()[-1])
        assert result['error'] == 'ProjectImportError', result
        assert result['text'].startswith(I8A), result

    @pytest.mark.parametrize('name', ['cançó.wav', 'i̇.wav'])
    def test_9_accented_and_combining_names_are_accepted(self, env, name):
        data = os.urandom(2000)
        report = env.run(env.zip(_one(name, data)))
        assert report['media']['added'] == [name]
        assert open(os.path.join(env.media_dir, name), 'rb').read() == data
        assert env.row(name) is not None
        assert name in media_ids_in(env.script_of(TOP))

    def test_9_noise_and_unknown_entries_are_ignored_and_listed(self, env):
        noise = [('__MACOSX/', None), (f'__MACOSX/{TOP}/._clip.mp4', b'mac'), ('.DS_Store', b'ds'),
                 (f'{TOP}/.DS_Store', b'ds'), (f'{TOP}/media/Thumbs.db', b'th'),
                 (f'{TOP}/manifest.json', b'{"v": 2}'), (f'{TOP}/media/unused.wav', b'u')]
        report = env.run(env.zip(_base() + noise))
        assert sorted(report['media']['added']) == sorted(MEDIA)
        assert {n for n, d in noise if d is not None} <= set(report['ignored'])
        assert env.row('unused.wav') is None
        assert not os.path.exists(os.path.join(env.media_dir, 'unused.wav'))


#: (name in the archive, the name the library holds): what the upload's sanitiser
#: makes of it, read on .111 (``İ`` lowers to ``i`` + the combining dot U+0307).
SANITISED = [('İ.wav', 'i\u0307.wav'), ('Clip.MP4', 'clip.mp4')]


class TestSanitisedNames:
    """(9) Ion, 2026-11-25 (D7): a used media name that
    ``StringSanitizer.sanitize_file_name`` changes is accepted, as the upload
    accepts it (``CuemsUpload.py:129``): registered under the sanitised name,
    reported as a rename like D8's, the script following. ``new()`` does not
    sanitise, so the importer must: nothing with a capital reaches ``media/``.
    Two used names that sanitise to one, or a name that sanitises to nothing,
    are refused (HOSTILE)."""

    @pytest.mark.parametrize('name, lib', SANITISED, ids=['dotted_capital_i', 'capital_clip'])
    def test_9_a_name_the_sanitiser_changes_is_added_under_the_sanitised_name(self, env, name,
                                                                               lib):
        data = os.urandom(2000)
        report = env.run(env.zip(_one(name, data)))
        assert report['media']['added'] == [lib]
        assert report['media']['renamed'] == [{'from': name, 'to': lib}]
        assert open(os.path.join(env.media_dir, lib), 'rb').read() == data
        assert not os.path.exists(os.path.join(env.media_dir, name))
        assert [n for n in os.listdir(env.media_dir) if n != n.lower()] == []
        row = env.row(lib)
        assert row is not None
        ids = media_ids_in(env.script_of(TOP))
        assert name not in ids and ids[lib] == str(row.uuid)        # file_name and id remapped
        assert env.links(report['project']['uuid']) == {lib: str(row.uuid)}

    def test_9_the_same_archive_again_reuses_the_sanitised_file(self, env):
        data = os.urandom(2000)
        path = env.zip(_one('Clip.MP4', data))
        env.run(path)
        report = env.run(path)
        assert report['media']['added'] == []
        assert report['media']['reused'] == ['clip.mp4']
        assert report['media']['renamed'] == [{'from': 'Clip.MP4', 'to': 'clip.mp4'}]
        assert not os.path.exists(os.path.join(env.media_dir, 'clip-001.mp4'))

    def test_9_the_sanitised_name_taken_by_another_file_goes_on_to_001(self, env):
        env.put_media('clip.mp4', os.urandom(1500))
        data = os.urandom(2000)
        report = env.run(env.zip(_one('Clip.MP4', data)))
        assert report['media']['added'] == ['clip-001.mp4']
        assert report['media']['renamed'] == [{'from': 'Clip.MP4', 'to': 'clip-001.mp4'}]
        assert open(os.path.join(env.media_dir, 'clip-001.mp4'), 'rb').read() == data
        ids = media_ids_in(env.script_of(TOP))
        assert ids == {'clip-001.mp4': str(env.row('clip-001.mp4').uuid)}

    def test_9_a_missing_name_is_remapped_to_the_name_an_upload_would_give_it(self, env):
        names = list(MEDIA) + ['Lost.WAV']                   # named, not carried
        report = env.run(env.zip(export_entries(script=script_bytes(names, MEDIA))))
        assert report['media']['missing'] == ['lost.wav']
        assert report['media']['renamed'] == [{'from': 'Lost.WAV', 'to': 'lost.wav'}]
        links = env.links(report['project']['uuid'])
        assert 'Lost.WAV' not in links and links['lost.wav'] is None
        ids = media_ids_in(env.script_of(TOP))
        assert 'Lost.WAV' not in ids and ids['lost.wav'] == media_id('Lost.WAV')  # its id kept

    def test_9_a_name_new_makes_keeps_its_hyphen(self, env):
        """``<base>-NNN<ext>`` is a library name (``new()`` makes it, N2) that the
        sanitiser would change, ``-`` to ``_``: an archive of that library carries
        it and it is imported as it is, so a second import can reuse it."""
        data = os.urandom(2000)
        report = env.run(env.zip(_one('clip-001.mp4', data)))
        assert report['media']['added'] == ['clip-001.mp4']
        assert report['media']['renamed'] == []
        assert not os.path.exists(os.path.join(env.media_dir, 'clip_001.mp4'))


class TestTheScript:
    def test_10_a_script_with_an_entity_is_refused(self, env):
        build = {i: b for i, b, _ in HOSTILE}['script_with_an_entity']
        before = env.state()
        error, text = env.refused(build(env))
        assert text.startswith(I8A)
        assert env.state() == before

    def test_10_a_script_above_the_cap_is_refused(self, env, monkeypatch):
        imp = _imp()
        monkeypatch.setattr(imp, 'MAX_SCRIPT_BYTES', 20_000)
        script = script_bytes() + b'<!--' + b'x' * 20_000 + b'-->'
        before = env.state()
        error, text = env.refused(env.zip(export_entries(script=script)))
        assert text.startswith(I8A)
        assert env.state() == before

    def test_10_the_cap_is_64_mib_and_the_directory_caps_are_the_plans(self):
        imp = _imp()
        assert imp.MAX_SCRIPT_BYTES == 64 * 1024 ** 2
        assert imp.MAX_DIRECTORY_BYTES == 4 * 1024 ** 2
        assert imp.MAX_ENTRIES == 10_000

    def test_10_a_script_the_schema_refuses_names_the_version(self, env):
        script = script_bytes().replace(b'<master_vol>66</master_vol>',
                                        b'<master_vol>66</master_vol><bogus>1</bogus>')
        before = env.state()
        error, text = env.refused(env.zip(export_entries(script=script)))
        assert text.startswith(I8B_HEAD()), text
        assert text.endswith(I8B_TAIL), text
        assert 'bogus' in text
        assert env.state() == before

    def test_10_a_valid_script_is_read_through_the_defused_resource(self, env, monkeypatch):
        import xmlschema
        seen = []
        real = xmlschema.XMLResource.__init__

        def spy(self, source, *a, **kw):
            where = (os.fspath(source) if isinstance(source, (str, os.PathLike))
                     else getattr(source, 'name', None))       # a path, or an open file
            seen.append((where if isinstance(where, str) else None,
                         kw.get('defuse', a[2] if len(a) > 2 else 'remote')))
            return real(self, source, *a, **kw)

        monkeypatch.setattr(xmlschema.XMLResource, '__init__', spy)
        staging = env.stage()
        env.run(env.zip(export_entries()), staging=staging)
        staged = [d for s, d in seen if s and s.startswith(staging)]
        assert staged and set(staged) == {'always'}, seen


# ---------------------------------------------------------------------------
# (11) the save gates are not applied: warned instead
# ---------------------------------------------------------------------------

class TestGates:
    def test_11_a_zero_fade_and_a_media_cue_with_no_block_are_imported_and_warned(self, env):
        no_block = (f'<AudioCue>{_common(NOMEDIA_ID)}<Media /><outputs />'
                    f'<master_vol>66</master_vol></AudioCue>')
        script = script_bytes(fade='00:00:00.000', extra_cues=no_block)
        report = env.run(env.zip(export_entries(script=script)))
        warnings_text = ' | '.join(report['warnings'])
        assert FADE_ID in warnings_text
        assert NOMEDIA_ID in warnings_text
        got = env.script_of(TOP)
        fades = [c['FadeCue'] for c in got['CuemsScript']['CueList']['contents'] if 'FadeCue' in c]
        assert len(fades) == 1                              # kept as it was
        assert '00:00:00.000' in str(fades[0]['duration'])


# ---------------------------------------------------------------------------
# (12) a dangling row of another project is relinked first (N1)
# ---------------------------------------------------------------------------

class TestRelink:
    def test_12_another_projects_dangling_row_is_relinked_and_our_rows_are_right(self, env):
        old_id = str(uuid.uuid4())                           # what Other's script holds
        other_script = script_bytes(['clip.mp4'], {}, name='Other Show',
                                    script_id=str(uuid.uuid4()), ids={'clip.mp4': old_id})
        other = env.add_project('other', 'Other Show', other_script, dangling=('clip.mp4',))
        report = env.run(env.zip(export_entries()))
        row = env.row('clip.mp4')
        assert str(row.uuid) == old_id                       # the upload's relink rewrote it
        assert env.links(other)['clip.mp4'] == old_id
        assert env.links(report['project']['uuid'])['clip.mp4'] == old_id
        assert media_ids_in(env.script_of(TOP))['clip.mp4'] == old_id
        assert report['relinked'] == [{'project': 'Other Show', 'name': 'clip.mp4'}]
        assert 'project_list' in env.lists


# ---------------------------------------------------------------------------
# (13) a failure: what D12 leaves, and the retry
# ---------------------------------------------------------------------------

class Killed(BaseException):
    """A kill between the move into media/ and the row: no ``except
    Exception`` catches it, as no handler survives a SIGKILL."""


class TestFailures:
    def test_13_a_failure_at_the_second_file(self, env, monkeypatch):
        real = env.media.new
        calls = []

        def new(*a, **kw):
            calls.append(a[1] if len(a) > 1 else kw['filename'])
            if len(calls) == 2:
                raise RuntimeError('disk error')
            return real(*a, **kw)

        monkeypatch.setattr(env.media, 'new', new)
        path = env.zip(export_entries())
        error, text = env.refused(path)
        reason, added = i9_parts(text)
        assert 'disk error' in reason
        assert added == [calls[0]]
        assert error.report is not None and error.report['media']['added'] == [calls[0]]
        assert env.row(calls[0]) is not None                 # an import only adds
        assert env.row(calls[1]) is None
        assert Project.get_or_none(Project.unix_name == TOP) is None
        assert 'file_list' in env.lists                      # the failure path tells too

        monkeypatch.setattr(env.media, 'new', real)
        env.lists.clear()
        report = env.run(path)
        assert calls[0] in report['media']['reused']
        assert sorted(report['media']['added']) == sorted(set(MEDIA) - {calls[0]})
        assert Project.get(Project.unix_name == TOP)

    def test_13_a_failure_at_the_creation_of_the_project(self, env, monkeypatch):
        real = env.project.import_project
        failing = [True]

        def import_project(*a, **kw):
            if failing[0]:
                raise RuntimeError('cannot create')
            return real(*a, **kw)

        monkeypatch.setattr(env.project, 'import_project', import_project)
        path = env.zip(export_entries())
        error, text = env.refused(path)
        reason, added = i9_parts(text)
        assert 'cannot create' in reason and sorted(added) == sorted(MEDIA)
        assert Project.get_or_none(Project.unix_name == TOP) is None
        assert not os.path.exists(os.path.join(env.library.projects_dir, TOP))
        assert all(env.row(n) for n in MEDIA)
        assert 'file_list' in env.lists

        failing[0] = False
        report = env.run(path)
        assert sorted(report['media']['reused']) == sorted(MEDIA)
        assert Project.get(Project.unix_name == TOP)

    def test_13_a_stop_between_the_move_and_the_row_leaves_a_file_the_retry_stores_as_001(
            self, env, monkeypatch):
        real_create = Media.create.__func__
        armed = [True]

        def create(cls, **kw):
            if armed[0] and kw.get('unix_name') == 'clip.mp4':
                raise Killed()
            return real_create(cls, **kw)

        monkeypatch.setattr(Media, 'create', classmethod(create))
        path = env.zip(export_entries())
        with pytest.raises(Killed):
            env.run(path)
        assert os.path.exists(os.path.join(env.media_dir, 'clip.mp4'))   # moved, no row
        assert env.row('clip.mp4') is None

        armed[0] = False
        report = env.run(path)
        assert {'from': 'clip.mp4', 'to': 'clip-001.mp4'} in report['media']['renamed']
        assert 'clip-001.mp4' in report['media']['added']
        assert open(os.path.join(env.media_dir, 'clip-001.mp4'), 'rb').read() == MEDIA['clip.mp4']
        assert env.row('clip.mp4') is None                   # the file with no row stays as it is
        assert 'clip-001.mp4' in media_ids_in(env.script_of(TOP))


# ---------------------------------------------------------------------------
# (14) the space rule (D6), after the checks; the guard's is in test_import_ws
# ---------------------------------------------------------------------------

class TestSpace:
    def _need(self, names=None):
        return sum(len(MEDIA[n]) for n in (names or MEDIA))

    @pytest.mark.parametrize('total_gib, reserve_gib', [(20, 5), (200, 20)])
    def test_14_one_filesystem_the_reserve_at_its_edges(self, env, disk, total_gib, reserve_gib):
        path = env.zip(export_entries())
        disk.total = total_gib * GIB
        reserve = reserve_gib * GIB
        disk.free = self._need() + reserve - 1
        before = env.state()
        error, text = env.refused(path)
        assert text == I2(self._need(), disk.free, env.media_dir, reserve)
        assert env.state() == before
        disk.free = self._need() + reserve + len(script_bytes())
        env.run(path)
        assert env.media_dir in disk.paths

    def test_14_only_the_files_to_add_count(self, env, disk):
        for n, data in MEDIA.items():
            env.put_media(n, data)
        disk.total = 20 * GIB
        disk.free = 5 * GIB + 64 * 1024                      # the reserve and a script's room
        report = env.run(env.zip(export_entries()))
        assert sorted(report['media']['reused']) == sorted(MEDIA)

    def test_14_two_filesystems_the_library_one_decides_and_files_are_copied(
            self, env, disk, monkeypatch):
        staging = env.stage()
        disk.by_prefix[env.staging_root] = (100 * GIB, 100 * GIB)
        disk.by_prefix[env.root] = (20 * GIB, self._need() + 5 * GIB - 1)
        path = env.zip(export_entries())
        before = env.state()
        error, text = env.refused(path, staging=staging)
        assert text == I2(self._need(), self._need() + 5 * GIB - 1, env.media_dir, 5 * GIB)
        assert env.state() == before

        disk.by_prefix[env.root] = (20 * GIB, 20 * GIB)
        real_rename = os.rename
        crossed = []

        def rename(src, dst, *a, **kw):
            if os.fspath(src).startswith(env.staging_root) and not os.fspath(dst).startswith(
                    env.staging_root):
                crossed.append(dst)
                raise OSError(18, 'Invalid cross-device link')
            return real_rename(src, dst, *a, **kw)

        monkeypatch.setattr(os, 'rename', rename)
        report = env.run(path)
        assert sorted(report['media']['added']) == sorted(MEDIA)
        assert crossed                                       # a rename was tried and refused
        for n, data in MEDIA.items():
            assert open(os.path.join(env.media_dir, n), 'rb').read() == data


# ---------------------------------------------------------------------------
# (19) the sweep at start
# ---------------------------------------------------------------------------

class TestSweep:
    def _settings(self, tmp_path):
        s = cli.get_settings()
        lib = tmp_path / 'lib'
        lib.mkdir()
        s['library_path'] = str(lib)
        s['tmp_path'] = str(tmp_path / 'tmp-upload')
        s['html_root_path'] = str(tmp_path / 'varlib')
        return s, lib

    def test_19_the_settings_name_the_staging_folder(self):
        assert cli.get_settings()['import_folder_name'] == '.import'

    def test_19_the_folder_is_made_0700(self, tmp_path):
        s, lib = self._settings(tmp_path)
        cli.ensure_directories(s)
        st = os.lstat(lib / '.import')
        assert stat.S_ISDIR(st.st_mode) and stat.S_IMODE(st.st_mode) == 0o700

    def test_19_only_import_hex_children_go_and_each_is_logged(self, tmp_path):
        s, lib = self._settings(tmp_path)
        root = lib / '.import'
        root.mkdir(mode=0o755)
        (root / 'import-0a1b2c').mkdir()
        (root / 'import-0a1b2c' / 'show.zip').write_bytes(b'z' * 100)
        (root / 'import-ff').write_bytes(b'left by a crash')
        for keep in ('import-xyz', 'notes.txt', '.hidden', 'import-', 'Import-00'):
            (root / keep).write_bytes(b'keep')
        with mock.patch.object(cli.Logger, 'info') as info:
            cli.ensure_directories(s)
        assert sorted(os.listdir(root)) == sorted(['import-xyz', 'notes.txt', '.hidden', 'import-',
                                                   'Import-00'])
        assert stat.S_IMODE(os.lstat(root).st_mode) == 0o700
        logged = ' '.join(str(c.args[0]) for c in info.call_args_list)
        assert 'import-0a1b2c' in logged and 'import-ff' in logged

    def test_19_a_symlink_in_place_of_the_folder_is_refused(self, tmp_path):
        s, lib = self._settings(tmp_path)
        target = tmp_path / 'elsewhere'
        target.mkdir()
        (target / 'import-00').mkdir()
        (target / 'import-00' / 'precious').write_bytes(b'keep me')
        os.symlink(target, lib / '.import')
        with mock.patch.object(cli.Logger, 'error') as error:
            cli.ensure_directories(s)                        # the editor still starts
        assert os.path.islink(lib / '.import')
        assert (target / 'import-00' / 'precious').read_bytes() == b'keep me'
        assert any(str(lib / '.import') in str(c.args[0]) for c in error.call_args_list)

    @pytest.mark.skipif(os.geteuid() == 0, reason='root can write to any folder')
    def test_19_an_unwritable_staging_root_is_refused_at_the_guard(self, tmp_path):
        """A staging folder the editor cannot write to (another owner, a wrong
        mode) is refused with a text of its own, not given a ticket (found on
        .111, 2026-11-25: the folder had been made by another user)."""
        import cuemseditor.CuemsProjectImport as imp      # lazy, as every test here
        from cuemseditor.CuemsErrors import ProjectImportError
        s, lib = self._settings(tmp_path)
        root = lib / '.import'
        root.mkdir(mode=0o700)
        os.chmod(root, 0o500)
        try:
            with mock.patch.object(imp.Logger, 'error') as error:
                with pytest.raises(ProjectImportError) as e:
                    imp.ensure_staging_root(s)
            assert 'cannot write to' in str(e.value) and str(root) in str(e.value)
            assert any(str(root) in str(c.args[0]) for c in error.call_args_list)
        finally:
            os.chmod(root, 0o700)

    def test_19_no_link_is_followed(self, tmp_path):
        s, lib = self._settings(tmp_path)
        root = lib / '.import'
        root.mkdir(mode=0o700)
        outside = tmp_path / 'outside'
        outside.mkdir()
        (outside / 'precious').write_bytes(b'keep me')
        os.symlink(outside, root / 'import-0c')              # a child that is a link
        (root / 'import-0d').mkdir()
        os.symlink(outside, root / 'import-0d' / 'inner')    # a link inside a child
        cli.ensure_directories(s)
        assert (outside / 'precious').read_bytes() == b'keep me'
        assert not os.path.lexists(root / 'import-0c')
        assert not os.path.lexists(root / 'import-0d')


# ---------------------------------------------------------------------------
# (20) the name new() picks is one the script names for a missing file
# ---------------------------------------------------------------------------

class TestCollision:
    def test_20_the_001_is_also_named_missing_warned_and_relinked_listed(self, env):
        env.put_media('clip.mp4', os.urandom(1000))           # other content under the name
        other_script = script_bytes(['clip-001.mp4'], {}, name='Other Show',
                                    script_id=str(uuid.uuid4()),
                                    ids={'clip-001.mp4': str(uuid.uuid4())})
        env.add_project('other', 'Other Show', other_script, dangling=('clip-001.mp4',))
        names = list(MEDIA) + ['clip-001.mp4']                # clip-001.mp4: named, not carried
        report = env.run(env.zip(export_entries(script=script_bytes(names, MEDIA))))
        assert {'from': 'clip.mp4', 'to': 'clip-001.mp4'} in report['media']['renamed']
        assert any('clip-001.mp4' in w for w in report['warnings']), report['warnings']
        assert {'project': 'Other Show', 'name': 'clip-001.mp4'} in report['relinked']


# ---------------------------------------------------------------------------
# (21) a sidecar that fails is listed by file
# ---------------------------------------------------------------------------

class TestSidecars:
    def test_21_a_missing_sidecar_is_listed_by_file(self, env):
        env.builders.skip |= {('cançó.wav', 'waveform'), ('clip.mp4', 'index')}
        report = env.run(env.zip(export_entries()))
        got = sorted((s['name'], s['what']) for s in report['sidecars_failed'])
        assert got == [('cançó.wav', 'waveform'), ('clip.mp4', 'index')]
        assert sorted(report['media']['added']) == sorted(MEDIA)   # never a failed import


# ---------------------------------------------------------------------------
# (22) no probe inside the creation transaction (round 2, row 3)
# ---------------------------------------------------------------------------

class TestCreationTransaction:
    def test_22_reused_legacy_media_are_probed_outside_the_transaction_and_both_writes_land(
            self, env):
        for n, data in MEDIA.items():
            env.put_media(n, data, with_size=False)          # legacy: no stored size
        in_txn = []
        other_wrote = []

        def other_session_saves(path):
            in_txn.append(database.in_transaction())
            con = sqlite3.connect(env.library.db_path, timeout=0)   # no wait at all
            try:
                con.execute("UPDATE project SET description = 'saved meanwhile' "
                            "WHERE unix_name = 'proj1'")
                con.commit()
                other_wrote.append(True)
            finally:
                con.close()

        env.probe.hook = other_session_saves
        report = env.run(env.zip(export_entries()))
        assert sorted(report['media']['reused']) == sorted(MEDIA)
        assert env.probe.calls                               # the legacy rows were measured
        assert in_txn and not any(in_txn), in_txn
        assert other_wrote and len(other_wrote) == len(env.probe.calls)
        assert Project.get(Project.unix_name == 'proj1').description == 'saved meanwhile'
        assert Project.get(Project.unix_name == TOP)
        for n, data in MEDIA.items():                        # the values a save fills in
            assert env.row(n).file_size == len(data)
