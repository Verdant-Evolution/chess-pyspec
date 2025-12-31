"""
This module implements the SPEC protocol for communication between
a client and server. It includes functionality for serializing and
deserializing messages, handling different protocol versions, and
managing endianness.

Most of the complexity arises from implementing compatibility with clients of
arbitrary endianness.

References:
- SPEC Server Help: https://certif.com/spec_help/server.html
- Associative Arrays: https://certif.com/spec_manual/ref_2_3_4_1.html

Notes:
The SPEC server protocol's has permissive endianness handling:
    "The spec server will check the endianess of the magic element of the first packet sent by the
    client and swap header and data bytes in that packet and subsequent incoming and outgoing data,
    if necessary, to accommodate the client. The client can send and read packet headers (and binary array data)
    using the native endian format of the client's platform."

So we have to be able to handle both big-endian and little-endian messages.
Endianness only affects multi-byte data types, which includes all numeric types.
Strings and string arrays are unaffected, since they are encoded in UTF-8, which is a single
byte encoding.



Classes:
- Header: Represents a message header.

Methods:
- serialize: Serializes a Header and DataType into bytes for sending.
- message_stream: Converts a StreamReader into an async generator of (Header, DataType) tuples.
- short_str: Constructs a short string representation of the header and data.
- long_str: Constructs a long string representation of the header and data.
"""

import asyncio
import ctypes
import logging
import struct
import time
from dataclasses import dataclass
from typing import Literal, TypeVar, Union

import numpy as np

from .command import Command
from .data import (
    NATIVE_ENDIANNESS,
    AssociativeArray,
    DataType,
    ErrorStr,
    Type,
    try_cast,
    with_endianness,
)

LOGGER = logging.getLogger("pyspec.protocol")

NAME_LEN = 80
SPEC_MAGIC = 4277009102


@dataclass
class Header:
    command: Command
    sequence_number: int = 0
    name: str = ""


def _encode_numpy_string_array(arr: np.ndarray) -> bytes:
    """
    Encode a numpy array of strings into bytes, with each string NULL-terminated.
    Numpy stores them as fixed-length, but SPEC expects NULL-terminated strings.
    """
    byte_strings = [str(s).encode("utf-8") + b"\x00" for s in arr.flat]
    return b"".join(byte_strings)


def _decode_to_numpy_string_array(data_bytes: bytes) -> np.ndarray:
    """
    Decode bytes into a numpy array of strings, splitting on NULL bytes.
    Needs special handling since strings are not fixed-length.
    """
    strings = [string.decode("utf-8") for string in data_bytes.split(b"\x00") if string]
    max_length = max(map(len, strings))
    array = np.array(strings, dtype=f"|U{max_length}")
    return array


FIELDS_V2 = [
    ("magic", ctypes.c_uint),
    ("version", ctypes.c_int),
    ("size", ctypes.c_int),
    ("sequence_number", ctypes.c_int),
    ("sec", ctypes.c_uint),
    ("usec", ctypes.c_uint),
    ("command", ctypes.c_int),
    ("data_type", ctypes.c_int),
    ("rows", ctypes.c_uint),
    ("cols", ctypes.c_uint),
    ("len", ctypes.c_uint),
    ("name", ctypes.c_char * NAME_LEN),
]


class HeaderV2_BE(ctypes.BigEndianStructure):
    _fields_ = FIELDS_V2


class HeaderV2_LE(ctypes.LittleEndianStructure):
    _fields_ = FIELDS_V2


FIELDS_V3 = [
    ("magic", ctypes.c_uint),
    ("version", ctypes.c_int),
    ("size", ctypes.c_int),
    ("sequence_number", ctypes.c_int),
    ("sec", ctypes.c_uint),
    ("usec", ctypes.c_uint),
    ("command", ctypes.c_int),
    ("data_type", ctypes.c_int),
    ("rows", ctypes.c_uint),
    ("cols", ctypes.c_uint),
    ("len", ctypes.c_uint),
    ("err", ctypes.c_int),
    ("name", ctypes.c_char * NAME_LEN),
]


class HeaderV3_BE(ctypes.BigEndianStructure):
    _fields_ = FIELDS_V3


class HeaderV3_LE(ctypes.LittleEndianStructure):
    _fields_ = FIELDS_V3


