from __future__ import annotations

import logging
from typing import Any, Callable, Generic, Literal, TypeVar

from pyee.asyncio import AsyncIOEventEmitter

from pyspec._connection.data import DataType

LOGGER = logging.getLogger(__name__)


T = TypeVar("T", bound=DataType)


class PropertyEventEmitter(Generic[T], AsyncIOEventEmitter):
    """
    This class extends AsyncIOEventEmitter to provide type-safe event emission and handling for property change events.
    """

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:  # type: ignore
        # type: (Literal["change"], T) -> None # type: ignore
        super().emit(event, *args, **kwargs)

    def on(self, event: Literal["change"], func: Callable[[T], Any]) -> Any:  # type: ignore
        super().on(event, func)


class Property(PropertyEventEmitter[T]):
    """
    Defines a property that can be remotely accessed by clients.

    :param name: The name of the property.
    :param initial_value: The initial value of the property.
    :param dtype: The expected data type of the property. Defaults to object (no validation).
    """

    def __init__(
        self,
        name: str,
        initial_value: T,
        dtype: type[T] | type[object] = object,
    ):
        super().__init__()
        self.name = name
        self._value: T = initial_value
        self._dtype = dtype

    def get(self) -> T:
        """
        Get the current value of the property.

        :returns: The current value of the property.
        """
        return self._value

    def set(self, value: T) -> None:
        """
        Set the value of the property and emit a change event.

        :param value: The new value to set.
        """
        if not isinstance(value, self._dtype):
            raise TypeError(f"Expected data of type {self._dtype}, got {type(value)}")
        self._value = value
        self.emit("change", value)
        LOGGER.debug(
            f"Property '{self.name}' updated to {value} and 'change' event emitted."
        )
