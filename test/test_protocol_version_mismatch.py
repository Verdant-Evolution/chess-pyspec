import ctypes
import pytest
import asyncio
from pyspec._connection.protocol import (
    HeaderV2_LE,
    HeaderV3_LE,
    HeaderV4_LE,
    SPEC_MAGIC,
    Command,
    Type,
    NAME_LEN,
    _read_one_message,
)


async def parse_header_and_data(header_bytes, data_bytes):
    stream = asyncio.StreamReader()
    stream.feed_data(header_bytes)
    stream.feed_data(data_bytes)
    stream.feed_eof()
    return await _read_one_message(stream)


@pytest.mark.asyncio
async def test_parse_old_headers():
    data2 = "abcd"
    data_bytes2 = data2.encode("utf-8") + b"\x00"
    h2 = HeaderV2_LE(
        magic=SPEC_MAGIC,
        version=2,
        size=ctypes.sizeof(HeaderV2_LE),
        length=len(data_bytes2),
        name="v2old".encode("utf-8").ljust(NAME_LEN, b"\x00"),
        data_type=Type.STRING.value,
        command=Command.CMD.value,
    )
    header2, data2_out, _ = await parse_header_and_data(bytes(h2), data_bytes2)
    assert header2.name == "v2old"
    assert data2_out == data2

    data3 = "12345j"
    data_bytes3 = data3.encode("utf-8") + b"\x00"
    h3 = HeaderV3_LE(
        magic=SPEC_MAGIC,
        version=3,
        size=ctypes.sizeof(HeaderV3_LE),
        length=len(data_bytes3),
        name="v3old".encode("utf-8").ljust(NAME_LEN, b"\x00"),
        data_type=Type.STRING.value,
        command=Command.CMD.value,
    )
    header3, data3_out, _ = await parse_header_and_data(bytes(h3), data_bytes3)
    assert header3.name == "v3old"
    assert data3_out == data3


@pytest.mark.asyncio
async def test_parse_newer_header_with_extra_fields():

    # V6 = V4 + extra fields (simulate by padding)
    class HeaderV6_LE(ctypes.LittleEndianStructure):
        _fields_ = tuple(HeaderV4_LE._fields_) + (
            ("extra1", ctypes.c_uint),
            ("extra2", ctypes.c_uint),
        )

    data6 = "abcdef"
    data_bytes = data6.encode("utf-8") + b"\x00"
    h6 = HeaderV6_LE(
        magic=SPEC_MAGIC,
        version=6,
        size=ctypes.sizeof(HeaderV6_LE),
        length=len(data_bytes),
        name="v6new".encode("utf-8").ljust(NAME_LEN, b"\x00"),
        data_type=Type.STRING.value,
        command=Command.CMD.value,
    )
    header_bytes6 = bytes(h6)
    header6, data6_out, _ = await parse_header_and_data(header_bytes6, data_bytes)
    assert header6.name == "v6new"
    assert data6_out == data6
