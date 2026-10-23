# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
import asyncio
import functools
import hashlib
import json
import os
import sys
from datetime import datetime

import websockets as ws
from cuemsutils.errors import IngestError, ValidationError
from cuemsutils.helpers import Unset, new_uuid
from cuemsutils.log import Logger
from cuemsutils.tools import coerce_identity
from cuemsutils.tools.CommunicatorServices import Communicator
from cuemsutils.tools.ConfigManager import ConfigManager, SchemaName
from cuemsutils.tools.Uuid import Uuid

from cuemseditor.CuemsErrors import DocumentLoadFailed, EngineError, NonExistentItemError, OriginalNotPreserved
from cuemseditor.CuemsMediaRefresh import check_media_on_open, refresh_media_before_load
from cuemseditor.node_reads import IdentityCollision

TIMEOUT = 25  # TODO: make it configurable, or get from settings

def functionNameAsString(n=0):
    return sys._getframe(n + 1).f_code.co_name

# document_load_failed always offers all three: the editor cannot know which
# one the operator can carry out.
LOAD_FAILED_NEXT_STEPS = ['restore_from_conversion_backup', 'correct_field_by_hand', 'remove_document']


def file_lock(server, path):
    """The ``asyncio.Lock`` that serialises saves of *path* (research R6).

    Keyed by the resolved path, so two spellings of one file share a lock.
    Event-loop thread only: ``server.file_locks`` is shared state.
    """
    return server.file_locks.setdefault(os.path.realpath(path), asyncio.Lock())


def bytes_md5(path):
    """md5 hex digest of *path*'s bytes, or ``None`` when it does not exist. Runs in the executor."""
    try:
        with open(path, 'rb') as fh:
            return hashlib.md5(fh.read()).hexdigest()
    except FileNotFoundError:
        return None


def _json_safe(value):
    """A library value as JSON: scalars as they are, ``None`` as null, anything
    else (``CTimecode``, ``Uuid``, an enum) as its string form."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    enum_value = getattr(value, 'value', None)
    if isinstance(enum_value, str):
        return enum_value
    return str(value)


def derive_gate(project_uuid, report, script_md5, media_repairs=(), media_rows_digest=None, prior=None):
    """The repair gate of *project_uuid* for a load of the bytes hashed as *script_md5*.

    A ``GateState`` (specs/002-config-round-trip/data-model.md): the library's
    *report* and the stale media values of the same load (*media_repairs*,
    read from the library rows that hash to *media_rows_digest*). When
    *prior* describes the same bytes and the same rows, it is updated in
    place and returned: its ``report_id``, ``acknowledged_by`` and
    ``preserved`` stand, so a second session loading the project does not
    revoke the first one's acknowledgment (research R8.5, FR-045).
    Otherwise a new ``report_id`` is minted and no session has acknowledged
    it. Event-loop thread only.
    """
    if (prior is not None and prior['script_md5'] == script_md5
            and prior['media_rows_digest'] == media_rows_digest):
        state = prior
    else:
        state = {
            'project_uuid': project_uuid,
            'report_id': str(new_uuid()),
            'script_md5': script_md5,
            'media_rows_digest': media_rows_digest,
            'preserved': False,
            'acknowledged_by': set(),
        }
    state['outcome'] = report.outcome.value
    state['media_repairs'] = list(media_repairs)
    state['acknowledgment_required'] = state['outcome'] != 'clean' or bool(media_repairs)
    state['file_differs_from_loaded'] = bool(report.file_differs_from_loaded) or bool(media_repairs)
    state['report'] = report
    return state


def clean_gate(project_uuid, script_md5):
    """The gate after a save wrote the document: nothing outstanding (FR-010)."""
    return {
        'project_uuid': project_uuid,
        'report_id': str(new_uuid()),
        'outcome': 'clean',
        'media_repairs': [],
        'acknowledgment_required': False,
        'file_differs_from_loaded': False,
        'script_md5': script_md5,
        'media_rows_digest': None,
        'preserved': False,
        'acknowledged_by': set(),
        'report': None,
    }


def gate_requires_ack(state):
    """Whether a save of the project waits for the saving session's acknowledgment."""
    return state['acknowledgment_required']


def load_report_value(report_id, project_uuid, report, media_repairs=()):
    """The ``value`` of ``document_load_report`` for a library ``LoadReport``.

    ``outcome``, ``conversions`` and ``repairs`` are the library's, verbatim.
    ``media_repairs`` (always a list) are the stale media values the editor
    found at load (002 FR-043, FR-044); ``acknowledgment_required`` says
    whether a save waits for an acknowledgment, and ``file_differs_from_loaded``
    covers both parts.
    """
    media_repairs = list(media_repairs)
    return {
        'report_id': report_id,
        'project_uuid': project_uuid,
        'document': report.document,
        'outcome': report.outcome.value,
        'file_differs_from_loaded': bool(report.file_differs_from_loaded) or bool(media_repairs),
        'conversions': [
            {
                'from_version': step.from_version,
                'to_version': step.to_version,
                'description': step.description,
                'dropped_elements': list(step.dropped_elements),
            }
            for step in report.conversions
        ],
        'repairs': [
            {
                'field_path': repair.field_path,
                'previous_value': _json_safe(repair.previous_value),
                'substituted_value': _json_safe(repair.substituted_value),
                'rule_name': repair.rule_name,
            }
            for repair in report.repairs
        ],
        'media_repairs': media_repairs,
        'acknowledgment_required': report.outcome.value != 'clean' or bool(media_repairs),
    }


def _descriptor_default(default):
    """A field default as JSON. No default (``Unset``), a default factory and a
    type are all ``null``, as the descriptor's own ``instance`` renders them."""
    if default is Unset or callable(default):
        return None
    return _json_safe(default)


def schema_descriptor_value(schema, types):
    """The ``value`` of ``schema_descriptor``: the library's descriptor, as JSON.

    Field objects are rendered, not reshaped: the same keys, in the
    library's order, with enums as their values.
    """
    return {
        'schema': schema,
        'types': [
            {
                'key': _json_safe(type_.key),
                'fields': [
                    {
                        'name': field.name,
                        'xsd_type': field.xsd_type,
                        'required': field.required,
                        'repeated': field.repeated,
                        'order': field.order,
                        'kind': _json_safe(field.kind),
                        'enum_values': None if field.enum_values is None else list(field.enum_values),
                        'default': _descriptor_default(field.default),
                        'repairability': _json_safe(field.repairability),
                    }
                    for field in type_.fields
                ],
                'instance': json.loads(json.dumps(type_.instance, default=_json_safe)),
            }
            for type_ in types
        ],
    }


# The four configuration documents, the file each is, and whether that file
# is system-wide (ConfigManager.conf_path) or per-project
# (ConfigManager.project_path, which needs the unix_name a "project_uuid"
# resolves to). Both raise FileNotFoundError for a file not created yet: on
# the read side that is the "exists: false" signal; the write side asks with
# must_exist=False for a first save (gate G1).
CONFIG_FILES = {
    'settings': ('conf', 'settings.xml'),
    'network_map': ('conf', 'network_map.xml'),
    'project_mappings': ('project', 'mappings.xml'),
    'project_settings': ('project', 'settings.xml'),
}

# config_save targets that are refused, with the reason the client is told.
CONFIG_SAVE_REFUSED = {
    'script': 'a script is saved with project_save, not config_save',
    'hardware_outputs': 'hardware_outputs is reserved and has no model bindings',
    'network_map': 'network_map.xml is written by cuems-nodeconf; set an alias with node_set',
}

# The domains config_save writes. network_map is not one (FR-019): nodeconf
# owns that file and reverts any other writer.
CONFIG_SAVE_TARGETS = {name: CONFIG_FILES[name] for name in ('settings', 'project_mappings', 'project_settings')}

# The services whose cached configuration a save makes stale (FR-016). The
# editor only says so (FR-021). where_active: the editor cannot see whether
# cuems-node-engine runs on this host, so the operator decides.
CONFIG_RESTART = {
    'settings': [
        {'service': 'cuems-controller-engine', 'where_active': False},
        {'service': 'cuems-node-engine', 'where_active': True},
    ],
}

# config_load targets that are refused, with the reason the client is told.
CONFIG_LOAD_REFUSED = {
    'script': 'a script is loaded with project_load, not config_load',
    'hardware_outputs': 'hardware_outputs is reserved and has no model bindings',
}

