from __future__ import annotations

from enum import Enum
from typing import Iterable, Literal, TypeVar, Union

import numpy as np


class ErrorStr(str): ...


DataType = Union[np.ndarray, str, float, "AssociativeArray", ErrorStr, None]


class Type(Enum):
    DOUBLE = 1
    STRING = 2
    ERROR = 3
    ASSOC = 4
    ARR_DOUBLE = 5
    ARR_FLOAT = 6
    ARR_LONG = 7
    ARR_ULONG = 8
    ARR_SHORT = 9
    ARR_USHORT = 10
    ARR_CHAR = 11
    ARR_UCHAR = 12
    ARR_STRING = 13
    ARR_LONG64 = 14
    ARR_ULONG64 = 15

    def is_array_type(self) -> bool:
        return self in {
            Type.ARR_DOUBLE,
            Type.ARR_FLOAT,
            Type.ARR_LONG,
            Type.ARR_ULONG,
            Type.ARR_SHORT,
            Type.ARR_USHORT,
            Type.ARR_CHAR,
            Type.ARR_UCHAR,
            Type.ARR_LONG64,
            Type.ARR_ULONG64,
            Type.ARR_STRING,
        }

    def to_numpy_type(self) -> np.dtype:
        if self in ARRAY_TYPE_TO_NUMERIC_DTYPE:
            return ARRAY_TYPE_TO_NUMERIC_DTYPE[self]
        else:
            raise ValueError(f"Type {self} is not an array type.")

    @staticmethod
    def from_numpy_type(dtype: np.dtype) -> "Type":
        if dtype.kind == "U":  # String type
            return Type.ARR_STRING
        if dtype.kind == "S":
            raise ValueError(
                "Byte string arrays are not supported. Ensure your strings are UTF-8 encoded."
            )
        key = (dtype_str(dtype), dtype.itemsize)
        if key in NUMERIC_DTYPE_TO_TYPE:
            return NUMERIC_DTYPE_TO_TYPE[key]
        raise ValueError(f"Unsupported numpy dtype: {dtype}")


DtypeStr = Literal["float", "int", "uint"]


def is_signed_int(dtype: np.dtype) -> bool:
    return np.issubdtype(dtype, np.signedinteger)


def is_floating_point(dtype: np.dtype) -> bool:
    return np.issubdtype(dtype, np.floating)


def dtype_str(dtype: np.dtype) -> DtypeStr:
    if is_floating_point(dtype):
        return "float"
    elif is_signed_int(dtype):
        return "int"
    elif np.issubdtype(dtype, np.unsignedinteger):
        return "uint"
    else:
        raise ValueError(f"Unsupported dtype: {dtype}")


NUMERIC_DTYPE_TO_TYPE: dict[tuple[DtypeStr, int], Type] = {
    ("int", 1): Type.ARR_CHAR,
    ("uint", 1): Type.ARR_UCHAR,
    ("int", 2): Type.ARR_SHORT,
    ("uint", 2): Type.ARR_USHORT,
    ("int", 4): Type.ARR_LONG,
    ("uint", 4): Type.ARR_ULONG,
    ("float", 4): Type.ARR_FLOAT,
    ("int", 8): Type.ARR_LONG64,
    ("uint", 8): Type.ARR_ULONG64,
    ("float", 8): Type.ARR_DOUBLE,
}
ARRAY_TYPE_TO_NUMERIC_DTYPE: dict[Type, np.dtype] = {
    Type.ARR_FLOAT: np.dtype(np.float32),
    Type.ARR_DOUBLE: np.dtype(np.float64),
    Type.ARR_CHAR: np.dtype(np.int8),
    Type.ARR_UCHAR: np.dtype(np.uint8),
    Type.ARR_SHORT: np.dtype(np.int16),
    Type.ARR_USHORT: np.dtype(np.uint16),
    Type.ARR_LONG: np.dtype(np.int32),
    Type.ARR_ULONG: np.dtype(np.uint32),
    Type.ARR_LONG64: np.dtype(np.int64),
    Type.ARR_ULONG64: np.dtype(np.uint64),
}


AssociativeArrayElement = Union[float, int, str]
AssociativeArrayKey = Union[
    AssociativeArrayElement, tuple[AssociativeArrayElement, AssociativeArrayElement]
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
    This class represents a SPEC associative array, which is a collection of key-value pairs.

    See https://certif.com/spec_manual/ref_2_3_4_1.html for more details on how spec handles them.

    Ultimately, the associative array is a mapping from one or two keys to a value.
    Example usage:
        ```python
        x = AssociativeArray()
        x["one"] = "now"
        x["three"] = "the"
        x["three","0"] = "time"
        x["two"] = "is"
        ```
    """

    KEY_SEPARATOR = "\x1c"
    ITEM_SEPARATOR = "\000"

    data: dict[str, AssociativeArrayElement]

    def __init__(self) -> None:
        self.data = {}

    def __getitem__(
        self,
        key: AssociativeArrayKey,
    ) -> AssociativeArrayElement:
        return self.data[self.compose_key(key)]

    def __setitem__(
        self,
        key: AssociativeArrayKey,
        value: AssociativeArrayElement,
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
        else:
            key1 = key
            key2 = ""
        return f"{key1}{cls.KEY_SEPARATOR}{key2}"

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
    def deserialize(cls, data: bytes) -> "AssociativeArray":
        instance = cls()
        data_str = data.decode("utf-8")
        for key, value in by_two(data_str.split(cls.ITEM_SEPARATOR)):
            instance.data[key] = try_cast(value)
        return instance