FIELDS_V4 = [
    ("magic", ctypes.c_uint),
    ("version", ctypes.c_int),
    ("size", ctypes.c_uint),  # Warning. Changed to unsigned in V4.
    ("sequence_number", ctypes.c_uint),
    ("sec", ctypes.c_uint),
    ("usec", ctypes.c_uint),
    ("command", ctypes.c_int),
    ("data_type", ctypes.c_int),
    ("rows", ctypes.c_uint),
    ("cols", ctypes.c_uint),
    ("len", ctypes.c_uint),
    ("err", ctypes.c_int),
    ("flags", ctypes.c_int),
    ("name", ctypes.c_char * NAME_LEN),
]


class HeaderV4_BE(ctypes.BigEndianStructure):
    _fields_ = FIELDS_V4


class HeaderV4_LE(ctypes.LittleEndianStructure):
    _fields_ = FIELDS_V4


HeaderStruct = Union[
    HeaderV2_BE,
    HeaderV2_LE,
    HeaderV3_BE,
    HeaderV3_LE,
    HeaderV4_BE,
    HeaderV4_LE,
]

S = TypeVar("S", bound=ctypes.Structure)


HEADER_STRUCT_MAP = {
    (2, "<"): HeaderV2_LE,
    (2, ">"): HeaderV2_BE,
    (3, "<"): HeaderV3_LE,
    (3, ">"): HeaderV3_BE,
    (4, "<"): HeaderV4_LE,
    (4, ">"): HeaderV4_BE,
}
LE_HEADERS = (HeaderV4_LE, HeaderV3_LE, HeaderV2_LE)
BE_HEADERS = (HeaderV4_BE, HeaderV3_BE, HeaderV2_BE)


def _determine_header_struct(
    version: int,
    header_size: int,
    endianness: Literal["<", ">"] = "<",
) -> type[HeaderStruct]:
    """
    Attempts to determine the appropriate Header
    structure based on version number, header size, and apparent endianness.
    """

    header_struct = HEADER_STRUCT_MAP.get((version, endianness), None)
    if header_struct is not None:
        return header_struct

    # If we don't have a known version, then just try to pick the target based on size.
    # We can't safely deserialize a header if it requires more bytes than we have.
    header_options = LE_HEADERS if endianness == "<" else BE_HEADERS
    for header_struct in header_options:
        if ctypes.sizeof(header_struct) <= header_size:
            return header_struct

    if header_struct is None:
        raise RuntimeError(
            f"Could not safely deserialize header with size {header_size} and version {version}; size too small."
        )
    return header_struct


def _deserialize_data(
    header: HeaderStruct,
    data_bytes: bytes,
    endianness: Literal["<", ">"] = NATIVE_ENDIANNESS,
) -> DataType:
    """
    Deserialize the given bytes into data.
    Uses the type, rows, and cols attributes to determine how to deserialize.

    Raises:
        ValueError: If the type is unsupported for deserialization.
        UnicodeDecodeError: If the bytes cannot be decoded as UTF-8 for string types.
    """
    # TODO: Need to check if data is supposed to end in a NULL byte or not.
    data_type = Type(header.data_type)
    if data_type == Type.DOUBLE:
        return struct.unpack(f"{endianness}d", data_bytes)[0]
    elif data_type == Type.STRING:
        data_string = data_bytes.decode("utf-8")
        # Try to cast to numeric is possible.
        # https://certif.com/spec_help/server.html
        # The spec server sends both string-valued and number-valued items as strings.
        # Numbers are converted to strings using a printf("%.15g") format.
        # However, spec will accept Type.DOUBLE values.
        value = try_cast(data_string)
        return value
    elif data_type == Type.ASSOC:
        return AssociativeArray.deserialize(data_bytes)
    elif data_type == Type.ERROR:
        return ErrorStr(data_bytes.decode("utf-8"))
    elif data_type == Type.ARR_STRING:
        array = _decode_to_numpy_string_array(data_bytes).reshape(
            (header.rows, header.cols)
        )
        if header.rows == 1:
            array = array.flatten()
        return array
    elif data_type.is_array_type():
        if data_type == Type.ARR_STRING:
            array = _decode_to_numpy_string_array(data_bytes)
        else:
            array = np.frombuffer(data_bytes, dtype=data_type.to_numpy_type(endianness))

        array = array.reshape((header.rows, header.cols))
        # TODO: Need to test this with SPEC.
        # I am not sure whether SPEC would send a 0 or 1 for the other dimension of a 1D array.
        # Based on the old pyspec impl, it looks like vectors are always row vectors.
        # So if we have rows == 1, we flatten to 1D.
        if header.rows == 1:
            array = array.flatten()
        return array


