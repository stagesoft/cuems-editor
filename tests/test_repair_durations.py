"""Tests for the repair_durations tool: pass A (DB) and the needs-a-save list.

Retired by 001-cuems-utils-migration (FR-007, FR-026,
specs/001-cuems-utils-migration/contracts/repair-tool.md): every pass B
assertion — that ``--apply`` rewrote ``<duration>`` inside ``script.xml`` so
the XML no longer held ``00:00:00.000`` — and ``--xml-only`` / ``--db-only``.
The tool writes no script under any flag now. What replaces those assertions:
after ``--apply`` every ``script.xml`` checksum is unchanged, and the projects
whose durations differ from the corrected DB are listed as ``NEEDS_SAVE``.
Saving one of them through the editor's save path takes it off the list.
"""
import hashlib
import os

import cuemseditor.repair_durations as rd


def _file_hash(path):
    with open(path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()


def _script_path(library):
    return os.path.join(library.projects_dir, 'proj1', 'script.xml')


def _all_script_hashes(library):
    out = {}
    for base, _dirs, files in os.walk(library.root):
        for name in files:
            if name == 'script.xml':
                path = os.path.join(base, name)
                out[path] = _file_hash(path)
    return out


def test_dry_run_changes_nothing(library, canned_probe):
    before = library.durations()
    xml_before = _file_hash(_script_path(library))

    rc = rd.main(['--library-path', library.root])

    assert library.durations() == before          # DB untouched
    assert _file_hash(_script_path(library)) == xml_before  # XML untouched
    assert rc == 1                                  # gone.wav MISSING -> exit 1


def test_apply_fixes_the_db_and_writes_no_script(library, canned_probe, capsys):
    _write_v2_script(library)
    scripts_before = _all_script_hashes(library)

    rc = rd.main(['--library-path', library.root, '--apply'])

    durations = library.durations()
    assert durations['file.ext'] == '00:01:23.456'      # CHANGED
    assert durations['file_video.ext'] == '00:01:30.000'  # NULL_FILLED
    assert durations['gone.wav'] == '00:00:01.000'       # MISSING -> untouched
    assert durations['pic.png'] is None                  # IMAGE skipped

    assert _all_script_hashes(library) == scripts_before   # no script written
    assert _needs_save(capsys.readouterr().out) == {
        ('proj1', 'file.ext', '00:01:23.456'),
        ('proj1', 'file_video.ext', '00:01:30.000'),
    }

    backups = [d for d in os.listdir(library.root)
               if d.startswith('duration_repair_backup_')]
    assert backups, 'a backup directory should have been created'
    assert os.path.exists(os.path.join(library.root, backups[0], 'project-manager.db'))
    assert sorted(os.listdir(os.path.join(library.root, backups[0]))) == ['project-manager.db']
    assert rc == 1  # still 1 because of the MISSING file


def test_dry_run_lists_the_same_projects_as_apply(library, canned_probe, capsys):
    _write_v2_script(library)
    rd.main(['--library-path', library.root])
    assert _needs_save(capsys.readouterr().out) == {
        ('proj1', 'file.ext', '00:01:23.456'),
        ('proj1', 'file_video.ext', '00:01:30.000'),
    }


def test_apply_is_idempotent(library, canned_probe):
    rd.main(['--library-path', library.root, '--apply'])
    # second run: nothing left to change
    durs_after_first = library.durations()
    rd.main(['--library-path', library.root, '--apply'])
    assert library.durations() == durs_after_first


def test_skip_trash(library, canned_probe):
    rd.main(['--library-path', library.root, '--apply', '--skip-trash'])
    # trashed tone_c.wav should be untouched by --skip-trash
    assert library.durations()['tone_c.wav'] == '00:00:03.9'


def test_trash_media_fixed_without_skip(library, canned_probe):
    rd.main(['--library-path', library.root, '--apply'])
    assert library.durations()['tone_c.wav'] == '00:00:03.000'


def test_skipped_invalid_xml_does_not_abort(library, canned_probe, capsys):
    # add a second project whose script.xml is malformed
    from cuemseditor.CuemsDBModel import Project, database
    from cuemsutils.helpers import new_uuid, new_datetime
    _write_v2_script(library)
    bad_dir = os.path.join(library.projects_dir, 'proj2')
    os.makedirs(bad_dir, exist_ok=True)
    with open(os.path.join(bad_dir, 'script.xml'), 'w') as f:
        f.write('<not-valid-xml>')
    library.connect()
    Project.create(uuid=str(new_uuid()), name='Proj Two', unix_name='proj2',
                   created=new_datetime(), modified=new_datetime(), in_trash=False)
    database.close()

    rc = rd.main(['--library-path', library.root, '--apply'])
    out = capsys.readouterr().out
    # proj1 is still compared and listed despite proj2 being invalid
    assert {p for p, _m, _d in _needs_save(out)} == {'proj1'}
    assert any(line.startswith('[SKIPPED_INVALID] proj2') for line in
               (l.strip() for l in out.splitlines()))
    assert library.durations()['file.ext'] == '00:01:23.456'
    assert rc == 1  # SKIPPED_INVALID (and the MISSING file) mark the run dirty


def test_missing_db_is_fatal(tmp_path):
    rc = rd.main(['--library-path', str(tmp_path)])
    assert rc == 2


# ─── 001: structured durations and pre-013 documents ─────────────────────

FIXTURE_013 = os.path.join(os.path.dirname(__file__), 'fixtures', 'script_minimal_013.xml')


def _write_v2_script(library):
    """proj1 holds the 013 fixture as the library writes it: doc_version 2,
    <duration><CTimecode>…</CTimecode></duration>, durations still zero."""
    from cuemsutils.cues import CuemsScript
    script, _report = CuemsScript.load_with_report(FIXTURE_013)
    script.save(_script_path(library))


def _status_lines(out, status):
    return [line.strip() for line in out.splitlines() if line.strip().startswith(f'[{status}]')]


def _needs_save(out):
    """``{(project, media, database_value)}`` from the NEEDS_SAVE lines."""
    found = set()
    for line in _status_lines(out, 'NEEDS_SAVE'):
        # [NEEDS_SAVE] proj1: file.ext: script 00:00:00.000 != database 00:01:23.456
        project, media, rest = line.split('] ', 1)[1].split(': ', 2)
        found.add((project, media, rest.rsplit(' ', 1)[1]))
    return found


def test_saving_a_listed_project_in_the_editor_takes_it_off_the_list(library, canned_probe, capsys):
    """US5 acceptance 4: the operator's save is what writes the durations."""
    from cuemseditor.cli import get_settings
    from cuemseditor.CuemsDBModel import Project, database
    from cuemseditor.CuemsDBProject import CuemsDBProject

    _write_v2_script(library)
    rd.main(['--library-path', library.root, '--apply'])
    assert {p for p, _m, _d in _needs_save(capsys.readouterr().out)} == {'proj1'}
    listed_hash = _file_hash(_script_path(library))

    settings = get_settings()
    settings['library_path'] = library.root
    library.connect()
    project = CuemsDBProject(settings, database)
    uuid = Project.get(Project.unix_name == 'proj1').uuid
    project.update(uuid, project.load(uuid))   # what project_save does with the open frame
    database.close()
    saved_hash = _file_hash(_script_path(library))
    assert saved_hash != listed_hash

    rd.main(['--library-path', library.root, '--apply'])
    out = capsys.readouterr().out
    assert _needs_save(out) == set()
    assert '[SCRIPT_OK] proj1' in out
    assert _file_hash(_script_path(library)) == saved_hash   # the tool did not write it


def test_structured_duration_differing_from_the_database_is_reported(library, canned_probe, capsys):
    _write_v2_script(library)
    with open(_script_path(library), encoding='utf-8') as fh:
        assert '<CTimecode>00:00:00.000</CTimecode></duration>' in fh.read().replace('\n', '')

    rd.main(['--library-path', library.root])

    needs_save = _status_lines(capsys.readouterr().out, 'NEEDS_SAVE')
    assert any('proj1' in line and 'file.ext' in line for line in needs_save), needs_save


def test_pre_013_script_is_skipped_invalid_and_untouched(library, canned_probe, capsys):
    before = _file_hash(_script_path(library))      # the library fixture is pre-013

    rd.main(['--library-path', library.root, '--apply'])

    skipped = _status_lines(capsys.readouterr().out, 'SKIPPED_INVALID')
    assert any('proj1' in line and 'cuems-reshape-devices' in line for line in skipped), skipped
    assert _file_hash(_script_path(library)) == before
    # cuems-reshape-devices leaves <name>.<ts>.bak beside each file it rewrites.
    assert not [f for f in os.listdir(os.path.dirname(_script_path(library))) if f.endswith('.bak')]
