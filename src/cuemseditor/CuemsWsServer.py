# SPDX-FileCopyrightText: 2026 Stagelab Coop SCCL
# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileContributor: Ion Reguera <ion@stagelab.coop>
import asyncio
import concurrent.futures
import functools
import json
import os
import time
import websockets as ws
from websockets.asyncio.server import serve
from multiprocessing import Process
import signal
from random import randint  #TODO: clean unused
from hashlib import md5
import re

from cuemsutils.log import logged, Logger

from cuemseditor.CuemsProjectManager import CuemsDBManager
from cuemseditor.CuemsWsUser import CuemsWsUser
from cuemseditor.CuemsUpload import CuemsUpload
from cuemseditor.CuemsErrors import *
from cuemseditor.node_reads import IdentityCollision, NodeLists, collided_identity

from cuemsutils.tools.CommunicatorServices import Communicator
from cuemsutils.tools.ConfigManager import ConfigManager
from cuemsutils.tools.NodeList import partition_by_adoption
from cuemsutils.tools import coerce_identity
from cuemsutils.errors import node_identity_collision_message
from cuemsutils.helpers import new_uuid


class CuemsWsServer():
    """Top-level asyncio WebSocket server for the CueMS editor backend.

    Accepts connections on two paths:

    * ``/`` or ``/?session=<uuid>`` — main project-manager session handled by
      :class:`CuemsWsUser`.
    * ``/upload`` — binary file upload session handled by
      :class:`CuemsUpload`.

    Owns the NNG ``Communicator`` (engine IPC), the ``CuemsDBManager``, the
    active ``users`` dict, the ``sessions`` state, and a thread-pool
    ``executor`` for blocking DB and filesystem operations.

    Example:
        >>> server = CuemsWsServer(settings_dict, mappings_dict)
        >>> server.start(port=9092)

    The ``settings_dict`` must contain at minimum:

    .. code-block:: python

        {
            "editor_ipc": "ipc:///tmp/cuems-editor.sock",
            "tmp_path": "/tmp/cuems",
            "session_uuid": "<uuid>",
            "library_path": "/var/lib/cuems/library",
            # ... plus all keys required by CuemsDBManager
        }
    """

    def __init__(self, settings_dict, mappings_dict):
        """Initialise the server: bind the NNG communicator and validate the tmp path.

        Does **not** start listening; call :meth:`start` to enter the event
        loop.

        Args:
            settings_dict: Settings dict from ``settings.xml``; required keys
                include ``editor_ipc``, ``tmp_path``, ``session_uuid``, and
                ``library_path``.
            mappings_dict: Output mapping document (``default_mappings.xml``),
                the library object or its wire form. Served verbatim as
                ``initial_mappings``; the network-map nodes are merged with
                its mapping nodes for ``node_list``, never into it.

        Raises:
            KeyError: If a required key is absent from *settings_dict*.
            FileNotFoundError: If ``tmp_path`` does not exist or is not
                read/write/executable.
        """
        self.engine_communicator = Communicator(address=settings_dict['editor_ipc'])
        #self.engine_queue = Comunicator(address="ipc:///tmp/test2.sock")
        self.engine_messages = list()
        self.users = dict()
        self.sessions = dict()
        self.settings_dict = settings_dict
        # Projected once, here. json.dumps of the library's mappings object
        # re-projects it through the mappings schema on every message and drops
        # every key that schema does not declare: nodeconf_available, and the
        # network-map fields merged into each node (node_role).
        self.mappings_dict = mappings_dict.to_wire() if hasattr(mappings_dict, 'to_wire') else mappings_dict
        # The network-map nodes merged with their mapping nodes, as served on
        # node_list. Assigned on the event-loop thread only (constructor aside).
        self.node_list = {'nodes': [], 'new_nodes': []}
        try:
            self.tmp_path = self.settings_dict['tmp_path']
            self.session_uuid = self.settings_dict['session_uuid']
            self.library_path = self.settings_dict['library_path']
        except KeyError as e:
            Logger.error(f'can not read settings {e}')
            raise e
        Logger.debug(f'library path set to : {self.library_path}')

        if (not os.path.exists(self.tmp_path)) or (not os.access(self.tmp_path, os.X_OK & os.R_OK & os.W_OK)):
            Logger.error("error: upload folder is not usable")
            raise FileNotFoundError('Can not access upload folder')

        self.network_map_watcher_task = None
        self.reload_network_map_nodes()

    def start(self, port=None):
        """Enter the asyncio event loop and start listening for connections.

        Blocks until :meth:`stop` is called (via SIGINT or SIGTERM).

        Args:
            port: TCP port to listen on.  May also be pre-set via
                ``self.port``; raises ``ValueError`` if neither is provided.

        Raises:
            ValueError: If *port* is ``None`` and ``self.port`` has not been
                set.
        """
        # Use provided port, or fall back to self.port if set
        if port is None:
            if not hasattr(self, 'port') or self.port is None:
                raise ValueError("port argument is required or must be set on server instance")
            port = self.port
        self.port = port
        self.host = 'localhost'
        newfeature = asyncio.get_event_loop().run_until_complete(self.run_async_server())

    async def run_async_server(self):
        """Initialise the DB, executor, and WebSocket server, then serve forever.

        Called by :meth:`start`.  Sets up:

        * ``self.db`` — ``CuemsDBManager`` instance.
        * ``self.executor`` — ``ThreadPoolExecutor`` for blocking work.
        * ``self.project_server`` — the ``websockets`` server object.
        * SIGINT / SIGTERM handlers that call :meth:`stop`.
        """
        self.db = CuemsDBManager(self.settings_dict)
        self.event_loop = asyncio.get_event_loop()

        self.executor = concurrent.futures.ThreadPoolExecutor(thread_name_prefix='ws_ProjectManager_ThreadPoolExecutor', max_workers=5)  # TODO: adjust max workers
        #self.event_loop.set_exception_handler(self.exception_handler) ### TODO:UNCOMENT FOR PRODUCTION
        self.project_server = await serve(self.connection_handler, self.host, self.port)
        self.network_map_watcher_task = asyncio.create_task(self.watch_network_map())
        for sig in (signal.SIGINT, signal.SIGTERM):
            self.event_loop.add_signal_handler(sig, self.stop)
        Logger.info('server listening on {}, port {}'.format(self.host, self.port))
        await self.project_server.serve_forever()

    def stop(self):
        """Initiate a graceful shutdown from a signal handler.

        Schedules ``project_server.close()`` and :meth:`stop_async` on the
        event loop from any thread context.
        """
        #self.event_loop.call_soon_threadsafe(self.queue_task.cancel)
        self.event_loop.call_soon_threadsafe(self.project_server.close)
        Logger.info('ws server closing')
        asyncio.run_coroutine_threadsafe(self.stop_async(), self.event_loop)

    async def stop_async(self):
        """Wait for the WebSocket server to finish closing, then stop the event loop."""
        watcher = getattr(self, 'network_map_watcher_task', None)
        if watcher is not None:
            watcher.cancel()
        await self.project_server.wait_closed()
        Logger.info('ws server closed')
        self.event_loop.call_soon(self.event_loop.stop)
        Logger.info('event loop stoped')

    async def connection_handler(self, websocket):
        """Route an incoming WebSocket connection to the correct session type.

        ``/`` and ``/?session=<uuid>`` go to :meth:`project_manager_session`;
        ``/upload`` goes to :meth:`upload_session`; other paths are logged and
        dropped.

        Args:
            websocket: Incoming ``websockets`` connection object.
        """
        Logger.info("new connection: {}, path: {}".format(websocket.remote_address, websocket.request.path))
        path = websocket.request.path
        if (path == '/' or path[0:9] == '/?session'):                   # project manager
            await self.project_manager_session(websocket, path)
        elif path == '/upload':                                           # file upload
            await self.upload_session(websocket)
        else:
            Logger.info("unknown path: {}".format(path))

    async def project_manager_session(self, websocket, path):
        """Manage the full lifecycle of a project-manager WebSocket session.

        Creates a :class:`CuemsWsUser`, sends ``payload_version``, registers
        it, sends the initial mappings (and a standing map error), then runs
        the consumer/producer/processor task set.  Cleans up via
        :meth:`unregister` on exit.

        Args:
            websocket: The accepted WebSocket connection.
            path: The request path (used to extract an optional session UUID).
        """
        user_session = CuemsWsUser(self, websocket)
        # Before register(): that already queues users and session_id.
        await user_session.outgoing.put(self.payload_version_message())
        await self.register(user_session, path)
        await self.send_initial_frames(user_session)
        try:
            consumer_task = asyncio.create_task(user_session.consumer_handler())
            producer_task = asyncio.create_task(user_session.producer_handler())
            # start 3 message processing task so a load or any other time consuming action still leaves with 2 tasks running  and interface feels responsive. TODO:discuss this
            processor_tasks = [asyncio.create_task(user_session.consumer()) for _ in range(3)]

            done_tasks, pending_tasks = await asyncio.wait([consumer_task, producer_task, *processor_tasks], return_when=asyncio.FIRST_COMPLETED)
            for task in pending_tasks:
                task.cancel()

        except Exception as e:
            Logger.debug(f"{e}, {type(e)}")

        finally:
            await self.unregister(user_session)

    #: The editor <-> UI wire version (not doc_version). +1 only, and only with
    #: a bump row in tests/ws-command-responses.txt (test_payload_version).
    PAYLOAD_VERSION = 1

    def payload_version_message(self):
        """``{"type": "payload_version", "value": PAYLOAD_VERSION}``, the first frame on connect."""
        return json.dumps({"type": "payload_version", "value": self.PAYLOAD_VERSION})

    async def send_initial_frames(self, user_session):
        """Queue the frames a project-manager session gets after registering, in order.

        ``initial_mappings``, ``node_list``, then ``network_map_error`` while a map error
        stands. ``payload_version`` precedes them (see
        :meth:`project_manager_session`). ``initial_template`` is retired at
        payload version 1: clients build from ``schema_descriptor``.
        """
        await user_session.outgoing.put(self.initial_setting_message())
        await user_session.outgoing.put(self.node_list_message())
        if self.network_map_error is not None:
            await user_session.outgoing.put(self.network_map_error_message())

    async def upload_session(self, websocket):
        """Handle a binary file upload over the ``/upload`` WebSocket path.

        Creates a :class:`CuemsUpload` and runs its :meth:`~CuemsUpload.message_handler`
        until the connection closes.

        Args:
            websocket: The accepted WebSocket connection on the ``/upload`` path.
        """
        user_upload_session = CuemsUpload(self, websocket)
        Logger.info("new upload session: {}".format(user_upload_session))

        await user_upload_session.message_handler()
        Logger.info("upload session ended: {}".format(user_upload_session))

    async def register(self, user_session, path):
        """Register a new user session and restore any prior session state.

        Adds *user_session* to ``self.users``, broadcasts the updated user
        count, assigns a ``session_id`` via :meth:`check_session`, and calls
        :meth:`load_session`.

        Args:
            user_session: The :class:`CuemsWsUser` to register.
            path: Request path string (may carry a ``?session=<uuid>`` param).
        """
        Logger.info("user registered: {}".format(id(user_session.websocket)))
        self.users[user_session] = None
        await self.notify_users("users")
        user_session.session_id = await self.check_session(user_session, path)
        await self.load_session(user_session)

    async def check_session(self, user_session, path):
        """Parse or generate a session UUID from the request path.

        If the path carries a ``?session=<uuid>`` parameter and the UUID is
        already in ``self.sessions``, it is reused.  Otherwise a new UUID is
        generated.  The session entry is updated with the current WebSocket id
        and the UUID is sent to the client via :meth:`notify_session`.

        Args:
            user_session: The :class:`CuemsWsUser` being registered.
            path: Request path string.

        Returns:
            Session UUID string.
        """
        session_uuid_patern = r"/\?session=(?P<uuid>[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12})?"

        matches = re.search(session_uuid_patern, path)
        if matches:
            if (matches.groupdict()['uuid'] != None):
                uuid = matches.groupdict()['uuid']
                if uuid not in self.sessions:
                    Logger.debug(f"uuid not found {uuid}, creating new session")
                    uuid = str(new_uuid())
                else:
                    Logger.debug(f"session_id found, reusing {uuid}")
            else:
                uuid = str(new_uuid())
        else:
            uuid = str(new_uuid())
        try:
            self.sessions[uuid]['ws'] = id(user_session.websocket)
        except KeyError:
            self.sessions[uuid] = {'ws': id(user_session.websocket)}

        await self.notify_session(user_session, uuid)

        return uuid

    async def load_session(self, user_session):
        """Restore session state for a reconnecting user.

        Currently a no-op; the commented-out body would re-send the previously
        loaded project.  Reserved for future reconnection support.

        Args:
            user_session: The :class:`CuemsWsUser` whose prior state to
                restore.
        """
        pass
        # try:
        #     await user_session.send_project(self.sessions[user_session.session_id]['loaded_project'], 'project_load')
        # except KeyError:
        #     pass

    async def notify_session(self, user_session, uuid):
        """Send the assigned session UUID to the client.

        Args:
            user_session: The :class:`CuemsWsUser` to notify.
            uuid: Session UUID string to send.
        """
        message = json.dumps({"type": "session_id", "value": uuid})
        await user_session.outgoing.put(message)

    async def unregister(self, user_task):
        """Remove a user session and broadcast the updated user count.

        Args:
            user_task: The :class:`CuemsWsUser` to remove.
        """
        Logger.info("user unregistered: {}".format(id(user_task.websocket)))
        self.users.pop(user_task, None)
        await self.notify_users("users")

    async def notify_others_list_changes(self, calling_user, list_type):
        """Notify all other connected users that a list has changed.

        Used after project/media create, delete, or restore operations so all
        open browser tabs refresh their lists.

        Args:
            calling_user: The user who triggered the change; excluded from
                the notification.
            list_type: String list name to include in the message value (e.g.
                ``"project_list"``, ``"file_list"``).
        """
        if self.users:  # notify others, not the user trigering the action, and only if the have same project loaded
            message = json.dumps({"type": "list_update", "value": list_type})
            for user, project in self.users.items():
                if user is not calling_user:
                    await user.outgoing.put(message)
                    Logger.debug('notifing {} {}'.format(user, list_type))

    async def notify_others_same_project(self, calling_user, msg_type, project_uuid=None):
        """Notify users who have the same project loaded that it was modified.

        If *project_uuid* is provided, only users with that exact project
        loaded are notified.  If ``None``, uses the calling user's loaded
        project.

        Args:
            calling_user: The user who triggered the change; excluded from
                the notification.
            msg_type: Message type string (not currently used in the payload).
            project_uuid: UUID string of the modified project, or ``None`` to
                infer from *calling_user*'s session.
        """
        if self.users:  # notify others, not the user trigering the action, and only if the have same project loaded
            message = json.dumps({"type": "project_update", "value": project_uuid})
            for user, project in self.users.items():
                if user is not calling_user:
                    if project_uuid is not None:
                        if str(project) != str(project_uuid):
                            continue
                    else:
                        if str(project) != str(self.users[calling_user]):
                            continue

                    Logger.debug('same project loaded')
                    await user.outgoing.put(message)
                    Logger.debug('notifing {}'.format(user))

    async def notify_users(self, type):
        """Broadcast a message to all connected users.

        Args:
            type: Message type string; only ``"users"`` is currently used
                (sends the connected-user count).
        """
        if self.users:  # asyncio.wait doesn't accept an empty dict
            message = self.users_event(type)
            for user in self.users:
                await user.outgoing.put(message)

    # warning, these non async functions should be not blocking or user @sync_to_async to get their own thread

    # Network-map fields a merged mapping node takes from the map. role_id /
    # alias / hostname are the optional identity fields from feat/node-identity
    # in cuems-common (docs/node-identity-contract.md there); they drive the
    # frontend's node label and cuems-logs' -n filter.
    NODE_STATUS_FIELDS = ('online', 'adopted', 'ip', 'name', 'node_role', 'mac',
                          'role_id', 'alias', 'hostname')

    def merge_node_data(self, existing_nodes, library_nodes):
        """Merge the map's nodes into the mapping nodes, in the map's order.

        A node the mappings already know keeps every key of its mapping node,
        output blocks included and copied through whatever their ``class``,
        and takes ``NODE_STATUS_FIELDS`` from the node's ``to_wire()``: string
        ``uuid``, real booleans for ``adopted`` and ``online`` (cuemsutils 014,
        xs:boolean), ``node_role``. A node the mappings do not know is its own
        ``to_wire()``.

        Args:
            existing_nodes: ``[{"node": <mapping node, wire form>}, ...]``.
            library_nodes: one side of the library's adoption partition, a tuple of
                bare node objects.

        Returns:
            ``[{"node": <dict>}, ...]``, one per library node.
        """
        existing_by_identity = {}
        for item in existing_nodes:
            node = item.get('node') if isinstance(item, dict) else None
            if node and node.get('uuid'):
                existing_by_identity[coerce_identity(node['uuid'])] = node

        merged = []
        for library_node in library_nodes:
            wire = library_node.to_wire()
            existing = existing_by_identity.get(coerce_identity(wire.get('uuid')))
            if existing is None:
                merged.append({'node': wire})
                continue
            node = dict(existing)
            for field in self.NODE_STATUS_FIELDS:
                if field in wire:
                    node[field] = wire[field]
            merged.append({'node': node})
        return merged

    # A standing duplicate-identity error, as sent on the wire, or None.
    network_map_error = None
    _logged_collisions = frozenset()

    def reload_network_map_nodes(self, assign=True):
        """Read ``network_map.xml`` and merge it into the mapping nodes.

        Called with ``assign=False`` from the executor: it then returns what it
        read (:class:`NodeLists` or :class:`IdentityCollision`, or ``None``)
        and the awaiting coroutine applies it on the event-loop thread with
        :meth:`assign_network_map_nodes` (constitution II). The default is the
        constructor's startup read, made before the loop exists, which assigns
        directly and returns whether the read succeeded.

        Retries up to 3 times with exponential back-off in case the file is
        being written concurrently. A duplicate node identity is not retried:
        the same file fails the same way.
        """
        result = self.read_network_map_nodes()
        if not assign:
            return result
        if result is None:
            return False
        self.assign_network_map_nodes(result)
        return isinstance(result, NodeLists)

    def read_network_map_nodes(self):
        """The read behind :meth:`reload_network_map_nodes`. Writes no shared state."""
        max_retries = 3
        initial_delay = 0.1
        delay_after_write = 0.05

        for attempt in range(max_retries):
            try:
                cf_manager = ConfigManager(load_all=False)
                network_map_file = cf_manager.conf_path('network_map.xml')

                if not os.path.isfile(network_map_file):
                    if attempt == 0:
                        Logger.warning(f'network_map.xml not found at {network_map_file}')
                    return None

                time.sleep(delay_after_write)

                try:
                    cf_manager.load_network_map()
                except Exception as e:
                    collision = node_identity_collision_message(network_map_file, e)
                    if collision is not None:
                        return IdentityCollision(collided_identity(e), network_map_file, collision)
                    raise
                adopted, unadopted = partition_by_adoption(cf_manager.network_map)

                # Merge with the mapping document's nodes to carry their outputs.
                # Both lists, so a node that changed adoption keeps its outputs.
                all_existing = (self.mappings_dict.get('nodes') or []) + (self.mappings_dict.get('new_nodes') or [])
                return NodeLists(self.merge_node_data(all_existing, adopted),
                                 self.merge_node_data(all_existing, unadopted))

            except Exception as e:
                if attempt < max_retries - 1:
                    delay = initial_delay * (2 ** attempt)
                    Logger.warning(f'Error loading network_map (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...')
                    time.sleep(delay)
                else:
                    Logger.error(f'Error loading network_map after {max_retries} attempts: {e}')
                    return None

        return None

    def assign_network_map_nodes(self, result):
        """Apply a read to shared state. Event-loop thread (or the constructor).

        A :class:`NodeLists` replaces ``node_list`` and clears a standing map
        error. An :class:`IdentityCollision` keeps the last good lists and
        records the error, logging each distinct identity once.

        Returns:
            ``True`` when this read cleared a standing map error.
        """
        if isinstance(result, IdentityCollision):
            if result.identity not in self._logged_collisions:
                Logger.error(result.message)
                self._logged_collisions = self._logged_collisions | {result.identity}
            self.network_map_error = {
                'kind': 'duplicate_identity',
                'identity': result.identity,
                'file': result.file,
            }
            return False

        self.node_list = {'nodes': result.nodes, 'new_nodes': result.new_nodes}
        Logger.debug(f'Network map reloaded successfully: {len(result.nodes)} adopted nodes, {len(result.new_nodes)} new nodes')
        cleared = self.network_map_error is not None
        self.network_map_error = None
        self._logged_collisions = frozenset()
        return cleared

    def network_map_error_message(self):
        """``{"type": "network_map_error", "value": <error or null>}``."""
        return json.dumps({"type": "network_map_error", "value": self.network_map_error})

    NODECONF_IPC = '/tmp/nodeconf.ipc'

    def nodeconf_available(self):
        """Is cuems-nodeconf reachable right now?

        Adoption goes engine -> /tmp/nodeconf.ipc, and nodeconf ships disabled
        on most of the fleet; there every adopt/un-adopt click can only end in
        an error, so the UI wants to grey the controls instead.

        Deliberately sampled per message rather than cached at map-reload time:
        nodeconf skips the write when the map's content has not changed, and it
        writes nothing at all once it is stopped — so a flag refreshed only on
        map changes would happily report `true` for as long as the operator
        left the panel open after `systemctl stop cuems-nodeconf`.
        """
        return os.path.exists(self.NODECONF_IPC)

    def initial_setting_message(self):
        """The project output mappings, as sent on connect.

        Returns:
            JSON string ``{"type": "initial_mappings", "value": <mapping document>}``.
            Since payload version 1 it carries no network-map status and no
            ``nodeconf_available``: those are :meth:`node_list_message`'s.
        """
        return json.dumps({"type": "initial_mappings", "value": self.mappings_dict})

    def node_list_message(self):
        """The node list, with ``nodeconf_available`` sampled now.

        Returns:
            JSON string ``{"type": "node_list", "value": {"nodes": [...],
            "new_nodes": [...], "nodeconf_available": bool}}``. The flag is an
            envelope field: it is not on any node and not in any document.
        """
        return json.dumps({"type": "node_list", "value": {
            "nodes": self.node_list['nodes'],
            "new_nodes": self.node_list['new_nodes'],
            "nodeconf_available": self.nodeconf_available(),
        }})

    NETWORK_MAP_POLL_S = 3.0

    async def watch_network_map(self):
        """Broadcast the node list whenever cuems-nodeconf rewrites the map.

        cuems-nodeconf is resident: it re-merges avahi discovery and rewrites
        network_map.xml on every (debounced) avahi event or every 30 s. We used
        to read that file only on connect and right after our own successful
        nodelist_modify, so a node powered on AFTER the operator opened the
        settings panel never appeared in `new_nodes` — the adoption feature
        looked broken exactly when it was needed.

        One mtime poll per host (not per client) at NETWORK_MAP_POLL_S; on a
        change every connected UI gets the refreshed list.
        """
        try:
            cf_manager = ConfigManager(load_all=False)
            map_file = cf_manager.conf_path('network_map.xml')
        except Exception as e:
            Logger.warning(f'network_map watcher disabled, cannot resolve path: {e}')
            return

        last_mtime = None
        try:
            last_mtime = os.stat(map_file).st_mtime
        except OSError:
            pass
        last_nodeconf = self.nodeconf_available()

        Logger.info(f'watching {map_file} for node list changes')
        while True:
            try:
                await asyncio.sleep(self.NETWORK_MAP_POLL_S)

                # nodeconf stopping or starting changes nothing on disk, so the
                # mtime check below would never notice it — and the UI would go
                # on offering adopt buttons that can only fail.
                nodeconf_now = self.nodeconf_available()
                if nodeconf_now != last_nodeconf:
                    Logger.info(
                        f'cuems-nodeconf availability changed: {nodeconf_now}'
                    )
                    last_nodeconf = nodeconf_now
                    await self.notify_all_node_list_update()

                try:
                    mtime = os.stat(map_file).st_mtime
                except OSError:
                    # nodeconf may be mid-replace, or the file may not exist on
                    # a host where nodeconf never ran. Neither is an error.
                    continue
                if last_mtime is not None and mtime != last_mtime:
                    Logger.debug('network_map.xml changed on disk, broadcasting')
                    await self.notify_all_node_list_update()
                last_mtime = mtime
            except asyncio.CancelledError:
                Logger.info('network_map watcher stopped')
                raise
            except Exception as e:
                Logger.warning(f'network_map watcher error: {e}')

    async def notify_all_node_list_update(self):
        """Reload the network map and broadcast the result to all clients.

        The read runs in the thread-pool executor; its result is assigned here,
        on the event-loop thread. On success every connected user gets
        ``node_list``, preceded by ``network_map_error: null`` when the read
        cleared a standing error. On a duplicate node identity every user
        gets ``network_map_error`` and the last good list stays in place.
        """
        result = await self.event_loop.run_in_executor(
            self.executor,
            functools.partial(self.reload_network_map_nodes, assign=False)
        )
        if not result:
            Logger.warning('Failed to reload network map, not broadcasting update')
            return
        cleared = self.assign_network_map_nodes(result)
        if isinstance(result, IdentityCollision):
            messages = [self.network_map_error_message()]
        else:
            messages = ([self.network_map_error_message()] if cleared else []) + [self.node_list_message()]
        if self.users:
            for user in self.users:
                for message in messages:
                    await user.outgoing.put(message)
            Logger.debug(f'Broadcasted node list update to {len(self.users)} connected client(s)')
        else:
            Logger.debug('Node list updated but no clients connected')

    def users_event(self, type, uuid=None):
        """Build a users-count or item-modified event message.

        Args:
            type: ``"users"`` to send the connected-user count; any other
                value builds an item-modified message (currently unused).
            uuid: Item UUID for non-``"users"`` message types.

        Returns:
            JSON string.
        """
        if type == "users":
            return json.dumps({"type": type, "value": len(self.users)})
        else:
            return json.dumps({"type": type, "uuid": uuid, "value": "modified in server"})  # TODO: not used

    def exception_handler(self, loop, context):
        """Log uncaught asyncio exceptions at DEBUG level.

        Registered as the event loop's exception handler in production mode
        (currently commented out to keep stack traces visible during
        development).

        Args:
            loop: The asyncio event loop.
            context: Exception context dict provided by asyncio.
        """
        Logger.debug("Caught the following exception: (ignore if on closing)")
        Logger.debug(context['message'])
