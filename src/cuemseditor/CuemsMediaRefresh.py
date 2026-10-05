# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Correct a project's media values before it is loaded (ClickUp 869fat84r, D20).

A project stores each media file's duration, pixel size, size and MD5. A file
replaced by hand on the controller, under the same name, leaves them stale: the
cue ends at the old length and an Auto follow fires at the old end. At load,
every node copies the media from the controller, so correcting the project on
the controller, before the engine is asked, corrects it for every node at once.

:func:`refresh_media_before_load`, awaited by ``project_ready``:

1. read and compare, writing nothing (``plan_media_refresh``): the normal
   load ends here, in milliseconds, without asking the engine anything;
0. only when there is work: not while a show is running, nor when the engine
   does not answer (``project_status``);
2. re-probe each changed file and correct its row (``verify_media_files``),
   within :data:`~cuemseditor.CuemsDBProject.REFRESH_DEADLINE_S`;
3. rebuild the ``.idx`` of a changed video (an asyncio subprocess: no
   executor worker is held), so the nodes receive a valid one in the same
   load instead of each rebuilding it at arm, where it would start the cue
   late; a busy indexer is never waited for;
4. rewrite the project when a value present in it is wrong
   (``rewrite_project_media``);
5. one INFO line; 6. never raises: the load always goes on.

A second request for a project whose check is running joins it.

Design: cuems-RELATIONS Plans/2026-10-01-engine-late-go-media-probe.md §7.
"""
import asyncio
import time

from cuemsutils.log import Logger

from cuemseditor import CuemsDBProject as _project
from cuemseditor.CuemsDBMedia import run_video_indexer

_IN_PROGRESS = {}
_indexer_busy = False


def reset_refresh_state():
    """Forget running checks and the indexer flag (tests)."""
    global _indexer_busy
    _IN_PROGRESS.clear()
    _indexer_busy = False


async def refresh_media_before_load(db_project, project_uuid, *, executor, engine_running,
                                    clock=time.monotonic):
    """Check and correct *project_uuid*'s media values before it is loaded.

    Args:
        db_project: the editor's ``CuemsDBProject``.
        project_uuid: the project about to be loaded.
        executor: where the blocking steps run (``None``: the loop's default).
        engine_running: coroutine function; ``True`` while a show is running,
            ``False`` when not, ``None`` when the engine did not answer.
        clock: monotonic seconds (tests).

    Returns:
        A report ``dict``, or ``None`` when the check failed (logged). Never
        raises.
    """
    key = str(project_uuid)
    task = _IN_PROGRESS.get(key)
    if task is None:
        task = asyncio.ensure_future(_refresh(db_project, key, executor, engine_running, clock))
        _IN_PROGRESS[key] = task

        def forget(done, key=key):
            if _IN_PROGRESS.get(key) is done:
                del _IN_PROGRESS[key]

        task.add_done_callback(forget)
    else:
        Logger.info(f'project {key}: its media check is already running; waiting for it')
    return await asyncio.shield(task)


def _new_report():
    return {'engine_asked': False, 'skipped': None, 'rewritten': False,
            'changed': 0, 'legacy': 0, 'failed': 0, 'not_reached': 0,
            'indexed': 0, 'index_failed': 0, 'index_busy': 0, 'index_not_started': 0}


async def _refresh(db, uuid, executor, engine_running, clock):
    loop = asyncio.get_running_loop()
    started = time.monotonic()
    deadline = clock() + _project.REFRESH_DEADLINE_S
    report = _new_report()
    try:
        plan = await loop.run_in_executor(executor, db.plan_media_refresh, uuid)
        if not plan.has_work:
            Logger.debug(f'project {uuid}: media values in line with the files')
            return report
        report['engine_asked'] = True
        running = await engine_running()
        if running is not False:
            report['skipped'] = 'running' if running else 'silent'
            reason = 'a show is running' if running else 'the engine did not answer'
            Logger.info(f'project {uuid}: media values to check, but {reason}: nothing '
                        'corrected, loading with the stored values')
            return report
        verified = await loop.run_in_executor(executor, db.verify_media_files, plan, deadline,
                                              clock)
        for name in ('changed', 'legacy', 'failed', 'not_reached'):
            report[name] = len(verified.get(name, []))
        done = set(verified.get('verified', []))
        to_index = [c.path for c in plan.to_index
                    if c.state == 'unchanged' or c.file_name in done]
        report.update(await _index_videos(to_index, deadline, clock))
        report['rewritten'] = await loop.run_in_executor(executor, db.rewrite_project_media, uuid)
        Logger.info(
            f'project {uuid}: media check before the load: {len(plan.checks)} file(s), '
            f'{report["changed"]} changed, {report["legacy"]} verified for the first time, '
            f'{report["failed"]} failed, {report["not_reached"]} left for the next load; '
            f'{report["indexed"]} index(es) rebuilt, {report["index_failed"]} failed; project '
            f'{"rewritten" if report["rewritten"] else "unchanged"} '
            f'({int((time.monotonic() - started) * 1000)} ms)')
        return report
    except Exception as e:
        Logger.error(f'project {uuid}: the media check before the load failed '
                     f'({type(e).__name__}: {e}); loading with the stored values')
        return None


async def _index_videos(paths, deadline, clock=time.monotonic):
    """Rebuild the index of each video in *paths*, one at a time.

    An indexer, once started, runs to completion (killing it at a deadline
    would make every load start it again). None is started after *deadline*,
    and none while another load's indexer runs: that load is never waited for.
    A video left without a valid index is rebuilt by each node at arm, and its
    cue can start late; that is logged.
    """
    global _indexer_busy
    out = {'indexed': 0, 'index_failed': 0, 'index_busy': 0, 'index_not_started': 0}
    for i, path in enumerate(paths):
        left = len(paths) - i
        if clock() >= deadline:
            out['index_not_started'] = left
            Logger.warning(f'{left} video index(es) not rebuilt before the time limit, left '
                           f'for the next load: nodes rebuild them at arm, and those cues can '
                           f'start late')
            break
        if _indexer_busy:
            out['index_busy'] = left
            Logger.warning(f'another load is rebuilding a video index: {left} index(es) left '
                           f'as they are; nodes rebuild them at arm, and those cues can '
                           f'start late')
            break
        _indexer_busy = True
        started = time.monotonic()
        try:
            ok = await run_video_indexer(path)
        finally:
            _indexer_busy = False
        if ok:
            out['indexed'] += 1
            Logger.info(f'rebuilt the video index of {path} '
                        f'({int((time.monotonic() - started) * 1000)} ms)')
        else:
            out['index_failed'] += 1
            _project.mark_index_failed(path)
            Logger.warning(f'the video index of {path} could not be rebuilt: nodes rebuild '
                           f'it at arm, and this cue can start late')
    return out
