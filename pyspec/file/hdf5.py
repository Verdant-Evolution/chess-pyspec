import h5py
from .css_logger import log
import numpy as np
from typing import TypeVar


import os
import re


DATA_LOCATION = "/entry/data/"

T = TypeVar("T", bound=object)  # TODO: Bind to h5py stuff


def get(object, path: str, expected_type: type[T]) -> T:
    value = object[path]
    if not isinstance(value, expected_type):
        raise ValueError(f"Expected {expected_type} at {path}, got {type(value)}")
    return value


class H5Reader(object):

    def __init__(self, filename):
        self.filename = filename

    def get_nb_images(self):
        with h5py.File(self.filename) as ifd:
            return ifd[DATA_LOCATION].attrs["nb_images"]

    def get_image(self, imgno):
        with h5py.File(self.filename) as ifd:
            nb_images = ifd[DATA_LOCATION].attrs["nb_images"]
            if imgno > 0 and imgno <= nb_images:
                dgroup = get(ifd, DATA_LOCATION, expected_type=h5py.Group)

                for ky in dgroup.keys():
                    d = get(dgroup, ky, expected_type=h5py.Dataset)
                    fimg = d.attrs["image_nr_low"]
                    limg = d.attrs["image_nr_high"]
                    if imgno >= fimg and imgno <= limg:
                        idx = imgno - fimg
                        return d[()][idx]

        return None


class H5Writer(object):
    def __init__(self, filename, images_per_file=5, overwrite=False):
        self.filename = filename
        self.overwrite = overwrite
        self.nr_imgs_per_file = images_per_file

    def create(self):
        if not self.overwrite:
            self.filename = choose_filename(self.filename)

        log.log(2, "Creating file: %s" % self.filename)

        with h5py.File(self.filename, "w") as ofd:
            ofd.create_group(DATA_LOCATION)

    def save_metadata(self, metadata, rootky="/entry"):
        self.metadata = metadata
        with h5py.File(self.filename, "r+") as fd:
            self._save_metadata(fd, metadata, rootky)

    def _save_metadata(self, fd, values, rootky="/entry"):
        for ky, value in values.items():
            h5ky = os.path.join(rootky, ky)

            if isinstance(value, dict):
                try:
                    fd.create_group(h5ky)
                except:
                    pass
                self._save_metadata(fd, value, h5ky)
            else:
                print("looking for %s in %s" % (ky, rootky))
                if ky in fd[rootky].keys():
                    print("%s already exists" % ky)
                    if isinstance(value, str):
                        del fd[h5ky]
                        fd.create_dataset(h5ky, data=value)
                    else:
                        fd[h5ky].write_direct(np.array([value]))
                else:
                    print("%s creating" % ky)
                    if isinstance(value, str):
                        dtype = "S"
                    else:  # valid for single number values and for list/tuple objects
                        value = np.array(value)
                        dtype = value.dtype
                    fd.create_dataset(h5ky, data=value)

    def save_img(self, data):
        dkeys = []

        fileno = 0
        with h5py.File(self.filename, "r+") as ofd:
            data_group = get(ofd, DATA_LOCATION, expected_type=h5py.Group)

            for ky in data_group.keys():
                fileno += 1
                dkeys.append(ky)
                last_imgno = data_group[ky].attrs["image_nr_high"]

            # how many images in last one
            newfile = False
            if dkeys:
                dataky = os.path.join(DATA_LOCATION, dkeys[-1])
                odata = get(ofd, dataky, expected_type=h5py.Dataset)[()]
                nb_images = len(odata)
                if nb_images >= self.nr_imgs_per_file:
                    newfile = True
                    fileno += 1
                imgno = last_imgno + 1
            else:
                newfile = True
                fileno = 1
                imgno = 1

            dataky = "data_%06d" % fileno
            fullky = os.path.join(DATA_LOCATION, dataky)

            if newfile:
                data_filename = self.create_datafile(dataky, data=data)
                ofd[fullky] = h5py.ExternalLink(
                    os.path.basename(data_filename), os.path.join(DATA_LOCATION, "data")
                )
                ofd[fullky].attrs.create("image_nr_low", imgno)
                ofd[fullky].attrs.create("image_nr_high", imgno)
            else:  # append data to latest file
                dset = get(ofd, fullky, expected_type=h5py.Dataset)
                newlen = dset.shape[0] + 1
                newshape = (newlen, dset.shape[1], dset.shape[2])
                dset.resize(newshape)
                dset[newlen - 1] = data
                ofd[fullky].attrs.modify("image_nr_high", imgno)
            ofd[DATA_LOCATION].attrs.modify("nb_images", imgno)

    def create_datafile(self, dataky, data):
        data_filename = self.filename.replace("master", dataky)
        log.log(2, " - creating datafile %s" % data_filename)
        with h5py.File(data_filename, "w") as dfd:
            maxshape = tuple((None,) + data.shape)
            shape = tuple((1,) + data.shape)
            dfd.create_dataset(
                os.path.join(DATA_LOCATION, "data"),
                data=data,
                shape=shape,
                dtype=data.dtype,
                maxshape=maxshape,
            )
        return data_filename


def choose_filename(filename):
    if not os.path.exists(filename):
        return filename

    # search for _master
    mat = re.search(r"(.*?)(([\-\.\_]master)(.*?)$)", filename)
    if mat:
        base = mat.group(1)
        master = mat.group(2)
    else:
        base, master = os.path.splitext(filename)
        master = "." + master

    fileno = 1
    while os.path.exists(filename):
        filename = "%s_%02d%s" % (base, fileno, master)
        fileno += 1

    return filename


def test():
    import time
    import numpy as np

    metadata = {
        "instrument": {
            "chi": 23,
            "phi": 12,
            "th": 100,
            "scanpositions": [7, 2, 3, 4],
        },
        "save_time": time.time(),
        "detector": {
            "exptime": 1.1,
            "threshold": 111,
            "acqmode": "PC",
            "name": "StreakCamera",
        },
    }

    data = np.zeros((100, 100), dtype="f")

    w = H5Writer("/tmp/multi_master.h5")
    w.create()
    w.save_metadata(metadata)
    for i in range(23):
        d = data + i
        w.save_img(d)


if __name__ == "__main__":
    log.start()
    test()
