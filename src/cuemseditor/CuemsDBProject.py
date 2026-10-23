import hashlib
import json
import os
import traceback
import shutil
from datetime import datetime
from peewee import DoesNotExist, IntegrityError, prefetch

from cuemsutils.tools.StringSanitizer import StringSanitizer
from cuemsutils.tools.CopyMoveVersioned import CopyMoveVersioned
from cuemsutils.tools.CTimecode import CTimecode
from cuemsutils.cues import AudioCue, CueList, CuemsScript, DmxCue, VideoCue
from cuemsutils.cues.MediaCue import MediaCue
from cuemsutils.errors import SchemaError, ValidationError
from cuemsutils.helpers import new_datetime, new_uuid
from cuemsutils.log import logged, Logger


from cuemseditor.CuemsErrors import *
from cuemseditor.CuemsDBModel import Project, Media, ProjectMedia


class DurationFixStats:
    """Result of a :func:`fix_media_durations_in_contents` walk.

    Attributes:
        media_refs: Number of cue ``Media`` blocks visited.
        replacements: Number of ``duration`` values actually changed.
        orphans: List of ``file_name`` values referencing a media file with no
            ``Media`` row (duration left untouched — a leftover
            ``00:00:00.000`` there matches the valid timecode shape, so it is
            invisible to a pattern scan; report it explicitly instead).
        changes: ``(file_name, previous, replacement)`` for each replacement,
            both as ``CTimecode`` (``previous`` may be ``None``).
        errors: ``file_name`` values whose ``Media`` block could not be
            processed (logged; the walk went on with the next cue).
    """

    def __init__(self):
        self.media_refs = 0
        self.replacements = 0
        self.orphans = []
        self.changes = []
        self.errors = []


#: What a cue's ``Media`` stores about its file (869fat84r, ``0b291d1``), in
#: ``MediaType`` order: the pixel size (not on an ``AudioCue``), then the
#: file's size and MD5 (every media cue, D18).
PIXEL_KEYS = ('pixel_width', 'pixel_height')
STORED_KEYS = PIXEL_KEYS + ('file_size', 'file_md5')


def _positive_int(value):
    """A usable stored size: a positive int (a digit string is accepted and
    converted). ``None`` for anything else, ``bool`` included."""
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if isinstance(value, int) and not isinstance(value, bool) and value > 0:
        return value
    return None


def _md5(value):
    """A usable MD5: 32 hex digits, returned lowercase; ``None`` otherwise."""
    if isinstance(value, str) and len(value) == 32 and all(
            c in '0123456789abcdef' for c in value.lower()):
        return value.lower()
    return None


def _valid(key, value):
    return _md5(value) if key == 'file_md5' else _positive_int(value)


def dimensions_of_row(media):
    """What a ``Media`` row knows about its file: ``pixel_width`` and
    ``pixel_height`` (both or neither), ``file_size``, ``file_md5``; only the
    valid ones. ``None`` when it knows nothing."""
    values = {}
    width, height = _positive_int(media.pixel_width), _positive_int(media.pixel_height)
    if width and height:
        values.update(pixel_width=width, pixel_height=height)
    size = _positive_int(media.file_size)
    if size:
        values.update(file_size=size)
    md5 = _md5(getattr(media, 'file_md5', None))
    if md5:
        values.update(file_md5=md5)
    return values or None


def db_duration_resolver(file_name):
    """Resolve a media ``unix_name`` to its stored duration string (or ``None``).

    Raises ``KeyError`` when no ``Media`` row exists for *file_name*, so the
    walk can distinguish an orphaned reference from a present-but-NULL duration.
    """
    try:
        media = Media.get(Media.unix_name == file_name)
    except DoesNotExist:
        raise KeyError(file_name)
    return media.duration


def db_dimensions_resolver(file_name):
    """Resolve a media ``unix_name`` to its stored size (see
    :func:`dimensions_of_row`), or ``None`` when unknown. Read-only: no probe.

    Raises ``KeyError`` when no ``Media`` row exists for *file_name*.
    """
    try:
        media = Media.get(Media.unix_name == file_name)
    except DoesNotExist:
        raise KeyError(file_name)
    return dimensions_of_row(media)


# Cues that can carry a ``Media`` block. A cue whose ``class`` is none of
# audio / video / dmx decodes as a bare ``MediaCue``, so it is listed too: a
# walker that only knows the three named classes skips it.
MEDIA_CUES = (AudioCue, VideoCue, DmxCue, MediaCue)


def fix_media_durations_in_contents(contents, resolver, dimensions_resolver=None):
    """Overwrite each media cue's ``Media`` values from the library, on the object.

    Shared by the WebSocket save path (:meth:`CuemsDBProject._fix_media_durations`)
    and the standalone duration-repair tool, so both trust the same DB source
    of truth and walk cue trees identically. The library will not fill these
    values from ``project-manager.db``; this is the one place that does.

    For every media cue's ``Media`` block, in this order (002 FR-038 to FR-041):

    1. each stored value present (``pixel_width``, ``pixel_height``,
       ``file_size``, ``file_md5``) is normalised with ``_valid``; one that is
       not valid, or that the cue may not carry (a pixel size on an
       ``AudioCue``), is cleared. ``CuemsScript.from_json`` stores a client's
       values raw, and ``CuemsScript.save`` would refuse the whole document;
    2. the duration, from *resolver* (an orphan stops here, untouched);
    3. the stored values, from *dimensions_resolver* when given: they replace
       the client's, for the keys the cue may carry; an unknown one (``None``)
       clears it.

    Every value is written through the ``Media`` attribute setters, never by
    item assignment (M11), and cleared by assigning ``None``. One block that
    fails is logged, counted in ``stats.errors`` and skipped; the walk goes on.

    Args:
        contents: ``CueList.contents`` of a ``CuemsScript`` (nested ``CueList``
            objects are walked).
        resolver: callable ``file_name -> duration_str_or_None``; must raise
            ``KeyError`` for a media file absent from the DB.
        dimensions_resolver: optional callable ``file_name -> dict | None``
            (see :func:`db_dimensions_resolver`); ``KeyError`` for an orphan.

    Returns:
        :class:`DurationFixStats`.
    """
    stats = DurationFixStats()
    _walk_media_durations(contents, resolver, dimensions_resolver, stats)
    return stats


