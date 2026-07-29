import asyncio
import re
import threading
import weakref
from contextlib import asynccontextmanager
from typing import Any, Callable, Literal, Optional, overload

import numpy as np
from pyee.asyncio import AsyncIOEventEmitter

from .connection import Connection
from .data import DataType, ErrorStr
from .protocol import Command, Header

LAST_SEQUENCE_NUMBER = 0

VAR_PROPERTY_NAME_PATTERN = re.compile(r"^/?var/([A-Za-z_][A-Za-z0-9_]*)/?$")


class RemoteException(Exception):
    """
    Exception raised when an error occurs on the remote server.
    """


def get_next_sequence_number() -> int:
    """
    Loops through a uint32 sequence number for messages.

    0 is reserved for messages that do not expect a reply.
    1-4294967295 are valid sequence numbers.

    Returns:
        int: The next sequence number.
    """
    global LAST_SEQUENCE_NUMBER
    LAST_SEQUENCE_NUMBER = (LAST_SEQUENCE_NUMBER + 1) % np.iinfo(np.uint32).max
    if LAST_SEQUENCE_NUMBER == 0:
        return get_next_sequence_number()
    return LAST_SEQUENCE_NUMBER


def _remote_function_arg_string(arg: Any) -> str:
    """
    Serialize one remote function argument.

    Client-side properties under the SPEC variable tree are sent as bare
    symbols so the server can resolve them. All other values keep the historic
    repr-based serialization.
    """
    from pyspec.client import Property

    if isinstance(arg, Property):
        match = VAR_PROPERTY_NAME_PATTERN.match(arg.name)
        if match:
            return match.group(1)
        else:
            raise ValueError(
                f"Property `{arg.name}` cannot be resolved to a remote variable."
            )
    return repr(arg)


def build_remote_function_string(func: str, *args: Any) -> str:
    args_string = ", ".join(_remote_function_arg_string(arg) for arg in args)
    return f"{func}({args_string})"


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


