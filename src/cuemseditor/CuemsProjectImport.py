# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Import of a project archive made by Export (ClickUp 1amfwm7kcjp).

Two parts:

* :func:`import_archive` reads a zip that is already in this import's staging
  folder: it checks the whole archive and its script with no write to the
  library (D7, D11), decides per media file (D8, D9), registers the new files
  through ``CuemsDBMedia.new`` one by one, each followed by the relink of other
  projects (N1), and creates the project (D10). An import only adds (D12):
  on a failure nothing is deleted; the error names what was added and the next
  import reuses it.
* :class:`ImportSession` owns the ``/upload`` socket after a first frame with
  ``type: "PROJECT"`` and a valid ticket (D1): it receives the zip into the
  staging folder, checks its size and MD5 (D2), asks the engine again (D4),
  runs :func:`import_archive` in the executor while a timer of its own sends a
  ``progress`` frame, and answers with the report.

The guard that hands out the ticket is ``CuemsWsUser.request_import_project``;
the one import slot is ``CuemsWsServer.ImportSlot``. Design: cuems-RELATIONS
``Plans/2026-11-24-project-import-from-zip.md`` (Spec rev 3); the archive's
layout: ``docs/project-archive.md``.
"""
import asyncio
import copy
import functools
import hashlib
import json
import os
import shutil
import stat
import struct
import unicodedata
import uuid
import zipfile
import zlib

import websockets as ws
import xmlschema

import cuemsutils
from cuemsutils.log import Logger
from cuemsutils.tools import media_sidecars
from cuemsutils.tools.StringSanitizer import StringSanitizer
from cuemsutils.xml.Parsers import CuemsParser
from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter

from cuemseditor.CuemsErrors import ProjectImportError
from cuemseditor.CuemsDBModel import Media, Project, ProjectMedia
from cuemseditor.CuemsDBMedia import MediaType, is_indexed_video
from cuemseditor.CuemsDBProject import (
    EXPORT_MIN_RESERVE, EXPORT_RESERVE_FRACTION, validate_fade_durations_in_contents,
    validate_media_cues_in_contents)

# --- Caps and timers: module constants, read at call time (tests patch them) --

#: The largest ``script.xml`` read (D7); the largest real one is 45 KB (step 0).
MAX_SCRIPT_BYTES = 64 * 1024 ** 2
#: The zip's directory, in bytes as its end record says, and in records counted
#: one by one: both bounded before ``ZipFile`` builds a ``ZipInfo`` (round 2, row 4).
MAX_DIRECTORY_BYTES = 4 * 1024 ** 2
MAX_ENTRIES = 10_000
#: A ``progress`` frame at least this often while the editor works (review row 7).
HEARTBEAT_S = 5
#: No frame from the browser for this long during the upload: I7.
UPLOAD_STALL_S = 120
#: A ticket not used within this many seconds is void and frees the slot.
TICKET_TTL_S = 60
#: Entries are read and copied in pieces of this size (step 2 (a)).
CHUNK = 1 << 20
#: A later check waits this long for the engine's answer (its own timeout is 25 s).
ENGINE_WAIT_S = 30

_GIB = 1024 ** 3

# --- The texts ("The messages", I1 to I9): one line each --------------------

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


def no_space_text(need, free, folder, reserve):
    """I2, formatted as the export's E2."""
    return (f'No space to import: needs {need / _GIB:.1f} GiB, {free / _GIB:.1f} GiB free '
            f'in {folder}, {reserve / _GIB:.1f} GiB kept in reserve')


def schema_text(reason):
    """I8b: the box's cuems-utils version and the validator's reason."""
    return (f"This project's script is not valid for this controller "
            f"(cuems-utils {cuemsutils.__version__}): {one_line(reason).rstrip('.')}. If the archive "
            f"comes from a newer version, update this controller first")


def interrupted_text(reason, added):
    """I9: the reason (I3, I4, I5 or the failure) and the media already added."""
    names = ', '.join(added) if added else 'none'
    return (f"{I9}{one_line(reason).rstrip('.')}. Nothing that existed was changed; "
            f'media added: {names}')


def one_line(text):
    return ' '.join(str(text).split())


def _refused(reason):
    """I8a, naming the offending entry or media name in *reason*."""
    return ProjectImportError(I8A + one_line(reason))


def import_refusal(status, accept_loaded):
    """The rule of D3, the same at the guard and at every later check (D4):
    the refusal text, or ``None`` when the import may go on.

    ``running`` is refused, also with the acceptance; no usable answer
    (``None``) is refused; ``loaded`` is refused unless *accept_loaded* is the
    JSON ``true`` (``True`` itself, nothing that only looks like it); ``none``
    goes on.
    """
    if status == 'running':
        return I3
    if status not in ('loaded', 'none'):
        return I4
    if status == 'loaded' and accept_loaded is not True:
        return I5
    return None


