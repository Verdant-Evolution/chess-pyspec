import logging
from typing import Any, Callable, Generic, Literal, Type, TypeVar, Union

from pyee.asyncio import AsyncIOEventEmitter

from pyspec._connection.data import DataType

LOGGER = logging.getLogger(__name__)


T = TypeVar("T", bound=DataType)


class PropertyEventEmitter(Generic[T], AsyncIOEventEmitter):
    """
    This class extends AsyncIOEventEmitter to provide type-safe event emission and handling for property change events.
    """

    def emit(self, event: str, *args: Any, **kwargs: Any) -> None:  # type: ignore
        # type: (Literal["update"], T) -> None # type: ignore
        super().emit(event, *args, **kwargs)

    def on(self, event: Literal["update"], func: Callable[[T], Any]) -> Any:  # type: ignore
        super().on(event, func)


class Property(PropertyEventEmitter[T]):
    """
    Defines a property that can be remotely accessed by clients.

    Args:
        name (str): The name of the property.
        initial_value (T): The initial value of the property.
        dtype (type[T] | type[object], optional): The expected data type of the property. Defaults to object (no validation).
    """

    def __init__(
        self,
        name: str,
        initial_value: T,
        dtype: Union[Type[T], Type[object]] = object,
    ):
        super().__init__()
        self.name = name
        self._value: T = initial_value
        self._dtype = dtype

    def get(self) -> T:
        """
        Get the current value of the property.

        Returns:
            T: The current value of the property.
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
        self.emit("update", value)
        LOGGER.debug(
            f"Property '{self.name}' updated to {value} and 'update' event emitted."
        )


def variable_property_name(name: str) -> str:
    """
    Build the canonical server property path for a SPEC variable.

    Leading and trailing slashes are stripped so inputs like "NAME/",
    "/var/NAME/", and "var/NAME" all normalize to "var/NAME".
    """
    normalized_name = name.strip("/")
    if normalized_name.startswith("var/"):
        return normalized_name
    return f"var/{normalized_name}"


class Variable(Property[T]):
    """
    Defines a remotely accessible SPEC variable property.

    Args:
        name (str): The variable name. It will be exposed as var/{name}.
            Accepts: "var/NAME", "/var/NAME", or "NAME" (all will be treated as var/NAME).
        initial_value (T): The initial value of the variable.
        dtype (type[T] | type[object], optional): The expected data type of the variable.
    """

    def __init__(
        self,
        name: str,
        initial_value: T,
        dtype: Union[Type[T], Type[object]] = object,
    ):

        full_name = variable_property_name(name)
        self.variable_name = full_name[len("var/") :]
        super().__init__(full_name, initial_value, dtype)
