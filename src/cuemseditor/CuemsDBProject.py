# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
import contextlib
import os
import time
import traceback
import shutil
import xml.etree.ElementTree as ET
from peewee import DoesNotExist, IntegrityError, prefetch

from cuemsutils.tools.StringSanitizer import StringSanitizer
from cuemsutils.tools.CopyMoveVersioned import CopyMoveVersioned
from cuemsutils.tools.CTimecode import CTimecode
from cuemsutils.xml.Parsers import CuemsParser
from cuemsutils.xml.XmlReaderWriter import XmlReaderWriter
from cuemsutils.helpers import new_datetime, new_uuid
from cuemsutils.log import logged, Logger


from cuemseditor.CuemsErrors import *
from cuemseditor.CuemsDBModel import Project, Media, ProjectMedia
from cuemseditor.CuemsDBMedia import (
    INDEX_STALE, INDEX_VALID, PROBE_FAILED, PROBE_OK, is_indexed_video,
    probe_dimensions, probe_media, video_index_state)


class DurationFixStats:
    """Result of a :func:`fix_media_durations_in_contents` walk.

    Attributes:
        media_refs: Number of cue ``Media`` blocks visited.
        replacements: Number of ``duration`` values actually changed.
        dimension_changes: Number of ``Media`` blocks whose stored size
            (``pixel_width`` / ``pixel_height`` / ``file_size``) changed:
            filled, replaced, or removed.
        orphans: List of ``file_name`` values referencing a media file with no
            ``Media`` row (duration left untouched — a leftover
            ``00:00:00.000`` there matches the valid timecode shape, so it is
            invisible to a pattern scan; report it explicitly instead).
        errors: ``file_name`` values whose ``Media`` block could not be
            processed (logged; the walk went on with the next cue).
    """

    def __init__(self):
        self.media_refs = 0
        self.replacements = 0
        self.dimension_changes = 0
        self.orphans = []
        self.errors = []


#: What a cue's ``Media`` stores about its file (869fat84r), in ``MediaType``
#: order: the pixel size (VideoCues only), then the file's size and MD5
#: (every media type, D18).
PIXEL_KEYS = ('pixel_width', 'pixel_height')
STORED_KEYS = PIXEL_KEYS + ('file_size', 'file_md5')
#: Kept for callers of the first version of this change.
DIMENSION_KEYS = STORED_KEYS


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
        values['file_size'] = size
    md5 = _md5(getattr(media, 'file_md5', None))
    if md5:
        values['file_md5'] = md5
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


