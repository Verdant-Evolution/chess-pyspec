from __future__ import annotations

import asyncio
import ctypes
import logging
import threading
import weakref
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Awaitable, Callable, Literal, TypeVar, overload
import re

import numpy as np
from pyee.asyncio import AsyncIOEventEmitter
from typing_extensions import Self

from .command import Command
from .data_types import ErrorStr, Type
from .message import DataType, Header, HeaderPrefix, HeaderV2, HeaderV3, HeaderV4

LOGGER = logging.getLogger("pyspec.connection")


T = TypeVar("T", bound=ctypes.Structure)


class RemoteException(Exception):
    """Exception raised when an error occurs on the remote server."""


class IndexedSingleton:
    """
    Metaclass for creating indexed singleton classes.

    Each unique combination of __init__ arguments will result in a single instance of the class.
    A weak reference to each instance is stored to allow for garbage collection when no longer in use.
    """

    _instances = {}
    _lock = threading.Lock()

    def __new__(
        cls,
        *args,
    ):
        key = args
        ref = cls._instances.get(key)
        instance = ref() if ref is not None else None
        if instance is None:
            with cls._lock:
                instance = super().__new__(cls)
            cls._instances[key] = weakref.ref(instance)
        return instance


class _Connection(AsyncIOEventEmitter):
    host: str
    """The host address of the connection."""
    port: int
    """The port number of the connection."""

    @dataclass
    class Message:
        """
        Represents a message received from the connection.
        """

        header: Header
        data: DataType

    @overload
    def __init__(
        self,
        host: str,
        port: int,
        /,
    ) -> None:
        """
        Initialize a connection to a remote host.

        This version should be used when you want to create a new client
        connection to a specified host and port.

        Args:
            host (str): The hostname or IP address of the remote server.
            port (int): The port number of the remote server.
        """

    @overload
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        /,
    ) -> None:
        """
        Initialize a connection using existing StreamReader and StreamWriter.
        This version should be used for when the socket connection is already established
        and you just want to interface with the sockets using the protocols defined here.

        Args:
            reader (asyncio.StreamReader): The stream reader for the connection.
            writer (asyncio.StreamWriter): The stream writer for the connection.
        """

    def __init__(
        self,
        host_or_reader: str | asyncio.StreamReader,
        port_or_writer: int | asyncio.StreamWriter,
        /,
    ) -> None:
        """
        Initialize a connection to a remote host.
        """
        super().__init__()

        if isinstance(host_or_reader, asyncio.StreamReader):
            if not isinstance(port_or_writer, asyncio.StreamWriter):
                raise TypeError(
                    "If the first argument is a StreamReader, the second must be a StreamWriter"
                )
            self._reader = host_or_reader
            self._writer = port_or_writer
            self.host: str = self._writer.get_extra_info("peername")[0]
            self.port: int = self._writer.get_extra_info("peername")[1]
        else:
            if not isinstance(port_or_writer, int):
                raise TypeError(
                    "If the first argument is a host string, the second must be an integer port"
                )
            self.host: str = host_or_reader
            self.port: int = port_or_writer
            self._reader = None
            self._writer = None

        self._listener: asyncio.Task | None = None
        self.logger = LOGGER.getChild(f"{self.host}:{self.port}")

    @property
    def is_connected(self) -> bool:
        """Returns True if the connection is established and open."""
        return self._writer is not None and not self._writer.is_closing()

    async def __aenter__(self) -> Self:
        self._listener = asyncio.create_task(self._listen())
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._listener:
            try:
                self._listener.cancel()
                await self._listener
            except asyncio.CancelledError:
                pass

    async def __send(self, msg: bytes) -> None:
        """Sends raw data to the connected server."""
        assert self._writer is not None, "Connection is not established."
        self.logger.debug("Sending message: %s", msg)
        self._writer.write(msg)
        await self._writer.drain()

    async def _send(self, header: Header, data: DataType = None) -> None:
        """Sends a message to the connected server."""
        data_bytes = header.prep_self_and_serialize_data(data)
        self.logger.info("Sending: %s", header.short_str(data))
        self.logger.debug("Detail: %s", header.long_str(data))
        await self.__send(bytes(header))
        if data_bytes:
            await self.__send(data_bytes)

    async def _listen(self):
        """Listens for raw data from the connected server."""
        assert self._reader is not None, "Connection is not established."
        while True:
            try:
                header = await self._read_header(self._reader)
            except asyncio.IncompleteReadError:
                self.logger.info("Connection closed by remote host")
                self.emit("close")
                break
            self.logger.debug("Received header: %s", header)
            data = await self._read_data(self._reader, header)
            self.logger.debug("Received data: %s", data)
            self.logger.info("Received: %s", header.short_str(data))
            self.emit("message", _Connection.Message(header, data))

    async def _read_header(
        self,
        stream: asyncio.StreamReader,
    ) -> Header:
        """Reads a message header from the stream."""
        prefix = await read_struct(stream, HeaderPrefix)
        prefix.vers

        if prefix.vers == 2:
            return await read_struct(stream, HeaderV2, prefix=bytes(prefix))
        elif prefix.vers == 3:
            return await read_struct(stream, HeaderV3, prefix=bytes(prefix))
        elif prefix.vers == 4:
            return await read_struct(stream, HeaderV4, prefix=bytes(prefix))

        raise ValueError(f"Unsupported header version: {prefix.vers}")

    async def _read_data(
        self,
        stream: asyncio.StreamReader,
        header: Header,
    ) -> DataType:
        """Deserialize data from the stream based on the provided header."""
        return header.deserialize_data(await stream.readexactly(header.len))


