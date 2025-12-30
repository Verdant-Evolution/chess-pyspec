from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TypeVar

from pyee.asyncio import AsyncIOEventEmitter

from pyspec._connection.data_types import DataType
from pyspec._motor import Motor
from pyspec._remote_property_table import RemotePropertyTable
from pyspec._status import Status

from ._connection import ClientConnection

T = TypeVar("T", bound=DataType)


class Client(AsyncIOEventEmitter):
    def __init__(self, host: str, port: int):
        self._connection = ClientConnection(host, port)
        self._remote_property_table = RemotePropertyTable(self._connection)

    async def __aenter__(self):
        await self._connection.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._connection.__aexit__(exc_type, exc, tb)

    def _property(
        self, name: str, dtype: type[T] | type[object] = object
    ) -> RemotePropertyTable.Property[T]:
        return self._remote_property_table.property(name, dtype)

    def _readonly_property(
        self, name: str, dtype: type[T] | type[object] = object
    ) -> RemotePropertyTable.ReadableProperty[T]:
        return self._remote_property_table.readonly_property(name, dtype)

    def status(self) -> Status:
        """
        The status properties reflect changes in the server state that may affect the server's ability
        to execute client commands or control hardware.

        Returns:
            Status: The status property group. See the Status class for details.
        """
        return Status(self._remote_property_table)

    def motor(self, motor_name: str) -> Motor:
        """
        The motor properties are used to control the motors.
        The parameters for the commands that are sent from the client and the values in the replies and events that are sent from the server
        are always transmitted as ASCII strings in the data that follows the packet header.

        Args:
            motor_name (str): The name of the motor to control.

        Returns:
            Motor: The motor property group. See the Motor class for details.
        """
        return Motor(motor_name, self._connection, self._remote_property_table)

    def var(
        self, var_name: str, dtype: type[T] | type[object] = object
    ) -> RemotePropertyTable.Property[T]:
        """
        The var properties allow values of any variables to be transferred between the server and the client.
        Enter only the variable name; the property will be created as: var/{var_name}

        var/var_name

            on("change")
                Sent to clients who have registered when the variable var_name changes value.
            get
                Returns the value of the var_name in the data, if var_name is an existing variable on the server.
            set
                Sets the value of var_name on the server to the contents of data.
        All data types (numbers, strings, associative arrays and data arrays) are supported.

        For built-in associative arrays (A[], S[] and possibly G[], Q[], Z[], U[] and UB[], depending on geometry),
        only existing elements can be set.

        Properties can be created for individual elements of associative arrays by using the syntax
            var_name = "array_name[element_key]"

        Args:
            var_name (str): The name of the variable on the server.
            dtype (type[T] | type[object], optional): The data type of the variable. Defaults to object (no validation)

        Returns:
            RemotePropertyTable.Property[T]: The property representing the variable on the server.
        """
        return self._property(f"var/{var_name}", dtype)

    def output(
        self, filename: str, dtype: type[T] | type[object] = object
    ) -> RemotePropertyTable.ReadableProperty[T]:
        """
        The output property puts copies of the strings written to files or to the screen in events sent to clients.

        output/filename

            on("change")
                Sent when the server sends output to the file or device given by filename, where filename can be the built-in name "tty" or a file or device name. The data will be a string representing the output.
            Once a client has registered for output events from a particular file,
            the server will keep track of the client's request as the file is opened and closed.
            File names are given relative to the server's current directory and can be relative or absolute path names,
            just as with the built-in commands that refer to files.

            (The output property was introduced in spec release 5.07.04-1.)
        """
        return self._readonly_property(f"output/{filename}", dtype)

    def count(self) -> RemotePropertyTable.Property[bool]:
        """
        The count property provides a count of the number of commands executed by the server since it was started.

        scaler/.all./count

        on("change")
            Sent when counting starts (data is True) and when counting stops (data is False).
        get
            Data indicates counting (True) or not counting (False).
        set
            If data is nonzero, the server pushes a
                count_em data\n
            onto the command queue.
            If data is False, counting is aborted as if a ^C had been typed at the server.
        """
        return self._property("scaler/.all./count", bool)

    async def call(self, function_name: str, *args: str | float | int) -> DataType:
        """
        Call a remote funciton on the server.
        Args:
            function_name (str): The name of the remote function to call.
            *args (str | float | int): The arguments to pass to the remote function.
        Returns:
            DataType: The result of the remote function call.
        """
        return await self._connection.remote_func(function_name, *args)

    async def exec(self, command: str) -> DataType:
        """
        Execute a command on the server.
        Args:
            command (str): The command to execute.
        Returns:
            DataType: The result of the command execution.
        """
        return await self._connection.remote_cmd(command)

    @asynccontextmanager
    async def synchronized_motors(self):
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
        async with self._connection.synchronized_motors():
            yield
