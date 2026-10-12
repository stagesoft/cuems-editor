# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""Upstream gates of the ``xml-refactor-merge-candidate`` tag (002 S6, S7, FR-032).

Each test asserts what the editor will do once another repository fixes a
gap, and is a strict xfail until then: the day it passes it XPASSes, which
fails the suite, and its marker comes off. Every reason names the gate as
``<repo> UR-<n>``. The tag is not cut while any of them is xfailed
(specs/002-config-round-trip/tag-readiness.md).

Gate G1 lives in ``tests/test_schema_descriptor.py``
(``test_first_config_save_of_project_settings_round_trips``).
"""

import pytest

from test_config_round_trip import PROJECT, _load, env, user  # noqa: F401  (fixtures)

PROJECT_SETTINGS = (
    "<?xml version='1.0' encoding='utf-8'?>"
    '<cms:CuemsProjectSettings xmlns:cms="https://stagelab.coop/cuems/" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
    'xsi:schemaLocation="https://stagelab.coop/cuems/ project_settings.xsd">'
    '<setting><name>previous</name><value>0</value></setting>'
    '</cms:CuemsProjectSettings>')


# ─── G2: cuems-editor UR-7 ───────────────────────────────────────────────


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="cuems-editor UR-7: project_settings has no public read projection (gate G2)")
def test_config_load_project_settings_round_trips(env, user):
    (env.project / 'settings.xml').write_text(PROJECT_SETTINGS, encoding='utf-8')

    frames = _load(user, 'project_settings', PROJECT)

    assert [f['type'] for f in frames] == ['config_load']
    value = frames[0]['value']
    assert value['exists'] is True
    assert value['document'] == {'setting': [{'name': 'previous', 'value': '0'}]}