def fix_media_durations_in_contents(contents, resolver, dimensions_resolver=None):
    """Overwrite each cue ``Media``'s duration, and VideoCues' stored size,
    from the resolvers, in place.

    Shared by the WebSocket save path (:meth:`CuemsDBProject._fix_media_durations`)
    and the standalone repair script, so both trust the same DB source of
    truth and walk cue trees identically. Each caller passes its own
    resolvers: only the save path's may probe and write the DB.

    For every ``Media`` block, in this order:

    1. a ``pixel_width`` / ``pixel_height`` / ``file_size`` that is not a
       positive integer, or a ``file_md5`` that is not 32 hex digits, is
       removed, whatever the cue: the parser assigns these keys raw, and the
       schema would reject the whole save; an AudioCue loses the pixel size
       (it belongs to VideoCues);
    2. the duration, from *resolver* (an orphan stops here, untouched);
    3. the stored values, from *dimensions_resolver* when given: the pixel
       size, size and MD5 on a VideoCue, size and MD5 on an AudioCue (D18).
       They replace the client's; ``None`` (unknown) removes them.

    One block that fails is logged and skipped; the walk goes on.

    Args:
        contents: ``CueList['contents']`` list (recursively walked).
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


def _dimensions_snapshot(media):
    return {key: media[key] for key in STORED_KEYS if key in media}


def _allowed_keys(cue_type):
    """The stored keys a cue may carry: all of them on a VideoCue, size and
    MD5 on an AudioCue (D18), all on a flat structure (type unknown)."""
    if cue_type == 'AudioCue':
        return STORED_KEYS[len(PIXEL_KEYS):]
    return STORED_KEYS


def _set_dimensions(media, values, cue_type='VideoCue'):
    """Make *media*'s stored values exactly *values* (``None``: none),
    keeping only what *cue_type* may carry."""
    for key in STORED_KEYS:
        media.pop(key, None)
    for key in _allowed_keys(cue_type):  # appended after what is there, i.e. after regions
        value = _valid(key, (values or {}).get(key))
        if value:
            media[key] = value


def _fix_one_media(cue_type, media, resolver, dimensions_resolver, stats):
    file_name = media.get('file_name')
    before = _dimensions_snapshot(media)
    try:
        # 1. Never let an invalid client value reach the schema, and never
        #    a pixel size on an AudioCue.
        allowed = _allowed_keys(cue_type)
        for key in STORED_KEYS:
            if key in media:
                value = _valid(key, media[key])
                if value is None or key not in allowed:
                    del media[key]
                else:
                    media[key] = value
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
            new_value = str(duration)
            if media.get('duration') != new_value:
                media['duration'] = new_value
                stats.replacements += 1
        # 3. The stored values, from the DB, on Audio and Video cues.
        if cue_type in ('VideoCue', 'AudioCue') and dimensions_resolver is not None:
            try:
                values = dimensions_resolver(file_name)
            except KeyError:
                return
            _set_dimensions(media, values, cue_type)
    except Exception as e:
        stats.errors.append(file_name)
        Logger.warning(f'media metadata fix skipped for {file_name!r}: '
                       f'{type(e).__name__}: {e}')
    finally:
        if _dimensions_snapshot(media) != before:
            stats.dimension_changes += 1


def _walk_media_durations(contents, resolver, dimensions_resolver, stats):
    if not contents:
        return
    for item in contents:
        if not isinstance(item, dict):
            continue
        # Handle nested CueLists
        if 'CueList' in item:
            _walk_media_durations(item['CueList'].get('contents', []), resolver,
                                  dimensions_resolver, stats)

        # Check for AudioCue or VideoCue wrappers
        if 'AudioCue' in item:
            cue_type, cue_data = 'AudioCue', item['AudioCue']
        elif 'VideoCue' in item:
            cue_type, cue_data = 'VideoCue', item['VideoCue']
        else:
            cue_type, cue_data = None, item  # flat structure

        media = cue_data.get('Media') if isinstance(cue_data, dict) else None
        if media and isinstance(media, dict):
            _fix_one_media(cue_type, media, resolver, dimensions_resolver, stats)


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


def validate_fade_durations_in_contents(contents):
    """Reject any FadeCue whose duration is missing, unparseable, or <= 0.

    Save-time gate: ``CuemsParser``/``GenericParser`` assigns via
    ``dict.__setitem__``, bypassing ``FadeCue.set_duration``'s own
    positive-and-non-zero rule, so a zero coming from a client would reach
    the XML and later become a silent no-op at reveal (gradient-motiond
    drops ``dur <= 0`` over fire-and-forget UDP).  Collects ALL offenders and
    raises a single ``ValueError``; the WS layer forwards the text to the
    client.
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


# --- A media file that changed after its values were stored (869fat84r D20) --
#
# Before a project is loaded (CuemsMediaRefresh) and when a save meets a row
# with no stored size or a changed file, the editor checks the files a project
# uses against their rows, re-probes what changed and corrects the rows. It
# never rewrites a project on its own (D21): it reports the values a project
# still holds that no longer match (media_check_report, shown by the UI), and
# the next save writes them. Design: cuems-RELATIONS
# Plans/2026-10-01-engine-late-go-media-probe.md §7, §8.

#: Seconds a load (or a save) may spend probing files; the files not reached
#: wait for the next load or save. A module constant, not a config key.
REFRESH_DEADLINE_S = 20
#: Files listed in one media_check_report (the rest are counted): some
#: clients close a WebSocket on a frame over 1 MiB.
REPORT_FILES_MAX = 20

# In-memory marks, keyed by (path, size, mtime_ns), for the editor process's
# lifetime: a file whose duration could not be read is not probed again until
# it changes (or the editor restarts); a file verified is not re-verified for
# a stale index alone; an index that could not be rebuilt is not retried.
_FAILED_MARKS = set()
_VERIFIED_MARKS = set()
_INDEX_FAILED_MARKS = set()
# Per project: files the last load did not reach before its deadline.
_NOT_REACHED = {}

# Files a project copy does not take from its source (backups and temporary
# files an earlier version may have left).
_NOT_COPIED = ('*.pre-refresh-*', '.*.tmp')


def reset_refresh_marks():
    """Forget every in-memory mark (tests)."""
    for marks in (_FAILED_MARKS, _VERIFIED_MARKS, _INDEX_FAILED_MARKS, _NOT_REACHED):
        marks.clear()