class ClientConnectionEventEmitter(AsyncIOEventEmitter):
    """
    Defines the typed events emitted by the ClientConnection.
    """

    @overload
    def emit(
        self, event: Literal["message"], msg: "ClientConnection.Message"
    ) -> bool: ...
    @overload
    def on(
        self,
        event: Literal["message"],
        func: Callable[["ClientConnection.Message"], Any],
    ) -> Callable[["ClientConnection.Message"], Any]:
        """
        Register an event listener for the 'message' event.

        A 'message' event is emitted whenever a new message is received from the server.
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
        self, event: str, func: Optional[Callable[[DataType], Any]] = None
    ) -> Optional[Callable[[DataType], Any]]:
        """
        Register an event listener for 'reply-{sequence_number}' events.

        A 'reply-{sequence_number}' event is emitted when a reply is received from the server
        corresponding to a command previously sent by the client with that sequence number.
        """

    def emit(self, event: str, *args: Any) -> bool:  # type: ignore[override]
        return super().emit(event, *args)

    def on(self, event: str, func: Optional[Callable[..., Any]] = None):  # type: ignore[override]
        if func is None:
            return super().on(event)
        return super().on(event, func)


class ClientConnection(
    Connection,
    ClientConnectionEventEmitter,
    IndexedSingleton,
):
    """
    Represents a connection to a remote Spec server.

    Provides methods to interact with the server, including reading and writing properties,
    executing commands and functions, and handling events.
    """

    def __init__(self, host: str, port: int) -> None:
        Connection.__init__(self, host, port)
        self.on("message", self._dispatch_typed_message_events)

    async def _dispatch_typed_message_events(self, msg: Connection.Message) -> None:
        """
        Given a received message, emit the appropriate typed event based on the message command.

        Args:
            msg (Connection.Message): The received message.
        """
        if msg.header.command == Command.EVENT:
            self.emit("property-change", msg.header.name, msg.data)
        elif (
            msg.header.command == Command.REPLY
            or msg.header.command == Command.HELLO_REPLY
        ):
            self.emit(f"reply-{msg.header.sequence_number}", msg.data)
        else:
            self.logger.error(
                "Received message with unrecognized command: %s", msg.header.command
            )

    async def __aenter__(self) -> "ClientConnection":
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        await super().__aenter__()

        self.logger.info("Connected")

        await self.hello()

        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await super().__aexit__(exc_type, exc, tb)

        if self.is_connected:
            await self._send(Header(Command.CLOSE))
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()

    async def _send_with_reply(self, header: Header, data: DataType = None) -> DataType:
        """
        Sends a message to the connected server and waits for a reply.

        Args:
            header (Header): The header to send.
            data (DataType, optional): The data to send.
        Returns:
            DataType: The reply data from the server.
        Raises:
            RemoteException: If the server replies with an error.
        """
        sequence_number = get_next_sequence_number()
        header.sequence_number = sequence_number
        response = asyncio.Future()

        def set_response(data: DataType) -> None:
            if response.done():
                return

            if isinstance(data, ErrorStr):
                self.logger.error(
                    "Received ERROR reply for sequence number %d",
                    sequence_number,
                )
                error_message = data if isinstance(data, str) else "Unknown error"
                response.set_exception(
                    RemoteException(f"Error from server: {error_message}")
                )
            else:
                response.set_result(data)

        self.once(f"reply-{sequence_number}", set_response)
        await self._send(header, data)
        return await response

    async def prop_get(self, prop: str) -> DataType:
        """
        Reads and returns the current value of a property from the remote host.
        Single-valued, associative-array and data-array types can be returned.

        Args:
            prop (str): The name of the property to get.
        Returns:
            DataType: The value of the property.
        Raises:
            RemoteException: If the property does not exist on the remote host, or another error occurs.
        """
        return await self._send_with_reply(Header(Command.CHAN_READ, name=prop))

    async def prop_set(self, prop: str, value: DataType) -> None:
        """
        Sets a property to a value on the remote host.
        Single-valued, associative-array and data-array types can be sent.

        Args:
            prop (str): The name of the property to set.
            value (DataType): The value to set the property to.
        Raises:
            RemoteException: If the property does not exist on the remote host, or another error occurs.
        """
        await self._send(Header(Command.CHAN_SEND, name=prop), data=value)

    async def prop_watch(self, prop: str) -> None:
        """
        Registers a property on the remote host for watching.
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

        Args:
            prop (str): The name of the property to watch.
        """
        await self._send(Header(Command.REGISTER, name=prop))

    async def prop_unwatch(self, prop: str) -> None:
        """
        Unregisters a property on the remote host.
        The remote host will no longer send events to the client when the property value changes.

        Args:
            prop (str): The name of the property to unwatch.
        """
        await self._send(Header(Command.UNREGISTER, name=prop))

    async def abort(self) -> None:
        """
        Aborts the current command on the remote host.
        This has the same effect on the remote host as a ^C from the keyboard.
        Any pending commands in the server queue from the client will be removed.
        """
        await self._send(Header(Command.ABORT))

    @asynccontextmanager
    async def _abort_on_interrupt(self):
        """
        Context manager to automatically abort the current command on the remote host if an interrupt signal is received.
        """
        try:
            yield
        except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
            await self.abort()
            raise

    async def remote_cmd_no_return(self, cmd: str) -> None:
        """
        Puts the spec command on the execution queue of the remote host.
        Does not wait for the command to resolve or return a value.

        Args:
            cmd (str): The command string to send to the remote host. e.g. "1+1"
        """
        await self._send(Header(Command.CMD), data=cmd)

    async def remote_cmd(self, cmd: str) -> DataType:
        """
        Puts the spec command on the execution queue of the remote host.
        Waits for the command to resolve and returns the resulting value.

        Args:
            cmd (str): The command string to send to the remote host. e.g. "1+1"
        Returns:
            DataType: The result of the command execution from the remote host.
        """
        async with self._abort_on_interrupt():
            return await self._send_with_reply(
                Header(Command.CMD_WITH_RETURN), data=cmd
            )

    async def remote_func_no_return(self, func: str, *args) -> None:
        """
        Calls a function on the remote host with the provided arguments.
        Does not wait for the function to resolve or return a value.

        Args:
            func (str): The name of the function to call on the remote host.
            *args: The arguments to pass to the function. These will all be converted to strings before sending.
        """
        func_string = build_remote_function_string(func, *args)
        await self._send(Header(Command.FUNC), data=func_string)

    async def remote_func(self, func: str, *args) -> DataType:
        """
        Calls a function on the remote host with the provided arguments.
        Waits for the command to resolve and returns the resulting value.

        Args:
            func (str): The name of the function to call on the remote host.
            *args: The arguments to pass to the function. These will all be converted to strings before sending.
        Returns:
            DataType: The result of the function execution from the remote host.
        """
        func_string = build_remote_function_string(func, *args)
        async with self._abort_on_interrupt():
            return await self._send_with_reply(
                Header(Command.FUNC_WITH_RETURN), data=func_string
            )

    async def hello(self, *, timeout: float = 5.0):
        """
        Sends a HELLO command to the remote host.
        The remote host should respond with a HELLO_REPLY message.

        Waits for the reply up to the specified timeout.

        Args:
            timeout (float, optional): The maximum time to wait for a reply, in seconds.
        Returns:
            DataType: The message received from the server in response to the HELLO command.
        """
        return await asyncio.wait_for(
            self._send_with_reply(Header(Command.HELLO)),
            timeout=timeout,
        )