class ClientConnectionEventEmitter(AsyncIOEventEmitter):
    """
    This class defines the typed events emitted by the ClientConnection.
    """

    @overload
    def emit(
        self, event: Literal["message"], msg: ClientConnection.Message
    ) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["message"],
        func: Callable[[ClientConnection.Message], Any],
    ) -> Callable[[ClientConnection.Message], Any]:
        """
        Register an event listener for the 'message' event.

        A 'message' event is emitted whenever a new message is received from the server.
        """

    @overload
    def emit(self, event: Literal["hello-reply"]) -> bool: ...
    @overload
    def on(
        self, event: Literal["hello-reply"], func: Callable[[], Any]
    ) -> Callable[[], Any]:
        """
        Register an event listener for the 'hello-reply' event.

        A 'hello-reply' event is emitted when a HELLO_REPLY message is received from the server.
        This should only correspond to a HELLO command previously sent by the client.
        """

    @overload
    def emit(
        self, event: Literal["property-change"], property_name: str, value: DataType
    ) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["property-change"],
        func: Callable[[str, DataType], Any],
    ) -> Callable[[str, DataType], Any]:
        """
        Register an event listener for the 'property-change' event.

        A 'property-change' event is emitted whenever a property value changes on the server.
        'property-change' events are only emitted for properties that are subscribed to.
        """

    # This is for reply-{sequence_number} events
    @overload
    def emit(self, event: str, data: DataType) -> bool: ...
    @overload
    def on(
        self, event: str, func: Callable[[DataType], Any] | None = None
    ) -> Callable[[DataType], Any] | None:
        """
        Register an event listener for 'reply-{sequence_number}' events.

        A 'reply-{sequence_number}' event is emitted when a reply is received from the server
        corresponding to a command previously sent by the client with that sequence number.
        """

    def emit(self, event: str, *args: Any) -> bool:  # type: ignore[override]
        return super().emit(event, *args)

    def on(self, event: str, func: Callable[..., Any] | None = None):  # type: ignore[override]
        if func is None:
            return super().on(event)
        return super().on(event, func)


