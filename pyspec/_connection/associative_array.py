from contextlib import contextmanager
from email import contentmanager
from typing import Any, Callable, Literal, Mapping, Union, Iterable, TypeVar, overload, Dict, Tuple, Union, Optional
from pyee.asyncio import AsyncIOEventEmitter
import re

AssociativeArrayElement = Union[float, int, str]
AssociativeArrayKey = Union[
    AssociativeArrayElement, Tuple[AssociativeArrayElement, AssociativeArrayElement]
]


T = TypeVar("T")


def by_two(iterable: Iterable[T]) -> Iterable[tuple[T, T]]:
    """Yield successive pairs from an iterable."""
    a = iter(iterable)
    return zip(a, a)


def try_cast(value: str) -> AssociativeArrayElement:
    try:
        v = float(value)
        if v.is_integer():
            return int(v)
        return v
    except ValueError:
        return value


class AssociativeArray:
    """
    Represents a SPEC associative array, which is a collection of key-value pairs.

    See https://certif.com/spec_manual/ref_2_3_4_1.html for more details on how spec handles them.

    Ultimately, the associative array is a mapping from one or two keys to a value.

    Example usage:
    .. code-block:: python

        x = AssociativeArray()
        x["one"] = "now"
        x["three"] = "the"
        x["three", "0"] = "time"
        x["two"] = "is"

    All keys are stored as strings on spec with decimal numbers being expanded to something similar to ".5g" format.
    """

    KEY_SEPARATOR = "\x1c"
    ITEM_SEPARATOR = "\000"

    data: Dict[str, Optional[AssociativeArrayElement]]

    def __init__(self) -> None:
        super().__init__()
        self.data = {}

    def __getitem__(
        self,
        key: AssociativeArrayKey,
    ) -> AssociativeArrayElement:
        value = self.data.get(self.compose_key(key))
        if value is None:
            raise KeyError(f"Key {key} has been deleted from associative array")
        return value

    def __setitem__(
        self,
        key: AssociativeArrayKey,
        value: Optional[AssociativeArrayElement],
        /,
    ) -> None:
        self.data[self.compose_key(key)] = value

    def __delitem__(
        self,
        key: AssociativeArrayKey,
    ) -> None:
        del self.data[self.compose_key(key)]

    @classmethod
    def compose_key(cls, key: AssociativeArrayKey) -> str:
        if isinstance(key, tuple):
            key1, key2 = key
            if key2 == "":
                return cls.stringify_key(key1)
            return (
                f"{cls.stringify_key(key1)}{cls.KEY_SEPARATOR}{cls.stringify_key(key2)}"
            )
        return cls.stringify_key(key)

    @staticmethod
    def stringify_key(key: Union[float, int, str]) -> str:
        if isinstance(key, (float, int)):
            return f"{key:.5g}"
        return str(key)

    def serialize(self) -> bytes:
        key_value_list = []
        for key, value in self.data.items():
            key_value_list.append(key)
            key_value_list.append(value)

        return (
            self.ITEM_SEPARATOR.join(str(item) for item in key_value_list)
            + self.ITEM_SEPARATOR
        ).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes, deleted: bool = False) -> "AssociativeArray":
        instance = cls()
        data_str = data.decode("utf-8")
        # Not sure why spec is sending an extra separator.
        for key, value in by_two(data_str.split(cls.ITEM_SEPARATOR)[:-1]):
            if deleted:
                instance.data[key] = None
            else:
                instance.data[key] = try_cast(value)
        return instance

    def __str__(self) -> str:
        items = list(self.data.items())
        if len(items) > 5:
            display_items = items[:5]
            display_str = "{" + ", ".join(
                f"{self.to_display_key(key)}: {value}" for key, value in display_items
            )
            display_str += ", ... }"
        else:
            display_str = (
                "{"
                + ", ".join(
                    f"{self.to_display_key(key)}: {value}" for key, value in items
                )
                + "}"
            )
        return display_str

    @staticmethod
    def to_display_key(key: str) -> str:
        if AssociativeArray.KEY_SEPARATOR not in key:
            key1 = key
            key2 = ""
        else:
            key1, key2 = key.split(AssociativeArray.KEY_SEPARATOR)
        return f"[{key1}][{key2}]" if key2 else f"[{key1}]"

    def update(self, other: "AssociativeArray") -> None:
        """
        Update the associative array with another associative array.

        Args:
            other (AssociativeArray): The other associative array to update from.
        """
        self.data.update(other.data)


# This is just:
# (not-brackets)* "[ .? ]" + maybe "[ .? ]"
# ?: is is used to form non-capturing groups for the parts of the regex we don't care about.
KEY_PATTERN = re.compile(r"^[^\[\]]*(?:\[(.*?)\])(?:\[(.*?)\])?$")


def get_associative_array_key(prop_name: str) -> Optional[Tuple[str, str]]:
    """
    Parse the property name to get the keys indexing into an associative array.

    Example:
    .. code-block:: none

        "../x" -> None
        "../x[1]" -> ("1", "")
        "../x[1][2]" -> ("1", "2")


    Args:
        prop_name (str): The property name to parse.
    """

    if not prop_name.endswith("]"):
        return None

    match = KEY_PATTERN.search(prop_name)
    if match is not None:
        groups = match.groups()
        # The groups from parsing are structured like:
        # ("../x", "key1",  "key2" or None)
        return groups[0], groups[1] or ""
    return None


def unpack_associative_array_element(property_name: str, value):
    """
    Given a property name and a value, if the property name indicates that this is an element of an associative array, extract the value of the element from the associative array.

    Example:
    .. code-block:: none

        property_name = "x[1]"
        value = AssociativeArray({("1", ""): "one"})
        returns "one"

        property_name = "x[1][2]"
        value = AssociativeArray({("1", "2"): "one two"})
        returns "one two"

        property_name = "x"
        value = ...
        returns value

    Args:
        property_name (str): The property name to parse for the associative array keys.
        value: The value to extract the element from if the property name indicates this is an element

    Returns:
        The extracted element value if the property name indicates this is an element of an associative array, otherwise the original value.
    """
    if (
        isinstance(value, AssociativeArray)
        and (key := get_associative_array_key(property_name)) is not None
    ):
        return value[key]
    return value


def pack_associative_array_element(property_name: str, value):
    """
    Given a property name and a value, if the property name indicates that this is an element of an associative array, pack the value into an associative array with the appropriate key.

    Example:
    .. code-block:: none

        property_name = "x[1]"
        value = "one"
        returns AssociativeArray({("1", ""): "one"})

        property_name = "x[1][2]"
        value = "one two"
        returns AssociativeArray({("1", "2"): "one two"})
        property_name = "x"
        value = ...
        returns value
    """
    if (key := get_associative_array_key(property_name)) is not None:
        arr = AssociativeArray()
        arr[key] = value
        return arr
    return value