# What a fresh ConfigManager(load_all=False) must load before
# to_wire(<schema>) can project the domain (research R2), each step called
# with the manager and the project's unix_name.
CONFIG_LOAD_STEPS = {
    'settings': (),
    'network_map': (lambda manager, uname: manager.load_network_map(),),
    'project_mappings': (lambda manager, uname: manager.load_net_and_node_mappings(),
                         lambda manager, uname: manager.load_project_mappings(uname)),
    # Gate G2 (cuems-editor UR-7): cuems-utils 015 projects project_settings.
    'project_settings': (lambda manager, uname: manager.load_project_settings(uname),),
}

# Errors by which the library refuses a document: config_save_refused /
# config_load_failed, not the error frame (research R5). SchemaError is a
# ValidationError.
LIBRARY_REFUSALS = (IngestError, ValidationError)


class ConfigChanged(Exception):
    """The file changed between the revision check and the backup, under the lock."""


def _config_path(manager, name, project_uname, *, must_exist=True):
    """The document's path.

    With ``must_exist`` (the read side) a file not created yet raises
    ``FileNotFoundError``, which ``config_load`` answers as ``exists: false``.
    ``config_save`` passes ``must_exist=False`` for a first save (gate G1,
    cuems-editor UR-6): the path of the file it is about to create.
    """
    kind, file_name = CONFIG_FILES[name.value]
    if kind == 'conf':
        return manager.conf_path(file_name, must_exist=must_exist)
    return manager.project_path(project_uname, file_name, must_exist=must_exist)


def _root_instance(manager, name):
    """The descriptor ``instance`` of the domain's root type (FR-013, research R4).

    A form's starting point that is also a saveable document: since cuems-utils
    015 (gate G3) every required leaf is seeded with a value its type accepts,
    and the instance is in ``to_wire()`` shape, so ``config_save`` accepts it
    unmodified (``test_a_config_root_instance_saves_through_config_save``). The
    seeds are placeholders, not an operator's values. Each call gets its own
    copy from the library, so the JSON round trip below is only for
    ``_json_safe``, not for isolation.
    """
    types = manager.get_schema_descriptor(name)
    root = next(t for t in types if t.key.is_path and '/' not in t.key.name)
    return json.loads(json.dumps(root.instance, default=_json_safe))


def _load_config_document(name, project_uname=None):
    """``(exists, revision, document)`` of one config document. Runs in the executor.

    The revision is the md5 of the bytes, taken before the load: a file that
    changes in between makes the client's next save a conflict carrying the
    current document, which is safe. A fresh manager per call: the server's
    startup copy is never served (S3).
    """
    manager = ConfigManager(load_all=False)
    try:
        path = _config_path(manager, name, project_uname)
    except FileNotFoundError:
        return False, None, _root_instance(manager, name)
    revision = bytes_md5(path)
    for step in CONFIG_LOAD_STEPS[name.value]:
        step(manager, project_uname)
    document = json.loads(json.dumps(manager.to_wire(name.value), default=_json_safe))
    return True, revision, document


def _resolve_config_path(name, project_uname=None):
    """The target path, or ``None`` when the file does not exist. Runs in the executor."""
    try:
        return _config_path(ConfigManager(load_all=False), name, project_uname)
    except FileNotFoundError:
        return None


def _save_config_document(name, document, path, scope, revision):
    """Back up, build and write one ``config_save`` document; return the new md5. Runs in the executor.

    Called under the file's lock after the revision check. The bytes backed
    up are the bytes that hashed to *revision*: a writer outside the editor
    in between raises :class:`ConfigChanged`. The document is built first, so
    a payload the library refuses leaves no backup; a refusal at ``.save()``
    (T1) removes the backup it made, since the file is unchanged. If the
    backup cannot be written, nothing is saved (FR-015a).

    A *revision* of ``None`` is a first save (gate G1): there is nothing to
    back up, and a file that appeared since the check is a ``ConfigChanged``,
    exactly as a changed one is.
    """
    manager = ConfigManager(load_all=False)
    if revision is None:
        if os.path.exists(path):
            raise ConfigChanged(path)
        built = manager.from_json(name, document)
        built.save(path)
        Logger.info(f'config_save of {name.value}: {path} created')
        return bytes_md5(path)
    with open(path, 'rb') as fh:
        original = fh.read()
    if hashlib.md5(original).hexdigest() != revision:
        raise ConfigChanged(path)
    built = manager.from_json(name, document)
    backup = _write_config_backup(manager.library_path, scope, path, original)
    try:
        built.save(path)
    except Exception:
        os.remove(backup)
        raise
    Logger.info(f'config_save of {name.value}: {path} replaced, previous bytes in {backup}')
    return bytes_md5(path)


def _write_config_backup(library_path, scope, path, original):
    """``<library>/trash/config/<scope>_<file stem>_<YYYYmmddTHHMMSS>.xml``, never overwritten."""
    directory = os.path.join(library_path, 'trash', 'config')
    os.makedirs(directory, exist_ok=True)
    stem = os.path.splitext(os.path.basename(path))[0]
    base = f"{scope}_{stem}_{datetime.now().strftime('%Y%m%dT%H%M%S')}"
    candidate, n = os.path.join(directory, f'{base}.xml'), 0
    while True:
        try:
            with open(candidate, 'xb') as fh:
                fh.write(original)
            return candidate
        except FileExistsError:
            n += 1
            candidate = os.path.join(directory, f'{base}-{n}.xml')


def refusal_value(schema, project_uuid, error):
    """The ``value`` of ``config_save_refused`` / ``config_load_failed`` for a library refusal.

    The location comes from the library's ``Violation``, never from parsing
    its message (research R5): a refusal without one has null ``field``,
    ``location`` and ``rule``.
    """
    violation = getattr(error, 'violation', None)
    location = getattr(violation, 'location', None)
    return {
        'schema': schema,
        'project_uuid': project_uuid,
        'field': location[1] if location and len(location) > 1 else None,
        'location': None if location is None else list(location),
        'rule': getattr(violation, 'rule', None),
        'message': str(error),
    }


# node_set carries the one node field the operator owns (002 M7,
# cuems-common docs/node-identity-contract.md). Discovery owns uuid, name,
# node_role, ip and online; nodeconf owns adopted, role_id and hostname.
NODE_SET_FIELDS = ('node_uuid', 'alias')


def node_set_refused(node_uuid, reason, message):
    """``node_set_refused``: unavailable, timeout, nodeconf_error, not_operator_field or invalid_value."""
    return json.dumps({"type": "node_set_refused", "value": {
        "node_uuid": node_uuid, "reason": reason, "message": message}})


def load_failed_value(project_uuid, error):
    """The ``value`` of ``document_load_failed`` for a :class:`DocumentLoadFailed`."""
    violation = getattr(error.cause, 'violation', None)
    cue_id, field = getattr(violation, 'location', None) or (None, None)
    return {
        'project_uuid': project_uuid,
        'document': error.document,
        'cue_id': None if cue_id is None else str(cue_id),
        'field': field,
        'message': str(error.cause),
        'next_steps': list(LOAD_FAILED_NEXT_STEPS),
    }