class ClientConnection(
    _Connection,
    ClientConnectionEventEmitter,
    IndexedSingleton,
):
    def __init__(self, host: str, port: int) -> None:
        _Connection.__init__(self, host, port)
        self.on("message", self._dispatch_typed_message_events)
        self._synchronizing_motors = False
        self._pending_motions: dict[str, float] = {}

    async def _dispatch_typed_message_events(self, msg: _Connection.Message) -> None:
        """
        Given a received message, emit the appropriate typed event based on the message command.
        """
        if msg.header.cmd == Command.EVENT:
            self.emit("property-change", msg.header.name, msg.data)
        elif msg.header.cmd == Command.HELLO_REPLY:
            self.emit("hello-reply")
        elif msg.header.cmd == Command.REPLY:
            self.emit(f"reply-{msg.header.sequence_number}", msg.data)

    async def __aenter__(self) -> ClientConnection:
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        await super().__aenter__()

        self.logger.info("Connected")

        response = await self._send_with_reply(HeaderV4(Command.HELLO))
        if response.header.cmd != Command.HELLO_REPLY:
            raise RuntimeError(
                f"Expected HELLO_REPLY from server. Received: {response.header.cmd}"
            )

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await super().__aexit__(exc_type, exc, tb)

        if self.is_connected:
            await self._send(HeaderV4(Command.CLOSE))
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    async def _send_with_reply(
        self, header: Header, data: DataType = None
    ) -> _Connection.Message:
        """
        Sends a message to the connected server and waits for a reply.
        """
        sequence_number = get_next_sequence_number()
        header.sequence_number = sequence_number
        response = asyncio.Future()
        self.once(
            "message",
            lambda msg: msg.header.sequence_number == sequence_number
            and response.set_result(msg),
        )
        await self._send(header, data)
        msg: _Connection.Message = await response
        if msg.header.type == Type.ERROR:
            self.logger.error(
                "Received %s reply for sequence number %d",
                msg.header.type,
                sequence_number,
            )
            error_message = msg.data if isinstance(msg.data, str) else "Unknown error"
            raise RemoteException(f"Error from server: {error_message}")
        return msg

    async def prop_get(self, prop: str) -> DataType:
        """
        Reads and returns the current value of property from the remote host.
        Single-valued, associative-array and data-array types can be returned.

        Args:
            prop (str): The name of the property to get.

        Raises:
            RemoteException: If the property does not exist on the remote host, or another error occurs.
        """
        return (
            await self._send_with_reply(HeaderV4(Command.CHAN_READ, name=prop))
        ).data

    async def prop_set(self, prop: str, value: DataType) -> None:
        """
        Sets property to value on the remote host.
        Single-valued, associative-array and data-array types can be sent.

        Args:
            prop (str): The name of the property to set.
            value (DataType): The value to set the property to.

        Raises:
            RemoteException: If the property does not exist on the remote host, or another error occurs.
        """
        await self._send(HeaderV4(Command.CHAN_SEND, name=prop), data=value)

    async def prop_watch(self, prop: str) -> None:
        """
        Registers property on the remote host.
        When the property value changes, the remote host will send an event to the client.

        Consider:
            prop_watch("var/TEMP")
        If a variable named TEMP exists on the local client, then the value of the local client's instance
        will track changes to the value of the same variable on the remote host.

        The variable must exist on the server before the client requests it be watched.
        If the variable goes out of existence on the server, but is subsequently recreated as the same type of global variable,
        the watched status will be reinstated (as of spec release 5.05.05-1).

        If the variable doesn't exist on the client or goes out of existence, the client will continue to receive events,
        and if the variable is recreated on the client, its value will track the values sent with the events (as of spec release 5.05.05-1).

        Regular global variables, associative arrays and associative array elements can be watched.
        Data arrays cannot be watched.
        The built-in motor and scaler arrays A[] and S[] can be watched, but events will only be generated when
        the elements are explicitly assigned values on the server,
        not when the values change by way of built-in code, such as from calcA, getangles or getcounts.
        """
        await self._send(HeaderV4(Command.REGISTER, name=prop))

    async def prop_unwatch(self, prop: str) -> None:
        """
        Unregisters property on the remote host.
        The remote host will no longer send events to the client when the property value changes.
        """
        await self._send(HeaderV4(Command.UNREGISTER, name=prop))

    async def abort(self) -> None:
        """
        Aborts the current command on the remote host.
        This has the same effect on the remote host as a ^C from the keyboard.
        Any pending commands in the server queue from the client will be removed.
        """
        await self._send(HeaderV4(Command.ABORT))

    async def remote_cmd_no_return(self, cmd: str) -> None:
        """
        Puts the spec command cmd on the execution queue of the remote host.
        Does not wait for the command to resolve or return a value.

        Args:
            cmd (str): The command string to send to the remote host. e.g. "1+1"
        """
        await self._send(HeaderV4(Command.CMD), data=cmd)

    async def remote_cmd(self, cmd: str) -> DataType:
        """
        Puts the spec command cmd on the execution queue of the remote host.
        Waits for the command to resolve and returns the resulting value.

        Args:
            cmd (str): The command string to send to the remote host. e.g. "1+1"

        Returns:
            DataType: The result of the command execution from the remote host.
        """
        return (
            await self._send_with_reply(HeaderV4(Command.CMD_WITH_RETURN), data=cmd)
        ).data

    async def remote_func_no_return(self, func: str, *args) -> None:
        """
        Calls the function func on the remote host with the provided arguments.
        Does not wait for the function to resolve or return a value.

        Args:
            func (str): The name of the function to call on the remote host.
            *args: The arguments to pass to the function. These will all be converted to strings before sending.
        """
        func_string = f"{func}(" + ", ".join(repr(arg) for arg in args) + ")"
        await self._send(HeaderV4(Command.FUNC), data=func_string)

    async def remote_func(self, func: str, *args) -> DataType:
        """
        Calls the function func on the remote host with the provided arguments.
        Waits for the command to resolve and returns the resulting value.

        Args:
            func (str): The name of the function to call on the remote host.
            *args: The arguments to pass to the function. These will all be converted to strings before sending.

        Returns:
            DataType: The result of the function execution from the remote host.
        """
        func_string = f"{func}(" + ", ".join(repr(arg) for arg in args) + ")"
        return (
            await self._send_with_reply(
                HeaderV4(Command.FUNC_WITH_RETURN), data=func_string
            )
        ).data

    async def hello(self, timeout: float = 5.0) -> bool:
        """
        Sends a HELLO command to the remote host.
        The remote host should respond with a HELLO_REPLY message.

        Waits for the reply up to the specified timeout.
        Args:
            timeout (float): The maximum time to wait for a reply, in seconds.


        Returns:
            bool: True if the HELLO_REPLY was received within the timeout, False otherwise.
        """

        try:
            await asyncio.wait_for(
                self._send_with_reply(HeaderV4(Command.HELLO)),
                timeout=timeout,
            )
            return True
        except asyncio.TimeoutError:
            self.logger.info("Timeout waiting for HELLO_REPLY from remote host")
            return False

    @asynccontextmanager
    async def synchronized_motors(
        self, timeout: float | None = None
    ) -> AsyncGenerator[None]:
        """
        Context manager to enable synchronized motor operations for the client.

        While this context is active, motor movements will be held.
        Upon exiting the context, the movements will be initialized simultaneously

        Usage:
            async with client.synchronized_motors():
                # Motor movement will be held in here.
                motor1.move(position)
                motor2.move(position)

                # Motors will not start moving yet.
                await asyncio.sleep(1)  # Simulate other operations
                # Motors will start moving simultaneously here.

            # Outside of the context, all motors have completed their movements.
        """
        assert (
            not self._synchronizing_motors
        ), "Nested synchronized_motors contexts are not allowed."

        move_done_pattern = re.compile(r"motor/(.+)/move_done")

        waiting_for: dict[str, asyncio.Future] = {}

        def motor_move_done_check(name: str, value: DataType) -> None:
            if (match := move_done_pattern.match(name)) is None:
                return
            motor_name = match.group(1)
            if motor_name in waiting_for:
                self.logger.info(
                    "move_done received for `%s` during synchronized motion.",
                    motor_name,
                )
                waiting_for[motor_name].set_result(True)

        motion_started = False
        try:
            if len(self._pending_motions) > 0:
                raise RuntimeError(
                    "There are pending motor motions from a previous synchronized_motors context."
                )
            self._synchronizing_motors = True

            # Give control back to user.
            yield

            self.on("property-change", motor_move_done_check)
            for mne in self._pending_motions.keys():
                waiting_for[mne] = asyncio.Future()

            # Start the prestart message
            motion_started = True
            await self.prop_set("motor/../prestart_all", None)

            # Append the individual motor commands
            for mne, position in self._pending_motions.items():
                self.logger.info(
                    "Starting synchronized move for `%s` to position %s.",
                    mne,
                    position,
                )

                await self.prop_set(f"motor/{mne}/start_one", position)

            # Start all the motors simultaneously
            await self.prop_set("motor/../start_all", None)

            # Wait for them to be done
            await asyncio.wait(waiting_for.values(), timeout=timeout)
        except Exception as e:
            self.logger.error("Error during synchronized motor operations: %s", str(e))
            if motion_started:
                await self.prop_set("motor/../abort_all", None)
            raise
        finally:
            self._synchronizing_motors = False
            self._pending_motions.clear()
            self.remove_listener("message", motor_move_done_check)


