import ctypes
import struct
import time
from typing import Generic, Literal, TypeVar, Union

import numpy as np

from .command import Command
from .data_types import AssociativeArray, DataType, ErrorStr, Type, try_cast

T = TypeVar("T", bound=Literal[2, 3, 4])

NAME_LEN = 80
SPEC_MAGIC = 4277009102


class HeaderPrefix(ctypes.Structure):
    _fields_ = [
        ("magic", ctypes.c_uint),
        ("vers", ctypes.c_uint),
        ("size", ctypes.c_uint),
    ]
    magic: int
    vers: int
    size: int


def encode_numpy_string_array(arr: np.ndarray) -> bytes:
    """
    Encode a numpy array of strings into bytes, with each string NULL-terminated.
    Numpy stores them as fixed-length, but SPEC expects NULL-terminated strings.
    """
    byte_strings = [str(s).encode("utf-8") + b"\x00" for s in arr.flat]
    return b"".join(byte_strings)


def decode_to_numpy_string_array(data_bytes: bytes) -> np.ndarray:
    """
    Decode bytes into a numpy array of strings, splitting on NULL bytes.
    Needs special handling since strings are not fixed-length.
    """
    strings = [string.decode("utf-8") for string in data_bytes.split(b"\x00") if string]
    max_length = max(map(len, strings))
    array = np.array(strings, dtype=f"|U{max_length}")
    return array


class _HeaderBase(ctypes.Structure, Generic[T]):
    magic: Literal[4277009102]
    vers: T
    size: int
    sequence_number: int
    sec: int
    usec: int
    _cmd: int
    _type: int
    rows: int
    cols: int
    len: int
    _name: bytes

    def __init__(
        self,
        vers: T,
        size: int,
        cmd: Command,
        name: str = "",
        sequence_number: int = 0,
    ) -> None:
        super().__init__()
        self.magic = SPEC_MAGIC
        self.vers = vers
        self.size = size

        now = time.time()
        sec = int(now)
        usec = int((now - sec) * 1_000_000)
        self.sec = sec
        self.usec = usec
        self.cmd = cmd
        self.name = name
        self.rows = 0
        self.cols = 0
        self.len = 0
        self.sequence_number = sequence_number
        self.type = Type.STRING  # Default type

    @property
    def name(self) -> str:
        return self._name.decode("utf-8").rstrip("\x00")

    @name.setter
    def name(self, value: str) -> None:
        if len(value) > NAME_LEN:
            raise ValueError(f"Name too long (max {NAME_LEN} characters)")
        self._name = value.encode("utf-8").ljust(NAME_LEN, b"\x00")

    @property
    def cmd(self) -> Command:
        return Command(self._cmd)

    @cmd.setter
    def cmd(self, value: Command) -> None:
        self._cmd = value.value

    @property
    def type(self) -> Type:
        return Type(self._type)

    @type.setter
    def type(self, value: Type) -> None:
        self._type = value.value

    def prep_self_and_serialize_data(self, data: DataType) -> bytes:
        """
        Serialize the given data.
        Sets the type, rows, and cols attributes accordingly.
        """
        # TODO: Need to check if data is supposed to end in a NULL byte or not.
        data_bytes = b""
        if isinstance(data, ErrorStr):
            _type = Type.ERROR
            data_bytes = data.encode("utf-8")
        elif isinstance(data, float):
            _type = Type.DOUBLE
            # We choose to always serialize floats as DOUBLEs.
            data_bytes = struct.pack("<d", data)
        elif isinstance(data, (str, int)):
            _type = Type.STRING
            # The spec server sends both string-valued and number-valued items as strings.
            # Numbers are converted to strings using a printf("%.15g") format.
            if isinstance(data, int):
                data = f"{data:.15g}"
            data_bytes = struct.pack("<{}s".format(len(data)), data.encode("utf-8"))
        elif isinstance(data, AssociativeArray):
            _type = Type.ASSOC
            data_bytes = data.serialize()
        elif isinstance(data, np.ndarray):
            _type = Type.from_numpy_type(data.dtype)
            if data.ndim > 2:
                raise ValueError("Only 1D and 2D arrays are supported.")
            data = np.atleast_2d(data)
            self.rows, self.cols = data.shape
            if _type == Type.ARR_STRING:
                data_bytes = encode_numpy_string_array(data)
            else:
                data_bytes = data.tobytes()
        elif data is None:
            _type = Type.STRING  # Default to STRING type for None
            data_bytes = b""
        else:
            raise ValueError(f"Cannot serialize data of type {type(data)}.")

        self.type = _type
        self.len = len(data_bytes)
        return data_bytes

    def deserialize_data(self, data_bytes: bytes) -> DataType:
        """
        Deserialize the given bytes into data.
        Uses the type, rows, and cols attributes to determine how to deserialize.

        Raises:
            ValueError: If the type is unsupported for deserialization.
            UnicodeDecodeError: If the bytes cannot be decoded as UTF-8 for string types.
        """
        # TODO: Need to check if data is supposed to end in a NULL byte or not.
        _type = self.type
        if _type == Type.DOUBLE:
            return struct.unpack("<d", data_bytes)[0]
        elif _type == Type.STRING:
            data_string = data_bytes.decode("utf-8")
            # Try to cast to numeric is possible.
            # https://certif.com/spec_help/server.html
            # The spec server sends both string-valued and number-valued items as strings.
            # Numbers are converted to strings using a printf("%.15g") format.
            # However, spec will accept Type.DOUBLE values.
            value = try_cast(data_string)
            return value
        elif _type == Type.ASSOC:
            return AssociativeArray.deserialize(data_bytes)
        elif _type == Type.ERROR:
            return ErrorStr(data_bytes.decode("utf-8"))
        elif _type == Type.ARR_STRING:
            array = decode_to_numpy_string_array(data_bytes).reshape(
                (self.rows, self.cols)
            )
            if self.rows == 1:
                array = array.flatten()
            return array
        elif _type.is_array_type():
            if _type == Type.ARR_STRING:
                array = decode_to_numpy_string_array(data_bytes)
            else:
                array = np.frombuffer(data_bytes, dtype=_type.to_numpy_type())

            array = array.reshape((self.rows, self.cols))
            # TODO: Need to test this with SPEC.
            # I am not sure whether SPEC would send a 0 or 1 for the other dimension of a 1D array.
            # Based on the old pyspec impl, it looks like vectors are always row vectors.
            # So if we have rows == 1, we flatten to 1D.
            if self.rows == 1:
                array = array.flatten()
            return array

        raise ValueError(f"Cannot deserialize data with Type {_type}")

    def __repr__(self) -> str:
        return (
            f"<HeaderV2 cmd={self.cmd} type={self.type} name='{self.name}' "
            f"seq={self.sequence_number} rows={self.rows} cols={self.cols} len={self.len}>"
        )

    __str__ = __repr__


