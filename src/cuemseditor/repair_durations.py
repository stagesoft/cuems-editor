"""Repair corrupted media durations in the CueMS library.

Historical ``CuemsDBMedia.get_duration`` reformatted ffprobe sexagesimal output
with a string-slicing hack that dropped zero-padding, so any duration whose
millisecond fraction ended in a zero was stored short (by up to ~0.9 s) and the
whole-second carry case overshot by minutes. Those corrupted values live in the
``media.duration`` column of ``project-manager.db`` and, because the editor
copies the DB value into every saved ``script.xml`` on save, in the project
scripts too.

This tool re-probes every media file with the fixed :func:`probe_duration` and:

- **Pass A** rewrites ``media.duration`` in the DB (the source of truth).
- It then opens every project script with the library's public load and lists
  each project whose media durations differ from the corrected DB values as
  **needs a save**, naming the project, the media, the script value and the
  database value. It compares with ``CTimecode`` through the same walk the
  editor's save path uses.

**This tool never writes a script file.** Script files change only when an
operator opens the project in the editor and saves it; until that save, the
engine plays the file on disk, short durations included. A script the library
cannot open is ``SKIPPED_INVALID`` with the library's reason. A document still
in the pre-013 device shape (``<AudioCue>`` with no ``class``) is corrected by
running ``cuems-reshape-devices`` over the whole library and then saving in
the editor, not by this tool.

Dry-run is the default; ``--apply`` writes the DB after backing it up. Run
with the editor STOPPED (single-writer SQLite).

Invoke as a console script (``cuems-editor-repair-durations``) or module
(``python -m cuemseditor.repair_durations``).
"""
import argparse
import os
import shutil
import sys
from datetime import datetime

from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Project, Media, database
from cuemseditor.CuemsDBMedia import probe_duration
from cuemseditor.CuemsDBProject import (
    fix_media_durations_in_contents,
    db_duration_resolver,
)
from cuemseditor.CuemsErrors import NotTimeCodeError
from cuemsutils.cues import CuemsScript
from cuemsutils.tools.CTimecode import CTimecode

HELP_EPILOG = (
    'Script files are never written by this tool. They change only when an '
    'operator opens the project in the editor and saves it; until then the '
    'engine plays the file on disk. Projects listed as NEEDS_SAVE are the ones '
    'to open and save. A script in the old device shape (<AudioCue> with no '
    'class) is corrected by running cuems-reshape-devices over the whole '
    'library, then saving in the editor, not by this tool.'
)


def build_settings(args):
    settings = get_settings()
    if args.library_path:
        settings['library_path'] = args.library_path
    if args.database_name:
        settings['database_name'] = args.database_name
    return settings


def _media_file_path(settings, media):
    """Absolute path of a media file, honouring its trash state."""
    library = settings['library_path']
    if media.in_trash:
        return os.path.join(library, settings['trash_folder_name'],
                            settings['media_folder_name'], media.unix_name)
    return os.path.join(library, settings['media_folder_name'], media.unix_name)


def _project_xml_path(settings, project):
    library = settings['library_path']
    if project.in_trash:
        base = os.path.join(library, settings['trash_folder_name'],
                            settings['project_folder_name'])
    else:
        base = os.path.join(library, settings['project_folder_name'])
    return os.path.join(base, project.unix_name, settings['script_file_name'])


def _delta_ms(old_str, new_tc):
    """Best-effort millisecond delta new-old; None if old is unparseable."""
    try:
        old_ms = CTimecode(old_str).milliseconds_exact
    except Exception:
        return None
    return new_tc.milliseconds_exact - old_ms


class Report:
    """Accumulates per-item statuses and drives the exit code."""

    def __init__(self):
        self.lines = []
        self.counts = {}
        self.dirty = False  # any MISSING / PROBE_FAILED / SKIPPED_INVALID / orphan

    def add(self, status, detail, dirty=False):
        self.counts[status] = self.counts.get(status, 0) + 1
        self.lines.append(f'  [{status}] {detail}')
        if dirty:
            self.dirty = True

    def dump(self):
        for line in self.lines:
            print(line)
        print('\n  --- summary ---')
        for status in sorted(self.counts):
            print(f'    {status}: {self.counts[status]}')


def backup_database(settings, backup_dir):
    db_path = os.path.join(settings['library_path'], settings['database_name'])
    os.makedirs(backup_dir, exist_ok=True)
    for suffix in ('', '-wal', '-shm'):
        src = db_path + suffix
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(backup_dir, os.path.basename(src)))
    print(f'  DB backed up to {backup_dir}')