class ServerConnectionEventEmitter(AsyncIOEventEmitter):
    """
    This class defines the typed events emitted by the ServerConnection.
    """

    @overload
    def emit(self, event: Literal["close"]) -> bool: ...
    @overload
    def on(self, event: Literal["close"], func: Callable[[], Any]) -> Callable[[], Any]:
        """
        Register an event listener for the 'close' event.

        A 'close' event is emitted whenever the client connection is closed.
        """

    @overload
    def emit(self, event: Literal["abort"]) -> bool: ...
    @overload
    def on(self, event: Literal["abort"], func: Callable[[], Any]) -> Callable[[], Any]:
        """
        Register an event listener for the 'abort' event.

        An 'abort' event is emitted whenever the client sends an ABORT command.
        The server should treat this like a "^C" from the keyboard with respect to any currently executing commands.
        """

    @overload
    def emit(self, event: Literal["hello"], sequence_number: int) -> bool: ...
    @overload
    def on(
        self, event: Literal["hello"], func: Callable[[int], Any]
    ) -> Callable[[int], Any]:
        """
        Register an event listener for the 'hello' event.

        A 'hello' event is emitted whenever the client sends a HELLO command.
        The server should respond with a HELLO_REPLY message.
        """

    @overload
    def emit(self, event: Literal["remote-cmd-no-return"], command: str) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["remote-cmd-no-return"],
        func: Callable[[str], Any],
    ) -> Callable[[str], Any]:
        """
        Register an event listener for the 'remote-cmd-no-return' event.

        A 'remote-cmd-no-return' event is emitted whenever the client sends a command
        that does not expect a return value.
        """

    @overload
    def emit(
        self, event: Literal["remote-cmd"], sequence_number: int, command: str
    ) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["remote-cmd"],
        func: Callable[[int, str], Awaitable[DataType]],
    ) -> Callable[[int, str], Awaitable[DataType]]:
        """
        Register an event listener for the 'remote-cmd' event.

        A 'remote-cmd' event is emitted whenever the client sends a command
        that expects a return value.
        """

    @overload
    def emit(
        self, event: Literal["remote-func-no-return"], function_call: str
    ) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["remote-func-no-return"],
        func: Callable[[str], Any],
    ) -> Callable[[str], Any]:
        """
        Register an event listener for the 'remote-func-no-return' event.

        A 'remote-func-no-return' event is emitted whenever the client calls a function
        that does not expect a return value.

        A function call is represented as a string, e.g. "my_function(1, 'arg2')".
        """

    @overload
    def emit(
        self, event: Literal["remote-func"], sequence_number: int, function_call: str
    ) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["remote-func"],
        func: Callable[[int, str], Awaitable[DataType]],
    ) -> Callable[[int, str], Awaitable[DataType]]:
        """
        Register an event listener for the 'remote-func' event.

        A 'remote-func' event is emitted whenever the client calls a function
        that expects a return value.

        A function call is represented as a string, e.g. "my_function(1, 'arg2')".
        """

    @overload
    def emit(
        self, event: Literal["property-set"], property_name: str, value: DataType
    ) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["property-set"],
        func: Callable[[str, DataType], Any],
    ) -> Callable[[str, DataType], Any]:
        """
        Register an event listener for the 'property-set' event.

        A 'property-set' event is emitted whenever the client sets a property value on the server.
        """

    @overload
    def emit(
        self, event: Literal["property-get"], sequence_number: int, property_name: str
    ) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["property-get"],
        func: Callable[[int, str], Any],
    ) -> Callable[[int, str], Any]:
        """
        Register an event listener for the 'property-get' event.

        A 'property-get' event is emitted whenever the client requests a property value from the server.
        """

    @overload
    def emit(self, event: Literal["property-watch"], property_name: str) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["property-watch"],
        func: Callable[[str], Any],
    ) -> Callable[[str], Any]:
        """
        Register an event listener for the 'property-watch' event.

        A 'property-watch' event is emitted whenever the client registers to watch a property on the server.
        The server should start sending events to the client when the property value changes.
        """

    @overload
    def emit(self, event: Literal["property-unwatch"], property_name: str) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["property-unwatch"],
        func: Callable[[str], Any],
    ) -> Callable[[str], Any]:
        """
        Register an event listener for the 'property-unwatch' event.

        A 'property-unwatch' event is emitted whenever the client unregisters from watching a property on the server.
        The server should stop sending events to the client when the property value changes.
        """

    @overload
    def on(
        self, event: Literal["message"], func: Callable[[ServerConnection.Message], Any]
    ) -> Callable[[ServerConnection.Message], Any]:
        """
        Register an event listener for the 'message' event.

        A 'message' event is emitted whenever a new message is received from the client.
        Consider using the more specific events defined in this class instead.
        """

    def emit(self, event: str, *args: Any) -> bool:  # type: ignore[override]
        return super().emit(event, *args)

    def on(self, event: str, func: Callable[..., Any] | None = None):  # type: ignore[override]
        if func is None:
            return super().on(event)
        return super().on(event, func)