def _allowed_keys(cue):
    """The stored keys *cue* may carry, by cue identity (FR-039): size and MD5
    on an ``AudioCue``; all four on anything else, a bare ``MediaCue`` (an
    unknown ``class``) included."""
    return STORED_KEYS[len(PIXEL_KEYS):] if isinstance(cue, AudioCue) else STORED_KEYS


def _set_stored(media, values, cue):
    """Make *media*'s stored values exactly *values* (``None``: none), keeping
    only what *cue* may carry. Attribute assignment only; ``None`` clears."""
    allowed = _allowed_keys(cue)
    for key in STORED_KEYS:
        setattr(media, key, _valid(key, (values or {}).get(key)) if key in allowed else None)


def _fix_one_media(cue, media, resolver, dimensions_resolver, stats):
    file_name = media.get('file_name')
    try:
        # 1. Never let an invalid client value reach the schema, and never a
        #    pixel size on an AudioCue. These are derived values the row owns
        #    (FR-040): a drop or a normalisation is logged, not refused.
        allowed = _allowed_keys(cue)
        for key in STORED_KEYS:
            if key not in media:
                continue
            raw = media.get(key)
            value = _valid(key, raw) if key in allowed else None
            if value is None or value != raw or type(value) is not type(raw):
                Logger.warning(
                    f"media value {key}={raw!r} of cue {cue.get('id')} ({file_name!r}) "
                    + ('dropped' if value is None else f'normalised to {value!r}'))
                setattr(media, key, value)
        if not file_name:
            return
        stats.media_refs += 1
        # 2. Duration.
        try:
            duration = resolver(file_name)
        except KeyError:
            stats.orphans.append(file_name)  # media not in DB; keep original
            return
        if duration:
            new_value = CTimecode(str(duration))
            previous = media.get('duration')
            if previous != new_value:
                media.duration = new_value
                stats.replacements += 1
                stats.changes.append((file_name, previous, new_value))
        # 3. The stored values, from the row.
        if dimensions_resolver is not None:
            try:
                values = dimensions_resolver(file_name)
            except KeyError:
                return
            _set_stored(media, values, cue)
    except Exception as e:
        stats.errors.append(file_name)
        Logger.warning(f'media values fix skipped for {file_name!r} (cue {cue.get("id")}): '
                       f'{type(e).__name__}: {e}')


def _walk_media_durations(contents, resolver, dimensions_resolver, stats):
    for cue in contents or ():
        if isinstance(cue, CueList):
            _walk_media_durations(cue.contents, resolver, dimensions_resolver, stats)
            continue
        if not isinstance(cue, MEDIA_CUES):
            continue
        media = cue.get('Media')
        if not media:
            continue
        _fix_one_media(cue, media, resolver, dimensions_resolver, stats)


def _media_cues(contents):
    """Every media cue of *contents*, nested ``CueList`` objects walked."""
    for cue in contents or ():
        if isinstance(cue, CueList):
            yield from _media_cues(cue.contents)
        elif isinstance(cue, MEDIA_CUES):
            yield cue


def _stale_entries(cue, media, row):
    """The values PRESENT in *media* that the fill would change (002 FR-043).

    The decisions of ``0b291d1`` ``stale_changes``, on the object: the same
    as :func:`_fix_one_media`'s. A value that is only missing (a project
    written before rc15) is not stale: the next save adds it. An orphan (no
    *row*) is compared with nothing; only a value its cue may not carry is
    stale there. ``stored`` and ``current`` are strings, ``current`` ``None``
    when the save will remove the value.
    """
    file_name = media.get('file_name')
    allowed = _allowed_keys(cue)
    present = {key: media.get(key) for key in STORED_KEYS if key in media}
    known = row is not None
    expected = ({key: value for key, value in (dimensions_of_row(row) or {}).items() if key in allowed}
                if known else {})
    wrong = {key for key, value in present.items()
             if key not in allowed or _valid(key, value) is None
             or (known and _valid(key, value) != expected.get(key))}
    entry = lambda field, stored, current: {
        'cue_id': str(cue.get('id')), 'file_name': file_name, 'field': field,
        'stored': stored, 'current': current}
    entries = []
    if known and row.duration and media.get('duration') is not None:
        current = CTimecode(str(row.duration))
        if media.get('duration') != current:
            entries.append(entry('duration', str(media.get('duration')), str(current)))
    if wrong & set(PIXEL_KEYS):
        stored = f"{present.get('pixel_width', '?')}x{present.get('pixel_height', '?')}"
        current = (f"{expected['pixel_width']}x{expected['pixel_height']}"
                   if 'pixel_width' in expected else None)
        entries.append(entry('pixel_size', stored, current))
    for key in ('file_size', 'file_md5'):
        if key in wrong:
            current = expected.get(key)
            entries.append(entry(key, str(present[key]), None if current is None else str(current)))
    return entries


def _rows_digest(rows):
    """md5 of the canonical JSON of the rows a comparison read (FR-045)."""
    tuples = sorted(
        (row.unix_name, None if row.duration is None else str(row.duration),
         row.pixel_width, row.pixel_height, row.file_size, row.file_md5)
        for row in rows if row is not None)
    return hashlib.md5(json.dumps(tuples, separators=(',', ':')).encode()).hexdigest()


def media_staleness(script):
    """``(media_repairs, media_rows_digest)`` of a loaded *script* (002 FR-043, FR-045).

    Compares each media cue's present stored values with its file's library
    row, on the object: no probe, no second reader of the file.
    ``media_repairs`` lists ``{cue_id, file_name, field, stored, current}``
    (see :func:`_stale_entries`); ``media_rows_digest`` changes whenever a
    row the comparison read changes, or a row appears for a file that had
    none. Reads the database: call it in the executor.
    """
    rows, repairs = {}, []
    for cue in _media_cues(script.cuelist.contents):
        media = cue.get('Media')
        file_name = media.get('file_name') if media else None
        if not file_name:
            continue
        if file_name not in rows:
            rows[file_name] = Media.get_or_none(Media.unix_name == file_name)
        repairs.extend(_stale_entries(cue, media, rows[file_name]))
    return repairs, _rows_digest(rows.values())