def _file_key(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (path, st.st_size, st.st_mtime_ns)


def mark_index_failed(path):
    """Do not try to rebuild *path*'s index again until the file changes."""
    key = _file_key(path)
    if key:
        _INDEX_FAILED_MARKS.add(key)


_LIGHT_KEYS = ('file_name', 'duration') + STORED_KEYS


def _light_media_blocks(path):
    """``[(cue_type, {key: text})]`` for every cue ``Media`` of a project
    file, read without the schema (milliseconds). ``Media`` occurs only in
    AudioCues and VideoCues, at any CueList depth, and is not namespaced."""
    root = ET.parse(path).getroot()
    blocks = []
    for cue_type in ('AudioCue', 'VideoCue'):
        for cue in root.iter(cue_type):
            media = cue.find('Media')
            if media is None:
                continue
            blocks.append((cue_type, {child.tag: (child.text or '').strip()
                                      for child in media if child.tag in _LIGHT_KEYS}))
    return blocks


def stale_changes(cue_type, values, row):
    """The values PRESENT in this ``Media`` block that the fill would change.

    The same decisions as :func:`_fix_one_media`, on normalised values, so a
    value read as a string from the file is compared as the int the fill
    writes. A value that is only missing (a project written before rc15) is
    not stale: the next save adds it. Returns ``[{field, stored, current}]``,
    ``field`` one of ``duration``, ``pixel_size`` (``"WxH"``), ``file_size``,
    ``file_md5``; ``current`` is ``None`` when the fill would remove it.
    """
    allowed = _allowed_keys(cue_type)
    present = {k: values[k] for k in STORED_KEYS if k in values}
    known = bool(values.get('file_name')) and row is not None   # an orphan: the fill stops
    expected = ({k: v for k, v in (dimensions_of_row(row) or {}).items() if k in allowed}
                if known else {})
    wrong = {k for k, v in present.items()
             if k not in allowed or _valid(k, v) is None or (known and _valid(k, v) != expected.get(k))}
    changes = []
    if known and row.duration and 'duration' in values and values['duration'] != str(row.duration):
        changes.append({'field': 'duration', 'stored': values['duration'], 'current': str(row.duration)})
    if wrong & set(PIXEL_KEYS):
        stored = f"{present.get('pixel_width', '?')}x{present.get('pixel_height', '?')}"
        current = (f"{expected['pixel_width']}x{expected['pixel_height']}"
                   if 'pixel_width' in expected else None)
        changes.append({'field': 'pixel_size', 'stored': stored, 'current': current})
    for key in ('file_size', 'file_md5'):
        if key in wrong:
            current = expected.get(key)
            changes.append({'field': key, 'stored': present[key],
                            'current': None if current is None else str(current)})
    return changes


def _media_rows(blocks):
    rows = {}
    for _, values in blocks:
        name = values.get('file_name')
        if name and name not in rows:
            rows[name] = Media.get_or_none(Media.unix_name == name)
    return rows


def stale_by_file(blocks, rows):
    """The stale values of a project, one entry per file:
    ``[{file_name, cues, changes}]``, ``cues`` counting the cues whose block
    holds stale values for that file."""
    files = {}
    for cue_type, values in blocks:
        name = values.get('file_name') or ''
        changes = stale_changes(cue_type, values, rows.get(name))
        if not changes:
            continue
        entry = files.setdefault(name, {'file_name': name, 'cues': 0, 'changes': []})
        entry['cues'] += 1
        seen = {c['field'] for c in entry['changes']}
        entry['changes'].extend(c for c in changes if c['field'] not in seen)
    return [files[k] for k in sorted(files)]


def cap_report_files(entries, cap=None):
    """At most *cap* (:data:`REPORT_FILES_MAX`) entries, and their full count."""
    cap = REPORT_FILES_MAX if cap is None else cap
    return entries[:cap], len(entries)


class MediaFileCheck:
    """Step 1's verdict on one file a project uses.

    ``state``: ``unchanged``, ``changed`` (its size differs from the row, or
    its video index was made for another file), ``legacy`` (the row has no
    stored size yet), or ``skipped`` (its duration could not be read before
    and the file has not changed since).
    """

    def __init__(self, file_name, path, media_type, size, mtime_ns):
        self.file_name = file_name
        self.path = path
        self.media_type = media_type
        self.size = size
        self.mtime_ns = mtime_ns
        self.state = 'unchanged'
        self.index = None            # None: not a video the sync carries
        self.needs_index = False

    def __repr__(self):
        return f'MediaFileCheck({self.file_name!r}, {self.state}, index={self.index})'


class RefreshPlan:
    """What a load must do before the engine is asked, and what the project
    holds that is stale (step 1, read-only)."""

    def __init__(self, project_uuid, unix_name, project_name=None):
        self.project_uuid = str(project_uuid)
        self.unix_name = unix_name
        self.project_name = project_name
        self.checks = []
        self.stale = []              # stale_by_file()

    @property
    def has_stale_values(self):
        return bool(self.stale)

    @property
    def to_verify(self):
        return [c for c in self.checks if c.state in ('changed', 'legacy')]

    @property
    def to_index(self):
        return [c for c in self.checks if c.needs_index]

    @property
    def has_work(self):
        """Files to measure or to index. Stale values alone are reported, not
        work: they cost no engine query and no probe."""
        return bool(self.to_verify or self.to_index)


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
        """Load a project's ``CuemsScript`` dict from its XML file on disk.

        Args:
            uuid: Project UUID string.
            include_trash: When ``True``, also searches trashed projects.
                Defaults to ``False``.

        Returns:
            ``dict`` produced by ``XmlReaderWriter.read()`` — the parsed
            ``CuemsScript`` structure.

        Raises:
            NonExistentItemError: If no project with *uuid* exists (or the
                project is in the trash and *include_trash* is ``False``).
        """
        try:
            if not include_trash:
                project = Project.get((Project.uuid == uuid) & (Project.in_trash == False))
            else:
                project = Project.get(Project.uuid == uuid)
            return self.load_xml(project.unix_name)
        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(uuid))

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

    def update(self, uuid, data):
        """Save an edited project: update DB metadata and rewrite the XML file.

        Runs inside a Peewee atomic transaction.  The XML is validated
        against ``script.xsd`` by ``XmlReaderWriter.write_from_object`` —
        an invalid cue tree raises before any persistent change is made.

        A pre-save pass via :meth:`_fix_media_durations` corrects zero
        durations sent by the frontend.

        Args:
            uuid: Project UUID string; must match ``data['CuemsScript']['id']``.
            data: ``CuemsScript`` dict as received from the frontend over
                WebSocket.

        Raises:
            NonExistentItemError: If the project does not exist or is in the
                trash.
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

        # SAFETY NET: older frontends send Media.duration as '00:00:00.000';
        # overwrite from the DB (source of truth) before saving.
        # As of the media-duration fix, the frontend copies the real duration
        # from the file_list payload (CuemsDBMedia.list() now carries a
        # 'duration' key) — remove this net only once ALL deployed frontends
        # AND editors are >= those versions.
        self._fix_media_durations(data)

        self._clean_dangling_targets(data)

        # Reject zero/unparseable FadeCue durations BEFORE parsing: the parser
        # bypasses FadeCue.set_duration, and a saved zero later becomes a
        # silent no-op at reveal (gradient-motiond drops dur <= 0).
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
                project_object = CuemsParser(data).parse()
                self.update_media_relations(project, project_object)
                self.save_xml(project.unix_name, project_object)
            except Exception as e:
                Logger.error("error: {} {} trying to update  project, rolling back database update".format(type(e), e))
                transaction.rollback()
                raise e

    # SAFETY NET (see update()): overwrite frontend-sent Media durations from
    # the DB. Delegates to the module-level fix_media_durations_in_contents so
    # the repair script and this path share one walk.
    def _fix_media_durations(self, data):
        """Overwrite each cue's ``Media.duration``, and each VideoCue's stored
        pixel size and file size, from the database.

        The DB is the source of truth for media duration. This corrects the
        legacy frontend behaviour of sending ``00:00:00.000``. Orphaned media
        references (no ``Media`` row) are logged, not modified. The frontend
        never sends the stored size, so it is always added here (869fat84r).
        """
        try:
            cuelist = data.get('CuemsScript', {}).get('CueList', {})
            contents = cuelist.get('contents', [])
            stats = fix_media_durations_in_contents(contents, *self._save_resolvers())
            if stats.orphans:
                Logger.warning(
                    f"media duration fix: {len(stats.orphans)} cue(s) reference "
                    f"media not in DB (duration left as-is): {stats.orphans}")
        except Exception as e:
            Logger.warning(f"Could not fix media durations: {e}")

    def _save_resolvers(self):
        """The save path's resolvers, ``(duration, stored values)``, for one
        save (869fat84r).

        Both read the ``Media`` row. A row with no stored size yet (written
        before rc15), or whose file no longer matches it, is first measured,
        as a load measures it (D20, plan §7.9.4, §8.2.3): one probe for its
        duration and pixel size, the size written last as the "checked" mark;
        so the save writes the file's real values.
        Verification stops at :data:`REFRESH_DEADLINE_S`; the rows not reached
        are verified at a later save or load. A movie or image row with a size
        but no pixel size is probed for it once (D13). The MD5 is never
        computed here: hashing a large file would make the save wait; it comes
        from the upload or the repair tool (D18). A failed probe stores
        nothing. Memoised per save: a file used by several cues is read once.
        """
        deadline = time.monotonic() + REFRESH_DEADLINE_S
        rows = {}
        values_cache = {}

        def row_of(file_name):
            if file_name not in rows:
                try:
                    media = Media.get(Media.unix_name == file_name)
                except DoesNotExist:
                    raise KeyError(file_name)
                media = self._verify_row_for_save(media, deadline)
                rows[file_name] = media
            return rows[file_name]

        def duration(file_name):
            return row_of(file_name).duration

        def stored_values(file_name):
            if file_name in values_cache:
                return values_cache[file_name]
            media = row_of(file_name)
            values = dimensions_of_row(media) or {}
            if ('pixel_width' not in values and 'file_size' in values
                    and media.media_type in ('MOVIE', 'IMAGE')):
                width, height = probe_dimensions(self._media_file_path(media))
                if width and height:
                    Media.update(pixel_width=width, pixel_height=height).where(
                        Media.uuid == media.uuid).execute()
                    values.update(pixel_width=width, pixel_height=height)
                    Logger.info(f'stored the pixel size of {file_name}: {width}x{height}')
            values_cache[file_name] = values or None
            return values_cache[file_name]

        return duration, stored_values

    def _verify_row_for_save(self, media, deadline):
        """Measure a row's file before a save writes its values, when the row
        has no stored size yet (legacy) or its file no longer matches it (a
        file replaced by hand): so a save writes the file's real values
        (plan §8.2.3). Not after the save's deadline, not for a missing or
        empty file, not for a file that failed before and has not changed.
        Returns the row as it is now."""
        if time.monotonic() >= deadline:
            return media
        check = self._check_media_file(media)
        if check is None or check.state not in ('legacy', 'changed'):
            return media
        try:
            self._verify_media_row(media, check.path, legacy=(check.state == 'legacy'))
        except Exception as e:
            Logger.error(f'could not verify {media.unix_name}: {type(e).__name__}: {e}')
            return media
        return Media.get_or_none(Media.uuid == media.uuid) or media

    def _media_file_path(self, media):
        """Absolute path of a media file, honouring its trash state."""
        if media.in_trash:
            return os.path.join(self.library_path, self.settings_dict['trash_folder_name'],
                                self.settings_dict['media_folder_name'], media.unix_name)
        return os.path.join(self.media_path, media.unix_name)

    CUE_TYPES = ['AudioCue', 'VideoCue', 'DmxCue', 'ActionCue', 'FadeCue', 'CueList']

    def _clean_dangling_targets(self, data):
        """Clear target and action_target references that point to non-existing cues.

        When a cue is deleted in the frontend, any ActionCue (or regular cue)
        still referencing it by UUID will have a dangling reference. This method
        collects all cue UUIDs and nullifies any reference that cannot be resolved.
        """
        try:
            cuelist = data.get('CuemsScript', {}).get('CueList', {})
            contents = cuelist.get('contents', [])
            all_ids = set()
            self._collect_cue_ids(contents, all_ids)
            self._nullify_dangling_refs(contents, all_ids)
        except Exception as e:
            Logger.warning(f"Could not clean dangling targets: {e}")

    def _collect_cue_ids(self, contents, ids):
        """Recursively collect all cue UUIDs from the project contents."""
        if not contents:
            return
        for item in contents:
            for cue_type in self.CUE_TYPES:
                if cue_type in item:
                    cue_data = item[cue_type]
                    cue_id = cue_data.get('id')
                    if cue_id:
                        ids.add(cue_id)
                    if cue_type == 'CueList':
                        self._collect_cue_ids(cue_data.get('contents', []), ids)

    def _nullify_dangling_refs(self, contents, valid_ids):
        """Recursively clear target/action_target refs that point to non-existing cues."""
        if not contents:
            return
        for item in contents:
            for cue_type in self.CUE_TYPES:
                if cue_type in item:
                    cue_data = item[cue_type]
                    if cue_type == 'CueList':
                        self._nullify_dangling_refs(cue_data.get('contents', []), valid_ids)
                        continue
                    target = cue_data.get('target')
                    if target and target not in valid_ids:
                        Logger.warning(f"{cue_type} {cue_data.get('id')} has dangling target {target}, clearing")
                        cue_data['target'] = None
                    if cue_type in ('ActionCue', 'FadeCue'):
                        action_target = cue_data.get('action_target')
                        if action_target and action_target not in valid_ids:
                            Logger.warning(f"{cue_type} {cue_data.get('id')} has dangling action_target {action_target}, clearing")
                            cue_data['action_target'] = None

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

        # Same metadata fill and save-time gate as update().
        self._fix_media_durations(data)
        validate_fade_durations_in_contents(
            (data.get('CuemsScript', {}).get('CueList') or {}).get('contents') or []
        )

        with self.db.atomic() as transaction:
            try:
                project = Project.create(uuid=project_uuid, unix_name=unix_name, name=StringSanitizer.sanitize_name(data['CuemsScript']['name']), description=StringSanitizer.sanitize_text_size(data['CuemsScript']['description']), created=now, modified=now)
                os.mkdir(os.path.join(self.projects_path, unix_name))
                Logger.debug('data is now: {}'.format(data))
                project_object = CuemsParser(data).parse()
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
        record.  The duplicated ``cue_script.xml`` has its ``CuemsScript.id``
        and ``name`` updated to match the new DB record.

        Args:
            uuid: UUID of the project to duplicate; must be a live project.

        Returns:
            New project UUID string.

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
                    data = self.load_xml(dup_project.unix_name)
                    data['CuemsScript']['id'] = new_project_uuid
                    data['CuemsScript']['name'] = project.name
                    data['CuemsScript']['modified'] = project.modified
                    # Fill durations and stored sizes from the DB, as a save
                    # does, so a legacy project's copy carries them (869fat84r).
                    self._fix_media_durations(data)
                    # NO fade-duration validation here on purpose: the source is
                    # load_xml of an existing project — legacy scripts must stay
                    # duplicable; the engine's reveal guard covers them.
                    project_object = CuemsParser(data).parse()
                    self.add_media_relations(dup_project, project_object)
                    self.save_xml(new_unix_name, project_object)
                    return new_project_uuid
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

    # --- A media file that changed after its values were stored (D20) -------

    def _script_path(self, unix_name):
        return os.path.join(self.projects_path, unix_name, self.script_file_name)

    def plan_media_refresh(self, project_uuid):
        """Step 1 of the load-time check: read and compare, write nothing.

        Reads the project file without the schema, finds each file it uses,
        compares the file with its row (size; and the ``.idx`` header of a
        video the sync carries), and lists the values present in the project
        that no longer match their rows (:func:`stale_by_file`).

        Raises:
            NonExistentItemError: no live project with *project_uuid*.
        """
        try:
            project = Project.get((Project.uuid == project_uuid) & (Project.in_trash == False))
        except DoesNotExist:
            raise NonExistentItemError("item with uuid: {} does not exist".format(project_uuid))
        plan = RefreshPlan(project_uuid, project.unix_name, project.name)
        blocks = _light_media_blocks(self._script_path(project.unix_name))
        rows = _media_rows(blocks)
        plan.stale = stale_by_file(blocks, rows)
        for row in rows.values():
            if row is not None:     # an orphan is skipped; the node's check covers it
                check = self._check_media_file(row)
                if check is not None:
                    plan.checks.append(check)
        return plan

    def _check_media_file(self, row):
        path = self._media_file_path(row)
        try:
            st = os.stat(path)
        except OSError:
            return None             # missing on the controller: the node's check covers it
        if st.st_size <= 0:
            return None
        key = (path, st.st_size, st.st_mtime_ns)
        check = MediaFileCheck(row.unix_name, path, row.media_type, st.st_size, st.st_mtime_ns)
        if row.media_type == 'MOVIE' and not row.in_trash and is_indexed_video(row.unix_name):
            check.index = video_index_state(path)
        stored = _positive_int(row.file_size)
        if key in _FAILED_MARKS:
            check.state = 'skipped'
        elif stored is None:
            check.state = 'legacy'
        elif stored != st.st_size:
            check.state = 'changed'
        elif check.index == INDEX_STALE and key not in _VERIFIED_MARKS:
            check.state = 'changed'     # same size, but not the file the index was made for
        check.needs_index = (check.index is not None and check.index != INDEX_VALID
                             and check.state != 'skipped' and key not in _INDEX_FAILED_MARKS)
        return check

    def verify_media_files(self, plan, deadline, clock=time.monotonic):
        """Step 2: re-probe each changed or legacy file and correct its row.

        Stops at *deadline* (a *clock* value); the files not reached go first
        at the next load. One file that fails is logged and skipped.

        Returns:
            ``dict`` of file-name lists: ``verified``, ``changed``,
            ``legacy``, ``failed``, ``in_copy``, ``not_reached``.
        """
        report = {k: [] for k in ('verified', 'changed', 'legacy', 'failed',
                                  'in_copy', 'not_reached')}
        first = _NOT_REACHED.get(plan.project_uuid, [])
        todo = sorted(plan.to_verify, key=lambda c: c.file_name not in first)
        for check in todo:
            if clock() >= deadline:
                report['not_reached'].append(check.file_name)
                continue
            row = Media.get_or_none(Media.unix_name == check.file_name)
            if row is None:
                continue
            try:
                self._verify_media_row(row, check.path, legacy=(check.state == 'legacy'),
                                       report=report)
            except Exception as e:
                report['failed'].append(check.file_name)
                Logger.error(f'could not verify {check.file_name}: {type(e).__name__}: {e}')
        if report['not_reached']:
            _NOT_REACHED[plan.project_uuid] = report['not_reached']
            Logger.warning(f'project {plan.unix_name}: {len(report["not_reached"])} media '
                           f'file(s) not checked before the {REFRESH_DEADLINE_S} s limit, '
                           f'left for the next load: {report["not_reached"]}')
        else:
            _NOT_REACHED.pop(plan.project_uuid, None)
        return report

    def _verify_media_row(self, row, path, legacy, report=None):
        """Probe *path* once and make *row* match it. Returns ``True`` when the
        row was written.

        stat, probe, stat again: a file still being copied is left alone. The
        values are written in one statement with ``file_size`` (the "checked"
        mark) in it, and only when the duration was read: a failed duration
        probe leaves the row untouched, so the next load tries again (after
        the file changes or the editor restarts). The pixel size is only an
        arm-time saving: when it cannot be read the engine probes it, so it
        never holds the row back. A changed file's MD5 is cleared (the repair
        tool refills it); hashing here would cost seconds.
        """
        started = time.monotonic()
        name = row.unix_name
        report = report if report is not None else {}
        try:
            st1 = os.stat(path)
            result = probe_media(path)
            st2 = os.stat(path)
        except OSError as e:
            Logger.warning(f'could not check {name}: {e}')
            return False
        if (st1.st_size, st1.st_mtime_ns) != (st2.st_size, st2.st_mtime_ns):
            report.setdefault('in_copy', []).append(name)
            Logger.warning(f'{name} changed while it was being checked (still being '
                           'copied?); left for the next load')
            return False
        key = (path, st1.st_size, st1.st_mtime_ns)
        update = {}
        old_duration = row.duration
        if row.media_type in ('MOVIE', 'AUDIO'):
            if result.duration_state != PROBE_OK:
                _FAILED_MARKS.add(key)
                report.setdefault('failed', []).append(name)
                Logger.error(f'could not read the duration of {name} '
                             f'({result.duration_state}): its stored values are kept '
                             f'(duration {old_duration}); it is tried again when the file '
                             'changes or the editor restarts')
                return False
            if str(result.duration) != (old_duration or ''):
                update['duration'] = str(result.duration)
        if row.media_type in ('MOVIE', 'IMAGE'):
            if result.picture_state == PROBE_OK:
                if (row.pixel_width, row.pixel_height) != (result.width, result.height):
                    update.update(pixel_width=result.width, pixel_height=result.height)
            else:
                if result.picture_state == PROBE_FAILED:
                    Logger.warning(f'could not read the pixel size of {name}: the engine '
                                   'probes it when it arms the cue')
                if not legacy and (row.pixel_width or row.pixel_height):
                    update.update(pixel_width=None, pixel_height=None)
        if not legacy and row.file_md5:
            update['file_md5'] = None
        update['file_size'] = st1.st_size
        Media.update(**update).where(Media.uuid == row.uuid).execute()
        _VERIFIED_MARKS.add(key)
        report.setdefault('verified', []).append(name)
        report.setdefault('legacy' if legacy else 'changed', []).append(name)
        ms = int((time.monotonic() - started) * 1000)
        new_duration = update.get('duration', old_duration)
        if not legacy:
            Logger.warning(f'media file {name} changed after its values were stored: size '
                           f'{row.file_size} -> {st1.st_size}, duration {old_duration} -> '
                           f'{new_duration}; values corrected ({ms} ms)')
        elif 'duration' in update:
            Logger.warning(f'media file {name}: stored duration {old_duration} corrected to '
                           f'{new_duration} (editors before 2026-07-06 stored some durations '
                           f'up to 0.9 s short) ({ms} ms)')
        else:
            Logger.info(f'media file {name}: stored values verified ({ms} ms)')
        return True

    def media_report(self, project_uuid, context, reason=None):
        """The value of a ``media_check_report`` frame (plan §8.3), read-only.

        ``files``: the stale values the project holds, by file, capped at
        :data:`REPORT_FILES_MAX` (``total_files`` counts them all).
        ``unverified``: files whose size or index no longer matches their row
        and that have not been measured yet. ``complete`` is false when part
        of the check did not run (*reason*, or a file whose probe failed
        before): the UI must not take that report as an all-clear.
        """
        plan = self.plan_media_refresh(project_uuid)
        if reason is None and any(c.state == 'skipped' for c in plan.checks):
            reason = 'probe_failed'
        files, total = cap_report_files(plan.stale)
        return {
            'project_uuid': str(project_uuid),
            'project_name': plan.project_name,
            'context': context,
            'complete': reason is None,
            'reason': reason,
            'files': files,
            'unverified': sorted(c.file_name for c in plan.checks if c.state == 'changed'),
            'total_files': total,
        }

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
        # A trashed project lives in the trash, not where load() reads; it is
        # relinked when it is restored and saved (869fat84r D20, Q2).
        try:
            project = Project.get(Project.uuid == project_uuid)
        except DoesNotExist:
            Logger.warning(f'no project {project_uuid} to relink {media_filename} in')
            return
        if project.in_trash:
            Logger.info(f'project {project.unix_name} is in the trash: not relinking {media_filename}')
            return
        # Relink only (D21): the re-uploaded row has fresh values; the project
        # still holds the old file's, reported at its next load or open and
        # written by its next save.
        self._relink_existed_media(project, media_filename)

    def _relink_existed_media(self, project, media_filename):
        project_uuid = str(project.uuid)
        project_object = CuemsParser(self.load(project_uuid)).parse()
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

    def save_xml(self, unix_name, project_object):
        """Write *project_object* to ``<projects_path>/<unix_name>/cue_script.xml``.

        Validates against ``script.xsd`` before writing; raises if the
        ``CuemsScript`` object fails schema validation.

        The file is replaced atomically (869fat84r D20): written to a
        temporary file in the same directory, given the old file's mode (the
        nodes' rsync reads it as ``nobody``), then renamed over it, so a power
        cut never leaves a truncated project. A directory the editor cannot
        create files in falls back to writing in place, as before.

        Args:
            unix_name: Project directory name.
            project_object: ``CuemsScript`` instance to serialize.
        """
        final = self._script_path(unix_name)
        directory = os.path.dirname(final)
        tmp = os.path.join(directory, f'.{self.script_file_name}.{os.getpid()}.{os.urandom(4).hex()}.tmp')
        try:
            open(tmp, 'xb').close()
        except OSError as e:
            Logger.warning(f'cannot create a temporary file in {directory} ({e}); writing '
                           f'{final} in place')
            XmlReaderWriter(schema_name=self.script_schema_name, xmlfile=final).write_from_object(project_object)
            return
        try:
            XmlReaderWriter(schema_name=self.script_schema_name, xmlfile=tmp).write_from_object(project_object)
            if os.path.exists(final):
                shutil.copymode(final, tmp)
            os.replace(tmp, final)
        except BaseException:
            with contextlib.suppress(OSError):
                os.remove(tmp)
            raise

    def load_xml(self, unix_name):
        """Read and parse ``<projects_path>/<unix_name>/cue_script.xml``.

        Args:
            unix_name: Project directory name.

        Returns:
            ``CuemsScript`` dict produced by ``XmlReaderWriter.read()``.
        """
        reader = XmlReaderWriter(schema_name=self.script_schema_name, xmlfile=(os.path.join(self.projects_path, unix_name, self.script_file_name)))
        return reader.read()
