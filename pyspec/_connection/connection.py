from __future__ import annotations

import asyncio
import ctypes
import logging
from dataclasses import dataclass
from typing import Literal, TypeVar, overload

from pyee.asyncio import AsyncIOEventEmitter
from typing_extensions import Self

from . import protocol
from .protocol import DataType, Header, message_stream

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

        self._peer_endianness: Literal["<", ">"] | None = None
        """
        Keeps track of the endianness of the remote connection.
        Endianness is determined by looking at the magic number in the header of incoming messages.
        If None, endianness has not yet been determined, and messages will be sent with native endianness.

        If set, all messages sent along this connection will use the determined endianness.
        A warning will be logged if the endianness is changed mid-connection.
        """

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
        header_struct, data_bytes = protocol.serialize(
            header, data, self._peer_endianness
        )
        self.logger.info("Sending: %s", protocol.short_str(header_struct, data))
        self.logger.debug("Detail: %s", protocol.long_str(header_struct, data))
        await self.__send(bytes(header_struct))
        if data_bytes:
            await self.__send(data_bytes)

    async def _listen(self):
        """Listens for raw data from the connected server."""
        assert self._reader is not None, "Connection is not established."
        async for header, data, endianness in message_stream(self._reader, self.logger):
            if self._peer_endianness is not None:
                if self._peer_endianness != endianness:
                    self.logger.warning(
                        "Endianness changed mid-connection from %s to %s",
                        self._peer_endianness,
                        endianness,
                    )
            self._peer_endianness = endianness
            self.emit("message", Connection.Message(header, data))
