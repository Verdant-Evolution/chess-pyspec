from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Any, Awaitable, Callable, Literal, overload

from pyee.asyncio import AsyncIOEventEmitter

from .connection import Connection
from .data import DataType, ErrorStr
from .header import Command, HeaderV4


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


class ServerConnection(Connection, ServerConnectionEventEmitter):
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        Connection.__init__(self, reader, writer)
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
