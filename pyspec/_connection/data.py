from __future__ import annotations

import sys
from enum import Enum
from typing import Literal, Union
from .associative_array import AssociativeArray

import numpy as np

NATIVE_ENDIANNESS = "<" if sys.byteorder == "little" else ">"


class ErrorStr(str): ...


DataType = Union[np.ndarray, str, float, AssociativeArray, ErrorStr, None]


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
        """
        Returns True if the type is an array type.

        Returns:
            bool: True if array type, False otherwise.
        """
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

    def to_numpy_type(
        self, endianness: Literal["<", ">"] = NATIVE_ENDIANNESS
    ) -> np.dtype:
        """
        Returns the numpy dtype corresponding to this SPEC type.

        Args:
            endianness (Literal['<', '>']): Endianness, '<' for little-endian, '>' for big-endian.
        Returns:
            np.dtype: Corresponding numpy dtype.
        Raises:
            ValueError: If the type is not an array type.
        """
        if self in ARRAY_TYPE_TO_NUMERIC_DTYPE:
            return with_endianness(
                ARRAY_TYPE_TO_NUMERIC_DTYPE[self], endianness=endianness
            )
        else:
            raise ValueError(f"Type {self} is not an array type.")

    @staticmethod
    def from_numpy_type(dtype: np.dtype) -> "Type":
        """
        Returns the SPEC Type corresponding to a numpy dtype.

        Args:
            dtype (np.dtype): Numpy dtype to convert.
        Returns:
            Type: Corresponding SPEC Type.
        Raises:
            ValueError: If the dtype is not supported.
        """
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


def with_endianness(dtype: np.dtype, endianness: Literal["<", ">"]) -> np.dtype:
    """
    Returns a numpy dtype with the specified endianness.

    Args:
        dtype (np.dtype): The base numpy dtype.
        endianness (Literal['<', '>']): Endianness, '<' for little-endian, '>' for big-endian.
    Returns:
        np.dtype: Numpy dtype with specified endianness.
    """
    return np.dtype(endianness + dtype.str[1:])


def is_signed_int(dtype: np.dtype) -> bool:
    """
    Returns True if the dtype is a signed integer type.

    Args:
        dtype (np.dtype): Numpy dtype to check.
    Returns:
        bool: True if signed integer, False otherwise.
    """
    return np.issubdtype(dtype, np.signedinteger)


def is_floating_point(dtype: np.dtype) -> bool:
    """
    Returns True if the dtype is a floating point type.

    Args:
        dtype (np.dtype): Numpy dtype to check.
    Returns:
        bool: True if floating point, False otherwise.
    """
    return np.issubdtype(dtype, np.floating)


def dtype_str(dtype: np.dtype) -> DtypeStr:
    """
    Returns a string representing the type of the numpy dtype ('float', 'int', or 'uint').

    Args:
        dtype (np.dtype): Numpy dtype to check.
    Returns:
        DtypeStr: String representing the dtype category.
    Raises:
        ValueError: If the dtype is not supported.
    """
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