async def _read_prefix(
    stream: asyncio.StreamReader,
):
    """
    Reads the header prefix from the stream.

    Args:
        stream (asyncio.StreamReader): The stream to read from.

    Returns:
        HeaderPrefix: The read header prefix.
    """
    magic_bytes = await stream.readexactly(4)
    (magic_le,) = struct.unpack("<I", magic_bytes)
    (magic_be,) = struct.unpack(">I", magic_bytes)
    if magic_le == SPEC_MAGIC:
        endianness = "<"
    elif magic_be == SPEC_MAGIC:
        endianness = ">"
    else:
        raise RuntimeError(
            f"Invalid magic number: {magic_le} (LE) / {magic_be} (BE); expected {SPEC_MAGIC}."
        )

    version_bytes = await stream.readexactly(4)
    (version,) = struct.unpack(f"{endianness}I", version_bytes)

    # Warning. We parse the size field as an unsigned int here, since in V4 it was changed to unsigned.
    # However, older versions of SPEC used a signed int.
    # Unless the size of the header is larger than 2GB, this should not cause issues.
    size_bytes = await stream.readexactly(4)
    (size,) = struct.unpack(f"{endianness}I", size_bytes)

    return magic_bytes + version_bytes + size_bytes, version, size, endianness


async def _read_one_message(
    stream: asyncio.StreamReader,
    logger: logging.Logger = LOGGER,
) -> tuple[Header, DataType, Literal["<", ">"]]:
    """
    Attempts to read a single message (header + data) from the stream.

    Args:
        stream (asyncio.StreamReader): The stream to read from.
        endianness: The current endianness setting, or None to use native endianness.
        logger (logging.Logger): Logger for logging messages.

    Returns:
        Tuple[Header, DataType]: The header and deserialized data.

    Raises:
        RuntimeError: If the magic number is invalid.
    """
    prefix_bytes, version, header_size, apparent_endianness = await _read_prefix(stream)

    header_struct = _determine_header_struct(version, header_size, apparent_endianness)

    header = header_struct.from_buffer_copy(
        prefix_bytes
        + await stream.readexactly(ctypes.sizeof(header_struct) - len(prefix_bytes))
    )

    data_bytes = await stream.readexactly(header.len)
    data = _deserialize_data(header, data_bytes, apparent_endianness)

    logger.info("Received: %s", short_str(header, data))
    logger.debug("Detail: %s", long_str(header, data))
    logger.debug("Raw data bytes: %s", data_bytes)

    return (
        Header(
            command=Command(header.command),
            sequence_number=header.sequence_number,
            name=header.name.decode("utf-8").rstrip("\x00"),
        ),
        data,
        apparent_endianness,
    )


async def message_stream(
    stream: asyncio.StreamReader,
    logger: logging.Logger = LOGGER,
):
    """
    Converts a StreamReader into an async generator of (Header, DataType) tuples.

    Args:
        stream (asyncio.StreamReader): The stream to read from.
        endianness: The current endianness setting, or None to use native endianness.
        logger (logging.Logger): Logger for logging messages.
    Yields:
        Tuple[Header, DataType]: The header and deserialized data.
    """
    while True:
        try:
            yield await _read_one_message(stream, logger)
        except asyncio.IncompleteReadError:
            break


