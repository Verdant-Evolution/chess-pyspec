from __future__ import annotations

import asyncio
import ctypes
import logging
from dataclasses import dataclass
from typing import TypeVar, overload

from pyee.asyncio import AsyncIOEventEmitter
from typing_extensions import Self

from .header import DataType, Header, HeaderPrefix, HeaderV2, HeaderV3, HeaderV4

LOGGER = logging.getLogger("pyspec.connection")


T = TypeVar("T", bound=ctypes.Structure)


class Connection(AsyncIOEventEmitter):
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
            self.emit("message", Connection.Message(header, data))

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
