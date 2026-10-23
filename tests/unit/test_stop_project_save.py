# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The editor's half of the ``stop_project`` ActionCue (003, FR-032; cuems-utils 017 §2).

``stop_project`` acts on the whole project and takes no target. The editor sends none
(``null``, an absent key or ``""``), saves, and the project reopens. A cue retyped from
``stop`` to ``stop_project`` that still carries a target is refused by the library at
save with the rule ``project_action_takes_no_target``.

The value is in cuems-utils' ``script.xsd`` from ``0.1.0rc17``. The candidate tag
(``4b336cd``) does not carry it; the library head (``387598e``) does. Until the
tag is re-cut every case here is a strict expected failure, and it turns XPASS (red)
on the re-cut: drop the markers then (task T022, the compatibility check).
"""
import pytest

from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Project, database
from cuemseditor.CuemsDBProject import CuemsDBProject

NOT_IN_THE_TAG = pytest.mark.xfail(
    strict=True,
    reason="cuems-utils 4b336cd lacks stop_project in script.xsd (0 matches); utils 387598e has it. "
           "See specs/003-release-line-reconciliation/upstream-reports/cuems-utils.md",
)

SOME_TARGET = '1f301cf8-dd03-4b40-ac17-ef0e5e7988be'


def _manager(library):
    library.connect()
    settings = get_settings()
    settings['library_path'] = library.root
    return CuemsDBProject(settings, database)


def _action_cue(data):
    """The fixture's ActionCue, as the wire carries it."""
    for item in data['CuemsScript']['CueList']['contents']:
        if 'ActionCue' in item:
            return item['ActionCue']
    raise AssertionError('the 013 fixture holds an ActionCue')


def _retype(library, target):
    mgr = _manager(library)
    uuid = str(Project.get(Project.unix_name == 'proj1').uuid)
    data = mgr.load(uuid)
    cue = _action_cue(data)
    cue['action_type'] = 'stop_project'
    if target == 'absent':
        cue.pop('action_target', None)
    else:
        cue['action_target'] = target
    return mgr, uuid, data


@NOT_IN_THE_TAG
@pytest.mark.parametrize('target', [None, '', 'absent'])
def test_a_stop_project_cue_without_a_target_saves_and_reopens(library013, target):
    mgr, uuid, data = _retype(library013, target)
    mgr.update(uuid, data)
    reopened = _manager(library013).load(uuid)
    database.close()
    cue = _action_cue(reopened)
    assert cue['action_type'] == 'stop_project'
    assert cue.get('action_target') in (None, '')


@NOT_IN_THE_TAG
def test_a_leftover_target_is_refused_with_the_librarys_rule(library013):
    mgr, uuid, data = _retype(library013, SOME_TARGET)
    with pytest.raises(Exception) as e:
        mgr.update(uuid, data)
    if not database.is_closed():
        database.close()
    assert 'project_action_takes_no_target' in str(e.value)