class ServerConnection(_Connection, ServerConnectionEventEmitter):
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        _Connection.__init__(self, reader, writer)
        self.on("message", self._dispatch_typed_message_events)
        self.logger = logging.getLogger("pyspec.server").getChild(
            f"{self.host}:{self.port}"
        )

    def _dispatch_typed_message_events(self, msg: ServerConnection.Message) -> None:
        """
        Match the msg with the appropriate event and emit it.
        Validates the message data type where possible.

        Args:
            msg (ServerConnection.Message): The message to dispatch.

        Raises:
            TypeError: If the message data type is invalid for the command.
            ValueError: If the command is unknown.

        """

        match msg.header.cmd:
            case Command.CLOSE:
                self.emit("close")
            case Command.ABORT:
                self.emit("abort")
            case Command.HELLO:
                self.emit("hello", msg.header.sequence_number)
            case Command.CHAN_SEND:
                self.emit("property-set", msg.header.name, msg.data)
            case Command.CHAN_READ:
                self.emit("property-get", msg.header.sequence_number, msg.header.name)
            case Command.REGISTER:
                self.emit("property-watch", msg.header.name)
            case Command.UNREGISTER:
                self.emit("property-unwatch", msg.header.name)
            case (
                Command.CMD
                | Command.CMD_WITH_RETURN
                | Command.FUNC
                | Command.FUNC_WITH_RETURN
            ):
                if not isinstance(msg.data, str):
                    raise TypeError(
                        f"Expected command data to be str, got {type(msg.data)}"
                    )
                match msg.header.cmd:
                    case Command.CMD:
                        self.emit("remote-cmd-no-return", msg.data)
                    case Command.CMD_WITH_RETURN:
                        self.emit("remote-cmd", msg.header.sequence_number, msg.data)
                    case Command.FUNC:
                        self.emit("remote-func-no-return", msg.data)
                    case Command.FUNC_WITH_RETURN:
                        self.emit("remote-func", msg.header.sequence_number, msg.data)
            case _:
                raise ValueError(f"Unknown command: {msg.header.cmd}")

    async def prop_send(self, property: str, value) -> None:
        """
        Sends an event to all clients registered for property.
        There is nothing to prevent a user-level call of prop_send() from generating events for built-in properties,
        although that may lead to an unexpected client response.
        """
        await self._send(HeaderV4(Command.EVENT, name=property), data=value)

    async def serve_forever(self) -> None:
        """
        Start listening for messages from the client indefinitely.
        This coroutine will run until the connection is closed.
        """
        if self._listener is None:
            raise RuntimeError("Connection is not started.")
        await self._listener

    async def reply(self, sequence_number: int, data: DataType) -> None:
        """
        Sends a reply to a remote command or function call.
        """
        await self._send(
            HeaderV4(Command.REPLY, sequence_number=sequence_number), data=data
        )

    async def reply_error(self, sequence_number: int, error_message: str) -> None:
        """
        Sends an error reply to a remote command or function call.
        """
        await self._send(
            HeaderV4(Command.REPLY, sequence_number=sequence_number),
            data=ErrorStr(error_message),
        )

    @asynccontextmanager
    async def catch_reply_exceptions(self, sequence_number: int):
        """
        Context manager to catch exceptions during command handling and send error replies.
        Will send an error reply to the client if an exception is raised within the context.
        """
        try:
            yield
        except Exception as e:
            self.logger.error(
                "Exception occurred while handling command (%s): `%s`",
                sequence_number,
                e,
            )
            await self.reply_error(sequence_number, str(e))

    async def hello_reply(self, sequence_number: int) -> None:
        """
        Sends a HELLO_REPLY to the client in response to a HELLO command.
        """
        await self._send(HeaderV4(Command.HELLO_REPLY, sequence_number=sequence_number))


LAST_SEQUENCE_NUMBER = 0


def get_next_sequence_number() -> int:
    """
    Loops throuhg a uint32 sequence number for messages.
    0 is reserved for messages that do not expect a reply.
    1-4294967295 are valid sequence numbers.
    """
    global LAST_SEQUENCE_NUMBER
    LAST_SEQUENCE_NUMBER = (LAST_SEQUENCE_NUMBER + 1) % np.iinfo(np.uint32).max
    if LAST_SEQUENCE_NUMBER == 0:
        return get_next_sequence_number()
    return LAST_SEQUENCE_NUMBER


async def read_struct(
    stream: asyncio.StreamReader,
    struct_type: type[T],
    prefix: bytes = b"",
) -> T:
    """
    Reads a ctypes structure from the stream.

    Args:
        stream (asyncio.StreamReader): The stream to read from.
        struct_type (type[T]): The ctypes structure type to read.
        prefix (bytes, optional): Any bytes that have already been read for the structure. Defaults to b"".
    """
    return struct_type.from_buffer_copy(
        prefix + await stream.readexactly(ctypes.sizeof(struct_type) - len(prefix))
    )
