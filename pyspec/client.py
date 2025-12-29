from __future__ import annotations

import asyncio
from typing import Generic, TypeVar

from pyee.asyncio import AsyncIOEventEmitter

from pyspec._connection.data_types import DataType
from pyspec._memory_table import RemotePropertyTable

from ._connection import ClientConnection

T = TypeVar("T", bound=DataType)


# class _Motor:

#     def __init__(
#         self,
#         name: str,
#         connection: ClientConnection,
#         property_table: RemotePropertyTable,
#     ):
#         self.name = name
#         self._connection = connection

#         self.position = property_table.property(
#             self._get_property_name("position"), float
#         )

#     def _get_property_name(self, prop: str) -> str:
#         return f"/motor/{self.name}/{prop}"


class Client(AsyncIOEventEmitter):
    def __init__(self, host: str, port: int):
        self._connection = ClientConnection(host, port)
        self._remote_property_table = RemotePropertyTable(self._connection)

    async def __aenter__(self):
        await self._connection.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc, tb):
        await self._connection.__aexit__(exc_type, exc, tb)

    def property(
        self, name: str, dtype: type[T] | type[object] = object
    ) -> RemotePropertyTable.Property[T]:
        return self._remote_property_table.property(name, dtype)

    # async def motor(self, name: str) -> _Motor:
    #     return _Motor(name, self._connection, self._remote_property_table)