class HeaderV2(_HeaderBase[Literal[2]]):
    _fields_ = [
        ("magic", ctypes.c_uint),
        ("vers", ctypes.c_uint),
        ("size", ctypes.c_uint),
        ("sequence_number", ctypes.c_uint),
        ("sec", ctypes.c_uint),
        ("usec", ctypes.c_uint),
        ("_cmd", ctypes.c_int),
        ("_type", ctypes.c_int),
        ("rows", ctypes.c_uint),
        ("cols", ctypes.c_uint),
        ("len", ctypes.c_uint),
        ("_name", ctypes.c_char * NAME_LEN),
    ]

    def __init__(
        self,
        cmd: Command,
        name: str = "",
        sequence_number: int = 0,
    ) -> None:
        super().__init__(2, ctypes.sizeof(HeaderV2), cmd, name, sequence_number)


class HeaderV3(_HeaderBase[Literal[3]]):
    _fields_ = [
        ("magic", ctypes.c_uint),
        ("vers", ctypes.c_uint),
        ("size", ctypes.c_uint),
        ("sequence_number", ctypes.c_uint),
        ("sec", ctypes.c_uint),
        ("usec", ctypes.c_uint),
        ("_cmd", ctypes.c_int),
        ("_type", ctypes.c_int),
        ("rows", ctypes.c_uint),
        ("cols", ctypes.c_uint),
        ("len", ctypes.c_uint),
        ("err", ctypes.c_int),
        ("_name", ctypes.c_char * NAME_LEN),
    ]

    def __init__(
        self,
        cmd: Command,
        name: str = "",
        sequence_number: int = 0,
    ) -> None:
        super().__init__(3, ctypes.sizeof(HeaderV3), cmd, name, sequence_number)


class HeaderV4(_HeaderBase[Literal[4]]):
    _fields_ = [
        ("magic", ctypes.c_uint),
        ("vers", ctypes.c_uint),
        ("size", ctypes.c_uint),
        ("sequence_number", ctypes.c_uint),
        ("sec", ctypes.c_uint),
        ("usec", ctypes.c_uint),
        ("_cmd", ctypes.c_int),
        ("_type", ctypes.c_int),
        ("rows", ctypes.c_uint),
        ("cols", ctypes.c_uint),
        ("len", ctypes.c_uint),
        ("err", ctypes.c_int),
        ("flags", ctypes.c_int),
        ("_name", ctypes.c_char * NAME_LEN),
    ]

    def __init__(
        self,
        cmd: Command,
        name: str = "",
        sequence_number: int = 0,
    ) -> None:
        super().__init__(4, ctypes.sizeof(HeaderV4), cmd, name, sequence_number)


HeaderVersion = Literal[2, 3, 4]
Header = Union[HeaderV2, HeaderV3, HeaderV4]