class CuemsWsUser():
    """Per-connection session handler for the project-manager WebSocket endpoint.

    Owns two asyncio queues — ``incoming`` (fed by :meth:`consumer_handler`)
    and ``outgoing`` (drained by :meth:`producer_handler`).  Three concurrent
    :meth:`consumer` coroutines dispatch commands from the incoming queue so
    that slow operations (e.g. engine IPC) do not block the interface.

    All project and media operations are dispatched to the thread-pool
    executor via ``server.event_loop.run_in_executor`` so they do not block
    the event loop.

    Attributes:
        session_id: UUID string assigned by :meth:`CuemsWsServer.check_session`
            after registration; ``None`` until then.
        incoming: ``asyncio.Queue`` of raw JSON strings from the WebSocket.
        outgoing: ``asyncio.Queue`` of serialised JSON strings to send.

    Example:
        The server creates one instance per connection::

            user = CuemsWsUser(server, websocket)
            await server.register(user, path)
            consumer_task = asyncio.create_task(user.consumer_handler())
            producer_task = asyncio.create_task(user.producer_handler())
            processor_tasks = [asyncio.create_task(user.consumer()) for _ in range(3)]
    """

    def __init__(self, server, websocket):
        """Bind the session to *server* and *websocket*.

        Args:
            server: The parent ``CuemsWsServer`` instance.
            websocket: The WebSocket connection for this session.
        """
        self.server = server
        asyncio.set_event_loop(server.event_loop)
        self.incoming = asyncio.Queue()
        self.outgoing = asyncio.Queue()
        self.websocket = websocket
        self.session_id = None
        server.users[self] = None

    async def consumer_handler(self):
        """Read frames from the WebSocket and enqueue them on ``incoming``.

        Runs until the WebSocket closes.  Connection-closed exceptions are
        caught and logged at DEBUG level.
        """
        try:
            async for message in self.websocket:
                await self.incoming.put(message)
        except (ws.exceptions.ConnectionClosed, ws.exceptions.ConnectionClosedOK, ws.exceptions.ConnectionClosedError) as e:
            Logger.debug(e)

    async def producer_handler(self):
        """Dequeue messages from ``outgoing`` and send them over the WebSocket.

        Runs until the WebSocket closes.  Connection-closed exceptions break
        the loop cleanly.
        """
        while True:
            message = await self.outgoing.get()
            try:
                await self.websocket.send(message)
            except (ws.exceptions.ConnectionClosed, ws.exceptions.ConnectionClosedOK, ws.exceptions.ConnectionClosedError) as e:
                Logger.debug(e)
                break

    async def consumer(self):
        """Dequeue and dispatch one command at a time from ``incoming``.

        Parses the JSON frame, looks up the ``action`` key in the dispatch
        map, and awaits the corresponding handler coroutine.  Errors at any
        stage are caught and reported to the client via
        :meth:`notify_error_to_user`.

        The server launches three concurrent instances of this coroutine so
        that one slow handler (e.g. engine IPC) does not starve the other two.
        """
        while True:
            message = await self.incoming.get()
            try:
                data = json.loads(message)
            except Exception as e:
                Logger.error("error: {} {}".format(type(e), e))
                await self.notify_error_to_user('error decoding json')
                continue
            try:
                action = data.get("action")
                value = data.get("value")
                if not action:
                    Logger.error(f"unsupported event: {data}")
                    await self.notify_error_to_user(f"unsupported event: {data}")
                    return

                action_map = {
                    "project_load": lambda: self.send_project(value, action),
                    "project_ready": lambda: self.project_ready(value, action),
                    "project_deploy": lambda: self.project_deploy(value, action),
                    "project_new": lambda: self.received_new_project(value, action, data.get("unix_name")),
                    "project_save": lambda: self.received_project(value, action),
                    "project_delete": lambda: self.request_delete_project(value, action),
                    "project_restore": lambda: self.request_restore_project(value, action),
                    "project_trash_delete": lambda: self.request_delete_project_trash(value, action),
                    "project_list": lambda: self.list_project(action),
                    "project_duplicate": lambda: self.request_duplicate_project(value, action),
                    "project_export": lambda: self.request_export_project(value, action),
                    "file_list": lambda: self.list_file(action),
                    "project_trash_list": lambda: self.list_project_trash(action),
                    "file_trash_list": lambda: self.list_file_trash(action),
                    "file_save": lambda: self.received_file_data(value, action),
                    "file_load_meta": lambda: self.request_file_load_meta(value, action),
                    "file_load_thumbnail": lambda: self.request_file_load_thumbnail(value, action),
                    "file_load_waveform": lambda: self.request_file_load_waveform(value, action),
                    "file_delete": lambda: self.request_delete_file(value, action),
                    "file_restore": lambda: self.request_restore_file(value, action),
                    "file_trash_delete": lambda: self.request_delete_file_trash(value, action),
                    "hw_discovery": lambda: self.hw_discovery(action),
                    "nodeconf": lambda: self.nodeconf(action),
                    "nodelist_modify": lambda: self.nodelist_modify(value, action, data.get("modify_action")),
                    "nodelist_get": lambda: self.nodelist_get(action),
                    "node_set": lambda: self.node_set(value, action),
                    "node_status": lambda: self.node_status(action),
                    "project_status": lambda: self.project_status(action),
                    "project_unload": lambda: self.project_unload(action),
                    "repair_acknowledge": lambda: self.repair_acknowledge(value, action),
                    "schema_descriptor": lambda: self.schema_descriptor(value, action),
                    "config_load": lambda: self.config_load(value, action),
                    "config_save": lambda: self.config_save(value, action),
                }

                if action in action_map:
                    await action_map[action]()
                else:
                    Logger.error(f"unsupported action: {data}")
                    await self.notify_error_to_user(f"unsupported action: {data}")
            except KeyError as e:
                Logger.error("error missing key:  {}".format(e))
                await self.notify_error_to_user('error missing key {} in request'.format(e))
            except Exception as e:
                Logger.error("error: {} {}".format(type(e), e))
                await self.notify_error_to_user('error processing request')

    async def comunicate_with_engine(self, action, action_uuid, engine_command, query_mode=False):
        """Send a command to ``cuems-engine`` via NNG and validate the response.

        Waits up to ``TIMEOUT`` seconds for a response.  Validates that the
        response carries the expected ``action_uuid``, ``type``, and (unless
        *query_mode* is ``True``) a ``value`` of ``"OK"``.

        Args:
            action: The action string used for type-checking the engine reply.
            action_uuid: UUID string embedded in the command; must be echoed
                back by the engine.
            engine_command: Dict to send as the NNG request payload.
            query_mode: When ``True``, accepts any ``value`` from the engine
                (not just ``"OK"``).  Used for ``project_status`` which returns
                a state dict.  Defaults to ``False``.

        Returns:
            ``response['value']`` from the engine reply.

        Raises:
            EngineError: On timeout, connection failure, UUID mismatch,
                error response, or unexpected response type.

        Example:
            >>> action_uuid = str(new_uuid())
            >>> result = await self.comunicate_with_engine(
            ...     "project_load",
            ...     action_uuid,
            ...     {"action": "project_load", "action_uuid": action_uuid, "value": "my-show"},
            ... )
        """
        try:
            async with asyncio.timeout(TIMEOUT):
                response = await self.server.engine_communicator.send_request(engine_command)
        except TimeoutError:
            raise EngineError(f'Timeout: Engine did not respond in {TIMEOUT}s for {action} (uuid: {action_uuid})')
        except Exception as e:
            raise EngineError(f'Cannot connect to engine: {e} ({type(e).__name__})')

        if not response:
            raise EngineError(f'Engine did not respond with valid response for {action}')

        Logger.debug(f'Got response from engine: {response}')

        if 'action_uuid' not in response:
            raise EngineError(f'Engine response missing action_uuid: {response}')

        if action_uuid not in response['action_uuid']:
            raise EngineError(f'Action UUID mismatch. Expected: {action_uuid}, Got: {response.get("action_uuid")}')

        if 'type' not in response:
            raise EngineError(f'Engine response missing type field: {response}')

        if response['type'] == 'error':
            error_value = response.get('value', 'Unknown error')
            raise EngineError(f'Engine reports error: {error_value}')

        if response['type'] != action:
            raise EngineError(f'Response type mismatch. Expected: {action}, Got: {response["type"]}')

        if not query_mode and response.get('value') != 'OK':
            raise EngineError(f'Engine reports error: {response.get("value", "Unknown error")}')

        Logger.debug(f'Engine response for {action} is OK')
        return response['value']

    async def notify_user(self, msg=None, uuid=None, action=None, new_uuid=None):
        """Enqueue a success notification to the client.

        Three call forms:

        * ``notify_user(msg=...)`` — state message: ``{"type": "state", "value": msg}``.
        * ``notify_user(uuid=..., action=...)`` — action confirmation:
          ``{"type": action, "value": uuid}``.
        * ``notify_user(uuid=..., action=..., new_uuid=...)`` — action with
          rename: ``{"type": action, "value": {"uuid": uuid, "new_uuid": new_uuid}}``.

        Args:
            msg: Plain state message string.
            uuid: Subject item UUID string.
            action: Action name echoed back to the client.
            new_uuid: New UUID string (used for ``project_duplicate``).
        """
        if (uuid is None) and (action is None) and (msg is not None):
            await self.outgoing.put(json.dumps({"type": "state", "value": msg}))
        elif (msg is None and new_uuid is None):
            await self.outgoing.put(json.dumps({"type": action, "value": uuid}))
        elif (msg is None and new_uuid is not None):
            await self.outgoing.put(json.dumps({"type": action, "value": {"uuid": uuid, "new_uuid": new_uuid}}))

    async def notify_error_to_user(self, msg=None, uuid=None, action=None):
        """Enqueue an error notification to the client.

        Three call forms depending on which combination of arguments is
        provided:

        * ``notify_error_to_user(msg=...)`` — bare error:
          ``{"type": "error", "value": msg}``.
        * ``notify_error_to_user(msg=..., action=...)`` — action error:
          ``{"type": "error", "action": action, "value": msg}``.
        * ``notify_error_to_user(msg=..., action=..., uuid=...)`` — item error:
          ``{"type": "error", "uuid": uuid, "action": action, "value": msg}``.

        Args:
            msg: Human-readable error description.
            uuid: UUID of the subject item, if applicable.
            action: Action name that triggered the error, if applicable.
        """
        if (msg is not None) and (uuid is None) and (action is None):
            await self.outgoing.put(json.dumps({"type": "error", "value": msg}))
        elif (action is not None) and (msg is not None) and (uuid is None):
            await self.outgoing.put(json.dumps({"type": "error", "action": action, "value": msg}))
        elif (action is not None) and (msg is not None) and (uuid is not None):
            await self.outgoing.put(json.dumps({"type": "error", "uuid": uuid, "action": action, "value": msg}))

    async def project_ready(self, project_uuid, action):
        """Tell the engine to arm the project identified by *project_uuid*.

        Resolves the ``unix_name`` from the DB, checks the project's media
        files first (869fat84r D20; never blocks the load), builds the
        ``project_ready`` engine command, and awaits the response. After the
        reply, the media check's ``media_check_report`` goes to this session
        and to every other session on the project.

        Args:
            project_uuid: UUID string of the project to arm.
            action: Action name from the WebSocket frame (echoed in the reply).
        """
        Logger.info(f"user {id(self.websocket)} requesting ready project {project_uuid}")
        try:
            unix_name = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.get_project_unix_name, project_uuid)
            refresh = await self._refresh_media(project_uuid)
            action_uuid = str(new_uuid())
            engine_command = {"action": functionNameAsString(), "action_uuid": action_uuid, "value": unix_name}

            result = await self.comunicate_with_engine(action, action_uuid, engine_command)
            Logger.debug(f"project {project_uuid} ready: {result}")

            await self.outgoing.put(json.dumps({"type": functionNameAsString(), "value": project_uuid}))
            # After the reply, so a client waiting for it never reads this first.
            await self._send_media_report(refresh.get('media_report') if refresh else None)

        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

    async def _refresh_media(self, project_uuid):
        """Check *project_uuid*'s media before it is loaded (see
        :mod:`cuemseditor.CuemsMediaRefresh`). Returns its report, or ``None``.
        Never raises: the load goes on with the stored values whatever
        happens here."""
        try:
            return await refresh_media_before_load(self.server.db.project, project_uuid,
                                                   executor=self.server.executor,
                                                   engine_running=self._engine_running)
        except Exception as e:
            Logger.error(f'media check before loading {project_uuid} failed: '
                         f'{type(e).__name__}: {e}; loading with the stored values')
            return None

    async def _send_media_report(self, value):
        """Send a ``media_check_report`` (plan §8.3) to this session and, for
        the ``ready`` and ``save`` contexts, to every other session on the
        project. Nothing when *value* is ``None``. Never raises."""
        if not value:
            return
        try:
            frame = json.dumps({"type": "media_check_report", "value": value})
            await self.outgoing.put(frame)
            if value.get('context') in ('ready', 'save'):
                await self.server.send_to_project_sessions(value['project_uuid'], frame, skip=self)
        except Exception as e:
            Logger.error(f'could not send the media report: {type(e).__name__}: {e}')

    def _in_background(self, coroutine):
        """Run *coroutine* after the current reply, keeping a reference so the
        task is not collected; its errors are logged, never raised."""
        task = asyncio.ensure_future(coroutine)
        pending = getattr(self, '_background_tasks', None)
        if pending is None:
            pending = self._background_tasks = set()
        pending.add(task)
        task.add_done_callback(pending.discard)
        return task

    async def _report_on_open(self, project_uuid):
        """The read-only media check of a project being opened, then its report."""
        value = await check_media_on_open(self.server.db.project, project_uuid,
                                          executor=self.server.executor)
        await self._send_media_report(value)

    async def _report_after_save(self, project_uuid):
        """The read-only media check after a save; its report clears (or keeps)
        the warning of every session on the project."""
        try:
            value = await self.server.event_loop.run_in_executor(
                self.server.executor, self.server.db.project.media_report, project_uuid, 'save')
        except Exception as e:
            Logger.error(f'project {project_uuid}: the media check after the save failed '
                         f'({type(e).__name__}: {e})')
            return
        await self._send_media_report(value)

    async def _engine_running(self):
        """The engine's ``project_status`` as the media check reads it.

        ``True`` while a show is running (re-probing is deferred), ``False``
        when it is not: ``loaded`` (a project loaded and stopped) and ``none``
        are both "not running", and ``None`` when the engine does not answer
        or says something unknown. Since cuems-engine rc6-4 the status is
        three-state; the released two-key mapping read ``loaded`` as silence
        (003 FR-015).
        """
        action_uuid = str(new_uuid())
        command = {"action": "project_status", "action_uuid": action_uuid}
        try:
            result = await self.comunicate_with_engine('project_status', action_uuid, command,
                                                       query_mode=True)
        except Exception as e:
            Logger.info(f'project_status before the media check: {e}')
            return None
        status = result.get('status') if isinstance(result, dict) else None
        return {'running': True, 'loaded': False, 'none': False}.get(status)

    async def hw_discovery(self, action):
        """Ask the engine to run a hardware discovery scan.

        Args:
            action: Action name from the WebSocket frame (echoed in the reply).
        """
        Logger.info(f"user {id(self.websocket)} requesting {functionNameAsString()} dicovery")
        try:
            action_uuid = str(new_uuid())
            engine_command = {"action": functionNameAsString(), "action_uuid": action_uuid}

            result = await self.comunicate_with_engine(action, action_uuid, engine_command)

            await self.outgoing.put(json.dumps({"type": functionNameAsString(), "value": result}))

        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), action=action)

    async def nodeconf(self, action):
        """Ask the engine to run node configuration.

        Args:
            action: Action name from the WebSocket frame (echoed in the reply).
        """
        Logger.info(f"user {id(self.websocket)} requesting {functionNameAsString()} dicovery")
        try:
            action_uuid = str(new_uuid())
            engine_command = {"action": functionNameAsString(), "action_uuid": action_uuid}

            result = await self.comunicate_with_engine(action, action_uuid, engine_command)

            await self.outgoing.put(json.dumps({"type": functionNameAsString(), "value": result}))

        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), action=action)

    async def project_status(self, action):
        """Query the engine for the current project load state without side effects.

        Uses ``query_mode=True`` so the engine's dict response (not just
        ``"OK"``) is accepted and forwarded to the client.

        Args:
            action: Action name from the WebSocket frame (echoed in the reply).
        """
        Logger.info(f"user {id(self.websocket)} requesting {functionNameAsString()}")
        try:
            action_uuid = str(new_uuid())
            engine_command = {"action": functionNameAsString(), "action_uuid": action_uuid}

            result = await self.comunicate_with_engine(action, action_uuid, engine_command, query_mode=True)

            await self.outgoing.put(json.dumps({"type": functionNameAsString(), "value": result}))

        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), action=action)

    async def project_unload(self, action):
        """Tell the engine to unload the current project and clear session state.

        On success, sets ``server.users[self] = None`` and clears
        ``sessions[session_id]['loaded_project']``.

        Args:
            action: Action name from the WebSocket frame (echoed in the reply).
        """
        Logger.info(f"user {id(self.websocket)} requesting {functionNameAsString()}")
        try:
            action_uuid = str(new_uuid())
            engine_command = {"action": functionNameAsString(), "action_uuid": action_uuid}

            await self.comunicate_with_engine(action, action_uuid, engine_command)

            self.server.users[self] = None
            loaded = None
            if self.session_id and self.session_id in self.server.sessions:
                loaded = self.server.sessions[self.session_id].get('loaded_project')
                self.server.sessions[self.session_id]['loaded_project'] = None
            self.release_gate(loaded)

            await self.outgoing.put(json.dumps({"type": functionNameAsString(), "value": "OK"}))

        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), action=action)

    async def nodelist_modify(self, node_uuid, action, modify_action):
        """Add or remove a node from the engine's active node list.

        After a successful engine response, triggers
        ``server.notify_all_node_list_update`` to broadcast the refreshed
        node list to all connected clients.

        Args:
            node_uuid: UUID string of the node to add or remove.
            action: Action name from the WebSocket frame (echoed in the reply).
            modify_action: ``"ADD"`` or ``"REMOVE"``.

        Raises:
            ValueError: If *modify_action* is not ``"ADD"`` or ``"REMOVE"``.
        """
        Logger.info(f"user {id(self.websocket)} requesting {functionNameAsString()} for node {node_uuid} with action {modify_action}")
        try:
            if modify_action not in ["ADD", "REMOVE"]:
                raise ValueError(f"Invalid modify_action: {modify_action}. Must be 'ADD' or 'REMOVE'")

            # Without this a None/empty value travels the whole chain and comes
            # back from nodeconf as the baffling "Node None not found".
            if not node_uuid or not isinstance(node_uuid, str):
                raise ValueError(f"nodelist_modify needs a node uuid, got {node_uuid!r}")

            action_uuid = str(new_uuid())
            engine_command = {
                "action": functionNameAsString(),
                "action_uuid": action_uuid,
                "value": node_uuid,
                "modify_action": modify_action
            }

            result = await self.comunicate_with_engine(action, action_uuid, engine_command)
            Logger.debug(f"nodelist_modify for node {node_uuid}: {result}")

            await self.outgoing.put(json.dumps({"type": "nodelist_modify", "value": "OK"}))

            await asyncio.sleep(0.1)

            try:
                await self.server.notify_all_node_list_update()
            except Exception as e:
                Logger.warning(f'Failed to reload and broadcast node list update after adoption: {e}')

        except EngineError as e:
            Logger.error(f"Engine error in nodelist_modify: {e}")
            await self.notify_error_to_user(str(e), action=action)
        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), action=action)

    async def node_set(self, value, action):
        """Set or remove a node's alias through cuems-nodeconf (FR-024 to FR-026).

        Sent straight to nodeconf on ``server.NODECONF_IPC``, not through the
        engine (Q2), as ``{"action": "node_set", "node_uuid", "alias"}``. The
        editor writes no file: nodeconf owns ``network_map.xml`` and persists
        the alias itself. On ``{"OK": true}`` the caller gets ``node_set`` and
        every session a fresh ``node_list``; nodeconf's ``error`` is relayed
        verbatim and not retried.

        Refused (``node_set_refused``) before any IPC: a field other than
        ``node_uuid`` and ``alias`` (``not_operator_field``); an alias that is
        not a non-empty string or null, or a ``node_uuid`` that
        ``coerce_identity`` does not turn into a uuid (``invalid_value``); no
        nodeconf socket on this host (``unavailable``, at once).

        Args:
            value: ``{"node_uuid": "<uuid>", "alias": "<text>" | null}``;
                null removes the alias.
            action: Action name from the WebSocket frame.
        """
        value = value if isinstance(value, dict) else {}
        node_uuid = value.get('node_uuid')
        others = sorted(str(key) for key in value if key not in NODE_SET_FIELDS)
        if others:
            await self.outgoing.put(node_set_refused(node_uuid, 'not_operator_field',
                f"node_set sets the alias only; not an operator field: {', '.join(others)}"))
            return
        alias = value.get('alias', Unset)
        if not (alias is None or (isinstance(alias, str) and alias.strip())):
            await self.outgoing.put(node_set_refused(node_uuid, 'invalid_value',
                'alias must be a non-empty string, or null to remove it'))
            return
        identity = coerce_identity(node_uuid) if isinstance(node_uuid, str) else None
        if not isinstance(identity, Uuid):
            await self.outgoing.put(node_set_refused(node_uuid, 'invalid_value',
                f"node_uuid {node_uuid!r} is not a node identity"))
            return
        if not self.server.nodeconf_available():
            await self.outgoing.put(node_set_refused(node_uuid, 'unavailable',
                'cuems-nodeconf is not running on this controller; a node alias cannot be set here'))
            return
        request = {"action": "node_set", "node_uuid": str(identity), "alias": alias}
        Logger.info(f"user {id(self.websocket)} requesting node_set {request}")
        try:
            # Communicator calls sys.exit(1) on an unreadable socket path;
            # that must never stop the editor.
            nodeconf = Communicator(self.server.NODECONF_IPC)
        except (SystemExit, PermissionError) as e:
            Logger.error(f"node_set: cannot open {self.server.NODECONF_IPC}: {e!r}")
            await self.outgoing.put(node_set_refused(node_uuid, 'unavailable',
                f"cannot reach cuems-nodeconf on {self.server.NODECONF_IPC}"))
            return
        try:
            async with asyncio.timeout(TIMEOUT):
                reply = await nodeconf.send_request(request)
        except TimeoutError:
            await self.outgoing.put(node_set_refused(node_uuid, 'timeout',
                f"cuems-nodeconf did not answer in {TIMEOUT}s"))
            return
        if not isinstance(reply, dict):
            await self.outgoing.put(node_set_refused(node_uuid, 'unavailable',
                'no reply from cuems-nodeconf'))
            return
        if reply.get('OK') is not True:
            await self.outgoing.put(node_set_refused(node_uuid, 'nodeconf_error', str(reply.get('error'))))
            return
        await self.outgoing.put(json.dumps({"type": "node_set", "value": {
            "node_uuid": node_uuid, "alias": alias}}))
        try:
            await self.server.notify_all_node_list_update()
        except Exception as e:
            Logger.warning(f'Failed to reload and broadcast node list update after node_set: {e}')

    async def nodelist_get(self, action):
        """Re-read network_map.xml and send this client the current node list.

        Same ``node_list`` frame the client gets on connect and on every map
        change (``nodes`` = adopted, ``new_nodes`` = discovered but not
        adopted, ``nodeconf_available``) — a way to refresh on demand instead
        of reconnecting. While the map has a duplicate node identity,
        ``network_map_error`` comes first and the list is the last good one; a
        read that clears it sends ``network_map_error: null`` first.

        Args:
            action: Action name from the WebSocket frame.
        """
        Logger.info(f"user {id(self.websocket)} requesting {functionNameAsString()}")
        try:
            result = await self.server.event_loop.run_in_executor(
                self.server.executor,
                functools.partial(self.server.reload_network_map_nodes, assign=False)
            )
            if not result:
                raise ValueError("could not read network_map.xml")

            # Shared state is assigned here, on the event-loop thread.
            cleared = self.server.assign_network_map_nodes(result)
            if isinstance(result, IdentityCollision) or cleared is True:
                await self.outgoing.put(self.server.network_map_error_message())
            await self.outgoing.put(self.server.node_list_message())

        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), action=action)

    async def schema_descriptor(self, schema, action):
        """Send this client one schema's descriptor.

        The source is ``ConfigManager.get_schema_descriptor(SchemaName(schema))``
        only. Each type carries ``key``, ``fields`` and ``instance``, the
        constructible empty instance a client builds a new document from.

        Args:
            schema: a ``SchemaName`` value (``script``, ``settings``,
                ``network_map``, ``project_mappings``, ``project_settings``,
                ``hardware_outputs``).
            action: Action name from the WebSocket frame.
        """
        try:
            name = SchemaName(schema)
            types = await self.server.event_loop.run_in_executor(
                self.server.executor,
                lambda: ConfigManager(load_all=False).get_schema_descriptor(name))
            await self.outgoing.put(json.dumps({
                "type": "schema_descriptor",
                "value": schema_descriptor_value(name.value, types),
            }))
        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), action=action)

    async def config_domain(self, value, action, refused, targets):
        """Resolve a config request's ``(SchemaName, project_uuid, unix_name)``, or answer it.

        Shared by ``config_load`` and ``config_save``. Sends the error frame
        and returns ``None`` for a name that is not a schema, a refused or
        non-target domain, and a project domain whose ``project_uuid`` is
        missing or unknown (FR-014).
        """
        schema = value.get('schema') if isinstance(value, dict) else None
        try:
            name = SchemaName(schema)
        except ValueError:
            await self.notify_error_to_user(f"{action}: {schema!r} is not a schema", action=action)
            return None
        if name.value in refused:
            await self.notify_error_to_user(f"{action}: {refused[name.value]}", action=action)
            return None
        if name.value not in targets:
            await self.notify_error_to_user(f"{action}: {name.value} is not a target", action=action)
            return None
        project_uuid = project_uname = None
        if CONFIG_FILES[name.value][0] == 'project':
            project_uuid = value.get('project_uuid')
            if not project_uuid or not isinstance(project_uuid, str):
                await self.notify_error_to_user(f"{action} of {name.value} needs a project_uuid", action=action)
                return None
            try:
                project_uname = await self.server.event_loop.run_in_executor(
                    self.server.executor, self.server.db.project.get_project_unix_name, project_uuid)
            except Exception as e:
                Logger.error(f"error: {type(e)} {e}")
                await self.notify_error_to_user(str(e), action=action)
                return None
        return name, project_uuid, project_uname

    async def config_load(self, value, action):
        """Send this client a configuration document as the file holds it (FR-012, FR-013).

        Replies ``config_load`` with ``{schema, project_uuid, exists,
        revision, document}``: the document is ``ConfigManager.to_wire`` of a
        manager loaded for this request, and ``revision`` the md5 of the
        file's bytes, to send back as ``config_save``'s ``base_revision``.
        With no file, ``exists`` is false, ``revision`` null, and the document
        the descriptor's root ``instance``: a form's starting point, which
        ``config_save`` also accepts as it is (gate G3). ``network_map`` is
        served read only.
        A document the library cannot load is ``config_load_failed``;
        anything else the error frame.

        Args:
            value: ``{"schema": <name>}``, plus ``"project_uuid"`` for
                ``project_mappings`` and ``project_settings``.
            action: Action name from the WebSocket frame.
        """
        domain = await self.config_domain(value, action, CONFIG_LOAD_REFUSED, CONFIG_FILES)
        if domain is None:
            return
        name, project_uuid, project_uname = domain
        try:
            exists, revision, document = await self.server.event_loop.run_in_executor(
                self.server.executor, functools.partial(_load_config_document, name, project_uname))
        except LIBRARY_REFUSALS as e:
            Logger.warning(f"config_load of {name.value} refused by the library: {e}")
            await self.outgoing.put(json.dumps({
                "type": "config_load_failed", "value": refusal_value(name.value, project_uuid, e)}))
            return
        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), action=action)
            return
        await self.outgoing.put(json.dumps({"type": "config_load", "value": {
            "schema": name.value, "project_uuid": project_uuid,
            "exists": exists, "revision": revision, "document": document}}))

    async def config_save(self, value, action):
        """Persist a whole configuration document the client loaded (FR-015 to FR-020).

        ``value["base_revision"]`` is required: the ``revision`` the client's
        ``config_load`` returned, or null for "I expect no file" (Q3). Under
        the file's lock the file is hashed again; a mismatch writes nothing
        and answers ``config_conflict`` with the current revision and
        document. Otherwise the bytes just hashed are copied into
        ``<library>/trash/config/`` (if that fails, nothing is saved), the
        document is built with ``ConfigManager.from_json`` and written with
        its own ``save(path)``. The reply carries the new revision and the
        services to restart; every other session gets ``config_changed``.

        Refuses ``script`` (that is ``project_save``), ``hardware_outputs``
        (no model bindings), ``network_map`` (cuems-nodeconf's file; an alias
        is set with ``node_set``), and anything that is not a ``SchemaName``,
        ``default_mappings.xml`` included. A document the library refuses is
        ``config_save_refused`` with the violation's location.

        A first save (``base_revision`` null, no file yet) creates the file,
        with no backup since there is nothing to keep (gate G1, cuems-editor
        UR-6). If the file appears in the meantime, the reply is
        ``config_conflict``.

        Args:
            value: ``{"schema", "document", "base_revision"}``, plus
                ``"project_uuid"`` for ``project_mappings``/``project_settings``.
            action: Action name from the WebSocket frame.
        """
        domain = await self.config_domain(value, action, CONFIG_SAVE_REFUSED, CONFIG_SAVE_TARGETS)
        if domain is None:
            return
        name, project_uuid, project_uname = domain
        if 'base_revision' not in value:
            await self.notify_error_to_user(
                f"config_save of {name.value} needs base_revision (the revision config_load returned, "
                f"or null for no file)", action=action)
            return
        base_revision = value['base_revision']
        document = value.get('document')
        scope = 'controller' if CONFIG_FILES[name.value][0] == 'conf' else project_uname
        try:
            path = await self.server.event_loop.run_in_executor(
                self.server.executor, functools.partial(_resolve_config_path, name, project_uname))
            if path is None:
                if base_revision is not None:
                    await self.send_config_conflict(name, project_uuid, project_uname)
                    return
                # A first save (gate G1): the path of the file about to be
                # created. If it appears meanwhile, the revision check below,
                # or _save_config_document under the lock, answers a conflict.
                path = await self.server.event_loop.run_in_executor(
                    self.server.executor,
                    lambda: _config_path(ConfigManager(load_all=False), name, project_uname, must_exist=False))
            async with file_lock(self.server, path):
                current = await self.server.event_loop.run_in_executor(self.server.executor, bytes_md5, path)
                if current != base_revision:
                    await self.send_config_conflict(name, project_uuid, project_uname)
                    return
                try:
                    revision = await self.server.event_loop.run_in_executor(
                        self.server.executor,
                        functools.partial(_save_config_document, name, document, path, scope, current))
                except ConfigChanged:
                    await self.send_config_conflict(name, project_uuid, project_uname)
                    return
        except LIBRARY_REFUSALS as e:
            Logger.warning(f"config_save of {name.value} refused by the library: {e}")
            await self.outgoing.put(json.dumps({
                "type": "config_save_refused", "value": refusal_value(name.value, project_uuid, e)}))
            return
        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), action=action)
            return
        await self.outgoing.put(json.dumps({"type": "config_save", "value": {
            "schema": name.value, "project_uuid": project_uuid, "revision": revision,
            "restart": CONFIG_RESTART.get(name.value, [])}}))
        await self.server.notify_others_config_changed(self, {
            "schema": name.value, "project_uuid": project_uuid, "revision": revision})

    async def send_config_conflict(self, name, project_uuid, project_uname):
        """``config_conflict`` with the document's current revision and content (FR-015)."""
        _exists, revision, document = await self.server.event_loop.run_in_executor(
            self.server.executor, functools.partial(_load_config_document, name, project_uname))
        await self.outgoing.put(json.dumps({"type": "config_conflict", "value": {
            "schema": name.value, "project_uuid": project_uuid, "revision": revision, "document": document}}))

    async def node_status(self, action):
        """Ask the engine which nodes are answering right now.

        Relays the engine's ``cluster_status``:
        ``{"alive": [...], "adopted": [...], "controller": uuid, "age_s": n}``.

        This is NOT the same thing as the ``online`` field in each node of
        ``initial_mappings``: that one is cuems-nodeconf's discovery view
        (refreshed within ~30 s), while ``alive`` here is the engine's
        sub-second ping/pong — the only signal the GO gate trusts. A UI must
        show them as two separate indicators; merging them tells the operator
        a node is dead when it was merely not seen by the last discovery pass,
        or alive when it vanished 20 s ago.

        ``age_s`` is how stale the probe behind this answer is. A failed or
        timed-out call means *unknown*, never *dead*: while a project load is
        in flight this request queues behind it (the engine serializes editor
        commands) and can time out while every node is perfectly healthy.

        The reply also carries the last load's diagnosis — ``missing`` (project
        nodes not in the cluster at all) and ``unreachable`` (adopted, used by
        the project, no pong). Their cues will not play, and GO is deliberately
        *not* blocked. Nothing is done to them here on purpose: this method
        relays the engine's dict verbatim, so new keys reach the browser with
        no editor change. Do not add a hop.

        Args:
            action: Action name from the WebSocket frame (echoed in the reply).
        """
        Logger.info(f"user {id(self.websocket)} requesting {functionNameAsString()}")
        try:
            action_uuid = str(new_uuid())
            engine_command = {
                "action": "cluster_status",
                "action_uuid": action_uuid,
            }

            result = await self.comunicate_with_engine(
                "cluster_status", action_uuid, engine_command, query_mode=True
            )

            await self.outgoing.put(json.dumps({"type": "node_status", "value": result}))

        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), action=action)

    async def project_deploy(self, project_uuid, action):
        """Deploy a project to the engine for playback.

        Resolves ``unix_name`` from the DB and sends a ``project_deploy``
        command to the engine.

        Args:
            project_uuid: UUID string of the project to deploy.
            action: Action name from the WebSocket frame (echoed in the reply).
        """
        Logger.info(f"user {id(self.websocket)} requesting deploy project {project_uuid}")
        try:
            unix_name = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.get_project_unix_name, project_uuid)
            action_uuid = str(new_uuid())
            engine_command = {"action": functionNameAsString(), "action_uuid": action_uuid, "value": unix_name}

            await self.comunicate_with_engine(action, action_uuid, engine_command)

            await self.outgoing.put(json.dumps({"type": functionNameAsString(), "value": project_uuid}))

        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

    async def list_project(self, action):
        """Send the list of live projects to the client.

        Args:
            action: Action name echoed back in the response frame.
        """
        Logger.info("user {} loading project list".format(id(self.websocket)))
        try:
            project_list = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.list)
            await self.outgoing.put(json.dumps({"type": action, "value": project_list}))
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), action=action)

    async def send_project(self, project_uuid, action):
        """Load a project's script from disk and send it to the client.

        Sends ``{"type": "project"}`` with the script's wire value, then
        ``document_load_report`` with what the library did on load (never
        omitted, also for a clean load). When the library refuses the document
        (an unrepairable value, or a document newer than the library) the
        session gets ``document_load_failed`` instead of ``project``; the
        session stays up and the project stays listed. Opening writes nothing.

        Also records *project_uuid* as the session's loaded project in
        ``server.users`` and ``server.sessions``, and derives the project's
        repair gate (``server.repair_gates``). The file unchanged since the
        outstanding report keeps that report's ``report_id``.

        Args:
            project_uuid: UUID string of the project to load.
            action: Action name from the WebSocket frame.
        """
        try:
            Logger.info("user {} loading project {}".format(id(self.websocket), project_uuid))
            project, report, script_md5, media_repairs, rows_digest = await self.server.event_loop.run_in_executor(
                self.server.executor, self.server.db.project.open, project_uuid)
            msg = json.dumps({"type": "project", "value": project})
            await self.outgoing.put(msg)
            self.server.users[self] = project_uuid
            self.server.sessions[self.session_id]['loaded_project'] = project_uuid

            state = derive_gate(project_uuid, report, script_md5, media_repairs, rows_digest,
                                prior=self.server.repair_gates.get(project_uuid))
            self.server.repair_gates[project_uuid] = state
            await self.outgoing.put(json.dumps({
                "type": "document_load_report",
                "value": load_report_value(state['report_id'], project_uuid, report, state['media_repairs']),
            }))
            # After the project frame, never before it (869fat84r D20).
            self._in_background(self._report_on_open(project_uuid))
        except DocumentLoadFailed as e:
            Logger.warning(f"project {project_uuid} not opened: {e}")
            await self.outgoing.put(json.dumps({
                "type": "document_load_failed",
                "value": load_failed_value(project_uuid, e),
            }))
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

    async def repair_acknowledge(self, value, action):
        """Record that this session's operator has seen the project's load report.

        The report is the project's outstanding one in ``server.repair_gates``,
        matched by ``project_uuid`` and ``report_id``. The acknowledgment is
        this session's: another session's never unlocks this one's save
        (001 FR-021). A session that reconnected with its ``session_id`` may
        acknowledge without loading again (FR-008). Writes nothing to disk.

        Args:
            value: ``{"project_uuid": ..., "report_id": ...}``.
            action: Action name from the WebSocket frame.
        """
        value = value if isinstance(value, dict) else {}
        state = self.server.repair_gates.get(value.get('project_uuid'))
        if state is None or value.get('report_id') != state['report_id']:
            await self.refuse_save(state or {'project_uuid': value.get('project_uuid'), 'report_id': None},
                                   'unacknowledged')
            return
        state['acknowledged_by'].add(self.session_id)
        await self.outgoing.put(json.dumps({"type": "repair_acknowledge", "value": {
            "project_uuid": state['project_uuid'], "report_id": state['report_id']}}))

    async def refuse_save(self, state, reason):
        """``repair_save_refused`` for the project's outstanding report."""
        await self.outgoing.put(json.dumps({"type": "repair_save_refused", "value": {
            "project_uuid": state['project_uuid'], "report_id": state['report_id'], "reason": reason}}))

    @staticmethod
    def _error_text(e):
        """What the client shows for a failed save.

        A ``ValueError`` is a save-time gate speaking to the operator (fade
        duration, media cue without a file): forward its text as is. Anything
        else keeps the ``<class '…'>`` prefix the UI has always shown.
        """
        if isinstance(e, ValueError):
            return str(e)
        return str(type(e)) + str(e)

    async def received_new_project(self, data, action, unix_name):
        """Create a new project and notify the client and other users.

        Args:
            data: ``CuemsScript`` dict from the frontend.
            action: Action name echoed back in the confirmation.
            unix_name: Candidate directory name from the frontend.
        """
        try:
            project_uuid = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.new, data, unix_name)

            Logger.info("user {} new project {}".format(id(self.websocket), project_uuid))

            self.server.users[self] = project_uuid
            await self.notify_user(uuid=project_uuid, action=action)
            await self.server.notify_others_list_changes(self, "project_list")
            await self.server.notify_others_same_project(self, "project_modified", project_uuid)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(self._error_text(e), action="project_new")

    async def received_project(self, data, action):
        """Save an edited project and notify the client and other users.

        The gate is the project's (``server.repair_gates``), not the
        connection's. A project whose script the library repaired or
        converted is not saved until *this* session acknowledges the
        outstanding report (``repair_save_refused``, reason
        ``unacknowledged``). The first save after that moves the original file
        into the trash before overwriting it; if that move fails nothing is
        saved (reason ``preserve_failed``).

        With no state for the project (an editor restart, a session that never
        loaded it), the gate is derived from the file on disk first (FR-009).
        With a state that still waits for acknowledgment, the file is
        re-hashed, and a changed file gets a new report (FR-009a). A clean
        state adds no hash and no load (Q4). The decision is made on the
        event-loop thread under the script's file lock; hashing, loading and
        saving run in the executor.

        Args:
            data: ``CuemsScript`` dict containing ``id`` and updated fields.
            action: Action name echoed back in the confirmation.
        """
        project_uuid = None
        state = None
        preserve = False
        try:
            project_uuid = data['CuemsScript']['id']
            unix_name = await self.server.event_loop.run_in_executor(
                self.server.executor, self.server.db.project.get_project_unix_name, project_uuid)
            path = self.server.db.project.script_path(unix_name)
            async with file_lock(self.server, path):
                state = self.server.repair_gates.get(project_uuid)
                if state is None:
                    state = await self.rederive_gate(project_uuid)
                elif gate_requires_ack(state):
                    on_disk = await self.server.event_loop.run_in_executor(self.server.executor, bytes_md5, path)
                    if on_disk != state['script_md5']:
                        state = await self.rederive_gate(project_uuid)
                    else:
                        rows = await self.server.event_loop.run_in_executor(
                            self.server.executor, self.server.db.project.media_rows_digest, project_uuid)
                        if rows != state['media_rows_digest']:
                            state = await self.rederive_gate(project_uuid)
                if state is not None and gate_requires_ack(state) and self.session_id not in state['acknowledged_by']:
                    await self.refuse_save(state, 'unacknowledged')
                    return
                required = state is not None and gate_requires_ack(state)
                preserve = bool(state and state['file_differs_from_loaded'] and not state['preserved'])
                if preserve:
                    state['preserved'] = True   # claimed before the await: one move per stale file
                await self.server.event_loop.run_in_executor(
                    self.server.executor,
                    functools.partial(self.server.db.project.update, project_uuid, data, preserve_original=preserve))
                if required:
                    # The file now holds the saved document: the report is retired.
                    written = await self.server.event_loop.run_in_executor(self.server.executor, bytes_md5, path)
                    self.server.repair_gates[project_uuid] = clean_gate(project_uuid, written)
            Logger.info("user {} saving project {}".format(id(self.websocket), project_uuid))

            self.server.users[self] = project_uuid
            await self.notify_user(uuid=project_uuid, action=action)
            await self.server.notify_others_list_changes(self, "project_list")
            await self.server.notify_others_same_project(self, "project_modified", project_uuid)
            self._in_background(self._report_after_save(project_uuid))
        except OriginalNotPreserved as e:
            Logger.error(f"project {project_uuid} not saved: {e}")
            state['preserved'] = False
            await self.refuse_save(state, 'preserve_failed')
        except Exception as e:
            if preserve:
                state['preserved'] = False
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(self._error_text(e), uuid=project_uuid, action=action)

    async def rederive_gate(self, project_uuid):
        """Derive the project's gate from the script file on disk (FR-009, FR-009a).

        ``inspect`` runs in the executor; the table is written here, on the
        loop. Bytes unchanged since a state recorded meanwhile keep that
        state's report. Returns ``None``, recording nothing, when there is no
        script file: there is no original to protect.
        """
        try:
            report, script_md5, media_repairs, rows_digest = await self.server.event_loop.run_in_executor(
                self.server.executor, self.server.db.project.inspect, project_uuid)
        except FileNotFoundError:
            return None
        state = derive_gate(project_uuid, report, script_md5, media_repairs, rows_digest,
                            prior=self.server.repair_gates.get(project_uuid))
        self.server.repair_gates[project_uuid] = state
        return state

    def release_gate(self, project_uuid):
        """This session leaves *project_uuid*: drop its acknowledgment (FR-010).

        The project's state goes too once no session has it loaded. A later
        save re-derives it from the file. Event-loop thread only.
        """
        state = self.server.repair_gates.get(project_uuid)
        if state is None:
            return
        state['acknowledged_by'].discard(self.session_id)
        if not any(session.get('loaded_project') == project_uuid
                   for session in self.server.sessions.values()):
            del self.server.repair_gates[project_uuid]

    async def list_project_trash(self, action):
        """Send the list of trashed projects to the client.

        Args:
            action: Action name echoed back in the response frame.
        """
        Logger.info("user {} loading project trash list".format(id(self.websocket)))
        try:
            project_trash_list = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.list_trash)
            await self.outgoing.put(json.dumps({"type": action, "value": project_trash_list}))
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), action=action)

    async def request_delete_project(self, project_uuid, action):
        """Soft-delete a project (move to trash) and notify affected clients.

        Args:
            project_uuid: UUID string of the project to trash.
            action: Action name echoed back in the confirmation.
        """
        try:
            Logger.info("user {} deleting project: {}".format(id(self.websocket), project_uuid))

            await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.delete, project_uuid)
            self.server.repair_gates.pop(project_uuid, None)

            await self.notify_user(uuid=project_uuid, action=action)
            await self.server.notify_others_same_project(self, "project_update", project_uuid=project_uuid)
            await self.server.notify_others_list_changes(self, "project_list")
            await self.server.notify_others_list_changes(self, "project_trash_list")
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

    async def request_duplicate_project(self, project_uuid, action):
        """Duplicate a project and notify the client and other users.

        The reply includes both the original and new UUID so the frontend can
        navigate to the copy.

        Args:
            project_uuid: UUID string of the project to duplicate.
            action: Action name echoed back in the confirmation.
        """
        try:
            Logger.info("user {} duplicating project: {}".format(id(self.websocket), project_uuid))
            new_project_uuid, report = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.duplicate, project_uuid)
            reply = {"uuid": project_uuid, "new_uuid": new_project_uuid}
            if report.outcome.value != 'clean':
                # The copy is the repaired / converted document; say so. Optional
                # key: an old reader ignores it. The source is not overwritten
                # and no acknowledgment is asked for.
                reply["report"] = load_report_value(str(new_uuid()), project_uuid, report)
            await self.outgoing.put(json.dumps({"type": action, "value": reply}))
            await self.server.notify_others_list_changes(self, "project_list")
            await self.server.notify_others_list_changes(self, "file_list")
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

    async def request_export_project(self, project_uuid, action):
        try:
            Logger.info("user {} exporting project: {}".format(id(self.websocket), project_uuid))
            exported_file_url = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.export, project_uuid)
            await self.outgoing.put(json.dumps({"type": action, "value": exported_file_url}))
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

    async def request_restore_project(self, project_uuid, action):
        """Restore a trashed project and notify the client and other users.

        Args:
            project_uuid: UUID string of the project to restore.
            action: Action name echoed back in the confirmation.
        """
        try:
            Logger.info("user {} restoring project: {}".format(id(self.websocket), project_uuid))
            await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.restore, project_uuid)
            await self.notify_user(uuid=project_uuid, action=action)
            await self.server.notify_others_list_changes(self, "project_list")
            await self.server.notify_others_list_changes(self, "project_trash_list")
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

    async def request_delete_project_trash(self, project_uuid, action):
        """Permanently delete a trashed project and notify the client.

        Args:
            project_uuid: UUID string of the trashed project to delete.
            action: Action name echoed back in the confirmation.
        """
        try:
            Logger.info("user {} deleting project from trash: {}".format(id(self.websocket), project_uuid))

            await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.delete_from_trash, project_uuid)

            await self.notify_user(uuid=project_uuid, action=action)
            await self.server.notify_others_list_changes(self, "project_trash_list")
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

    async def list_file(self, action):
        """Send the list of live media files to the client.

        Args:
            action: Action name echoed back in the response frame.
        """
        Logger.info("user {} loading file list".format(id(self.websocket)))
        try:
            file_list = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.list)
            await self.outgoing.put(json.dumps({"type": action, "value": file_list}))
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), action=action)

    async def received_file_data(self, data, action):
        """Update metadata (name, description) for a media file.

        Args:
            data: Dict with structure ``{uuid: {name, description}}``.
            action: Action name echoed back in the confirmation.
        """
        try:
            file_uuid = data['uuid']

            Logger.info("user {} update file data {}".format(id(self.websocket), file_uuid))

            await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.save, file_uuid, data)
            await self.notify_user(uuid=file_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)

    async def request_file_load_meta(self, file_uuid, action):
        """Send full metadata for a media file to the client.

        Args:
            file_uuid: UUID string of the media file.
            action: Action name echoed back in the response frame.
        """
        try:
            Logger.info("user {} loading file meta data {}".format(id(self.websocket), file_uuid))

            file_meta_data = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.load_meta, file_uuid)
            await self.outgoing.put(json.dumps({"type": action, "value": file_meta_data}))
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)

    async def request_file_load_thumbnail(self, file_uuid, action):
        """Send the thumbnail binary frame for a media file to the client.

        The response is a raw binary WebSocket frame with a 36-byte UUID
        header prepended (not a JSON frame).

        Args:
            file_uuid: UUID string of the media file.
            action: Action name (used only in error replies).
        """
        try:
            Logger.info("user {} loading file thumbnail {}".format(id(self.websocket), file_uuid))

            file_thumbnail = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.load_thumbnail, file_uuid)
            await self.outgoing.put(file_thumbnail)  # TODO: add uuid encoded in the binary message
        except NonExistentItemError as e:
            Logger.warning(e)
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)

    async def request_file_load_waveform(self, file_uuid, action):
        """Send the waveform binary frame for a media file to the client.

        The response is a raw binary WebSocket frame with a 36-byte UUID
        header prepended (not a JSON frame).

        Args:
            file_uuid: UUID string of the media file.
            action: Action name (used only in error replies).
        """
        try:
            Logger.info("user {} loading file waveform {}".format(id(self.websocket), file_uuid))

            file_waveform = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.load_waveform, file_uuid)
            await self.outgoing.put(file_waveform)  # TODO: add uuid encoded in the binary message
        except NonExistentItemError as e:
            Logger.warning(e)
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)

    async def list_file_trash(self, action):
        """Send the list of trashed media files to the client.

        Args:
            action: Action name echoed back in the response frame.
        """
        Logger.info("user {} loading file trash list".format(id(self.websocket)))
        try:
            file_trash_list = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.list_trash)
            await self.outgoing.put(json.dumps({"type": action, "value": file_trash_list}))
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), action=action)

    async def request_delete_file(self, file_uuid, action):
        """Soft-delete a media file (move to trash) and notify affected clients.

        Args:
            file_uuid: UUID string of the media file to trash.
            action: Action name echoed back in the confirmation.
        """
        try:
            Logger.debug("user {} deleting file: {}".format(id(self.websocket), file_uuid))
            await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.delete, file_uuid)
            await self.notify_user(uuid=file_uuid, action=action)
            await self.server.notify_others_list_changes(self, "file_list")
            await self.server.notify_others_list_changes(self, "file_trash_list")
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)

    async def request_restore_file(self, file_uuid, action):
        """Restore a trashed media file and notify affected clients.

        Args:
            file_uuid: UUID string of the trashed media file to restore.
            action: Action name echoed back in the confirmation.
        """
        try:
            Logger.debug("user {} restoring file: {}".format(id(self.websocket), file_uuid))
            await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.restore, file_uuid)
            await self.notify_user(uuid=file_uuid, action=action)
            await self.server.notify_others_list_changes(self, "file_list")
            await self.server.notify_others_list_changes(self, "file_trash_list")
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)

    async def request_delete_file_trash(self, file_uuid, action):
        """Permanently delete a trashed media file and notify the client.

        Args:
            file_uuid: UUID string of the trashed media file to delete permanently.
            action: Action name echoed back in the confirmation.
        """
        try:
            Logger.info("user {} deleting file from trash: {}".format(id(self.websocket), file_uuid))
            await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.delete_from_trash, file_uuid)
            await self.notify_user(uuid=file_uuid, action=action)
            await self.server.notify_others_list_changes(self, "file_trash_list")
        except NonExistentItemError as e:
            Logger.info(e)
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)
        except Exception as e:
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user(str(e), uuid=file_uuid, action=action)