def pass_a_db(settings, args, report):
    """Re-probe every media file, report/apply corrected durations.

    Returns:
        ``{unix_name: corrected_duration_str}`` for every row it would change,
        applied or not, so the script comparison can use the corrected values
        in a dry run too.
    """
    print('\n== Pass A: database media.duration ==')
    updates = []  # (uuid, new_str)
    corrected = {}
    for media in Media.select():
        label = f'{media.unix_name} ({media.media_type})'
        if media.media_type == 'IMAGE':
            report.add('SKIP_IMAGE', label)
            continue
        if args.skip_trash and media.in_trash:
            report.add('SKIP_TRASH', label)
            continue
        path = _media_file_path(settings, media)
        if not os.path.exists(path):
            report.add('MISSING', f'{label} -> {path}', dirty=True)
            continue
        try:
            new_tc = probe_duration(path)
        except NotTimeCodeError as e:
            report.add('PROBE_FAILED', f'{label}: {e}', dirty=True)
            continue
        except Exception as e:  # defensive: never abort the whole pass
            report.add('PROBE_FAILED', f'{label}: unexpected {type(e).__name__}: {e}',
                       dirty=True)
            continue
        new_str = str(new_tc)
        old = media.duration
        if old is None:
            report.add('NULL_FILLED', f'{label}: -> {new_str}')
            updates.append((media.uuid, new_str))
            corrected[media.unix_name] = new_str
        elif old == new_str:
            report.add('OK', label)
        else:
            delta = _delta_ms(old, new_tc)
            delta_txt = f'{delta:+.0f}ms' if delta is not None else 'Δ?(old unparseable)'
            flag = ' <<<>1s' if (delta is not None and abs(delta) > 1000) else ''
            report.add('CHANGED', f'{label}: {old} -> {new_str} ({delta_txt}){flag}')
            updates.append((media.uuid, new_str))
            corrected[media.unix_name] = new_str

    if args.apply and updates:
        with database.atomic():
            for uuid, new_str in updates:
                Media.update(duration=new_str).where(Media.uuid == uuid).execute()
        print(f'  applied {len(updates)} DB duration update(s)')
    elif updates:
        print(f'  {len(updates)} DB duration update(s) pending (dry-run)')
    return corrected


def corrected_resolver(corrected):
    """``db_duration_resolver`` with pass A's corrections laid over it.

    After ``--apply`` the overlay equals the DB; in a dry run it is what the DB
    would hold, so the script comparison reports the same list either way.
    """
    def resolve(file_name):
        if file_name in corrected:
            return corrected[file_name]
        return db_duration_resolver(file_name)
    return resolve


def scan_scripts(settings, args, report, corrected):
    """List projects whose script durations differ from the corrected DB.

    Opens each script with ``CuemsScript.load_with_report`` (in memory; a
    version conversion is not written either), runs the editor's own duration
    walk on the object, and reports what it would change. Writes nothing.
    """
    print('\n== Project scripts: media durations against the database ==')
    resolver = corrected_resolver(corrected)
    for project in Project.select():
        if args.skip_trash and project.in_trash:
            report.add('SKIP_TRASH_SCRIPT', project.unix_name)
            continue
        path = _project_xml_path(settings, project)
        label = f'{project.unix_name}'
        if not os.path.exists(path):
            report.add('MISSING_XML', f'{label} -> {path}', dirty=True)
            continue
        try:
            script, _load_report = CuemsScript.load_with_report(path)
        except Exception as e:
            report.add('SKIPPED_INVALID', f'{label}: {type(e).__name__}: {e}', dirty=True)
            continue

        stats = fix_media_durations_in_contents(script.cuelist.contents, resolver)
        if stats.orphans:
            report.add('ORPHAN_MEDIA_REF',
                       f'{label}: {len(stats.orphans)} ref(s) not in DB: {stats.orphans}',
                       dirty=True)
        if not stats.changes:
            report.add('SCRIPT_OK', label)
            continue
        for file_name, previous, replacement in stats.changes:
            report.add('NEEDS_SAVE',
                       f'{label}: {file_name}: script {previous} != database {replacement}')


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='cuems-editor-repair-durations',
        description='Re-probe and repair corrupted media durations in the DB, '
                    'and list the projects whose scripts need a save in the '
                    'editor. Dry-run by default; use --apply to write the DB.',
        epilog=HELP_EPILOG)
    parser.add_argument('--library-path', help='override library_path (default /opt/cuems_library)')
    parser.add_argument('--database-name', help='override database file name')
    parser.add_argument('--apply', action='store_true', help='write the DB (default: dry-run); never writes scripts')
    parser.add_argument('--skip-trash', action='store_true', help='skip trashed media and projects')
    parser.add_argument('--backup-dir', help='backup directory (default <library>/duration_repair_backup_<ts>)')
    args = parser.parse_args(argv)

    settings = build_settings(args)
    db_path = os.path.join(settings['library_path'], settings['database_name'])
    if not os.path.exists(db_path):
        print(f'FATAL: database not found at {db_path}', file=sys.stderr)
        return 2

    if not args.apply:
        print('*** DRY RUN — no changes will be written (use --apply to commit) ***')
    else:
        if os.path.exists(settings.get('editor_ipc', '')):
            print('*** WARNING: editor IPC socket present — cuems-editor may be '
                  'RUNNING. Stop it before --apply. ***')

    backup_dir = args.backup_dir or os.path.join(
        settings['library_path'],
        'duration_repair_backup_' + datetime.now().strftime('%Y%m%d-%H%M%S'))

    database.init(db_path)
    database.connect()
    if args.apply:
        backup_database(settings, backup_dir)

    report = Report()
    try:
        corrected = pass_a_db(settings, args, report)
        scan_scripts(settings, args, report, corrected)
    finally:
        database.close()

    print('\n== Report ==')
    report.dump()
    if args.apply:
        print(f'\n  backups: {backup_dir}')
    else:
        print('\n  (dry-run — re-run with --apply to write)')

    return 1 if report.dirty else 0


if __name__ == '__main__':
    sys.exit(main())
