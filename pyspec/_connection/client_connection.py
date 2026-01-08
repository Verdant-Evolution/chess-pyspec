

import asyncio
import re
import threading
import weakref
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Literal, overload, Dict, Optional

import numpy as np
from pyee.asyncio import AsyncIOEventEmitter

from pyspec._connection.associative_array import AssociativeArray

from .connection import Connection
from .data import DataType, ErrorStr
from .protocol import Command, Header

LAST_SEQUENCE_NUMBER = 0


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
        self._synchronizing_motors = False
        self._pending_motions: Dict[str, float] = {}

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

        self.once(f"reply-{sequence_number}", response.set_result)
        await self._send(header, data)

        msg_data: DataType = await response
        if isinstance(msg_data, ErrorStr):
            self.logger.error(
                "Received ERROR reply for sequence number %d",
                sequence_number,
            )
            error_message = msg_data if isinstance(msg_data, str) else "Unknown error"
            raise RemoteException(f"Error from server: {error_message}")
        return msg_data

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
        return await self._send_with_reply(Header(Command.CMD_WITH_RETURN), data=cmd)

    async def remote_func_no_return(self, func: str, *args) -> None:
        """
        Calls a function on the remote host with the provided arguments.
        Does not wait for the function to resolve or return a value.

        Args:
            func (str): The name of the function to call on the remote host.
            *args: The arguments to pass to the function. These will all be converted to strings before sending.
        """
        func_string = f"{func}(" + ", ".join(repr(arg) for arg in args) + ")"
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
        func_string = f"{func}(" + ", ".join(repr(arg) for arg in args) + ")"
        return await self._send_with_reply(
            Header(Command.FUNC_WITH_RETURN), data=func_string
        )

    async def hello(self, timeout: float = 5.0):
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

    @asynccontextmanager
    async def synchronized_motors(
        self, timeout: Optional[float] = None
    ):
        """
        Context manager to enable synchronized motor operations for the client.

        While this context is active, motor movements will be held.
        Upon exiting the context, the movements will be initialized simultaneously.

        Example usage:

        .. code-block:: python

            async with client_connection.synchronized_motors():
                # Motor movement will be held in here.
                motor1.move(position)
                motor2.move(position)

                # Motors will not start moving yet.
                await asyncio.sleep(1)  # Simulate other operations
                # Motors will start moving simultaneously here.

            # Outside of the context, all motors have completed their movements.

        Args:
            timeout (float, optional): Maximum time to wait for all motors to complete, in seconds.
        Yields:
            None
        Raises:
            RuntimeError: If there are pending motor motions from a previous context.
        """
        assert (
            not self._synchronizing_motors
        ), "Concurrent synchronized_motors contexts are not allowed."

        move_done_pattern = re.compile(r"motor/(.+)/move_done")

        waiting_for: dict[str, asyncio.Future] = {}

        def motor_move_done_check(name: str, value: DataType) -> None:
            if (match := move_done_pattern.match(name)) is None:
                return
            motor_name = match.group(1)
            # Here we are comparing the value of the move_done property to 0,
            # which is the value it should be set to when a move is completed.
            if motor_name in waiting_for and value == 0:
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
            try:
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
            finally:
                self.remove_listener("property-change", motor_move_done_check)
        except Exception as e:
            self.logger.error("Error during synchronized motor operations: %s", str(e))
            if motion_started:
                await self.prop_set("motor/../abort_all", None)
            raise
        finally:
            self._synchronizing_motors = False
            self._pending_motions.clear()
