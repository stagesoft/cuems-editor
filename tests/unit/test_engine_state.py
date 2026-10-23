# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
"""The media check reads the engine's ``project_status`` as four distinct cases (003, FR-015).

Since cuems-engine 0.1.0rc6-4 ``project_status`` is three-state: ``running`` (a show is
playing), ``loaded`` (a project is loaded and stopped) and ``none``. The released
``_engine_running`` mapped ``{'running': True, 'none': False}.get(status)``, so
``loaded`` came out as ``None``, "the engine did not answer", and the check skipped
every re-probe whenever a project was loaded but stopped (constitution IV gate 4: a
caller that still resolves but now computes the wrong answer).

``True`` defers re-probing (reason ``engine_running``); ``False`` lets it proceed;
``None`` is "no answer" (reason ``engine_silent``). ``loaded`` and ``none`` are both
``False``: neither is a show playing.
"""
import asyncio
from unittest import mock

import pytest

from cuemseditor.CuemsWsUser import CuemsWsUser


def _user():
    user = object.__new__(CuemsWsUser)
    user.websocket = mock.Mock()
    return user


def _ask(reply):
    user = _user()

    async def engine(action, action_uuid, command, query_mode=False):
        assert (command['action'], query_mode) == ('project_status', True)
        if isinstance(reply, Exception):
            raise reply
        return reply

    async def run():
        with mock.patch.object(user, 'comunicate_with_engine', side_effect=engine):
            return await user._engine_running()

    return asyncio.run(run())


@pytest.mark.parametrize('reply, expected', [
    ({'status': 'running', 'project_uuid': 'u', 'project_unix_name': 'p'}, True),
    ({'status': 'loaded', 'project_uuid': 'u', 'project_unix_name': 'p'}, False),
    ({'status': 'none', 'project_uuid': '', 'project_unix_name': ''}, False),
    (RuntimeError('timeout'), None),
    ('OK', None),
    ({'status': 'something-new'}, None),
    ({}, None),
])
def test_the_engine_reply_maps_to_four_cases(reply, expected):
    assert _ask(reply) is expected
