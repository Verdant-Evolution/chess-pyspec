import ctypes
import pytest
import struct
import numpy as np
from pyspec._connection.message import (
    HeaderV2,
    HeaderV3,
    HeaderV4,
    Command,
    Type,
    NAME_LEN,
)
from pyspec._connection.data_types import AssociativeArray, DataType, ErrorStr

# Helper to create a header and serialize/deserialize data


def test_header_v2_serialization():
    header = HeaderV2(cmd=Command.CMD, name="test", sequence_number=1)

    data = 3.14159
    data_bytes = header.prep_self_and_serialize_data(data)
    assert header.type == Type.DOUBLE
    assert header.len == len(data_bytes)

    header_bytes = bytes(header)
    assert len(header_bytes) == header.size

    # Now deserialize
    header = HeaderV2.from_buffer_copy(header_bytes)
    value = header.deserialize_data(data_bytes)
    assert pytest.approx(value, 1e-6) == data
    assert header.name == "test"
    assert header.cmd == Command.CMD
    assert header.sequence_number == 1
    assert header.rows == 0
    assert header.cols == 0
    assert header.len == struct.calcsize("d")
    assert header.type == Type.DOUBLE


def test_header_v3_serialization():
    header = HeaderV3(cmd=Command.CMD, name="test", sequence_number=1)

    data = 3.14159
    data_bytes = header.prep_self_and_serialize_data(data)
    assert header.type == Type.DOUBLE
    assert header.len == len(data_bytes)

    header_bytes = bytes(header)
    assert len(header_bytes) == header.size

    # Now deserialize
    header = HeaderV3.from_buffer_copy(header_bytes)
    value = header.deserialize_data(data_bytes)
    assert pytest.approx(value, 1e-6) == data
    assert header.name == "test"
    assert header.cmd == Command.CMD
    assert header.sequence_number == 1
    assert header.rows == 0
    assert header.cols == 0
    assert header.len == struct.calcsize("d")
    assert header.type == Type.DOUBLE


def test_header_v4_serialization():
    header = HeaderV4(cmd=Command.CMD, name="test", sequence_number=1)

    data = 3.14159
    data_bytes = header.prep_self_and_serialize_data(data)
    assert header.type == Type.DOUBLE
    assert header.len == len(data_bytes)

    header_bytes = bytes(header)
    assert len(header_bytes) == header.size

    # Now deserialize
    header = HeaderV4.from_buffer_copy(header_bytes)
    value = header.deserialize_data(data_bytes)
    assert pytest.approx(value, 1e-6) == data
    assert header.name == "test"
    assert header.cmd == Command.CMD
    assert header.sequence_number == 1
    assert header.rows == 0
    assert header.cols == 0
    assert header.len == struct.calcsize("d")
    assert header.type == Type.DOUBLE


def test_header_v3_string_serialization():
    header = HeaderV3(cmd=Command.CMD, name="strtest")
    data = "hello world"
    data_bytes = header.prep_self_and_serialize_data(data)
    assert header.type == Type.STRING
    value = header.deserialize_data(data_bytes)
    assert value == data


def test_header_v4_array_serialization():
    arr = np.array([[1, 2], [3, 4]], dtype=np.int32)
    header = HeaderV4(cmd=Command.CMD, name="arrtest")
    data_bytes = header.prep_self_and_serialize_data(arr)
    assert header.type == Type.ARR_LONG
    assert header.rows == 2
    assert header.cols == 2
    arr2 = header.deserialize_data(data_bytes)
    assert isinstance(arr2, np.ndarray)
    assert np.array_equal(arr, arr2)


def test_associative_array_serialization():
    aa = AssociativeArray()
    aa.data = {}
    aa["key1"] = "value1"
    aa["key2"] = "value2"
    aa["key2", "sub"] = 42
    b = aa.serialize()
    aa2 = AssociativeArray.deserialize(b)
    assert aa2.data["key1\x1c"] == "value1"
    assert aa2.data["key2\x1c"] == "value2"
    assert aa2.data["key2\x1csub"] == 42


def test_header_v2_error_type_serialization():
    header = HeaderV2(cmd=Command.CMD, name="none")
    data = ErrorStr("An error occurred")
    data_bytes = header.prep_self_and_serialize_data(data)
    assert header.type == Type.ERROR
    value = header.deserialize_data(data_bytes)
    assert value == data


def test_header_v2_array_1d_serialization():
    arr = np.array([1.5, 2.5, 3.5], dtype=np.float64)
    header = HeaderV2(cmd=Command.CMD, name="array1d")
    data_bytes = header.prep_self_and_serialize_data(arr)
    assert header.type == Type.ARR_DOUBLE
    arr2 = header.deserialize_data(data_bytes)
    assert isinstance(arr2, np.ndarray)
    assert np.array_equal(arr, arr2)


def test_header_v2_string_array():
    arr = np.array([["alpha", "beta", "gamma"], ["delta", "epsilon", "zeta"]])
    header = HeaderV2(Command.CMD)
    data_bytes = header.prep_self_and_serialize_data(arr)
    assert header.name == ""
    assert header.rows == 2
    assert header.cols == 3
    assert header.type == Type.ARR_STRING
    value = header.deserialize_data(data_bytes)
    assert isinstance(value, np.ndarray)
    assert np.array_equal(value, arr)


def test_header_v2_array_unsupported_ndim():
    arr = np.zeros((2, 2, 2), dtype=np.float32)
    header = HeaderV2(cmd=Command.CMD, name="badarray")
    with pytest.raises(ValueError):
        header.prep_self_and_serialize_data(arr)


def test_header_v2_unsupported_type():
    header = HeaderV2(cmd=Command.CMD, name="unsupported")

    class Dummy:
        pass

    dummy = Dummy()
    with pytest.raises(ValueError):
        header.prep_self_and_serialize_data(dummy)  # type: ignore


def test_header_v2_deserialize_wrong_type():
    header = HeaderV2(cmd=Command.CMD, name="wrongtype")
    header.type = Type.STRING
    with pytest.raises(UnicodeDecodeError):
        # Pass invalid bytes for string
        header.deserialize_data(b"\xff\xff\xff")


def test_header_name_length():
    header = HeaderV2(cmd=Command.CMD, name="a" * NAME_LEN)
    assert header.name == "a" * NAME_LEN
    with pytest.raises(ValueError):
        HeaderV2(cmd=Command.CMD, name="b" * (NAME_LEN + 1))


def test_number_serialization():
    header = HeaderV4(cmd=Command.CMD, name="number")
    numbers = [42, 3.14, -7, 0.001]
    for number in numbers:
        data_bytes = header.prep_self_and_serialize_data(number)
        if isinstance(number, int):
            assert header.type == Type.STRING
        else:
            assert header.type == Type.DOUBLE
        value = header.deserialize_data(data_bytes)
        assert value == number