def _fade_duration_ms(duration):
    """Best-effort milliseconds for a FadeCue ``duration`` JSON value.

    *duration* is the raw JSON shape the frontend/XML round-trip produces:
    ``{'CTimecode': '<timecode string>'}`` (dict possibly empty or with a
    ``None`` value) or ``None``.  Parsing delegates to the real ``CTimecode``
    on purpose: its millisecond semantics are literal and non-obvious
    (``'.3'`` is 3 ms, not 300) and some shapes raise (``'00:00:03'`` →
    ``IndexError``), so a hand-rolled parser here would silently diverge from
    what the engine computes when it loads the same string.  Any parse
    failure returns ``None``.
    """
    if isinstance(duration, dict):
        duration = duration.get('CTimecode')
    if not isinstance(duration, str) or not duration.strip():
        return None
    try:
        return CTimecode(duration).milliseconds_rounded
    except Exception:
        return None


def _walk_fade_durations(contents, offenders):
    if not contents:
        return
    for item in contents:
        if not isinstance(item, dict):
            continue
        if 'CueList' in item:
            _walk_fade_durations(item['CueList'].get('contents', []), offenders)
        if 'FadeCue' in item:
            cue_data = item['FadeCue']
            if not isinstance(cue_data, dict):
                continue
            ms = _fade_duration_ms(cue_data.get('duration'))
            if ms is None or ms <= 0:
                reason = (
                    'missing or unparseable'
                    if ms is None else 'must be greater than zero'
                )
                offenders.append(
                    (cue_data.get('name'), cue_data.get('id'), reason)
                )


MEDIA_CUE_KEYS = ('AudioCue', 'VideoCue')


def _walk_media_cues(contents, offenders, media_exists):
    if not contents:
        return
    for item in contents:
        if not isinstance(item, dict):
            continue
        if 'CueList' in item and isinstance(item['CueList'], dict):
            _walk_media_cues(item['CueList'].get('contents', []), offenders, media_exists)
        for key in MEDIA_CUE_KEYS:
            if key not in item:
                continue
            cue_data = item[key]
            if not isinstance(cue_data, dict):
                continue
            name, cue_id = cue_data.get('name'), cue_data.get('id')
            media = cue_data.get('Media')
            if not isinstance(media, dict) or not media.get('file_name'):
                offenders.append((name, cue_id, 'no media file'))
                continue
            if 'id' not in media:
                offenders.append((name, cue_id, 'media block has no id'))
                continue
            if media_exists is not None and not media_exists(media['file_name']):
                offenders.append(
                    (name, cue_id, f"media file '{media['file_name']}' does not exist")
                )


def validate_media_cues_in_contents(contents, media_exists=None):
    """Reject any AudioCue/VideoCue without a usable media block.

    Save-time gate, run BEFORE anything is written. A client that cannot
    resolve a cue's file drops the whole ``Media`` block (the frontend did
    so for files in the media trash); the shapes that then arrive are: no
    ``Media`` key, ``None``, ``{}``, or a block with an empty ``file_name``
    or no ``id``. Without this gate such a save died inside the atomic
    block with a bare ``KeyError 'file_name'`` from ``CueList.get_media``
    (cuems-utils < rc16) — and, had it not died, would have written an
    empty ``<Media/>`` and lost the cue's media for good.

    ``media_exists(file_name) -> bool`` lets the DB check that the file is
    known (trashed is fine: it can be restored; deleted cannot). Collects
    ALL offenders and raises a single ``ValueError`` whose text names them;
    the WS layer forwards it to the client as is.
    """
    offenders = []
    _walk_media_cues(contents, offenders, media_exists)
    if offenders:
        detail = '; '.join(
            f"'{name or 'unnamed'}' (id {cue_id or 'unknown'}: {reason})"
            for name, cue_id, reason in offenders
        )
        raise ValueError(f"Media cue without a usable media file: {detail}")


def validate_fade_durations_in_contents(contents):
    """Reject any FadeCue whose duration is missing, unparseable, or <= 0.

    Save-time gate, run on the raw client payload before it becomes an
    object: a zero coming from a client would otherwise reach the XML and
    later become a silent no-op at reveal (gradient-motiond drops
    ``dur <= 0`` over fire-and-forget UDP).  Collects ALL offenders and
    raises a single ``ValueError`` with the same text as before 001; the WS
    layer forwards it to the client.
    """
    offenders = []
    _walk_fade_durations(contents, offenders)
    if offenders:
        detail = '; '.join(
            f"'{name or 'unnamed'}' (id {cue_id or 'unknown'}: {reason})"
            for name, cue_id, reason in offenders
        )
        raise ValueError(
            f"FadeCue duration must be greater than zero: {detail}"
        )


#: Leftovers a project directory may hold that an export or a duplicate must not copy
#: (a script being written, a backup of an earlier release's refresh).
_NOT_COPIED = ('*.pre-refresh-*', '.*.tmp')


