import ctypes
import pytest
import struct
import numpy as np
from pyspec._connection.protocol import (
    Header,
    Command,
    Type,
    serialize,
    _read_one_message,
    NATIVE_ENDIANNESS,
)
from pyspec._connection.data import AssociativeArray, ErrorStr
import asyncio
import itertools


async def read_one_message(
    msg: bytes,
):
    stream = asyncio.StreamReader()
    stream.feed_data(msg)
    stream.feed_eof()
    return await _read_one_message(stream)


@pytest.mark.asyncio
async def test_string_serialization():
    header = Header(Command.CMD, 0, "here is a name or something!")
    data = "some data"

    header_struct, data_bytes = serialize(header, data)

    read_header, read_data, endianness = await read_one_message(
        bytes(header_struct) + data_bytes
    )

    assert read_header.command == header.command
    assert read_header.name == header.name
    assert read_data == data
    assert endianness == NATIVE_ENDIANNESS


@pytest.mark.asyncio
async def test_associative_array_serialization():
    aa = AssociativeArray()
    aa["one"] = "now"
    aa["three"] = "the"
    aa["three", "0"] = "time"
    aa["two"] = "is"
    aa["four"] = "fourth"
    aa["four", "sub"] = "fourth"

    header = Header(Command.CMD, 0, "assoc array test")
    header_struct, data_bytes = serialize(header, aa)

    read_header, read_data, _ = await read_one_message(
        bytes(header_struct) + data_bytes
    )

    assert read_header.command == header.command
    assert read_header.name == header.name
    assert isinstance(read_data, AssociativeArray)
    assert read_data["one"] == "now"
    assert read_data["two"] == "is"
    assert read_data["three"] == "the"
    assert read_data["three", "0"] == "time"


Endianness = [
    "<",
    ">",
]

DTypes = [
    np.uint8,
    np.int8,
    np.uint16,
    np.int16,
    np.uint32,
    np.int32,
    np.float32,
    np.float64,
]


@pytest.mark.parametrize(
    "endianness, dtype",
    itertools.product(Endianness, DTypes),
)
@pytest.mark.asyncio
async def test_numpy_array_serialization(endianness, dtype):
    array = np.array([[1, 2, 3], [4, 5, 6]], dtype=dtype)
    header = Header(Command.CHAN_SEND, 1, f"numpy array test {dtype}")
    header_struct, data_bytes = serialize(header, array, endianness=endianness)

    assert header_struct.data_type == Type.from_numpy_type(array.dtype).value
    read_header, read_data, read_endianness = await read_one_message(
        bytes(header_struct) + data_bytes
    )

    assert read_header == header
    assert read_endianness == endianness
    assert isinstance(read_data, np.ndarray)
    np.testing.assert_array_equal(read_data, array)


@pytest.mark.asyncio
async def test_error_string_serialization():
    error_message = ErrorStr("This is an error.")

    header = Header(Command.CMD, 0, "error string test")
    header_struct, data_bytes = serialize(header, error_message)

    read_header, read_data, _ = await read_one_message(
        bytes(header_struct) + data_bytes
    )

    assert read_header == header
    assert isinstance(read_data, ErrorStr)
    assert read_data == error_message


@pytest.mark.asyncio
async def test_empty_data_serialization():
    header = Header(Command.CMD, 0, "empty data test")
    data = None

    header_struct, data_bytes = serialize(header, data)

    read_header, read_data, _ = await read_one_message(
        bytes(header_struct) + data_bytes
    )

    assert read_header == header
    # For empty data, we expect an empty string
    assert read_data == ""


@pytest.mark.asyncio
async def test_float_data_serialization():
    float_data = 3.14159

    header = Header(Command.CMD, 0, "float data test")
    header_struct, data_bytes = serialize(header, float_data)

    read_header, read_data, _ = await read_one_message(
        bytes(header_struct) + data_bytes
    )

    assert read_header == header
    assert isinstance(read_data, float)
    assert read_data == float_data


@pytest.mark.asyncio
async def test_int_data_serialization():
    int_data = 42

    header = Header(Command.REPLY, 0, "int data test")
    header_struct, data_bytes = serialize(header, int_data)

    read_header, read_data, _ = await read_one_message(
        bytes(header_struct) + data_bytes
    )

    assert read_header == header
    assert isinstance(read_data, int)
    assert read_data == int_data
