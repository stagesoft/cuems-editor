# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
import functools
import json
import asyncio
from datetime import datetime, timedelta
from cuemsutils.helpers import new_uuid, new_datetime, Unset
from cuemsutils.tools.ConfigManager import ConfigManager, SchemaName
import websockets as ws
import sys

from cuemsutils.log import logged, Logger

from cuemseditor.CuemsErrors import DocumentLoadFailed, EngineError, NonExistentItemError, OriginalNotPreserved
from cuemseditor.node_reads import IdentityCollision

TIMEOUT = 25  # TODO: make it configurable, or get from settings

functionNameAsString = lambda n=0: sys._getframe(n + 1).f_code.co_name

# document_load_failed always offers all three: the editor cannot know which
# one the operator can carry out.
LOAD_FAILED_NEXT_STEPS = ['restore_from_conversion_backup', 'correct_field_by_hand', 'remove_document']


def _json_safe(value):
    """A library value as JSON: scalars as they are, ``None`` as null, anything
    else (``CTimecode``, ``Uuid``, an enum) as its string form."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    enum_value = getattr(value, 'value', None)
    if isinstance(enum_value, str):
        return enum_value
    return str(value)


def load_report_value(report_id, project_uuid, report):
    """The ``value`` of ``document_load_report`` for a library ``LoadReport``."""
    return {
        'report_id': report_id,
        'project_uuid': project_uuid,
        'document': report.document,
        'outcome': report.outcome.value,
        'file_differs_from_loaded': bool(report.file_differs_from_loaded),
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


# config_save targets that are refused, with the reason the client is told.
CONFIG_SAVE_REFUSED = {
    'script': 'a script is saved with project_save, not config_save',
    'hardware_outputs': 'hardware_outputs is reserved and has no model bindings',
}


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
        # This session's last project_load and what the library did to it:
        # project_uuid, report_id, outcome, file_differs_from_loaded,
        # acknowledged, preserved. Only this session reads or writes it, and
        # only on the event-loop thread. It dies with the connection.
        self.repair_state = None
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
                    "node_status": lambda: self.node_status(action),
                    "project_status": lambda: self.project_status(action),
                    "project_unload": lambda: self.project_unload(action),
                    "repair_acknowledge": lambda: self.repair_acknowledge(value, action),
                    "schema_descriptor": lambda: self.schema_descriptor(value, action),
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

        Resolves the ``unix_name`` from the DB, builds the ``project_ready``
        engine command, and awaits the response.

        Args:
            project_uuid: UUID string of the project to arm.
            action: Action name from the WebSocket frame (echoed in the reply).
        """
        Logger.info(f"user {id(self.websocket)} requesting ready project {project_uuid}")
        try:
            unix_name = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.get_project_unix_name, project_uuid)
            action_uuid = str(new_uuid())
            engine_command = {"action": functionNameAsString(), "action_uuid": action_uuid, "value": unix_name}

            result = await self.comunicate_with_engine(action, action_uuid, engine_command)
            Logger.debug(f"project {project_uuid} ready: {result}")

            await self.outgoing.put(json.dumps({"type": functionNameAsString(), "value": project_uuid}))

        except Exception as e:
            Logger.error(f"error: {type(e)} {e}")
            await self.notify_error_to_user(str(e), uuid=project_uuid, action=action)

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

            result = await self.comunicate_with_engine(action, action_uuid, engine_command)

            self.server.users[self] = None
            if self.session_id and self.session_id in self.server.sessions:
                self.server.sessions[self.session_id]['loaded_project'] = None
            self.repair_state = None

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

    async def nodelist_get(self, action):
        """Re-read network_map.xml and send this client the current node list.

        Same payload the client already gets on connect
        (``initial_mappings``: ``nodes`` = adopted, ``new_nodes`` = discovered
        but not adopted), so no new client-side handling is needed — it is just
        a way to refresh on demand instead of reconnecting. While the map has a
        duplicate node identity, ``network_map_error`` comes first and the
        list is the last good one; a read that clears it sends
        ``network_map_error: null`` first.

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
            await self.outgoing.put(self.server.initial_setting_message())

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

    async def config_save(self, value, action):
        """Persist a configuration document sent by the client.

        Refuses ``script`` (that is ``project_save``), ``hardware_outputs`` (no
        model bindings), and anything that is not a ``SchemaName`` —
        ``default_mappings.xml`` included, which is not a target.

        The four config domains would be written through
        ``ConfigManager.save_settings`` / ``save_network_map`` /
        ``save_project_mappings`` / ``save_project_settings``. Those save the
        object a ``ConfigManager`` holds, and cuemsutils offers no public way to
        build that object from a client's JSON document. The editor does not
        hand-build one or write XML itself, so this answers with an error
        naming that gap (upstream report UR-5) until the library has the call.

        Args:
            value: ``{"schema": <SchemaName value>, "document": {...}}``.
            action: Action name from the WebSocket frame.
        """
        schema = value.get('schema') if isinstance(value, dict) else None
        try:
            name = SchemaName(schema)
        except ValueError:
            await self.notify_error_to_user(f"config_save: {schema!r} is not a schema", action=action)
            return
        if name.value in CONFIG_SAVE_REFUSED:
            await self.notify_error_to_user(f"config_save: {CONFIG_SAVE_REFUSED[name.value]}", action=action)
            return
        await self.notify_error_to_user(
            f"config_save of {name.value} is not available: cuemsutils has no public way to "
            f"build a {name.value} document from JSON (cuems-editor 001 upstream report UR-5)",
            action=action)

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

            result = await self.comunicate_with_engine(action, action_uuid, engine_command)

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
        ``server.users`` and ``server.sessions``, and replaces this session's
        repair state.

        Args:
            project_uuid: UUID string of the project to load.
            action: Action name from the WebSocket frame.
        """
        self.repair_state = None   # a new load replaces whatever this session held
        try:
            Logger.info("user {} loading project {}".format(id(self.websocket), project_uuid))
            project, report = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.project.open, project_uuid)
            msg = json.dumps({"type": "project", "value": project})
            await self.outgoing.put(msg)
            self.server.users[self] = project_uuid
            self.server.sessions[self.session_id]['loaded_project'] = project_uuid

            report_id = str(new_uuid())
            self.repair_state = {
                'project_uuid': project_uuid,
                'report_id': report_id,
                'outcome': report.outcome.value,
                'file_differs_from_loaded': bool(report.file_differs_from_loaded),
                'acknowledged': False,
                'preserved': False,
            }
            await self.outgoing.put(json.dumps({
                "type": "document_load_report",
                "value": load_report_value(report_id, project_uuid, report),
            }))
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
        """Record that this session's operator has seen the load report.

        Only this session's current report counts, by ``project_uuid`` and
        ``report_id``; another session's acknowledgment never unlocks this one.
        Writes nothing to disk.

        Args:
            value: ``{"project_uuid": ..., "report_id": ...}``.
            action: Action name from the WebSocket frame.
        """
        state = self.repair_state
        if state is None:
            await self.notify_error_to_user('no load report to acknowledge on this session', action=action)
            return
        value = value if isinstance(value, dict) else {}
        if value.get('project_uuid') != state['project_uuid'] or value.get('report_id') != state['report_id']:
            await self.refuse_save(state, 'unacknowledged')
            return
        state['acknowledged'] = True
        await self.outgoing.put(json.dumps({"type": "repair_acknowledge", "value": {
            "project_uuid": state['project_uuid'], "report_id": state['report_id']}}))

    async def refuse_save(self, state, reason):
        """``repair_save_refused`` for this session's report."""
        await self.outgoing.put(json.dumps({"type": "repair_save_refused", "value": {
            "project_uuid": state['project_uuid'], "report_id": state['report_id'], "reason": reason}}))

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
            await self.notify_error_to_user((str(type(e)) + str(e)), action="project_new")

    async def received_project(self, data, action):
        """Save an edited project and notify the client and other users.

        A project this session opened with a repair or a conversion is not
        saved until this session acknowledges that report
        (``repair_save_refused``, reason ``unacknowledged``). The first save
        after that moves the original file into the trash before overwriting
        it; if that move fails nothing is saved (reason ``preserve_failed``).
        The decision is made here, on the event-loop thread; the move and the
        save run in the executor.

        Args:
            data: ``CuemsScript`` dict containing ``id`` and updated fields.
            action: Action name echoed back in the confirmation.
        """
        project_uuid = None
        state = None
        preserve = False
        try:
            project_uuid = data['CuemsScript']['id']
            if self.repair_state and self.repair_state['project_uuid'] == project_uuid:
                state = self.repair_state
            if state and state['outcome'] != 'clean' and not state['acknowledged']:
                await self.refuse_save(state, 'unacknowledged')
                return
            preserve = bool(state and state['file_differs_from_loaded'] and not state['preserved'])
            if preserve:
                state['preserved'] = True   # claimed before the await: one move per load
            await self.server.event_loop.run_in_executor(
                self.server.executor,
                functools.partial(self.server.db.project.update, project_uuid, data, preserve_original=preserve))
            Logger.info("user {} saving project {}".format(id(self.websocket), project_uuid))

            self.server.users[self] = project_uuid
            await self.notify_user(uuid=project_uuid, action=action)
            await self.server.notify_others_list_changes(self, "project_list")
            await self.server.notify_others_same_project(self, "project_modified", project_uuid)
        except OriginalNotPreserved as e:
            Logger.error(f"project {project_uuid} not saved: {e}")
            state['preserved'] = False
            await self.refuse_save(state, 'preserve_failed')
        except Exception as e:
            if preserve:
                state['preserved'] = False
            Logger.error("error: {} {}".format(type(e), e))
            await self.notify_error_to_user((str(type(e)) + str(e)), uuid=project_uuid, action=action)

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

            return_message = await self.server.event_loop.run_in_executor(self.server.executor, self.server.db.media.save, file_uuid, data)
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