class CuemsDBProject(StringSanitizer):
    """Project CRUD, XML script I/O, and filesystem directory management.

    Each CueMS project lives at
    ``<projects_path>/<unix_name>/cue_script.xml``.  All mutating operations
    are wrapped in Peewee atomic transactions with rollback; filesystem
    changes are reversed on failure where possible.

    User-supplied name strings are sanitised via the inherited
    ``StringSanitizer`` methods before being used as directory names or
    stored in the database.

    Example:
        >>> db_project = CuemsDBProject(settings_dict, database)
        >>> uuid = db_project.new({"CuemsScript": {"name": "My Show", ...}}, "my-show")
        >>> project_data = db_project.load(uuid)
        >>> db_project.update(uuid, project_data)
        >>> db_project.delete(uuid)          # soft-delete → trash
        >>> db_project.restore(uuid)         # restore from trash
        >>> db_project.delete_from_trash(uuid)  # permanent delete
    """

    def __init__(self, settings_dict, db_connection):
        """Initialise paths from *settings_dict*.

        Args:
            settings_dict: Mapping consumed from ``settings.xml``.  Required
                keys: ``tmp_path``, ``library_path``, ``script_file_name``,
                ``script_schema_name``, ``project_folder_name``,
                ``trash_folder_name``, ``media_folder_name``.
            db_connection: The shared Peewee ``SqliteDatabase`` instance owned
                by ``CuemsDBManager``.

        Raises:
            KeyError: If any required key is missing from *settings_dict*.
        """
        self.db = db_connection
        self.settings_dict = settings_dict
        try:
            self.tmp_path = self.settings_dict['tmp_path']
            self.library_path = settings_dict['library_path']
            self.script_file_name = settings_dict['script_file_name']
            self.script_schema_name = settings_dict['script_schema_name']
            self.projects_path = os.path.join(self.library_path, settings_dict['project_folder_name'])
            self.trash_path = os.path.join(self.library_path, settings_dict['trash_folder_name'], settings_dict['project_folder_name'])
            self.media_path = os.path.join(self.library_path, settings_dict['media_folder_name'])
        except KeyError as e:
            Logger.error(f'can not read settings {e}')
            raise e

    def get_project_unix_name(self, uuid):
        """Return the filesystem directory name for a live (non-trashed) project.

        Args:
            uuid: Project UUID string.

        Returns:
            ``unix_name`` value from the ``Project`` DB record.

        Raises:
            NonExistentItemError: If no live project with *uuid* exists.
        """
        try:
            project = Project.get((Project.uuid == uuid) & (Project.in_trash == False))
            return project.unix_name
        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))

    def load(self, uuid, include_trash=False):
        """Load a project's script and project it for the wire, once.

        This is the ``value`` of the ``{"type": "project"}`` frame. It is
        ``script.to_wire()`` and nothing walks it afterwards. Opening does not
        write the script file.

        Args:
            uuid: Project UUID string.
            include_trash: When ``True``, also searches trashed projects.
                Defaults to ``False``.

        Returns:
            ``{"CuemsScript": {...}}`` as ``CuemsScript.to_wire()`` builds it.

        Raises:
            NonExistentItemError: If no project with *uuid* exists (or the
                project is in the trash and *include_trash* is ``False``).
            ValidationError / SchemaError / OSError: from the library load,
                unwrapped. Nothing is written in either case.
        """
        script, _report = self.load_with_report(uuid, include_trash)
        return script.to_wire()

    def open(self, uuid):
        """Open a live project for a session: its wire value and what the gate needs.

        One library load, one ``to_wire()``, and the media comparison on the
        loaded object (002 FR-043). The file is not written.

        Returns:
            ``(value, LoadReport, script_md5, media_repairs, media_rows_digest)``
            — *value* is what :meth:`load` returns; *script_md5* is the md5 of
            the bytes read for the report; the last two are
            :func:`media_staleness`'s.

        Raises:
            NonExistentItemError: no live project with *uuid*.
            DocumentLoadFailed: the library refused the document with a
                ``ValidationError`` (an unrepairable value, or a document newer
                than the library). ``SchemaError`` and ``OSError`` propagate
                unwrapped.
        """
        script, report, script_md5 = self._load_for_gate(uuid)
        media_repairs, media_rows_digest = media_staleness(script)
        return script.to_wire(), report, script_md5, media_repairs, media_rows_digest

    def inspect(self, uuid):
        """What :meth:`open` reports, without building the wire value.

        The repair gate's view of the file on disk (FR-009, FR-009a). The
        file is not written.

        Returns:
            ``(LoadReport, script_md5, media_repairs, media_rows_digest)``.

        Raises:
            As :meth:`open`.
        """
        script, report, script_md5 = self._load_for_gate(uuid)
        return (report, script_md5) + media_staleness(script)

    def media_rows_digest(self, uuid):
        """The rows digest of the script on disk now (FR-045): has a row changed since the report?"""
        return self.inspect(uuid)[3]

    def _load_for_gate(self, uuid):
        """Hash the script's bytes once, then load it with the library's report.

        The library reads the path again, so a write between the two reads
        binds the report to the earlier bytes. The next save re-hashes and
        re-derives the gate on a mismatch, so that race fails safe.
        """
        try:
            project = Project.get((Project.uuid == uuid) & (Project.in_trash == False))
        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))
        path = self.script_path(project.unix_name)
        with open(path, 'rb') as fh:
            script_md5 = hashlib.md5(fh.read()).hexdigest()
        try:
            script, report = CuemsScript.load_with_report(path)
        except SchemaError:
            raise
        except ValidationError as e:
            raise DocumentLoadFailed(path, e) from e
        return script, report, script_md5

    def load_with_report(self, uuid, include_trash=False):
        """Load a project's script object and the library's report of what the load did.

        Args:
            uuid: Project UUID string.
            include_trash: When ``True``, also searches trashed projects.

        Returns:
            ``(CuemsScript, LoadReport)`` from ``CuemsScript.load_with_report``.

        Raises:
            NonExistentItemError: as :meth:`load`.
        """
        try:
            if not include_trash:
                project = Project.get((Project.uuid == uuid) & (Project.in_trash == False))
            else:
                project = Project.get(Project.uuid == uuid)
        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))
        return self.load_xml(project.unix_name)

    def list(self):
        """Return a list of all live (non-trashed) projects, newest first.

        Returns:
            List of single-key dicts ``{uuid_str: {name, unix_name,
            description, created, modified}}``, ordered by ``created``
            descending.

        Example:
            >>> projects = db_project.list()
            >>> for entry in projects:
            ...     uuid, meta = next(iter(entry.items()))
            ...     print(uuid, meta['name'])
        """
        project_list = list()
        projects = Project.select().where(Project.in_trash == False).order_by(Project.created.desc())
        for project in projects:
            project_dict = {str(project.uuid): {'name': project.name, 'unix_name': project.unix_name, 'description': project.description, 'created': project.created, 'modified': project.modified}}
            project_list.append(project_dict)

        return project_list

    def list_trash(self):
        """Return a list of all trashed projects, newest first.

        Returns:
            Same shape as :meth:`list` but for projects where
            ``in_trash == True``.
        """
        project_trash_list = list()
        projects_trash = Project.select().where(Project.in_trash == True).order_by(Project.created.desc())
        for project in projects_trash:
            project_dict = {str(project.uuid): {'name': project.name, 'unix_name': project.unix_name, 'description': project.description, 'created': project.created, 'modified': project.modified}}
            project_trash_list.append(project_dict)

        return project_trash_list

    def update(self, uuid, data, preserve_original=False):
        """Save an edited project: update DB metadata and rewrite the script file.

        Runs inside a Peewee atomic transaction. The client payload becomes a
        ``CuemsScript`` through ``CuemsScript.from_json`` (which does not
        repair), the media durations are corrected on that object from the
        database, and ``CuemsScript.save`` validates (T1 then T2) before an
        atomic write. A violation raises before the file is touched, and the
        DB change is rolled back.

        A dangling ``target`` or ``action_target`` is not cleared here. The
        library repairs a dangling ``target`` on load and refuses a dangling
        ``action_target`` at save, with a message naming the cue.

        Args:
            uuid: Project UUID string; must match ``data['CuemsScript']['id']``.
            data: ``CuemsScript`` dict as received from the frontend over
                WebSocket.
            preserve_original: Move the script now on disk into the trash
                before the first overwrite. The session sets it when the
                library repaired or converted that file on load, so the
                original is recoverable. If the move fails nothing is saved;
                if the save fails the original is moved back.

        Raises:
            NonExistentItemError: If the project does not exist or is in the
                trash.
            ValueError: A FadeCue duration is missing, unparseable or ``<= 0``.
            OriginalNotPreserved: *preserve_original* and the move failed.
            Exception: Re-raises any error after rolling back the transaction.
        """
        try:
            project = Project.get((Project.uuid == uuid) & (Project.in_trash == False))
        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))

        try:
            del data['CuemsScript']['unix_name']
        except KeyError:
            pass

        # Reject zero/unparseable FadeCue durations on the raw payload, before
        # it becomes an object: a saved zero later becomes a silent no-op at
        # reveal (gradient-motiond drops dur <= 0).
        validate_fade_durations_in_contents(
            (data.get('CuemsScript', {}).get('CueList') or {}).get('contents') or []
        )

        with self.db.atomic() as transaction:
            try:
                project.name = StringSanitizer.sanitize_name(data['CuemsScript']['name'])
                now = new_datetime()
                data['CuemsScript']['modified'] = now
                project.modified = now
                project.description = StringSanitizer.sanitize_text_size(data['CuemsScript']['description'])
                project.save()
                project_object = CuemsScript.from_json(data)
                # SAFETY NET: older frontends send Media.duration as
                # '00:00:00.000'; overwrite from the DB (source of truth).
                # Remove only once ALL deployed frontends copy the real
                # duration from the file_list payload.
                self._fix_media_durations(project_object)
                self.update_media_relations(project, project_object)
                if preserve_original:
                    self._save_preserving_original(project.unix_name, project_object)
                else:
                    self.save_xml(project.unix_name, project_object)
            except Exception as e:
                Logger.error("error: {} {} trying to update  project, rolling back database update".format(type(e), e))
                transaction.rollback()
                raise e

    def _save_preserving_original(self, unix_name, project_object):
        """Move the script on disk into the trash, then save; undo the move if the save fails.

        The trashed copy is named ``<unix_name>_<YYYYmmddTHHMMSS>_<script_file_name>``
        so the project and the date are recoverable from the name alone.
        """
        path = self.script_path(unix_name)
        name = f"{unix_name}_{datetime.now().strftime('%Y%m%dT%H%M%S')}_{self.script_file_name}"
        try:
            os.makedirs(self.trash_path, exist_ok=True)
            trashed = CopyMoveVersioned.move(path, self.trash_path, name)
        except Exception as e:
            raise OriginalNotPreserved(f"could not move {path} into {self.trash_path}: {e}") from e
        Logger.info(f'original script of {unix_name} preserved as {os.path.join(self.trash_path, trashed)}')
        try:
            self.save_xml(unix_name, project_object)
        except Exception:
            shutil.move(os.path.join(self.trash_path, trashed), path)
            raise

    # SAFETY NET (see update()): overwrite frontend-sent Media values from
    # the DB. Delegates to the module-level fix_media_durations_in_contents so
    # the repair tool and this path share one walk.
    def _fix_media_durations(self, project_object):
        """Overwrite each media cue's ``Media`` values from the database, on the object.

        The DB is the source of truth for a media file's duration, pixel size,
        size and MD5 (002 FR-041). This corrects the legacy frontend behaviour
        of sending ``00:00:00.000``, and writes the values the upload stored.
        The resolvers only read the database: no probe, no file read (Q5).
        Orphaned media references (no ``Media`` row) are logged, not modified.

        Args:
            project_object: ``CuemsScript`` built from the client payload.
        """
        try:
            stats = fix_media_durations_in_contents(project_object.cuelist.contents, db_duration_resolver,
                                                    db_dimensions_resolver)
        except Exception as e:
            Logger.warning(f"Could not fix media values: {e}")
            return
        if stats.orphans:
            Logger.warning(
                f"media values fix: {len(stats.orphans)} cue(s) reference "
                f"media not in DB (values left as-is): {stats.orphans}")
        if stats.errors:
            Logger.warning(
                f"media values fix: {len(stats.errors)} cue(s) could not be corrected "
                f"and keep the client's values: {stats.errors}")

    def new(self, data, unix_name):
        """Create a new project: allocate a UUID, write the XML, insert the DB row.

        The project directory ``<projects_path>/<unix_name>/`` and its
        ``cue_script.xml`` are created inside an atomic transaction.  The
        directory is removed on rollback.

        Args:
            data: ``CuemsScript`` dict from the frontend; ``id``, ``created``,
                and ``modified`` are assigned here and written back into
                *data* before parsing.
            unix_name: Raw directory name candidate supplied by the frontend;
                sanitised via ``StringSanitizer.sanitize_dir_permit_increment``
                before use.

        Returns:
            New project UUID string.

        Raises:
            IntegrityError: If ``name`` or ``unix_name`` already exists.
            KeyError: If ``data['CuemsScript']`` is missing required fields.
            Exception: Re-raises after rollback and directory cleanup.
        """
        try:
            unix_name = StringSanitizer.sanitize_dir_permit_increment(unix_name)
        except Exception as e:
            raise e

        try:
            project_uuid = str(new_uuid())
            data['CuemsScript']['id'] = project_uuid
            now = new_datetime()
            data['CuemsScript']['created'] = now
            data['CuemsScript']['modified'] = now
        except KeyError as e:
            Logger.error("error: Missing {} ;trying to make new  project, rolling back database insert".format(e))
            raise e
        except Exception as e:
            Logger.error("error: {} {} ;trying to read  project data".format(type(e), e))
            raise e

        # Same save-time gate as update() — see validate_fade_durations_in_contents.
        validate_fade_durations_in_contents(
            (data.get('CuemsScript', {}).get('CueList') or {}).get('contents') or []
        )

        with self.db.atomic() as transaction:
            try:
                project = Project.create(uuid=project_uuid, unix_name=unix_name, name=StringSanitizer.sanitize_name(data['CuemsScript']['name']), description=StringSanitizer.sanitize_text_size(data['CuemsScript']['description']), created=now, modified=now)
                os.mkdir(os.path.join(self.projects_path, unix_name))
                Logger.debug('data is now: {}'.format(data))
                project_object = CuemsScript.from_json(data)
                Logger.debug(f'project_object is now: {type(project_object)},{project_object}')
                self.add_media_relations(project, project_object)
                self.save_xml(unix_name, project_object)
                return project_uuid
            except IntegrityError as e:
                transaction.rollback()
                Logger.error("error: {} {} ;name or unix_name already exists, rolling back database insert".format(type(e), e))
                raise e
            except Exception as e:
                transaction.rollback()
                Logger.error("error: {} {} ;trying to make new  project, rolling back database insert".format(type(e), e))

                if os.path.exists(os.path.join(self.projects_path, unix_name)):
                    shutil.rmtree(os.path.join(self.projects_path, unix_name))

                raise e

    def _is_name_available(self, unix_name, display_name):
        """Check that both unix_name and display_name are free in the DB
        (including trashed records, since unique constraints span all rows).
        """
        return not Project.select().where(
            (Project.unix_name == unix_name) | (Project.name == display_name)
        ).exists()

    def duplicate(self, uuid):
        """Duplicate a project: copy the directory and create a new DB record.

        The copy is named ``<original_name> - Copy``; a numeric suffix
        ``(N)`` is appended if the name is taken by another live or trashed
        record.  The source script is opened with the library's load (in
        memory; the source file is not written), its ``id``, ``name`` and
        ``modified`` are set to the new DB record's, and it is saved under the
        new directory only.  A source the library refuses to load is not
        duplicated; the library's error is raised unchanged.

        Args:
            uuid: UUID of the project to duplicate; must be a live project.

        Returns:
            ``(new project UUID string, LoadReport of the source)``.

        Raises:
            NonExistentItemError: If the source project does not exist.
            Exception: Re-raises after rollback and copy cleanup.
        """
        try:
            project = Project.get((Project.uuid == uuid) & (Project.in_trash == False))
            with self.db.atomic() as transaction:
                try:
                    new_unix_name = None
                    project_path = os.path.join(self.projects_path, project.unix_name)
                    base_unix = project.unix_name
                    base_display = project.name + ' - Copy'

                    # Find a name pair unique on both filesystem AND DB
                    # (trashed projects keep their DB records and unique constraints)
                    candidate_unix = base_unix
                    candidate_display = base_display
                    i = 0
                    # The source, in memory. Its file is not written here.
                    project_object, source_report = self.load_xml(base_unix)
                    while (os.path.exists(os.path.join(self.projects_path, candidate_unix))
                           or not self._is_name_available(candidate_unix, candidate_display)):
                        i += 1
                        candidate_unix = f"{base_unix}-{i:03d}"
                        candidate_display = f"{base_display} ({i})"

                    shutil.copytree(project_path, os.path.join(self.projects_path, candidate_unix),
                                    ignore=shutil.ignore_patterns(*_NOT_COPIED))
                    new_unix_name = candidate_unix

                    project.unix_name = new_unix_name
                    new_project_uuid = str(new_uuid())
                    project.uuid = new_project_uuid
                    project.name = candidate_display
                    project.modified = new_datetime()
                    project.save(force_insert=True)

                    dup_project = Project.get(Project.uuid == new_project_uuid)
                    project_object.id = new_project_uuid
                    project_object.name = project.name
                    project_object.modified = project.modified
                    # NO fade-duration validation here on purpose: the source is
                    # an existing project — legacy scripts must stay duplicable
                    # beyond what the library load itself refuses; the engine's
                    # reveal guard covers them.
                    self.add_media_relations(dup_project, project_object)
                    self.save_xml(new_unix_name, project_object)
                    return new_project_uuid, source_report
                except Exception as e:
                    Logger.error("error: {} {}; trying to duplicate  project, rolling back database update".format(type(e), e))
                    transaction.rollback()
                    if new_unix_name is None:  # if move or copy where not successful with don't need to clean and can end here forwarding the exception, else continue cleaning and then forward the exception
                        raise e
                    if os.path.exists(os.path.join(self.projects_path, new_unix_name)):
                        shutil.rmtree(os.path.join(self.projects_path, new_unix_name))
                    raise e

        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))

    def export(self, uuid):
        tmp_project_path = None
        output_filename = None
        try:
            try:
                project = Project.get(Project.uuid==uuid)
            except DoesNotExist:
                raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))

            unix_name = project.unix_name
            project_path = os.path.join(self.projects_path, unix_name, self.script_file_name)
            project_medias = ProjectMedia.select().where(ProjectMedia.project == project)
            tmp_project_path = os.path.join(self.tmp_path, unix_name)
            if not os.path.exists(tmp_project_path):
                os.makedirs(tmp_project_path)
            Logger.debug('exporting project {} to {}'.format(unix_name, tmp_project_path))
            shutil.copy(project_path, tmp_project_path)

            project_medias = prefetch(project_medias, Media)
            if project_medias:
                Logger.debug('project {} has media relations, exporting them'.format(unix_name))
                tmp_media_path = os.path.join(tmp_project_path, 'media')
                os.makedirs(tmp_media_path)
                for media in project_medias:
                    if media.media is None:
                        # A file deleted for good, still named by the project
                        # until it is re-uploaded (869fat84r D20).
                        Logger.warning(f'project {unix_name} uses {media.media_filename}, which '
                                       'is no longer in the library: not exported')
                        continue
                    media_path = os.path.join(self.media_path, media.media.unix_name)
                    try:
                        shutil.copy(media_path, tmp_media_path)
                        Logger.debug('copying media {} to {}'.format(media.media.unix_name, tmp_media_path))
                    except Exception as e:
                        Logger.error("error: {} {}; copying media to project export dir".format(type(e), e))
                        raise e
            else:
                Logger.debug('project {} has no media relations, skipping media export'.format(unix_name))

            shutil.make_archive(tmp_project_path, 'zip', self.tmp_path, unix_name)
            output_filename = unix_name + '.zip'
            server_export_path = os.path.join(self.settings_dict['html_root_path'], self.settings_dict['export_folder_name'])
            try:
                dest_filename = CopyMoveVersioned.move(os.path.join(self.tmp_path, output_filename), server_export_path, output_filename)
                return os.path.join(self.settings_dict['export_folder_name'], dest_filename)
            except Exception as e:
                Logger.error("error: {} {}; moving exported project to exports folder".format(type(e), e))
                raise e
        except Exception as e:
            Logger.error("error: {} {}; exporting project".format(type(e), e))
            raise e
        finally:
            if tmp_project_path is not None and os.path.exists(tmp_project_path):
                shutil.rmtree(tmp_project_path)
                Logger.debug('cleaning tmp project export folder: {}'.format(tmp_project_path))
            if output_filename is not None and os.path.exists(os.path.join(self.tmp_path, output_filename)):
                os.remove(os.path.join(self.tmp_path, output_filename))
                Logger.debug('cleaning tmp project export file: {}'.format(os.path.join(self.tmp_path, output_filename)))

    def delete(self, uuid):
        """Soft-delete a project by moving it to the trash directory.

        The project directory is moved via ``CopyMoveVersioned.move`` to
        ``<trash_path>/``.  The DB row's ``in_trash`` flag is set to ``True``
        atomically.  On any failure the directory is moved back and the
        transaction is rolled back.

        Args:
            uuid: UUID of the live project to trash.

        Raises:
            NonExistentItemError: If no live project with *uuid* exists.
            Exception: Re-raises after rollback and filesystem cleanup.
        """
        try:
            project = Project.get((Project.uuid == uuid) & (Project.in_trash == False))
            with self.db.atomic() as transaction:
                try:
                    dest_filename = None
                    file_path = os.path.join(self.projects_path, project.unix_name)
                    dest_filename = CopyMoveVersioned.move(file_path, self.trash_path, project.unix_name)
                    project.in_trash = True
                    project.save()
                    Logger.debug('updating instance in db: {}'.format(project))
                except Exception as e:
                    Logger.error("error: {} {}; trying to move file to trash, rolling back database".format(type(e), e))
                    transaction.rollback()
                    if dest_filename is None:  # if move or copy where not successful with don't need to clean and can end here forwarding the exception, else continue cleaning and then forward the exception
                        raise e
                    if os.path.exists(os.path.join(self.trash_path, dest_filename)):
                        shutil.move(os.path.join(self.trash_path, dest_filename), os.path.join(self.projects_path, project.unix_name))
                    raise e

        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))

    def restore(self, uuid):
        """Restore a trashed project back to the active projects directory.

        Moves the directory from ``<trash_path>/`` to ``<projects_path>/``
        via ``CopyMoveVersioned.move``, which handles name collisions by
        appending a numeric suffix.  The DB record's ``unix_name`` is updated
        to the actual destination name and ``in_trash`` is set to ``False``.

        Args:
            uuid: UUID of the trashed project to restore.

        Raises:
            NonExistentItemError: If no trashed project with *uuid* exists.
            Exception: Re-raises after rollback and filesystem cleanup.
        """
        try:
            project_trash = Project.get((Project.uuid == uuid) & (Project.in_trash == True))

            with self.db.atomic() as transaction:
                try:
                    dest_filename = None
                    project_path = os.path.join(self.trash_path, project_trash.unix_name)
                    dest_filename = CopyMoveVersioned.move(project_path, self.projects_path, project_trash.unix_name)
                    project_trash.unix_name = dest_filename
                    project_trash.in_trash = False
                    project_trash.save()
                    Logger.debug('updating instance in db: {}'.format(project_trash))
                except Exception as e:
                    Logger.error("error: {} {}; trying to move file to trash, rolling back database".format(type(e), e))
                    transaction.rollback()
                    if dest_filename is None:  # if move or copy where not successful with don't need to clean and can end here forwarding the exception, else continue cleaning and then forward the exception
                        raise e
                    if os.path.exists(os.path.join(self.projects_path, dest_filename)):
                        shutil.move(os.path.join(self.projects_path, dest_filename), os.path.join(self.trash_path, project_path.unix_name))
                    raise e
        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))

    def delete_from_trash(self, uuid):
        """Permanently delete a trashed project: remove the DB record and directory.

        Calls ``project.delete_instance(recursive=True)`` to cascade-delete
        ``ProjectMedia`` join rows, then removes the project directory tree
        with ``shutil.rmtree``.

        Args:
            uuid: UUID of a project that is currently in the trash.

        Raises:
            NonExistentItemError: If no trashed project with *uuid* exists.
            Exception: Re-raises after rolling back the transaction (directory
                may already be gone at that point).
        """
        try:
            project = Project.get((Project.uuid == uuid) & (Project.in_trash == True))

            with self.db.atomic() as transaction:
                try:
                    project_path = os.path.join(self.trash_path, project.unix_name)
                    project.delete_instance(recursive=True)
                    shutil.rmtree(project_path)  # non empty dir, must use rmtree
                    Logger.debug('deleting project from trash: {}'.format(project))
                except Exception as e:
                    Logger.error("error: {} {}; trying to delete project to trash, rolling back database".format(type(e), e))
                    transaction.rollback()
                    raise e
        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))

    def add_media_relations(self, project, project_object):
        """Create ``ProjectMedia`` join rows for all media referenced by *project_object*.

        Args:
            project: ``Project`` ORM instance.
            project_object: ``CuemsScript`` object whose ``get_media_filenames()``
                returns the set of ``unix_name`` strings to link.
        """
        media_filenames_list = project_object.get_media_filenames()
        for media_name in media_filenames_list:
            media = Media.get(Media.unix_name == media_name)
            ProjectMedia.create(project=project, media=media, media_filename=media_name)

    def update_media_relations(self, project, project_object):
        """Diff and sync ``ProjectMedia`` join rows after a project save.

        Computes the symmetric difference between the old and new media sets,
        then removes stale ``ProjectMedia`` rows and creates new ones.

        Args:
            project: ``Project`` ORM instance being saved.
            project_object: ``CuemsScript`` object reflecting the new cue
                tree after the save.
        """
        Logger.debug('updating media relations for project: {}'.format(project.unix_name))
        old_media_query = project.medias()
        old_media_dict = dict()
        Logger.debug('query done')
        for media in old_media_query:
            old_media_dict[media.unix_name] = str(media.uuid)
        old_media_list = list(old_media_dict.keys())
        Logger.debug('old media list: {}'.format(old_media_list))
        media_list = project_object.get_media_filenames()
        Logger.debug('media list: {}'.format(media_list))

        remove_set = set(old_media_list).difference(media_list)
        add_set = set(media_list).difference(old_media_list)

        Logger.debug('media remove list: {}'.format(remove_set))
        Logger.debug('media add list: {}'.format(add_set))

        if remove_set:
            for media_unix_name in remove_set:
                ProjectMedia.delete().where((ProjectMedia.project == project) & (ProjectMedia.media == old_media_dict[media_unix_name])).execute()

        if add_set:
            for media_unix_name in add_set:
                media = Media.select(Media.uuid).where(Media.unix_name == media_unix_name).get()
                ProjectMedia.create(project=project, media=media, media_filename=media_unix_name)

    def update_projects_existed_media(self, project_uuid, media_filename):
        """Re-link a re-uploaded media file to the projects that referenced it by filename.

        Called after ``CuemsUpload`` detects that *media_filename* was already
        referenced by one or more projects.  Reads the XML, finds matching
        cues, and reconciles the stored media UUID with what is now in the DB.

        Args:
            project_uuid: UUID of the project to update.
            media_filename: ``unix_name`` of the re-uploaded media file.
        """
        project_object, _report = self.load_with_report(project_uuid, include_trash=True)
        media_dict = project_object.get_media()
        matching_media_dict = dict()
        for cue_uuid, media_object in media_dict.items():
            for media_uiid, project_media_filename in media_object.items():
                if media_filename == project_media_filename:
                    matching_media_dict[cue_uuid] = media_object

        if matching_media_dict:
            Logger.debug('found cues with media filename: {} in project: {}'.format(media_filename, project_uuid))
            first_media_object = next(iter(matching_media_dict.values()))
            old_media_uuid = next(iter(first_media_object.keys()))
            # TODO: manage if  all media with same filename have the same uuid  SHOULD BE TRUE
            for cue_uuid, media in matching_media_dict.items():
                for media_uuid, media_filename in media.items():
                    if media_uuid != old_media_uuid:
                        Logger.warning('found different media uuid for same media filename: {} in project {},  cue {}, using first found: {}'.format(media_filename, project_uuid, cue_uuid, old_media_uuid))
            try:
                self.update_existed_media_uuid(media_filename, old_media_uuid)
            except IntegrityError:
                Logger.warning('error updating media uuid for media filename: {} from project: {}. Media uuid inconsistency detected'.format(media_filename, project_uuid))
            self.deletele_mising_media_references(media_filename)
            project = Project.get(Project.uuid == project_uuid)
            self.update_media_relations(project, project_object)
        else:
            Logger.warning('no cues found for media filename: {}'.format(media_filename))

    def update_existed_media_uuid(self, media_filename, old_media_uuid):
        """Overwrite the UUID of a ``Media`` row to match the value recorded in project XML.

        Used when a re-uploaded file produces a new UUID in the DB that differs
        from the UUID stored inside existing project XML files.

        Args:
            media_filename: ``unix_name`` identifying the ``Media`` row.
            old_media_uuid: The UUID string to assign (taken from the XML).

        Raises:
            NonExistentItemError: If no ``Media`` row has *media_filename*.
        """
        Logger.debug('updating media uuid for media filename: {} with old uuid: {}'.format(media_filename, old_media_uuid))
        try:
            media = Media.get(Media.unix_name == media_filename)
            with self.db.atomic() as transaction:
                try:
                    Media.update(uuid=old_media_uuid).where(Media.unix_name == media_filename).execute()
                except Exception as e:
                    Logger.error("error: {} {}; trying to update media uuid, rolling back database update".format(type(e), e))
                    transaction.rollback()
                    raise e
        except DoesNotExist:
            raise NonExistentItemError("item with unix_name: {} does not exist".format(media_filename))

    def deletele_mising_media_references(self, media_filename):
        """Delete ``ProjectMedia`` rows whose ``media_id`` FK is NULL for *media_filename*.

        Cleans up dangling join rows left when a ``Media`` record was replaced
        by a re-upload.

        Args:
            media_filename: ``unix_name`` to filter on.
        """
        Logger.debug('deleting missing media references for media filename: {}'.format(media_filename))
        # Parenthesised: Python's ``&`` binds tighter than ``==``. (It was
        # ``and``, which deleted every dangling row of every file.)
        missing_media_project_refs = ProjectMedia.delete().where(
            (ProjectMedia.media_filename == media_filename) & (ProjectMedia.media.is_null())
        ).execute()

    def script_path(self, unix_name):
        """``<projects_path>/<unix_name>/<script_file_name>``."""
        return os.path.join(self.projects_path, unix_name, self.script_file_name)

    def save_xml(self, unix_name, project_object):
        """Write *project_object* to the project's script file.

        ``CuemsScript.save`` validates (T1, then T2) and raises before writing
        anything; the write itself is a temp file in the target directory
        renamed over the target, so a reader sees the old file or the new one.

        Args:
            unix_name: Project directory name.
            project_object: ``CuemsScript`` instance to persist.
        """
        project_object.save(self.script_path(unix_name))

    def load_xml(self, unix_name):
        """Read the project's script file through the library's public load.

        Conversion and repair, when the library applies them, happen in
        memory. The file is not written.

        Args:
            unix_name: Project directory name.

        Returns:
            ``(CuemsScript, LoadReport)`` from ``CuemsScript.load_with_report``.
        """
        return CuemsScript.load_with_report(self.script_path(unix_name))
