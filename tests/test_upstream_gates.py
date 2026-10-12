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

import asyncio
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from test_config_round_trip import PROJECT, _load, env, user  # noqa: F401  (fixtures)

NODECONF = Path(__file__).resolve().parent.parent.parent / 'cuems-nodeconf'
NODE = '4b9b5a1e-0000-4000-8000-0123456789ab'

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


# ─── G4: cuems-editor UR-8 ───────────────────────────────────────────────


class _Replies:
    """nodeconf's ``communications_thread``, reduced to the reply path, on a loop of its own."""

    def __init__(self):
        self.event_loop = asyncio.new_event_loop()
        self.replies = []
        self.answered = threading.Event()
        self.thread = threading.Thread(target=self.event_loop.run_forever, daemon=True)
        self.thread.start()

    async def respond_to_engine(self, message, context):
        self.replies.append(message)
        self.answered.set()

    def stop(self):
        self.event_loop.call_soon_threadsafe(self.event_loop.stop)
        self.thread.join(timeout=5)
        self.event_loop.close()


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="cuems-editor UR-8: cuems-nodeconf has no node_set (gate G4); "
                          "needs cuems-utils NodeIndex.set_alias")
def test_nodeconf_engine_callback_accepts_node_set(monkeypatch):
    """Gate G4: nodeconf's real handler, given the exact request the editor sends.

    Imports ``cuemsnodeconf.CuemsNodeConf`` from the sibling ``../cuems-nodeconf``
    working tree (a branch carrying ``engine_callback``: ``feat/xml-refactor``),
    with its OS-facing modules stubbed. An import failure errors; it is not
    an xfail.
    """
    if not NODECONF.is_dir():
        pytest.skip('../cuems-nodeconf is not checked out here (a deployed host)')
    monkeypatch.syspath_prepend(str(NODECONF))
    for module in ('netifaces', 'systemd', 'systemd.daemon', 'dbus', 'zeroconf'):
        monkeypatch.setitem(sys.modules, module, MagicMock())
    for module in [m for m in sys.modules if m == 'cuemsnodeconf' or m.startswith('cuemsnodeconf.')]:
        monkeypatch.delitem(sys.modules, module)
    from cuemsnodeconf.CuemsNodeConf import CuemsNodeConf

    nodeconf = CuemsNodeConf.__new__(CuemsNodeConf)
    nodeconf._ready = True
    nodeconf.communications_thread = replies = _Replies()
    try:
        nodeconf.engine_callback({'action': 'node_set', 'node_uuid': NODE, 'alias': 'Stage left'}, context=None)
        assert replies.answered.wait(timeout=5), 'engine_callback did not answer'
    finally:
        replies.stop()

    assert replies.replies == [{'OK': True}]
