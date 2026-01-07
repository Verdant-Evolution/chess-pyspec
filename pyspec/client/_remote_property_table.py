from __future__ import annotations

import asyncio
import inspect
import logging
from collections import defaultdict
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Generic,
    Literal,
    TypeVar,
    cast,
)

from pyee.asyncio import AsyncIOEventEmitter
from typing_extensions import Self

from pyspec._connection import ClientConnection
from pyspec._connection.data import DataType

T = TypeVar("T", bound=DataType)
K = TypeVar("K", bound=DataType)
LOGGER = logging.getLogger(__name__)


class ContextWaiter:
    """
    This class allows for awaiting an awaitable either via

        async with ContextWaiter(...):
            ...

    or via

        await ContextWaiter(...)
    """

    def __init__(self, awaitable: Awaitable):
        self._awaitable = awaitable

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._awaitable

    def __await__(self):
        async def enter_exit():
            async with self:
                pass

        return enter_exit().__await__()


class RemotePropertyTable(AsyncIOEventEmitter):
    """
    Class to manage remote properties on a SPEC server.
    Allows reading, writing, and subscribing to property changes.

    Attributes:
        _property_watchers (dict[str, int]): A dictionary to track the number of watchers
            for each property.
        _table (dict[str, DataType]): A local cache of property values.
        _connection (ClientConnection): The client connection to the SPEC server.

    Public Methods:
        read(property_name: str) -> DataType: Reads the value of a property.
        read_next(property_name: str) -> DataType: Waits for the next update of a property and returns its value.
        write(property_name: str, value: DataType) -> None: Writes a value to a property on the server.
        subscribe(property_name: str) -> None: Subscribes to updates for a property.
        unsubscribe(property_name: str) -> None: Unsubscribes from a property.
        property(name: str, coerce: Callable[[Any], T] | None = None) -> RemotePropertyTable.Property[T]: Gets a helper object to manage interfacing with a read-write property.
        readonly_property(name: str, coerce: Callable[[Any], T] | None = None) -> RemotePropertyTable.ReadableProperty[T]: Gets a helper object to manage interfacing with a read-only property.
        writeonly_property(name: str) -> RemotePropertyTable.WritableProperty: Gets a helper object to manage interfacing with a write-only property.
        is_subscribed(property_name: str) -> bool: Checks if there are any active subscriptions to a property.
    """

    def __init__(self, connection: ClientConnection):
        super().__init__()
        self._property_watchers: dict[str, int] = defaultdict(int)
        self._table: dict[str, DataType] = {}
        self._connection = connection
        self._connection.on("property-change", self._on_property_update)

    def _on_property_update(self, property_name: str, value: DataType) -> None:
        self._table[property_name] = value
        LOGGER.info("Dispatching property update for '%s'", property_name)
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

    async def read(self, property_name: str) -> DataType:
        """
        Read the value of a property from the local cache or from the server.
        If the property is not in the local cache, it will be fetched from the server.

        The result is only cached if it has been subscribed to.

        Args:
            property_name (str): The name of the property to read.
        Returns:
            DataType: The value of the property.
        """
        if self.is_subscribed(property_name):
            # This only happens when we are subscribed to the property
            # but there hasn't been a change since we subscribed.
            if property_name not in self._table:
                self._table[property_name] = await self._connection.prop_get(
                    property_name
                )
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
        assert self.is_subscribed(
            property_name
        ), "Property must be watched to read next value."

        future = asyncio.Future()
        self.once(f"property-{property_name}", lambda value: future.set_result(value))
        return await future

    async def write(self, property_name: str, value: DataType) -> None:
        """
        Writes a value to a property on the server.

        Args:
            property_name (str): The name of the property to write to.
            value (DataType): The value to write to the property.

        """
        await self._connection.prop_set(property_name, value)

    async def subscribe(self, property_name: str) -> None:
        """
        Subscribe to updates for a property.

        Subscribing to a property will cause the property values to be
        cached locally and the provided callback to be called
        whenever the property value changes.

        Args:
            property_name (str): The name of the property to subscribe to.
            callback (Callable[[K], None] | None): Optional callback to call on updates.
        """
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
        self,
        name: str,
        coerce: Callable[[Any], T] | None = None,
    ) -> Property[T]:
        """
        Gets a helper object to manage interfacing with a read-write property.
        """
        return Property(name, self, coerce)

    def readonly_property(
        self,
        name: str,
        coerce: Callable[[Any], T] | None = None,
    ) -> ReadableProperty[T]:
        """
        Gets a helper object to manage interfacing with a read-only property.
        """
        return ReadableProperty(name, self, coerce)

    def writeonly_property(self, name: str) -> WritableProperty:
        """
        Gets a helper object to manage interfacing with a write-only property.
        """
        return WritableProperty(name, self)

    def is_subscribed(self, property_name: str) -> bool:
        """
        Checks if there are any active subscriptions to a property.

        Args:
            property_name (str): The name of the property to check.
        Returns:
            bool: True if there are active subscriptions, False otherwise.
        """
        return (
            property_name in self._property_watchers
            and self._property_watchers[property_name] > 0
        )


class _PropertyBase(Generic[T]):
    def __init__(
        self,
        name: str,
        property_table: "RemotePropertyTable",
    ):
        super().__init__()
        self.name = name
        self._property_table = property_table


