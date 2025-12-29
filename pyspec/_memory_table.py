from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Callable, Generic, Literal, TypeVar, cast

from pyee.asyncio import AsyncIOEventEmitter

from pyspec._connection.data_types import DataType

from ._connection import ClientConnection

T = TypeVar("T", bound=DataType)
K = TypeVar("K", bound=DataType)


class PropertyEventEmitter(Generic[T], AsyncIOEventEmitter):
    def emit(self, event: Literal["change"], value: T) -> None:  # type: ignore[override]
        super().emit(event, value)

    def on(self, event: Literal["change"], func: Callable[[T], None]) -> None:  # type: ignore[override]
        super().on(event, func)


class RemotePropertyTable(AsyncIOEventEmitter):
    """
    Class to manage remote properties on a SPEC server.
    Allows reading, writing, and subscribing to property changes.

    Attributes:
        _property_watchers (dict[str, int]): A dictionary to track the number of watchers
            for each property.
        _table (dict[str, DataType]): A local cache of property values.
        _connection (ClientConnection): The client connection to the SPEC server.

    Nested Classes:
        _PropertyBase(Generic[T], PropertyEventEmitter[T]):
            Base class for properties, providing common functionality for getting values
            and emitting change events.
        ReadonlyProperty(_PropertyBase[T]):
            A read-only property that allows getting values and subscribing to changes.
        Property(_PropertyBase[T]):
            A read-write property that allows getting and setting values, as well as
            subscribing to changes.
    """

    class _PropertyBase(PropertyEventEmitter[T]):
        def __init__(
            self,
            name: str,
            property_table: "RemotePropertyTable",
            dtype: type[T] | type[object] = object,
        ):
            self.name = name
            self._property_table = property_table
            self._dtype = dtype

        def _emit_change(self, value: T) -> None:
            if not isinstance(value, self._dtype):
                raise TypeError(
                    f"Expected data of type {self._dtype}, got {type(value)}"
                )
            self.emit("change", value)

        async def get(self) -> T:
            return await self._property_table.read_as(self.name, self._dtype)

        async def get_next(self) -> T:
            return await self._property_table.read_next_as(self.name, self._dtype)

        async def __aenter__(self):
            await self._property_table.subscribe(self.name, self._emit_change)
            return self

        async def __aexit__(self, exc_type, exc, tb):
            await self._property_table.unsubscribe(self.name)

    class ReadonlyProperty(_PropertyBase[T]): ...

    class Property(_PropertyBase[T]):
        async def set(self, value: T) -> None:
            await self._property_table.write(self.name, value)

    def __init__(self, connection: ClientConnection):
        self._property_watchers: dict[str, int] = defaultdict(int)
        self._table: dict[str, DataType] = {}
        self._connection = connection
        self._connection.on("property-change", self._on_property_update)

    def _on_property_update(self, property_name: str, value: DataType) -> None:
        self._table[property_name] = value
        self.emit(f"property-{property_name}", value)

    def _increment_watcher(self, property_name: str) -> bool:
        self._property_watchers[property_name] += 1
        return self._property_watchers[property_name] == 1

    def _decrement_watcher(self, property_name: str) -> bool:
        if property_name in self._property_watchers:
            self._property_watchers[property_name] -= 1
            if self._property_watchers[property_name] <= 0:
                del self._property_watchers[property_name]
                return True
        return False

    async def read(self, property_name: str):
        """
        Read the value of a property from the local cache or from the server.
        If the property is not in the local cache, it will be fetched from the server.
        The cache is only updated from property change notifications. The result of this function
        call is not cached for future calls.

        Args:
            property_name (str): The name of the property to read.
        Returns:
            DataType: The value of the property.

        """
        if property_name in self._table:
            return self._table[property_name]
        return await self._connection.prop_get(property_name)

    async def read_next(self, property_name: str) -> DataType:
        """
        Wait for the next update of a property and return its value.
        See read() for more details.

        Args:
            property_name (str): The name of the property to read.
        Returns:
            DataType: The next value of the property.
        """
        future = asyncio.Future()
        self.once(f"property-{property_name}", lambda value: future.set_result(value))
        return await future

    async def read_as(
        self, property_name: str, dtype: type[T] | type[object] = object
    ) -> T:
        """
        Reads the value of a property and ensures it is of the specified type.
        See read() for more details.

        Args:
            property_name (str): The name of the property to read.
            dtype (type[T] | type[object]): The expected type of the property value.
        Returns:
            T: The value of the property cast to the specified type.
        """
        data = await self.read(property_name)
        if not isinstance(data, dtype):
            raise TypeError(f"Expected data of type {dtype}, got {type(data)}")
        return cast(T, data)

    async def read_next_as(
        self, property_name: str, dtype: type[T] | type[object] = object
    ) -> T:
        """
        Reads the next value of a property and ensures it is of the specified type.
        See read_next() for more details.

        Args:
            property_name (str): The name of the property to read.
            dtype (type[T] | type[object]): The expected type of the property value.
        Returns:
            T: The next value of the property cast to the specified type.
        """
        future = asyncio.Future()
        self.once(f"property-{property_name}", lambda value: future.set_result(value))
        data = await future
        if not isinstance(data, dtype):
            raise TypeError(f"Expected data of type {dtype}, got {type(data)}")
        return cast(T, data)

    async def write(self, property_name: str, value: DataType) -> None:
        """
        Writes a value to a property on the server.

        Args:
            property_name (str): The name of the property to write to.
            value (DataType): The value to write to the property.

        """
        await self._connection.prop_set(property_name, value)

    async def subscribe(
        self, property_name: str, callback: Callable[[K], None] | None = None
    ) -> None:
        """
        Subscribe to updates for a property.

        Subscribing to a property will cause the property values to be
        cached locally and the provided callback to be called
        whenever the property value changes.

        Args:
            property_name (str): The name of the property to subscribe to.
            callback (Callable[[K], None] | None): Optional callback to call on updates.
        """
        if callback is not None:
            self.on(f"property-{property_name}", callback)
        if self._increment_watcher(property_name):
            await self._connection.prop_watch(property_name)

    async def unsubscribe(self, property_name: str) -> None:
        """
        Unsubscribes from a property.

        Args:
            property_name (str): The name of the property to unsubscribe from.
        """
        if self._decrement_watcher(property_name):
            await self._connection.prop_unwatch(property_name)

    def property(
        self, name: str, dtype: type[T] | type[object] = object
    ) -> RemotePropertyTable.Property[T]:
        """
        Gets a helper object to manage interfacing with a read-write property.
        """
        return RemotePropertyTable.Property(name, self, dtype)

    def readonly_property(
        self, name: str, dtype: type[T] | type[object] = object
    ) -> RemotePropertyTable.ReadonlyProperty[T]:
        """
        Gets a helper object to manage interfacing with a read-only property.
        """
        return RemotePropertyTable.ReadonlyProperty(name, self, dtype)