def serialize(
    header: Header,
    data: DataType,
    endianness: Literal["<", ">"] | None = NATIVE_ENDIANNESS,
) -> tuple[HeaderStruct, bytes]:
    """
    Serializes a Header and DataType into bytes for sending.

    Args:
        header (Header): The header to serialize.
        data (DataType): The data to serialize.

    Returns:
        bytes: The serialized header bytes.
        bytes: The serialized data bytes.
    """
    if endianness is None:
        endianness = NATIVE_ENDIANNESS

    # TODO: Need to check if data is supposed to end in a NULL byte or not.
    rows, cols = 0, 0
    data_bytes = b""
    if isinstance(data, ErrorStr):
        data_type = Type.ERROR
        data_bytes = data.encode("utf-8")
    elif isinstance(data, float):
        data_type = Type.DOUBLE
        # We choose to always serialize floats as DOUBLEs.
        data_bytes = struct.pack("<d", data)
    elif isinstance(data, (str, int)):
        data_type = Type.STRING
        # The spec server sends both string-valued and number-valued items as strings.
        # Numbers are converted to strings using a printf("%.15g") format.
        if isinstance(data, int):
            data = f"{data:.15g}"
        data_bytes = struct.pack("<{}s".format(len(data)), data.encode("utf-8"))
    elif isinstance(data, AssociativeArray):
        data_type = Type.ASSOC
        data_bytes = data.serialize()
    elif isinstance(data, np.ndarray):
        data_type = Type.from_numpy_type(data.dtype)
        if data.ndim > 2:
            raise ValueError("Only 1D and 2D arrays are supported.")
        data = np.atleast_2d(data)

        rows, cols = data.shape
        if data_type == Type.ARR_STRING:
            data_bytes = _encode_numpy_string_array(data)
        else:
            # Make sure the data is encoded in the right format.
            # This is not relevant for string arrays.
            # String arrays are communicated as a sequence of 1 byte chars (utf-8).
            data_bytes = data.astype(
                with_endianness(data.dtype, endianness), copy=False
            ).tobytes()
    elif data is None:
        data_type = Type.STRING  # Default to STRING type for None
        data_bytes = b""
    else:
        raise ValueError(f"Cannot serialize data of type {type(data)}.")

    # Send as V4 header.
    header_struct = HeaderV4_LE if endianness == "<" else HeaderV4_BE

    return (
        header_struct(
            magic=SPEC_MAGIC,
            version=4,
            size=ctypes.sizeof(header_struct),
            sequence_number=header.sequence_number,
            sec=int(time.time()),
            usec=int((time.time() % 1) * 1_000_000),
            command=header.command.value,
            data_type=data_type.value,
            rows=rows,
            cols=cols,
            len=len(data_bytes),
            err=0,
            flags=0,
            name=header.name.encode("utf-8").ljust(NAME_LEN, b"\x00"),
        ),
        data_bytes,
    )


def short_str(header: HeaderStruct, data: DataType) -> str:
    """
    Construct a short string representation of the header and data.
    Focuses on the command and key parameters.
    Useful for frequent logging compared to `long_str`.

    Args:
        header (HeaderStruct): The header to represent.
        data (DataType): The data to represent.
    """
    cmd = Command(header.command)
    name = header.name.decode("utf-8").rstrip("\x00")
    match cmd:
        case Command.HELLO:
            return f"{cmd.name}(seq={header.sequence_number})"
        case Command.HELLO_REPLY:
            return f"{cmd.name}(seq={header.sequence_number})"
        case Command.CMD | Command.FUNC:
            return f"{cmd.name}(`{data}`)"
        case Command.CMD_WITH_RETURN | Command.FUNC_WITH_RETURN:
            return f"{cmd.name}(`{data}`, seq={header.sequence_number})"
        case Command.CHAN_SEND:
            return f"{cmd.name}(`{name}`, seq={header.sequence_number})"
        case Command.REGISTER | Command.UNREGISTER:
            return f"{cmd.name}(`{name}`)"
        case Command.EVENT:
            return f"{cmd.name}(`{name}`)"
        case Command.REPLY:
            return f"{cmd.name}(seq={header.sequence_number})"
        case Command.CLOSE | Command.ABORT:
            return f"{cmd.name}"
        case Command.RETURN:
            # This is unused in the current version of SPEC.
            # So the semantics are not defined.
            return f"{cmd.name}(seq={header.sequence_number})"
        case _:
            return f"{cmd.name}(seq={header.sequence_number})"


def long_str(header: HeaderStruct, data: DataType) -> str:
    """
    Construct a long string representation of the header and data.
    Contains all of the information in the V2 header.

    Args:
        header (HeaderStruct): The header to represent.
        data (DataType): The data to represent.
    """
    cmd = Command(header.command)
    _type = Type(header.data_type)
    return (
        f"<HeaderV{header.version} magic={header.magic} size={header.size} cmd={cmd.name} "
        f"type={_type.name} name='{header.name}'seq={header.sequence_number} "
        f"rows={header.rows} cols={header.cols} len={header.len} data={data}>"
    )