class EventStream(_PropertyBase[T]):
    """
    Represents a stream of events for a property. Events are sent from the server whenever the property value changes or when the server wants to send data to clients.
    Clients can subscribe to these events using the on() method, and can also await the next event using the get_next() method or wait for a specific value using the wait_for() method.
    Clients can also check if there are active subscriptions to the property using the is_subscribed() method.
    """

    EventType = Literal["change", "event"]

    def __init__(
        self,
        name: str,
        property_table: "RemotePropertyTable",
        coerce: Callable[[DataType], T] | None = None,
    ):
        super().__init__(name, property_table)
        self._emitter = AsyncIOEventEmitter()
        self._coerce = coerce

    def _cast_value(self, value: DataType) -> T:
        if self._coerce is not None:
            try:
                return self._coerce(value)
            except Exception as e:
                raise TypeError(
                    f"Failed to coerce value '{value}' to type {self._coerce}"
                ) from e
        return cast(T, value)

    def _emit_change(self, value: T) -> None:
        try:
            value = self._cast_value(value)
            self._emitter.emit("change", value)
        except TypeError:
            LOGGER.error(
                "Received value of incorrect type for property '%s': expected %s, got %s",
                self.name,
                type(value),
            )
            return

    def _emit_event(self, value: T) -> None:
        self._emitter.emit("event", value)

    def on(self, event: EventType, func: Callable[[T], None]) -> None:
        self._emitter.on(event, func)

    def once(self, event: EventType, func: Callable[[T], None]) -> None:
        self._emitter.once(event, func)

    def remove_listener(self, event: EventType, func: Callable[[T], None]) -> None:
        self._emitter.remove_listener(event, func)

    async def get_next(self) -> T:
        value = await self._property_table.read_next(self.name)
        return self._cast_value(value)

    def wait_for(self, value: T, timeout: float | None = None) -> ContextWaiter:
        """
        Waits until the property changes to the specified value.

        Args:
            value (T): The value to wait for.
            timeout (float | None): Optional timeout in seconds.
        """
        assert self.is_subscribed(), "Property must be watched to wait for a value."
        future = asyncio.Future()

        def check_value(new_value: T) -> None:
            if new_value == value and not future.done():
                future.set_result(None)

        def on_done(*args, **kwargs) -> None:
            self.remove_listener("change", check_value)

        future.add_done_callback(on_done)

        self.on("change", check_value)
        return ContextWaiter(asyncio.wait_for(future, timeout))

    def is_subscribed(self) -> bool:
        """
        Checks if there are any active subscriptions to this property.

        Returns:
            bool: True if there are active subscriptions, False otherwise.
        """
        return self._property_table.is_subscribed(self.name)

    @asynccontextmanager
    async def subscribed(
        self,
    ) -> AsyncIterator[Self]:

        event_name = f"property-{self.name}"
        initialized = False

        def skip_first_emit_change(value: T) -> None:
            # This shenanigans is necessary to preserve change semantics.
            # The initial value of the property is sent back immediately upon subscribing as an "event".
            # We don't want to call that a "change" at this level, so we don't emit that.
            # The initialized value is of course still available from read() at any time.
            nonlocal initialized
            if initialized:
                self._emit_change(value)
            initialized = True

        try:
            self._property_table.on(event_name, skip_first_emit_change)
            self._property_table.on(event_name, self._emit_event)
            await self._property_table.subscribe(self.name)
            yield self
        finally:
            self._property_table.remove_listener(event_name, skip_first_emit_change)
            self._property_table.remove_listener(event_name, self._emit_event)
            await self._property_table.unsubscribe(self.name)

    @asynccontextmanager
    async def capture(self, wait_time: float = 0.0):
        """
        Context manager that captures output from the server for the duration of the context.

        Example usage:
            async with client.output("tty").capture() as output:
                await client.exec('print("Hello, world!")')
                assert output[-1] == "Hello, world!\n"

        Args:
            wait_time (float): Optional time to wait after the context block exits to ensure all output is captured.
        """
        lines = []
        self.on("event", lines.append)
        try:
            async with self.subscribed():
                yield lines
                # Wait for any remaining output to be captured before unsubscribing.
                await asyncio.sleep(wait_time)
        finally:
            self.remove_listener("event", lines.append)


class ReadableProperty(EventStream[T]):
    async def get(self) -> T:
        value = await self._property_table.read(self.name)
        return self._cast_value(value)


class WritableProperty(_PropertyBase[T]):
    async def set(self, value: T) -> None:
        await self._property_table.write(self.name, value)


class Property(ReadableProperty[T], WritableProperty[T]): ...


class PropertyGroup:

    _stack = AsyncExitStack()

    def __init__(self, prefix: str | Path, remote_property_table: RemotePropertyTable):
        self._prefix = Path(prefix)
        self._remote_property_table = remote_property_table

    def _path(self, name: str) -> str:
        return (self._prefix / name).as_posix()

    def _property(
        self,
        name: str,
        coerce: Callable[[Any], T] | None = None,
    ) -> Property[T]:
        return self._remote_property_table.property(self._path(name), coerce)

    def _event_stream(
        self,
        name: str,
        coerce: Callable[[Any], T] | None = None,
    ) -> EventStream[T]:
        return self._remote_property_table.readonly_property(self._path(name), coerce)

    def _readonly_property(
        self,
        name: str,
        coerce: Callable[[Any], T] | None = None,
    ) -> ReadableProperty[T]:
        return self._remote_property_table.readonly_property(self._path(name), coerce)

    def _writeonly_property(
        self,
        name: str,
    ) -> WritableProperty:
        return self._remote_property_table.writeonly_property(self._path(name))

    async def __aenter__(self) -> Self:
        await self._stack.__aenter__()
        # Attempt to subscribe to all at the same time.
        await asyncio.gather(
            *[
                self._stack.enter_async_context(prop.subscribed())
                for _, prop in inspect.getmembers(self)
                # Only subscribe to ReadableProperty instances
                if isinstance(prop, ReadableProperty)
            ]
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self._stack.__aexit__(exc_type, exc, tb)
        self._stack = AsyncExitStack()
