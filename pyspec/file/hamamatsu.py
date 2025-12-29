import struct
import re
import sys
from typing import Optional

from click import group
import numpy as np

re_comment = re.compile(r"(?P<key>\w+)=\"(?P<value>\w+)\"")
re_group = re.compile(r"\[(?P<groupname>.*?)\]")


class ItexImage(object):

    _data: Optional[np.ndarray] = None

    @property
    def data(self) -> np.ndarray:
        if self._data is None:
            raise RuntimeError("No data loaded")
        return self._data

    def __init__(self, filename=None):
        self.head_info = None
        self.comments = {}
        self._data = None

        if filename:
            self.from_file(filename)

    def from_buffer(self, buff):

        _id = struct.unpack("2c", buff[0:2])
        _fst = ""

        for _c in _id:
            _fst += _c.decode("utf-8")

        if _fst != "IM":
            print("not an ITEX data file")
            return

        head_info = struct.unpack("5h", buff[2:12])

        self.width, self.height = head_info[1:3]
        self.xoffset, self.yoffset = head_info[3:5]

        print(self.width, self.height)

        comm_length = head_info[0]
        comm_string = buff[64 : comm_length + 64].decode("utf-8")
        self.parse_comments(comm_string)

        img_size = self.width * self.height * 2
        start_img = comm_length + 64
        end_img = comm_length + 64 + img_size

        data = np.frombuffer(buff[start_img:end_img], dtype=np.uint16)
        self._data = data.reshape(self.height, self.width)
        print(self.data.shape)

        # only if calib present (ScalingXScalingFile in comments)
        try:
            self.calib_data = struct.unpack("672f", buff[end_img:])
        except:
            self.calib_data = None

    def from_file(self, filename):
        buff = open(filename, "rb").read()
        self.from_buffer(buff)

    def get_roisum(self, bx, by, ex, ey):
        pass

    def parse_comments(self, comms):
        curr_group = ""
        cursor = 0
        group_begin = None
        while True:
            mat = re_group.search(comms, cursor)
            if mat:
                if curr_group:
                    group_block = comms[group_begin : mat.start()]
                    print(curr_group)
                    print(group_block)
                curr_group = mat.group("groupname")
                cursor = mat.end()
                group_begin = cursor
            else:
                break

        if group_begin is None:
            raise ValueError("No groups found in comments")

        group_block = comms[group_begin:]
        print(curr_group)
        print(group_block)


def main():
    img = ItexImage(sys.argv[1])
    data = img.data
    print(type(data))
    print(data.shape)
    print(data.mean())


if __name__ == "__main__":
    main()
