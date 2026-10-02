# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The ``project`` frame differs from the pre-migration capture by three deltas only.

FR-011, FR-014, FR-040, contracts/project-payload.md. The capture is the
``{"type":"project"}`` frame the editor sent before 001, for
``tests/fixtures/script_minimal.xml``
(``specs/001-cuems-utils-migration/evidence/project-capture/``). The library no
longer loads that pre-013 shape, so the open path reads
``script_minimal_013.xml``, which is ``cuems-reshape-devices`` over a copy of it.

Sanctioned deltas, applied to the capture by ``apply_project_deltas``:

(a) ``schemaLocation`` is absent;
(b) ``Media.duration`` is ``{"CTimecode": "HH:MM:SS.mmm"}``;
(c) a hardware cue's key is ``Cue`` with ``class`` last, and a hardware cue
    output's key is ``CueOutput`` with ``class`` last. ``ActionCue``,
    ``FadeCue`` and ``CueList`` keep their keys. ``AudioCue`` is not written
    back onto the wire.

Everything else is compared as serialised JSON text, so key order and the
string booleans are part of the check. ``cuems-utils`` golden XML is not.

The second half pins the save path's duration fix (FR-012, FR-015): a client
cue keyed ``Cue`` with a zero media duration is accepted and corrected from the
media database, for ``class`` ``audio``, ``video`` and one the editor has no
name for.
"""

import copy
import hashlib
import json
import os
import shutil

import pytest

from cuemseditor.cli import get_settings
from cuemseditor.CuemsDBModel import Media, Project, ProjectMedia, database
from cuemseditor.CuemsDBProject import CuemsDBProject
from cuemsutils.cues import CuemsScript
from cuemsutils.helpers import new_datetime, new_uuid

HERE = os.path.dirname(__file__)
FIXTURE_013 = os.path.join(HERE, 'fixtures', 'script_minimal_013.xml')
CAPTURE = os.path.join(
    HERE, '..', 'specs', '001-cuems-utils-migration', 'evidence', 'project-capture',
    'script_minimal.frame.json')

SCHEMA_LOCATION = '{http://www.w3.org/2001/XMLSchema-instance}schemaLocation'
HARDWARE_CUES = {'AudioCue': 'audio', 'VideoCue': 'video', 'DmxCue': 'dmx'}
HARDWARE_OUTPUTS = {'AudioCueOutput': 'audio', 'VideoCueOutput': 'video', 'DmxCueOutput': 'dmx'}

DB_DURATIONS = {'file.ext': '00:01:23.456', 'file_video.ext': '00:01:30.000'}


def apply_project_deltas(value):
    """The captured ``value`` moved through deltas (a), (b) and (c), and nothing else."""
    def move(node, parent=None):
        if isinstance(node, list):
            return [move(item, parent) for item in node]
        if not isinstance(node, dict):
            return node
        if len(node) == 1:
            (key, body), = node.items()
            if key in HARDWARE_CUES:                      # (c)
                moved = {k: move(v, k) for k, v in body.items()}
                moved['class'] = HARDWARE_CUES[key]
                return {'Cue': moved}
            if key in HARDWARE_OUTPUTS:                   # (c)
                moved = {k: move(v, k) for k, v in body.items()}
                moved['class'] = HARDWARE_OUTPUTS[key]
                return {'CueOutput': moved}
        moved = {}
        for key, item in node.items():
            if parent == 'Media' and key == 'duration' and isinstance(item, str):
                moved[key] = {'CTimecode': item}          # (b)
            else:
                moved[key] = move(item, key)
        return moved

    value = {k: v for k, v in value.items() if k != SCHEMA_LOCATION}  # (a)
    return move(value)


def _sha256(path):
    with open(path, 'rb') as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _capture():
    with open(CAPTURE, encoding='utf-8') as fh:
        return json.load(fh)


@pytest.fixture
def lib(tmp_path):
    """A temporary library holding the 013 fixture as one project, plus its media rows."""
    root = str(tmp_path)
    for sub in ('media', 'trash/projects', 'trash/media', 'tmp', 'projects/minimal'):
        os.makedirs(os.path.join(root, sub), exist_ok=True)
    script = os.path.join(root, 'projects', 'minimal', 'script.xml')
    shutil.copy(FIXTURE_013, script)

    settings = get_settings()
    settings['library_path'] = root
    settings['tmp_path'] = os.path.join(root, 'tmp')
    database.init(os.path.join(root, 'project-manager.db'))
    database.connect()
    database.create_tables([Project, Media, ProjectMedia], safe=True)

    uuid = _capture()['value']['CuemsScript']['id']
    Project.create(uuid=uuid, name='Test Script', unix_name='minimal',
                   created=new_datetime(), modified=new_datetime(), in_trash=False)
    for name, duration in DB_DURATIONS.items():
        Media.create(uuid=str(new_uuid()), name=name, unix_name=name, created=new_datetime(),
                     modified=new_datetime(), duration=duration, media_type='AUDIO',
                     in_trash=False)

    class Lib:
        pass
    ctx = Lib()
    ctx.root, ctx.script, ctx.uuid = root, script, uuid
    ctx.project = CuemsDBProject(settings, database)
    yield ctx
    database.close()


# ─── the open path ───────────────────────────────────────────────────────


def test_the_capture_is_the_pre_013_frame():
    """Guards the delta function against a capture that already has the deltas."""
    text = json.dumps(_capture())
    assert SCHEMA_LOCATION in text
    assert '"AudioCue"' in text and '"Cue"' not in text
    assert '"duration": "00:00:00.000"' in text


def test_open_frame_differs_from_the_capture_by_three_deltas_only(lib):
    before = _sha256(lib.script)

    value = lib.project.load(lib.uuid)
    frame = json.loads(json.dumps({'type': 'project', 'value': value}))

    assert _sha256(lib.script) == before, 'opening a project wrote its script'
    expected = apply_project_deltas(_capture()['value'])
    # Text comparison: key order and "True"/"False" are part of the contract.
    assert json.dumps(frame['value']) == json.dumps(expected)
    assert 'doc_version' not in json.dumps(frame)


def test_open_writes_nothing_else(lib):
    listing_before = sorted(os.walk(lib.root))
    lib.project.load(lib.uuid)
    assert sorted(os.walk(lib.root)) == listing_before


# ─── the save path: media durations come from the database ───────────────


def _client_payload(cue_class=None):
    """What the UI sends back: the open frame's value, durations zeroed."""
    payload = copy.deepcopy(apply_project_deltas(_capture()['value']))
    for item in payload['CuemsScript']['CueList']['contents']:
        cue = item.get('Cue')
        if cue and 'Media' in cue:
            cue['Media']['duration'] = '00:00:00.000'   # an older UI sends a bare zero
    if cue_class is not None:
        # Every Media-bearing cue becomes this class.
        for item in payload['CuemsScript']['CueList']['contents']:
            if 'Cue' in item and 'Media' in item['Cue']:
                item['Cue']['class'] = cue_class
    return payload


@pytest.mark.parametrize('cue_class', ['audio', 'video', 'lighting'])
def test_zero_duration_on_a_cue_keyed_cue_is_corrected_from_the_database(lib, cue_class):
    lib.project.update(lib.uuid, _client_payload(cue_class))

    script, _report = CuemsScript.load_with_report(lib.script)
    seen = {}
    for cue in script.cuelist.contents:
        media = cue.get('Media') if hasattr(cue, 'get') else None
        if media:
            assert cue.get('class') == cue_class
            seen[media['file_name']] = str(media['duration'])
    assert seen == DB_DURATIONS