def reserve_of(usage):
    """D6, the export's reserve (its D14): the larger of 5 GiB and a tenth."""
    return max(EXPORT_MIN_RESERVE, usage.total // EXPORT_RESERVE_FRACTION)


def space_refusal(folder, need):
    """I2 when writing *need* bytes into *folder*'s filesystem would leave less
    than the reserve; else ``None``."""
    usage = shutil.disk_usage(folder)
    reserve = reserve_of(usage)
    if usage.free - need < reserve:
        return no_space_text(need, usage.free, folder, reserve)
    return None


def staging_root(settings_dict):
    """``<library>/<import_folder_name>``: one filesystem with ``media/`` (D5 (b))."""
    return os.path.join(settings_dict['library_path'], settings_dict['import_folder_name'])


def ensure_staging_root(settings_dict):
    """The staging root, made 0700 when it is missing. A link or anything but
    a folder in its place is refused: it is never followed (review row 9)."""
    root = staging_root(settings_dict)
    try:
        st = os.lstat(root)
    except FileNotFoundError:
        os.mkdir(root, 0o700)
        os.chmod(root, 0o700)
        return root
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISDIR(st.st_mode):
        Logger.error(f'import staging folder {root} is not a folder (a link or a file): '
                     'imports are refused until it is removed')
        raise ProjectImportError(f'Import is not available on this controller: {root} is not '
                                 'a folder (see the editor journal)')
    if not os.access(root, os.W_OK | os.X_OK):
        # A folder the editor cannot write to (made by another user, a wrong mode):
        # the guard must say so now, not hand out a ticket whose import dies on its
        # first write (found on .111, 2026-11-25).
        Logger.error(f'import staging folder {root} is not writable by the editor: '
                     'imports are refused until its owner and mode are fixed')
        raise ProjectImportError(f'Import is not available on this controller: the editor cannot '
                                 f'write to {root} (see the editor journal)')
    return root


def make_staging(settings_dict):
    """This import's own folder, ``import-<hex>``, 0700: the name the start-up
    sweep recognises (``cli.sweep_import_staging``)."""
    path = os.path.join(ensure_staging_root(settings_dict), 'import-' + uuid.uuid4().hex)
    os.mkdir(path, 0o700)
    return path


def new_report():
    """The report of "The messages", empty."""
    return {'project': {'uuid': None, 'name': None, 'unix_name': None, 'renamed': False},
            'media': {'added': [], 'reused': [], 'renamed': [], 'missing': [], 'from_library': []},
            'sidecars_failed': [], 'relinked': [], 'ignored': [], 'warnings': []}


# --- The zip's directory, bounded before ZipFile reads it (round 2, row 4) ---

def open_archive(zip_path):
    """``zipfile.ZipFile`` of *zip_path*, built only after its directory was
    bounded: the end record's size of the directory against
    :data:`MAX_DIRECTORY_BYTES`, then its records counted one by one against
    :data:`MAX_ENTRIES`, whatever count the end record declares (``ZipFile``
    would build one ``ZipInfo`` per record it finds). Raises
    ``ProjectImportError`` (I8a)."""
    try:
        with open(zip_path, 'rb') as fp:
            directory = _read_directory(fp)
        count = _count_records(directory)
        Logger.debug(f'import: {zip_path} has {count} entries, a directory of {len(directory)} bytes')
        return zipfile.ZipFile(zip_path)
    except ProjectImportError:
        raise
    except (OSError, EOFError, zipfile.BadZipFile, struct.error, ValueError) as e:
        raise _refused(f'it cannot be read as a zip ({type(e).__name__}: {e})')


def _read_directory(fp):
    """The directory's bytes, found as ``ZipFile`` finds them
    (``zipfile._EndRecData`` and the offsets of ``_RealGetContents``), read
    only when the end record's size is within the bound."""
    endrec = zipfile._EndRecData(fp)
    if not endrec:
        raise _refused('it is not a zip file (no end record)')
    size_cd = endrec[zipfile._ECD_SIZE]
    offset_cd = endrec[zipfile._ECD_OFFSET]
    if size_cd > MAX_DIRECTORY_BYTES:
        raise _refused(f'its directory is {size_cd} bytes, more than {MAX_DIRECTORY_BYTES}')
    concat = endrec[zipfile._ECD_LOCATION] - size_cd - offset_cd
    if endrec[zipfile._ECD_SIGNATURE] == zipfile.stringEndArchive64:
        concat -= zipfile.sizeEndCentDir64 + zipfile.sizeEndCentDir64Locator
    start = concat + offset_cd
    if start < 0:
        raise _refused('its directory starts before the file')
    fp.seek(start, 0)
    directory = fp.read(size_cd)
    if len(directory) != size_cd:
        raise _refused('its directory is truncated')
    return directory


def _count_records(directory):
    """The directory's records, walked as ``ZipFile`` walks them; refused above
    :data:`MAX_ENTRIES` or on a record that is not one."""
    pos = count = 0
    while pos < len(directory):
        if directory[pos:pos + 4] != zipfile.stringCentralDir or pos + 46 > len(directory):
            raise _refused('its directory is damaged')
        name_len, extra_len, comment_len = struct.unpack_from('<HHH', directory, pos + 28)
        pos += 46 + name_len + extra_len + comment_len
        count += 1
        if count > MAX_ENTRIES:
            raise _refused(f'it has more than {MAX_ENTRIES} entries')
    return count


# --- What the reader accepts (D7) --------------------------------------------

_NOISE_FOLDER = '__MACOSX'
_NOISE_FILES = ('.DS_Store', 'Thumbs.db')
_READ_ERRORS = (zipfile.BadZipFile, zlib.error, NotImplementedError, RuntimeError, EOFError,
                struct.error, ValueError, OSError)


def _q(name):
    """A name quoted for a one-line text (a control character comes escaped)."""
    return repr(name)


def _is_noise(name):
    parts = name.rstrip('/').split('/')
    return parts[0] == _NOISE_FOLDER or parts[-1] in _NOISE_FILES


def _check_entry(info):
    """The whole-archive refusals, for every entry, used or not (D7)."""
    name = info.filename
    if '\x00' in info.orig_filename:
        # zipfile cuts ``filename`` at the first NUL; ``orig_filename`` is the
        # name as the archive writes it (change review R9).
        raise _refused(f'entry {_q(info.orig_filename)} has a NUL in its name')
    if '\\' in name:
        raise _refused(f'entry {_q(name)} has a backslash in its name')
    if name.startswith('/'):
        raise _refused(f'entry {_q(name)} is an absolute name')
    parts = name[:-1].split('/') if name.endswith('/') else name.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise _refused(f"entry {_q(name)} has an empty, '.' or '..' part in its name")
    if stat.S_ISLNK(info.external_attr >> 16):
        raise _refused(f'entry {_q(name)} is a symbolic link')
    if info.flag_bits & 0x1:
        raise _refused(f'entry {_q(name)} is encrypted')
    if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise _refused(f'entry {_q(name)} uses compression method {info.compress_type}, '
                       'not Stored or Deflated')


def _local_name_length(info):
    try:
        return len(info.orig_filename.encode('utf-8' if info.flag_bits & 0x800 else 'cp437'))
    except (UnicodeError, AttributeError):
        return 0


def _check_sizes(zf, infos, zip_size):
    """Compressed sizes that add up to more than the zip, or entries whose data
    overlap one another or the directory, are refused (D7). The local header's
    extra field is not counted: a lower bound, so no real archive trips it."""
    total = sum(info.compress_size for info in infos)
    if total > zip_size:
        raise _refused(f'its entries add up to {total} bytes, more than the {zip_size} '
                       'bytes of the zip')
    end_of_data = getattr(zf, 'start_dir', zip_size)
    ordered = sorted(infos, key=lambda i: i.header_offset)
    for info, following in zip(ordered, ordered[1:] + [None]):
        end = info.header_offset + 30 + _local_name_length(info) + info.compress_size
        limit = following.header_offset if following is not None else end_of_data
        if info.header_offset < 0 or end > limit:
            raise _refused(f'entry {_q(info.filename)} overlaps the next one')


def _top_folder(infos):
    """The one top folder of the entries that are not noise (D7)."""
    tops = set()
    for info in infos:
        if _is_noise(info.filename):
            continue
        parts = info.filename.split('/')
        if len(parts) < 2:
            raise _refused(f'entry {_q(info.filename)} is not inside a project folder')
        tops.add(parts[0])
    if len(tops) != 1:
        raise _refused('it has no project folder' if not tops else
                       f'it has {len(tops)} top folders: {", ".join(sorted(map(_q, tops)))}')
    top = tops.pop()
    if StringSanitizer.sanitize_dir_permit_increment(top) != top:
        raise _refused(f'its folder {_q(top)} is not a project folder name')
    return top


def media_name_problem(name):
    """What the rule of D7 refuses in a media name as the archive writes it,
    or ``None`` (rev 3, round 2, row 5): it says only what is refused, so
    ``cançó.wav`` passes. A capital is not refused (Ion, 2026-11-25): the
    name is then sanitised (:func:`library_name`), and what the sanitiser
    leaves is asked again here: empty, ``.`` or ``..`` is refused."""
    if not isinstance(name, str) or not name:
        return 'empty'
    if name in ('.', '..'):
        return "'.' or '..'"
    if '/' in name or '\\' in name:
        return 'a slash or a backslash'
    if any(unicodedata.category(c) == 'Cc' for c in name):
        return 'a control character'
    try:
        if len(name.encode('utf-8')) > 255:
            return 'more than 255 bytes in UTF-8'
    except UnicodeError:
        return 'a character that is not UTF-8'
    return None


#: The longest library name an archive may carry, in UTF-8 bytes (change review
#: R12): a file name may have 255, and the library makes longer ones from it:
#: the ``-NNN`` that ``new()`` adds on a taken name, then the longest name built
#: from that, the loop period's temporary file ``.<name>.period.XXXXXXXX``
#: (``media_sidecars.write_period``, mkstemp's 8 characters); the video index's
#: ``<name>.idx.tmp`` (cuems-videoindexer) and the thumbnail and waveform
#: (``<stem>_<ext>.png``, ``.dat``) are shorter. 255 - 4 - 17 = 234.
_NNN_BYTES = len('-001')
_SIDECAR_GROWTH = max(len('.' + media_sidecars.SIDECAR_EXT + '.') + 8,
                      len(media_sidecars.INDEX_EXT + '.tmp'), len('_.png'), len('_.dat'))
MAX_LIBRARY_NAME_BYTES = 255 - _NNN_BYTES - _SIDECAR_GROWTH


#: What a library's media names are made of: what the sanitiser keeps
#: (alphanumerics, ``.``, ``_``), lower-cased, which adds U+0307 (lower-casing
#: ``İ`` leaves it; no other alphanumeric lowers to a character the sanitiser
#: drops, checked over all of Unicode on .111), and the ``-`` of ``new()``'s
#: ``<base>-NNN<ext>`` (N2).
_LIBRARY_EXTRA = '._-\u0307'


def library_name(name):
    """The name the library holds for the archive's media name *name* (D7, Ion
    2026-11-25). A name already made only of what a library name is made of
    (:data:`_LIBRARY_EXTRA`) and lower-case is kept: the sanitiser is not a
    fixed point on the library's own names (``clip-001.mp4`` would become
    ``clip_001.mp4``, the ``i`` + U+0307 it makes of ``İ`` would lose its
    dot), so sanitising an archive of a library again would rename its files
    and defeat D8's reuse. Any other name gets what the upload stores,
    ``StringSanitizer.sanitize_file_name`` (``CuemsUpload.py:129``; ``new()``
    itself does not sanitise): ``Clip.MP4`` is ``clip.mp4``, ``İ.wav`` is
    ``i`` + U+0307 ``.wav``."""
    if name == name.lower() and all(c.isalnum() or c in _LIBRARY_EXTRA for c in name):
        return name
    return StringSanitizer.sanitize_file_name(name)


# --- Reading entries ------------------------------------------------------

def _copy_entry(zf, info, sink=None, cap=None, progress=None, label=None):
    """Read *info* to its end in :data:`CHUNK` pieces, ``zipfile`` checking its
    CRC32 at the end; write each piece to *sink* when given. Returns its MD5
    (hex). A defect of the archive is I8a with the entry's name; a failure of
    the sink (the staging's disk) is not caught here."""
    digest = hashlib.md5()
    got = 0
    try:
        src = zf.open(info)
    except _READ_ERRORS as e:
        raise _refused(f'entry {_q(info.filename)} cannot be read ({type(e).__name__}: {e})')
    with src:
        while True:
            try:
                chunk = src.read(CHUNK)
            except _READ_ERRORS as e:
                raise _refused(f'entry {_q(info.filename)} cannot be read ({type(e).__name__}: {e})')
            if not chunk:
                break
            got += len(chunk)
            if cap is not None and got > cap:
                raise _refused(f'entry {_q(info.filename)} is more than {cap} bytes')
            digest.update(chunk)
            if sink is not None:
                sink.write(chunk)
            if progress is not None:
                progress('check', got, None, label)
    if got != info.file_size:
        raise _refused(f'entry {_q(info.filename)} holds {got} bytes, not the {info.file_size} '
                       'it declares')
    return digest.hexdigest()


def _hash_file(path):
    """The MD5 of a library file, read only (D8: a row with no ``file_md5``)."""
    digest = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


# --- The script (D11) ---------------------------------------------------

def _media_blocks(node):
    """Every Media block of a script dict that names a file, in order."""
    if isinstance(node, dict):
        block = node.get('Media')
        if isinstance(block, dict) and block.get('file_name'):
            yield block
        for value in node.values():
            yield from _media_blocks(value)
    elif isinstance(node, list):
        for value in node:
            yield from _media_blocks(value)


def _read_script(path, schema_name):
    """The script dict, read through a defused resource (N5): an entity or a
    file that is not XML is I8a; what the box's schema refuses is I8b. It is
    then parsed and serialised once, as the creation will (D12)."""
    try:
        resource = xmlschema.XMLResource(path, defuse='always')
    except Exception as e:
        raise _refused(f'script.xml cannot be read ({type(e).__name__}: {e})')
    reader = XmlReaderWriter(schema_name=schema_name, xmlfile=resource)
    try:
        data = reader.read()
    except xmlschema.XMLSchemaValidationError as e:
        raise ProjectImportError(schema_text(e.reason or e))
    except Exception as e:
        raise ProjectImportError(schema_text(f'{type(e).__name__}: {e}'))
    try:
        project_object = CuemsParser(copy.deepcopy(data)).parse()
        reader.validate_object(project_object)
    except xmlschema.XMLSchemaValidationError as e:
        raise ProjectImportError(schema_text(e.reason or e))
    except Exception as e:
        raise ProjectImportError(schema_text(f'{type(e).__name__}: {e}'))
    # No "holds no CuemsScript" check (change review R14): the schema's one
    # global element is CuemsProject and its CuemsScript is required, so a
    # document without one is refused by ``reader.read()`` above (I8b).
    return data


def _gate_warnings(data):
    """D11: the save gates are not applied; what they would refuse is listed."""
    contents = (data['CuemsScript'].get('CueList') or {}).get('contents') or []
    warnings = []
    for gate in (validate_media_cues_in_contents, validate_fade_durations_in_contents):
        try:
            gate(copy.deepcopy(contents))
        except ValueError as e:
            warnings.append(one_line(e))
    return warnings


# --- The plan of one import: everything checked before a write ------------

class _Plan:
    """What the check found: the archive's top folder, the script, and per
    media name what to do with it."""

    def __init__(self):
        self.top = None
        self.data = None
        self.source_name = None  # the script's name, before the free pair (D10)
        self.names = []          # every file the script names, in order
        self.library = {}        # name -> the name the library holds for it (D7)
        self.entries = {}        # name -> ZipInfo, for the names the archive carries
        self.md5 = {}            # name -> MD5 of its entry
        self.reuse = {}          # archive name -> library name (D8)
        self.add = []            # archive names to register, in order
        self.missing = []        # names the archive does not carry (D9)


def _check(zf, zip_size, db, staging, plan, report, progress):
    """Step 2 (a): every check, with no write to the library."""
    infos = zf.infolist()
    for info in infos:
        _check_entry(info)
    _check_sizes(zf, infos, zip_size)
    plan.top = _top_folder(infos)
    by_name = {}
    for info in infos:
        by_name.setdefault(info.filename, []).append(info)
    script_info = _read_script_entry(zf, by_name, db, staging, plan, report)
    _match_media(by_name, db, plan)
    used = {id(script_info)} | {id(info) for info in plan.entries.values()}
    report['ignored'] = [i.filename for i in infos if id(i) not in used]
    _read_media_entries(zf, plan, progress)
    _note_stale_md5(plan, report)


def _read_script_entry(zf, by_name, db, staging, plan, report):
    """``<top>/script.xml``, once and within :data:`MAX_SCRIPT_BYTES`, read to
    its end into the staging under a fixed name, then read as a script."""
    script_name = f'{plan.top}/script.xml'
    entries = by_name.get(script_name, [])
    if not entries or entries[0].is_dir():
        raise _refused(f'it has no {_q(script_name)}')
    if len(entries) > 1:
        raise _refused(f'{_q(script_name)} is in it twice')
    if entries[0].file_size > MAX_SCRIPT_BYTES:
        raise _refused(f'{_q(script_name)} is more than {MAX_SCRIPT_BYTES} bytes')
    script_path = os.path.join(staging, 'script.xml')
    with open(script_path, 'xb') as sink:
        _copy_entry(zf, entries[0], sink=sink, cap=MAX_SCRIPT_BYTES)
    plan.data = _read_script(script_path, db.project.script_schema_name)
    plan.source_name = plan.data['CuemsScript'].get('name')
    report['warnings'].extend(_gate_warnings(plan.data))
    return entries[0]


def _match_media(by_name, db, plan):
    """The names the script lists against ``<top>/media/`` (D7, D9), each with
    the name the library will hold for it (:func:`library_name`): from here on
    a file is looked up, registered and remapped under that name, and one that
    differs from the archive's is reported as a rename, as D8's are."""
    for block in _media_blocks(plan.data):
        if block['file_name'] not in plan.names:
            plan.names.append(block['file_name'])
    owner = {}
    for name in plan.names:
        problem = media_name_problem(name)
        if problem:
            raise _refused(f'the media name {_q(name)} is refused ({problem})')
        lib = library_name(name)
        problem = media_name_problem(lib)
        if problem:
            raise _refused(f'the media name {_q(name)} is refused ({problem} once sanitised)')
        if lib in owner:
            raise _refused(f'the media names {_q(owner[lib])} and {_q(name)} are both '
                           f'{_q(lib)} once sanitised')
        owner[lib] = name
        plan.library[name] = lib
        entries = by_name.get(f'{plan.top}/media/{name}', [])
        if len(entries) > 1:
            raise _refused(f'entry {_q(entries[0].filename)} is in it twice')
        if not entries:
            plan.missing.append(name)
            continue
        if db.media.get_type(lib) is None:
            raise _refused(f'the media file {_q(name)} has no known media type')
        if len(lib.encode('utf-8')) > MAX_LIBRARY_NAME_BYTES:
            raise _refused(f'the media name {_q(name)} is refused (more than '
                           f'{MAX_LIBRARY_NAME_BYTES} bytes in UTF-8 as the library holds it: '
                           'no room for the -NNN of a taken name and its sidecars)')
        plan.entries[name] = entries[0]


def _read_media_entries(zf, plan, progress):
    """Every used media entry read to its end, its CRC32 checked by
    ``zipfile`` and its MD5 kept (step 2 (a)): nothing reaches the library
    before its entry was read whole (N4)."""
    total = sum(info.file_size for info in plan.entries.values())
    done = 0
    for name, info in plan.entries.items():
        report_to = None
        if progress is not None:
            report_to = (lambda phase, got, _t, label, base=done:
                         progress(phase, base + got, total, label))
        plan.md5[name] = _copy_entry(zf, info, progress=report_to, label=name)
        done += info.file_size


def _note_stale_md5(plan, report):
    """N10: a script may rightly hold a file's old MD5: a line, never a refusal."""
    for block in _media_blocks(plan.data):
        name, held = block['file_name'], block.get('file_md5')
        if name in plan.md5 and isinstance(held, str) and held.lower() != plan.md5[name]:
            text = (f'{name}: the script holds another MD5 than the file in the archive; '
                    'the library keeps the file\'s own')
            if text not in report['warnings']:
                report['warnings'].append(text)


def _same_file(row, path, size, md5_hex):
    """D8: the library's file under that name is the archive's: same size on
    disk (and in the row when it has one) and same MD5 (the row's, or the
    file's own when the row has none)."""
    if row.file_size is not None and row.file_size != size:
        return False
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if not stat.S_ISREG(st.st_mode) or st.st_size != size:
        return False
    held = row.file_md5.lower() if isinstance(row.file_md5, str) and row.file_md5 else None
    return (held or _hash_file(path)) == md5_hex


def _decide(db, plan, report):
    """D8 per file: its library name (D7), then ``<base>-NNN<ext>`` as
    ``new()`` would try them, up to the first free one. A live file of the
    same content on the way is reused; the trash is never taken from; else
    the file is added."""
    for name, info in plan.entries.items():
        base, ext = os.path.splitext(plan.library[name])
        candidate, i = plan.library[name], 0
        while True:
            row = Media.get_or_none(Media.unix_name == candidate)
            path = os.path.join(db.media.media_path, candidate)
            if row is None and not os.path.lexists(path) and not Media.select().where(
                    Media.name == candidate).exists():
                plan.add.append(name)
                break
            if row is not None and not row.in_trash and _same_file(row, path, info.file_size,
                                                                   plan.md5[name]):
                plan.reuse[name] = candidate
                _note_reused(report, name, candidate)
                break
            i += 1
            candidate = f'{base}-{i:03d}{ext}'


def _note_reused(report, name, lib_name):
    report['media']['reused'].append(lib_name)
    if lib_name != name:
        report['media']['renamed'].append({'from': name, 'to': lib_name})
        Logger.info(f'import: reused {lib_name} (renamed {name} to {lib_name})')
    else:
        Logger.info(f'import: reused {name}')


def _check_space(db, plan, staging):
    """D6 after the checks: the bytes of the files that will really be added,
    on the library's filesystem; on two filesystems the staging is asked
    for the largest one, which it holds while it is extracted."""
    sizes = [plan.entries[name].file_size for name in plan.add]
    refusal = space_refusal(db.media.media_path, sum(sizes))
    if refusal is None and sizes and os.stat(staging).st_dev != os.stat(db.media.media_path).st_dev:
        refusal = space_refusal(staging, max(sizes))
    if refusal is not None:
        raise ProjectImportError(refusal)


# --- The writes (D12): the files one by one, then the project ------------

def _ask(status, accept_loaded):
    """D4: the rule of D3 asked again; its refusal stops the import (I9)."""
    refusal = import_refusal(status(), accept_loaded)
    if refusal is not None:
        raise _Stop(refusal)


class _Stop(Exception):
    """A later check refused: the import stops there (D4)."""


def _extract(zf, info, path, md5_hex):
    """The entry, extracted under a generated name of the staging folder (a
    name in the archive is never a path); its MD5 must be the check's."""
    with open(path, 'xb') as sink:
        got = _copy_entry(zf, info, sink=sink)
    if got != md5_hex:
        raise RuntimeError(f'{info.filename} changed after it was checked')


def _missing_sidecars(media_db, name):
    """What ``new()`` was expected to build for *name* and did not (review row
    16): it only logs those failures."""
    _type = media_db.get_type(name)
    path = media_db.get_file_path(name)
    failed = []
    if not os.path.exists(media_db.get_thumbnail_path(name)):
        failed.append('thumbnail')
    if _type is MediaType.AUDIO and not os.path.exists(media_db.get_waveform_path(name)):
        failed.append('waveform')
    if (_type is MediaType.MOVIE and is_indexed_video(name)
            and media_sidecars.video_index_state(path) != media_sidecars.INDEX_VALID):
        failed.append('index')
    if _type in (MediaType.MOVIE, MediaType.AUDIO) and media_sidecars.read_period(path) is None:
        failed.append('period')
    return failed


def _relink(db, lib_name, report, list_update):
    """N1: other projects that name *lib_name* with no media are relinked as an
    upload does (``CuemsUpload.check_if_media_existed``), best effort, right
    after the file is registered and before this import reads its uuid."""
    rows = db.media.check_if_media_existed_in_projects(lib_name) or []
    changed = False
    for project_id in dict.fromkeys(str(r.project_id) for r in rows):
        try:
            db.project.update_projects_existed_media(project_id, lib_name)
        except Exception as e:
            Logger.error(f'could not relink {lib_name} in project {project_id}: '
                         f'{type(e).__name__}: {e}')
            report['warnings'].append(f'{lib_name}: project {project_id} could not be relinked')
            continue
        project = Project.get_or_none(Project.uuid == project_id)
        linked = ProjectMedia.select().where(
            (ProjectMedia.project == project_id) & (ProjectMedia.media_filename == lib_name)
            & ProjectMedia.media.is_null(False)).exists()
        if project is not None and linked:
            report['relinked'].append({'project': project.name, 'name': lib_name})
            changed = True
    if changed and list_update:
        list_update('project_list')


def _after_registration(db, lib_name, report, list_update):
    """The relink and the sidecar check of a file just registered: best
    effort, the file is in the library whatever happens here."""
    try:
        _relink(db, lib_name, report, list_update)
    except Exception as e:
        Logger.error(f'import: relinking {lib_name} failed: {type(e).__name__}: {e}')
        report['warnings'].append(f'{lib_name}: other projects could not be relinked')
    try:
        for what in _missing_sidecars(db.media, lib_name):
            report['sidecars_failed'].append({'name': lib_name, 'what': what})
            Logger.warning(f'import: {lib_name} has no {what}')
    except Exception as e:
        Logger.error(f'import: checking the sidecars of {lib_name} failed: {type(e).__name__}: {e}')


def _register(zf, db, plan, staging, report, status, accept_loaded, progress, list_update):
    """Step 2 (b): each file to add, the rule asked again before its
    extraction and again right before its registration (D4)."""
    for i, name in enumerate(plan.add):
        _ask(status, accept_loaded)
        if progress:
            progress('media', i, len(plan.add), name)
        staged = os.path.join(staging, f'media-{i}')
        _extract(zf, plan.entries[name], staged, plan.md5[name])
        # Asked again right before the registration: a big file takes a while
        # to extract, and a show may start meanwhile (change review R1).
        _ask(status, accept_loaded)
        lib_name = db.media.new(staged, plan.library[name], plan.md5[name])
        plan.reuse[name] = lib_name
        report['media']['added'].append(lib_name)
        if lib_name != name:
            report['media']['renamed'].append({'from': name, 'to': lib_name})
            Logger.info(f'import: added {lib_name} (renamed {name} to {lib_name})')
        else:
            Logger.info(f'import: added {name}')
        if list_update:
            list_update('file_list')
        _after_registration(db, lib_name, report, list_update)
        if progress:
            progress('media', i + 1, len(plan.add), lib_name)


def _remap(plan):
    """D10: each Media block names the library's file and carries its row's
    uuid, read back by name after every relink (N1); a missing file is named
    as the library would hold it (D7) and keeps the archive's id."""
    for block in _media_blocks(plan.data):
        name = block['file_name']
        lib_name = plan.reuse.get(name, plan.library.get(name, name))
        block['file_name'] = lib_name
        row = Media.get_or_none(Media.unix_name == lib_name)
        if row is not None:
            block['id'] = str(row.uuid)


def _note_not_carried(plan, project_uuid, report):
    """D9, after the creation: a file the script names and the archive lacks
    is ``missing`` (a row with no media) or ``from_library`` (linked to the
    library's live file of that name), under the name the library would
    hold (D7), with a rename when that differs from the script's. When
    ``new()`` gave one of this import's files that very name, it is a warning
    instead (D8). A name whose row is in the media trash keeps its link to
    that row, as a delete of a used media leaves it, so a restore heals the
    project; it is reported ``missing``, with a warning that says where the
    file is (Ion, 2026-11-25; change review R4). ``name`` and ``unix_name``
    are unique in the library: a name has one row, live or trashed."""
    registered = set(report['media']['added'])
    links = {r.media_filename: r.media_id for r in
             ProjectMedia.select().where(ProjectMedia.project == project_uuid)}
    trashed = {str(m.uuid) for m in Media.select(Media.uuid).where(
        Media.uuid.in_([v for v in links.values() if v is not None]) & (Media.in_trash == True))}  # noqa: E712
    for source in plan.missing:
        name = plan.library[source]
        if name != source:
            report['media']['renamed'].append({'from': source, 'to': name})
            Logger.info(f'import: renamed {source} to {name}')
        if name in registered:
            report['warnings'].append(
                f'{name}: the script names it for a file the archive does not carry, and a file '
                f'of this archive was registered under that name: both cues now use it')
        elif links.get(name) is None:
            report['media']['missing'].append(name)
            Logger.info(f'import: missing {name}')
        elif str(links[name]) in trashed:
            report['media']['missing'].append(name)
            report['warnings'].append(
                f'{name}: not in the archive, and the library has it only in the media trash: '
                'restoring it from the trash brings it back to this project')
            Logger.info(f'import: missing {name}, linked to its row in the media trash')
        else:
            report['media']['from_library'].append(name)
            Logger.info(f'import: {name} not in the archive, linked to the library\'s file '
                        '(its content was not compared)')


def _after_creation(plan, project_uuid, report, progress, list_update):
    """What follows the creation, each step on its own: a failure is logged
    and warned, never raised (change review R10)."""
    steps = (('the report of the files the archive does not carry',
              lambda: _note_not_carried(plan, project_uuid, report)),
             ('the project list update', lambda: list_update and list_update('project_list')),
             ('the progress frame', lambda: progress and progress('project', 1, 1,
                                                                 report['project']['unix_name'])))
    for what, step in steps:
        try:
            step()
        except Exception as e:
            Logger.error(f'import: the project {report["project"]["unix_name"]} was created, '
                         f'{what} failed: {type(e).__name__}: {e}')
            report['warnings'].append(f'The project was created, but {what} failed: '
                                      f'{type(e).__name__}: {one_line(e)}')


def _create(db, plan, report, status, accept_loaded, progress, list_update):
    """Step 2 (c), (d): the remap, the last question, the project."""
    _remap(plan)
    _ask(status, accept_loaded)
    script = plan.data['CuemsScript']
    source_uuid = script.get('id')
    if progress:
        progress('project', 0, 1, plan.top)
    project_uuid, unix_name, name = db.project.import_project(plan.data, plan.top, script['name'])
    # The project exists from here: what follows is best effort, and the import
    # is a success whatever happens (an I9 would make the operator import again
    # and get a second copy; change review R10).
    report['project'] = {'uuid': project_uuid, 'name': name, 'unix_name': unix_name,
                         'renamed': (unix_name, name) != (plan.top, plan.source_name)}
    _after_creation(plan, project_uuid, report, progress, list_update)
    media = report['media']
    Logger.info(f'imported {unix_name} ({project_uuid}): added {len(media["added"])}, reused '
                f'{len(media["reused"])}, renamed {len(media["renamed"])}, missing '
                f'{len(media["missing"])}; source project {source_uuid}')


def import_archive(zip_path, db, staging, *, status, accept_loaded=False, progress=None,
                   list_update=None):
    """Import the project archive *zip_path* into the library (synchronous:
    the session runs it in the executor).

    *db* has ``.project`` and ``.media``; *staging* is this import's own
    existing folder, the only place written outside the library's writers
    (the caller removes it). ``status()`` gives the engine's word and is asked
    before each file is registered and before the project is created (D4);
    ``progress(phase, done, total, name)`` and ``list_update(list_type)`` tell
    the socket and the other sessions.

    Returns the report ("The messages"). Raises ``ProjectImportError``: I8a,
    I8b or I2 before anything is written; I9 once something may have been,
    with ``.report`` naming what was added (an import only adds, D12).
    """
    report = new_report()
    plan = _Plan()
    with open_archive(zip_path) as zf:
        try:
            _check(zf, os.path.getsize(zip_path), db, staging, plan, report, progress)
            _decide(db, plan, report)
            _check_space(db, plan, staging)
        except ProjectImportError:
            raise
        except Exception as e:
            Logger.error(f'import: the check failed: {type(e).__name__}: {e}')
            raise ProjectImportError(interrupted_text(f'{type(e).__name__}: {e}', []))
        try:
            _register(zf, db, plan, staging, report, status, accept_loaded, progress, list_update)
            _create(db, plan, report, status, accept_loaded, progress, list_update)
        except _Stop as e:
            raise _interrupted(str(e), report)
        except ProjectImportError as e:
            raise _interrupted(str(e), report)
        except Exception as e:
            Logger.error(f'import: failed while adding: {type(e).__name__}: {e}')
            raise _interrupted(str(e) or type(e).__name__, report)
    return report


def _interrupted(reason, report):
    text = interrupted_text(reason, report['media']['added'])
    Logger.warning(f'{text}; report: {json.dumps(report, default=str)}')
    return ProjectImportError(text, copy.deepcopy(report))


# --- The /upload session of an import (D1, D2, D4) --------------------------

def is_project_upload(value):
    """A first frame of ``/upload`` that starts an import: ``type`` is exactly
    ``PROJECT`` (D1). Without it, or with another value, the frame is a media
    upload exactly as before."""
    return isinstance(value, dict) and value.get('type') == 'PROJECT'


class ImportSession:
    """The ``/upload`` socket of one import, from its first frame to its end.

    The ticket of the guard lets it in (I6 otherwise, before a byte is
    taken); the zip is written into this import's staging folder while its
    MD5 is computed (D2); the size and the MD5 must be what was announced
    (I7); the rule of D3 is asked again (D4); then :func:`import_archive`
    runs in the executor, every later check going through the server's
    communicator with no socket of the user's (N9), while a timer of the
    session's own sends a ``progress`` frame at least every
    :data:`HEARTBEAT_S` seconds (review row 7). The slot is freed and the
    staging removed whatever happens.
    """

    def __init__(self, server, websocket):
        self.server = server
        self.websocket = websocket
        self.loop = None
        self.owner = None
        self.ended = False
        self.latest = None
        self._last_key = None

    async def run(self, value):
        self.loop = asyncio.get_running_loop()
        slot = getattr(self.server, 'import_slot', None)
        record = slot.claim(value.get('ticket'), value.get('size')) if slot is not None else None
        if record is None:
            Logger.warning(f'import refused: {I6}')
            await self._send({'error': I6, 'fatal': True})
            return
        self.owner = record.owner
        staging = None
        try:
            staging = make_staging(self.server.settings_dict)
            await self._import(record, staging, value.get('name'))
        except ProjectImportError as e:
            await self._fail(e)
        except Exception as e:
            Logger.error(f'import failed: {type(e).__name__}: {e}')
            await self._fail(ProjectImportError(interrupted_text(f'{type(e).__name__}: {e}', [])))
        finally:
            self.ended = True
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=False, onerror=_log_rmtree_error)
            slot.release(record.ticket)

    async def _import(self, record, staging, name):
        Logger.info(f'import of {name!r} ({record.size} bytes) started')
        zip_path = os.path.join(staging, 'archive.zip')
        await self._send({'ready': True})
        if not await self._receive(zip_path, record.size):
            return
        self.latest = {'progress': {'phase': 'check', 'done': 0, 'total': 0, 'name': ''}}
        heartbeat = asyncio.ensure_future(self._heartbeat())
        try:
            # D4: asked again when the upload ends, before anything is read.
            refusal = import_refusal(await record.owner._engine_status(), record.accept_loaded)
            if refusal is not None:
                raise ProjectImportError(interrupted_text(refusal, []))
            report = await self.loop.run_in_executor(self.server.executor, functools.partial(
                import_archive, zip_path, self.server.db, staging, status=self._status,
                accept_loaded=record.accept_loaded, progress=self._progress,
                list_update=self._list_update))
        finally:
            heartbeat.cancel()
        Logger.info(f'import report: {json.dumps(report, default=str)}')
        self.ended = True
        await self._send({'imported': report})
        await self._send({'close': True})

    async def _receive(self, path, size):
        """The zip, frame by frame, each answered ``ready``; ``True`` once
        ``finished`` brought the MD5 of what was received, ``False`` when the
        socket closed before (the import is dropped). I7 on more bytes than
        announced, fewer, another MD5, a text frame that is not ``finished``,
        or no frame for :data:`UPLOAD_STALL_S`."""
        digest = hashlib.md5()
        got = 0
        with open(path, 'xb') as sink:
            while True:
                try:
                    message = await asyncio.wait_for(self.websocket.recv(), UPLOAD_STALL_S)
                except asyncio.TimeoutError:
                    raise ProjectImportError(I7)
                except ws.exceptions.ConnectionClosed:
                    Logger.warning('import dropped: the upload socket closed before the end')
                    return False
                if isinstance(message, bytes):
                    got += len(message)
                    if got > size:
                        raise ProjectImportError(I7)
                    await self.loop.run_in_executor(self.server.executor,
                                                    _write_chunk, sink, digest, message)
                    await self._send({'ready': True})
                    continue
                received = _finished_md5(message)
                if received is None:
                    # Only binary frames and ``finished`` belong here; anything
                    # else would hold the one slot while resetting the stall
                    # timer (change review R11).
                    Logger.warning('import: a text frame that is not finished during the '
                                   f'upload: {one_line(message)[:200]!r}')
                    raise ProjectImportError(I7)
                break
        if got != size or received.lower() != digest.hexdigest():
            raise ProjectImportError(I7)
        return True

    async def _heartbeat(self):
        while not self.ended:
            await asyncio.sleep(HEARTBEAT_S * 0.8)
            await self._send_progress(self.latest)

    async def _fail(self, error):
        text = str(error)
        if text.startswith(I9):
            Logger.warning(text)
        else:
            Logger.warning(f'import refused: {text}')
        self.ended = True
        frame = {'error': text, 'fatal': True}
        if error.report is not None:
            frame['report'] = error.report
        await self._send(frame)

    # --- called from the executor's thread by import_archive

    def _status(self):
        """The engine's word, asked through the session that took the ticket;
        ``None`` (I4) when it does not answer in time."""
        future = asyncio.run_coroutine_threadsafe(self.owner._engine_status(), self.loop)
        try:
            return future.result(ENGINE_WAIT_S)
        except Exception as e:
            Logger.warning(f'import: no answer from the engine ({type(e).__name__}: {e})')
            future.cancel()
            return None

    def _progress(self, phase, done, total, name):
        frame = {'progress': {'phase': phase, 'done': int(done or 0), 'total': int(total or 0),
                              'name': name or ''}}
        self.latest = frame
        if (phase, name) != self._last_key:     # a new file or phase goes out at once
            self._last_key = (phase, name)
            asyncio.run_coroutine_threadsafe(self._send_progress(frame), self.loop)

    def _list_update(self, list_type):
        """Every session is told, and before the next write or the error frame."""
        future = asyncio.run_coroutine_threadsafe(
            self.server.notify_others_list_changes(None, list_type), self.loop)
        try:
            future.result(10)
        except Exception as e:
            Logger.warning(f'import: list_update {list_type} not sent ({type(e).__name__}: {e})')

    # --- the socket

    async def _send_progress(self, frame):
        if not self.ended and frame is not None:
            await self._send(frame)

    async def _send(self, frame):
        try:
            await self.websocket.send(json.dumps(frame))
        except ws.exceptions.ConnectionClosed as e:
            Logger.debug(f'import: frame not sent, the socket is closed ({e})')


def _write_chunk(sink, digest, data):
    sink.write(data)
    digest.update(data)


def _finished_md5(message):
    """The MD5 of a ``finished`` frame, or ``None`` for any other text frame."""
    try:
        data = json.loads(message)
    except (TypeError, ValueError):
        return None
    if isinstance(data, dict) and data.get('action') == 'finished' and isinstance(data.get('value'), str):
        return data['value']
    return None


def _log_rmtree_error(function, path, excinfo):
    Logger.error(f'import: could not remove {path} from the staging: {excinfo[1]}')
