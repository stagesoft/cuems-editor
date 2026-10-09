# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
"""Check a project's media before it is loaded or opened (ClickUp 869fat84r, D20).

A project stores each media file's duration, pixel size, size and MD5. A file
replaced by hand on the controller, under the same name, leaves them stale: the
cue ends at the old length and an Auto follow fires at the old end.

The editor never rewrites a project on its own (D21, plan §8): it corrects what
belongs to the library (the media rows, the video indexes) and **reports** the
values the project still holds that no longer match, in a ``media_check_report``
the UI shows (D22). The next save writes them.

:func:`refresh_media_before_load`, awaited by ``project_ready``:

1. read and compare, writing nothing (``plan_media_refresh``);
0. only when there are files to measure or index: not while a show is running,
   nor when the engine does not answer (``project_status``);
2. re-probe each changed file and correct its row (``verify_media_files``),
   within :data:`~cuemseditor.CuemsDBProject.REFRESH_DEADLINE_S`;
3. rebuild the ``.idx`` of a changed video (an asyncio subprocess: no executor
   worker is held), so the nodes receive a valid one in the same load; a busy
   indexer is never waited for;
4. build the report (``media_report``), marked incomplete when part of the
   check did not run; one WARNING when the project holds stale values.

Never raises. A second request for a project whose check is running joins it.

:func:`check_media_on_open`, after the ``project`` frame of ``project_load``:
the read-only part only (no engine query, no probe, no indexer, no DB write),
shared by simultaneous opens of the same project.

Design: cuems-RELATIONS Plans/2026-10-01-engine-late-go-media-probe.md §7, §8.
"""
import asyncio
import time

from cuemsutils.log import Logger

from cuemseditor import CuemsDBProject as _project
from cuemseditor.CuemsDBMedia import run_video_indexer

_IN_PROGRESS = {}
_OPEN_IN_PROGRESS = {}
_indexer_busy = False


def reset_refresh_state():
    """Forget running checks and the indexer flag (tests)."""
    global _indexer_busy
    _IN_PROGRESS.clear()
    _OPEN_IN_PROGRESS.clear()
    _indexer_busy = False


def _shared(registry, key, make):
    """The running task for *key* in *registry*, or a new one from *make()*."""
    task = registry.get(key)
    if task is None:
        task = asyncio.ensure_future(make())
        registry[key] = task

        def forget(done, key=key):
            if registry.get(key) is done:
                del registry[key]

        task.add_done_callback(forget)
        return task, False
    return task, True


async def refresh_media_before_load(db_project, project_uuid, *, executor, engine_running,
                                    clock=time.monotonic):
    """Check *project_uuid*'s media before it is loaded, and report.

    Args:
        db_project: the editor's ``CuemsDBProject``.
        project_uuid: the project about to be loaded.
        executor: where the blocking steps run (``None``: the loop's default).
        engine_running: coroutine function; ``True`` while a show is running,
            ``False`` when not, ``None`` when the engine did not answer.
        clock: monotonic seconds (tests).

    Returns:
        A report ``dict`` whose ``media_report`` is the value of the
        ``media_check_report`` frame, or ``None`` when the check failed
        (logged). Never raises.
    """
    key = str(project_uuid)
    task, joined = _shared(_IN_PROGRESS, key,
                           lambda: _refresh(db_project, key, executor, engine_running, clock))
    if joined:
        Logger.info(f'project {key}: its media check is already running; waiting for it')
    return await asyncio.shield(task)


async def check_media_on_open(db_project, project_uuid, *, executor):
    """The read-only report for a project being opened (context ``open``).
    Returns ``None`` when it failed (logged). Never raises."""
    key = str(project_uuid)

    async def run():
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(executor, db_project.media_report, key, 'open')
        except Exception as e:
            Logger.error(f'project {key}: the media check at open failed '
                         f'({type(e).__name__}: {e})')
            return None

    task, _ = _shared(_OPEN_IN_PROGRESS, key, run)
    return await asyncio.shield(task)


def _new_report():
    return {'engine_asked': False, 'skipped': None, 'media_report': None,
            'changed': 0, 'legacy': 0, 'failed': 0, 'not_reached': 0,
            'indexed': 0, 'index_failed': 0, 'index_busy': 0, 'index_not_started': 0}


def _incomplete_reason(verified):
    """Why step 2 did not finish, as the report's ``reason``, or ``None``."""
    for name, reason in (('failed', 'probe_failed'), ('in_copy', 'copy_in_progress'),
                         ('not_reached', 'deadline')):
        if verified.get(name):
            return reason
    return None


async def _refresh(db, uuid, executor, engine_running, clock):
    loop = asyncio.get_running_loop()
    started = time.monotonic()
    deadline = clock() + _project.REFRESH_DEADLINE_S
    report = _new_report()
    try:
        plan = await loop.run_in_executor(executor, db.plan_media_refresh, uuid)
        reason = None
        if plan.has_work:
            report['engine_asked'] = True
            running = await engine_running()
            if running is not False:
                report['skipped'] = 'running' if running else 'silent'
                reason = 'engine_running' if running else 'engine_silent'
                Logger.info(f'project {uuid}: media files to measure, but '
                            f'{"a show is running" if running else "the engine did not answer"}: '
                            'nothing corrected')
            else:
                verified = await loop.run_in_executor(executor, db.verify_media_files, plan,
                                                      deadline, clock)
                for name in ('changed', 'legacy', 'failed', 'not_reached'):
                    report[name] = len(verified.get(name, []))
                reason = _incomplete_reason(verified)
                done = set(verified.get('verified', []))
                to_index = [c.path for c in plan.to_index
                            if c.state == 'unchanged' or c.file_name in done]
                report.update(await _index_videos(to_index, deadline, clock))
        media_report = await loop.run_in_executor(executor, db.media_report, uuid, 'ready', reason)
        report['media_report'] = media_report
        if media_report.get('files'):
            Logger.warning(
                f'project {media_report["project_name"]} ({uuid}): '
                f'{media_report["total_files"]} media file(s) with stale stored values '
                f'({", ".join(f["file_name"] for f in media_report["files"])}); the show uses '
                'the stored values until the project is saved')
        if plan.has_work:
            Logger.info(
                f'project {uuid}: media check before the load: {len(plan.checks)} file(s), '
                f'{report["changed"]} changed, {report["legacy"]} verified for the first time, '
                f'{report["failed"]} failed, {report["not_reached"]} left for the next load; '
                f'{report["indexed"]} index(es) rebuilt, {report["index_failed"]} failed; '
                f'{media_report["total_files"]} file(s) stale in the project '
                f'({int((time.monotonic() - started) * 1000)} ms)')
        else:
            Logger.debug(f'project {uuid}: no media file to measure')
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
