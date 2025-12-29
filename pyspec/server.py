from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from contextlib import contextmanager
import threading
from typing import Any, Callable, Generic, TypeVar

from pyee.asyncio import AsyncIOEventEmitter

from pyspec._connection.data_types import DataType
from pyspec._remote_function import (
    SyncOrAsyncCallable,
    is_remote_function,
    mark_remote_function,
    parse_remote_function_string,
    remote_function_name,
)

from ._connection import ServerConnection

LOGGER = logging.getLogger("pyspec.server")


T = TypeVar("T", bound=DataType)
F = TypeVar("F", bound=SyncOrAsyncCallable)


class Singleton(type):
    _lock = threading.Lock()

    def __new__(cls, name, bases, attrs):
        if not hasattr(cls, "instance"):
            with cls._lock:
                cls.instance = super(Singleton, cls).__new__(cls, name, bases, attrs)
        return cls.instance


class ServerException(Exception):
    def __init__(self, msg: str, *args: object) -> None:
        super().__init__(msg, *args)
        self.msg = msg

    def __str__(self) -> str:
        return self.msg


class Server(AsyncIOEventEmitter, metaclass=Singleton):

    class Property(Generic[T], AsyncIOEventEmitter):
        def __init__(
            self,
            name: str,
            initial_value: T,
            dtype: type[T] | type[object] = object,
        ):
            super().__init__()
            self.name = name
            self._value: T = initial_value
            self._dtype = dtype

        def get(self) -> T:
            return self._value

        def set(self, value: T) -> None:
            if not isinstance(value, self._dtype):
                raise TypeError(
                    f"Expected data of type {self._dtype}, got {type(value)}"
                )
            self._value = value
            self.emit("set", value)

    @staticmethod
    def remote_function(function: F) -> F:
        """Decorator to mark a function as remotely callable."""
        mark_remote_function(function)
        if not asyncio.iscoroutinefunction(function):
            LOGGER.warning(
                "Remote function '%s' is not asynchronous. "
                "Consider making it async for better performance.",
                function.__name__,
            )
        return function

    def __init__(
        self, host: str = "localhost", port: int | None = None, test_mode: bool = False
    ):
        super().__init__()
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None
        self._property_listeners: dict[str, set[ServerConnection]] = defaultdict(set)
        self._running_tasks: set[asyncio.Task] = set()
        self._remote_functions = self._build_remote_function_table()
        self._remote_properties = self._register_properties()

        self._test_mode = test_mode

        if self._test_mode:
            LOGGER.warning(
                "Server is running in TEST MODE. Arbitrary code execution is allowed."
            )

    def _build_remote_function_table(self):
        """
        Builds the table of remote functions by inspecting the Server instance for
        methods decorated with @remote_function.

        This table is used to dispatch remote function calls from clients.
        """
        remote_functions: dict[str, SyncOrAsyncCallable] = {}
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if is_remote_function(attr):
                remote_functions[remote_function_name(attr)] = attr
        return remote_functions

    def _register_properties(self):
        """
        Registers all Server.Property attributes found on the Server instance.
        This method sets up listeners to broadcast property changes to connected clients.
        """

        def make_broadcaster(property_name: str) -> Callable[[Any], asyncio.Task]:
            return lambda value: asyncio.create_task(
                self.broadcast_property(property_name, value)
            )

        remote_properties: dict[str, Server.Property[Any]] = {}
        for attr_name in dir(self):
            attr = getattr(self, attr_name)
            if isinstance(attr, Server.Property):
                attr.on("set", make_broadcaster(attr.name))
                remote_properties[attr.name] = attr
        return remote_properties

    @contextmanager
    def abortable(self, task: asyncio.Task):
        """
        Context manager to register a task as
        an abortable task on the server.

        A task registered like this will be interrupted by
        ABORT commands from clients or by calling the server's abort() method.

        Args:
            task (asyncio.Task): The task to register as abortable.
        """
        try:
            self._running_tasks.add(task)
            yield
        finally:
            self._running_tasks.discard(task)

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
        if self._test_mode:
            return eval(command)
        else:
            LOGGER.warning("Attempted to execute command in non-test mode: %s", command)
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
                    return await result
            return result
        except asyncio.CancelledError:
            LOGGER.info("Function '%s' aborted.", name)
            pass

    async def broadcast_property(self, property_name: str, value: DataType) -> None:
        """
        Broadcasts a property value to all connected clients
        that are subscribed to updates for that property.
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
        for task in list(self._running_tasks):
            task.cancel()
        self._running_tasks.clear()

    async def _on_client_connected(
        self, client_reader: asyncio.StreamReader, client_writer: asyncio.StreamWriter
    ):
        """
        Handles a new client connection. Sets up event handlers for all of the necessary
        messages that the server needs to handle to implement a "SPEC Server."
        """
        host, port = client_writer.get_extra_info("peername")
        logger = LOGGER.getChild(f"{host}:{port}")

        def on_close():
            logger.info("Close")
            client_writer.close()

        async def on_abort():
            logger.warning("Abort")
            await self.abort()

        async def on_hello(sequence_number: int):
            logger.info("Hello")
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

        async def on_property_unwatch(property_name: str):
            logger.info("Unsubscribed from property: %s", property_name)
            self._property_listeners[property_name].discard(connection)

        async with ServerConnection(client_reader, client_writer) as connection:
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
            while not client_writer.is_closing():
                await connection.serve_forever()

    async def __aenter__(self):
        self._server = await asyncio.start_server(
            self._on_client_connected,
            self.host,
            self.port,
        )
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def serve_forever(self):
        """Runs the server indefinitely."""
        if not self._server:
            raise RuntimeError("Server is not running. Use 'async with Server(...)'.")

        async with self._server:
            await self._server.serve_forever()
