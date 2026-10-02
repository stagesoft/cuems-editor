# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""``initial_template`` differs from the ``create_script()`` baseline only by listed deltas.

FR-008, research R10, constitution IV.2. The baseline is the last cuemsutils
release that still shipped ``create_script`` (``v0.1.0rc14``), recorded in
``specs/001-cuems-utils-migration/evidence/create-script-baseline.json``. The
served value is whatever ``CuemsWsServer`` puts on the wire. The deltas are
applied to the baseline here, one function each, and what is left must match
key for key, in order, and value for value outside the placeholder keys.

The same list is in ``tests/ws-command-responses.txt`` beside ``initial_template``.
"""

import json
import os
from unittest.mock import MagicMock

import pytest

import cuemseditor.CuemsWsServer as server_module
from cuemseditor.cli import get_mappings, get_settings
from cuemseditor.CuemsWsServer import CuemsWsServer

HERE = os.path.dirname(__file__)
CONF = os.path.join(HERE, 'fixtures', 'conf')
BASELINE = os.path.join(
    HERE, '..', 'specs', '001-cuems-utils-migration', 'evidence', 'create-script-baseline.json')

HARDWARE_CUES = {'AudioCue': 'audio', 'VideoCue': 'video', 'DmxCue': 'dmx'}
HARDWARE_OUTPUTS = {'AudioCueOutput': 'audio', 'VideoCueOutput': 'video', 'DmxCueOutput': 'dmx'}

# Delta (d): an example, not a template, so these carry example values. The key
# and its position are still pinned; only the value may differ.
PLACEHOLDER_KEYS = {
    'id', 'created', 'modified', 'name', 'description', 'file_name',
    'master_vol', 'output_name', 'output_vol', 'channel_vol', 'action_target',
    'CTimecode',
}


def apply_deltas(node, parent=None):
    """The baseline, moved through every enumerated delta.

    (a) a ``cms:BoolType`` value is the string ``"True"`` / ``"False"``, not JSON
        ``true`` / ``false`` (the same projection ``project`` uses);
    (b) a ``ui_properties`` scalar is its string form (``0`` -> ``"0"``,
        ``null`` -> ``"None"``);
    (c) a hardware cue's key is ``Cue`` with ``class`` last, and a hardware cue
        output's key is ``CueOutput`` with ``class`` last. ``ActionCue``,
        ``FadeCue`` and ``CueList`` keep their keys. ``generate_example`` emits
        this; it is not stripped;
    (e) hardware cues carry no ``fade_profiles`` key (dropped by the version 2
        document shape);
    (f) ``Media.duration`` is ``{"CTimecode": ...}``, not a bare string.
    (d) is ``PLACEHOLDER_KEYS``, checked in ``assert_matches``.
    """
    if isinstance(node, bool):
        return str(node)
    if isinstance(node, list):
        return [apply_deltas(item, parent) for item in node]
    if not isinstance(node, dict):
        return node
    if len(node) == 1:
        (key, body), = node.items()
        if key in HARDWARE_CUES:
            moved = {k: apply_deltas(v, k) for k, v in body.items() if k != 'fade_profiles'}
            moved['class'] = HARDWARE_CUES[key]
            return {'Cue': moved}
        if key in HARDWARE_OUTPUTS:
            moved = {k: apply_deltas(v, k) for k, v in body.items()}
            moved['class'] = HARDWARE_OUTPUTS[key]
            return {'CueOutput': moved}
    moved = {}
    for key, value in node.items():
        if parent == 'Media' and key == 'duration' and isinstance(value, str):
            moved[key] = {'CTimecode': value}
        elif parent == 'ui_properties' and not isinstance(value, (dict, list)):
            moved[key] = str(value)
        else:
            moved[key] = apply_deltas(value, key)
    return moved


def assert_matches(expected, served, path='value'):
    if isinstance(expected, dict):
        assert isinstance(served, dict), f'{path}: {served!r} is not an object'
        assert list(served) == list(expected), f'{path}: keys {list(served)} != {list(expected)}'
        for key in expected:
            if key in PLACEHOLDER_KEYS and not isinstance(expected[key], (dict, list)):
                assert served[key] is None or isinstance(served[key], (str, int, float)), f'{path}/{key}'
                continue
            assert_matches(expected[key], served[key], f'{path}/{key}')
    elif isinstance(expected, list):
        assert isinstance(served, list) and len(served) == len(expected), f'{path}: length'
        for index, (want, got) in enumerate(zip(expected, served)):
            assert_matches(want, got, f'{path}[{index}]')
    else:
        assert type(served) is type(expected) and served == expected, f'{path}: {served!r} != {expected!r}'


@pytest.fixture
def server(monkeypatch, tmp_path):
    monkeypatch.setenv('CUEMS_CONF_PATH', CONF)
    monkeypatch.setattr(server_module, 'Communicator', MagicMock())
    settings = get_settings()
    settings['tmp_path'] = str(tmp_path)
    return CuemsWsServer(settings, get_mappings())


def test_served_template_differs_from_the_baseline_only_by_the_listed_deltas(server):
    with open(BASELINE, encoding='utf-8') as fh:
        baseline = json.load(fh)
    frame = json.loads(server.initial_json_template())

    assert frame['type'] == 'initial_template'
    assert list(frame['value']) == ['CuemsScript']
    assert_matches(apply_deltas(baseline['payload']), frame['value'])


def test_the_delta_list_is_not_vacuous():
    """Each delta must change the baseline, or it is not a delta."""
    with open(BASELINE, encoding='utf-8') as fh:
        payload = json.load(fh)['payload']
    moved = json.dumps(apply_deltas(payload))
    original = json.dumps(payload)
    assert '"AudioCue"' in original and '"AudioCue"' not in moved
    assert '"AudioCueOutput"' in original and '"CueOutput"' in moved
    assert 'fade_profiles' in original and 'fade_profiles' not in moved
    assert 'true' in original and 'true' not in moved
    assert '"duration": "00:00:00.000"' in original and '"duration": {"CTimecode"' in moved
