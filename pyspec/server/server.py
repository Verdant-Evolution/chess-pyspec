from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Any, Callable

from pyee.asyncio import AsyncIOEventEmitter

from pyspec._connection.data import DataType
from pyspec.server._remote_property import Property

from .._connection import ServerConnection
from ._remote_function import (
    SyncOrAsyncCallable,
    is_remote_function,
    parse_remote_function_string,
    remote_function_name,
)

LOGGER = logging.getLogger("pyspec.server")


class Singleton:
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if not hasattr(cls, "_instance"):
                cls._instance = super(Singleton, cls).__new__(cls)
        return cls._instance

    @classmethod
    def dispose(cls):
        """
        Disposes of the singleton instance. This can be useful in testing scenarios
        where you want to reset the state of the server between tests.
        """
        with cls._lock:
            if hasattr(cls, "_instance"):
                del cls._instance
                LOGGER.debug(f"{cls.__name__} singleton instance disposed.")


class ServerException(Exception):
    def __init__(self, msg: str, *args: object) -> None:
        """
        Exception for server errors.

        Args:
            msg (str): The error message.
        """
        super().__init__(msg, *args)
        self.msg = msg

    def __str__(self) -> str:
        return self.msg


class Server(AsyncIOEventEmitter, Singleton):

    def __init__(
        self,
        host: str = "localhost",
        port: int | None = None,
        allow_remote_code_execution: bool = False,
    ):
        """
        Initialize the server.

        Args:
            host (str, optional): The hostname to bind the server to.
            port (int | None, optional): The port to bind the server to.
            allow_remote_code_execution (bool, optional): If True, enables test mode (arbitrary code execution allowed).
        """
        super().__init__()
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._property_listeners: dict[str, set[ServerConnection]] = defaultdict(set)
        self._abortable_tasks: set[asyncio.Task] = set()
        self._remote_functions = self._build_remote_function_table()
        self._remote_properties = self._register_properties()

        self._allow_remote_code_execution = allow_remote_code_execution

        if self._allow_remote_code_execution:
            LOGGER.warning(
                "Server is running in ALLOW_REMOTE_CODE_EXECUTION mode. Arbitrary code execution is allowed."
            )

    def _build_remote_function_table(self):
        """
        Builds the table of remote functions by inspecting the Server instance for
        methods decorated with @remote_function.

        This table is used to dispatch remote function calls from clients.
        Returns:
            dict: Dictionary mapping function names to callables.
        """
        remote_functions: dict[str, SyncOrAsyncCallable] = {}
        for attr_name, attr in inspect.getmembers(self):
            if is_remote_function(attr):
                LOGGER.debug("Registering remote function: `%s`", attr_name)
                remote_functions[remote_function_name(attr)] = attr
        return remote_functions

    def _register_properties(self):
        """
        Registers all Property attributes found on the Server instance.
        This method sets up listeners to broadcast property changes to connected clients.
        Returns:
            dict: Dictionary mapping property names to Property objects.
        """

        def make_broadcaster(property_name: str) -> Callable[[Any], asyncio.Task]:
            return lambda value: asyncio.create_task(
                self.broadcast_property(property_name, value)
            )

        remote_properties: dict[str, Property[Any]] = {}
        for attr_name, prop in inspect.getmembers(self):
            if isinstance(prop, Property):
                LOGGER.debug(
                    "Registering remote property: `%s` at `%s`", attr_name, prop.name
                )
                prop.on("change", make_broadcaster(prop.name))
                remote_properties[prop.name] = prop
        return remote_properties

    @contextmanager
    def abortable(self, task: asyncio.Task):
        """
        Context manager to register a task as an abortable task on the server.

        A task registered like this will be interrupted by ABORT commands from clients or by calling the server's abort() method.

        Args:
            task (asyncio.Task): The task to register as abortable.
        """
        try:
            self._abortable_tasks.add(task)
            yield
        finally:
            self._abortable_tasks.discard(task)

    async def execute_command(self, command: str) -> DataType:
        """
        WARNING: This method allows execution of arbitrary code.
        You should not allow this to be called in production environments.

        Executes an arbitrary command string in test mode only.

        Args:
            command (str): The command string to execute.
        Returns:
            DataType: The result of the executed command.
        Raises:
            PermissionError: If not in test mode.
        """
        if self._allow_remote_code_execution:
            return eval(command)
        else:
            try:
                return ast.literal_eval(command)
            except Exception:
                LOGGER.warning(
                    "Attempted to execute non-literal command in non-test mode: %s",
                    command,
                )
                raise PermissionError("Command execution is only allowed in test mode.")

    async def execute_function(self, function_call: str) -> DataType:
        """
        Attempts to execute a function call defined on the server.
        Refers to the table of remote functions built at server initialization.

        Args:
            function_call (str): The function call string, e.g. "func_name(arg1, arg2)".
        Returns:
            DataType: The result of the function call.
        """

        name, args = parse_remote_function_string(function_call)
        if name not in self._remote_functions:
            raise ValueError(f"Remote function '{name}' not found on server.")

        # These are already bound to self if necessary, since they came from
        # getattr(self, attr_name)
        func = self._remote_functions[name]
        try:
            result = func(*args)
            if asyncio.iscoroutine(result):
                task = asyncio.create_task(result)
                with self.abortable(task):
                    return await task
            return result
        except asyncio.CancelledError:
            LOGGER.info("Function '%s' aborted.", name)
            raise RuntimeError("Function execution aborted.")

    async def broadcast_property(self, property_name: str, value: DataType) -> None:
        """
        Broadcasts a property value to all connected clients that are subscribed to updates for that property.

        Args:
            property_name (str): The name of the property to broadcast.
            value (DataType): The value to broadcast.
        """
        listening_clients = self._property_listeners.get(property_name, set())
        await asyncio.gather(
            *[client.prop_send(property_name, value) for client in listening_clients]
        )

    async def abort(self):
        """
        Aborts all abortable tasks on the server.
        See the abortable() context manager.
        """
        for task in list(self._abortable_tasks):
            task.cancel()
        self._abortable_tasks.clear()

    async def _on_client_connected(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ):
        """
        Handles a new client connection. Sets up event handlers for all of the necessary
        messages that the server needs to handle to implement a "SPEC Server."

        Args:
            client_reader (asyncio.StreamReader): The stream reader for the client connection.
            client_writer (asyncio.StreamWriter): The stream writer for the client connection.
        """
        host, port = client_writer.get_extra_info("peername")
        logger = LOGGER.getChild(f"{host}:{port}")
        connection = ServerConnection(client_reader, client_writer)

        def on_close():
            client_writer.close()

        async def on_abort():
            await self.abort()

        async def on_hello(sequence_number: int):
            await connection.hello_reply(sequence_number)

        async def on_cmd_no_return(command: str):
            logger.info("Command: %s", command)
            return await self.execute_command(command)

        async def on_cmd(sequence_number: int, command: str):
            async with connection.catch_reply_exceptions(sequence_number):
                await connection.reply(sequence_number, await on_cmd_no_return(command))

        async def on_func_no_return(function_call: str):
            logger.info("Function call: %s", function_call)
            return await self.execute_function(function_call)

        async def on_func(sequence_number: int, function_call: str):
            async with connection.catch_reply_exceptions(sequence_number):
                await connection.reply(
                    sequence_number, await on_func_no_return(function_call)
                )

        async def on_property_get(sequence_number: int, property_name: str):
            logger.info("Property get: %s", property_name)
            async with connection.catch_reply_exceptions(sequence_number):
                if property_name not in self._remote_properties:
                    raise ServerException(
                        f"Property '{property_name}' not found on server."
                    )
                prop = self._remote_properties[property_name]
                await connection.reply(sequence_number, prop.get())

        async def on_property_set(property_name: str, value: DataType):
            logger.info("Property set: %s", property_name)
            logger.debug("Property value: %s", value)
            if property_name not in self._remote_properties:
                logger.error("Property '%s' not found on server.", property_name)
                return
            prop = self._remote_properties[property_name]
            prop.set(value)

        async def on_property_watch(property_name: str):
            logger.info("Subscribed to property: %s", property_name)
            self._property_listeners[property_name].add(connection)
            # Immediately send the current value of the property upon subscription
            if property_name in self._remote_properties:
                prop = self._remote_properties[property_name]
                await connection.prop_send(property_name, prop.get())

        async def on_property_unwatch(property_name: str):
            logger.info("Unsubscribed from property: %s", property_name)
            self._property_listeners[property_name].discard(connection)

        async with connection:
            connection.on("close", on_close)
            connection.on("abort", on_abort)
            connection.on("remote-cmd-no-return", on_cmd_no_return)
            connection.on("remote-cmd", on_cmd)
            connection.on("remote-func-no-return", on_func_no_return)
            connection.on("remote-func", on_func)
            connection.on("property-get", on_property_get)
            connection.on("property-set", on_property_set)
            connection.on("property-watch", on_property_watch)
            connection.on("property-unwatch", on_property_unwatch)
            connection.on("hello", on_hello)

            logger.info("Connected")

            await connection.serve_forever()

    async def __aenter__(self):
        """
        Async context manager entry. Starts the server.
        """
        self._server = await asyncio.start_server(
            self._on_client_connected, self.host, self.port, reuse_port=True
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        """
        Async context manager exit. Shuts down the server and disposes the singleton instance.
        """
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
            LOGGER.info("Server shut down.")
        # Dispose of the singleton instance to allow for fresh instances in testing or future runs
        self.dispose()

    async def serve_forever(self):
        """
        Runs the server indefinitely.
        """
        if not self._server:
            raise RuntimeError("Server is not running. Use 'async with Server(...)'.")

        async with self._server:
            await self._server.serve_forever()
