#!/usr/bin/env python
# ******************************************************************************
#
#  %W%  %G% CSS
#
#  "pyspec" Release %R%
#
#  Copyright (c) 2013,2014,2015,2016,2017,2018,2019,2020,2021
#  by Certified Scientific Software.
#  All rights reserved.
#
#  Permission is hereby granted, free of charge, to any person obtaining a
#  copy of this software ("pyspec") and associated documentation files (the
#  "Software"), to deal in the Software without restriction, including
#  without limitation the rights to use, copy, modify, merge, publish,
#  distribute, sublicense, and/or sell copies of the Software, and to
#  permit persons to whom the Software is furnished to do so, subject to
#  the following conditions:
#
#  The above copyright notice and this permission notice shall be included
#  in all copies or substantial portions of the Software.
#
#  Neither the name of the copyright holder nor the names of its contributors
#  may be used to endorse or promote products derived from this software
#  without specific prior written permission.
#
#     * The software is provided "as is", without warranty of any   *
#     * kind, express or implied, including but not limited to the  *
#     * warranties of merchantability, fitness for a particular     *
#     * purpose and noninfringement.  In no event shall the authors *
#     * or copyright holders be liable for any claim, damages or    *
#     * other liability, whether in an action of contract, tort     *
#     * or otherwise, arising from, out of or in connection with    *
#     * the software or the use of other dealings in the software.  *
#
# ******************************************************************************

"""

****************
filespec
****************

Description
****************
   This module offers an interface to files with data in the spec
   file format. The format specificiation can be consulted online
   at the certif.com website.

   A spec file normally consists of a series of header blocks and scan blocks.
   Data comes after scan blocks. Sometimes comment lines can be also
   be found in between blocks.
   These comment lines could contain for example the result of user
   calculations after a scan, or pure comments.  For practical purposes comment
   lines will be considered to belong to the preceding scan or header block.

.. _`certif.com`: http://www.certif.com/spec_help/scans.html

"""


import re
import numpy
import os
import time
import string


class FileSpecFormatUnknown(BaseException):
    pass


class FileSpec(list):
    """
    FileSpec class documentation
    """

    def __init__(self, filename):

        list.__init__(self)

        self._filename = filename
        self.origfilename = None
        self._headers = []
        self.lastpos = 0

        self.inheader = False

        self.filestat = os.stat(self._filename)
        self.st_size = 0

        # dictionary to hold references (by scan number) to the scanlist
        self.scans = {}

        self._indexscans()

        if len(self.scans) == 0:
            raise FileSpecFormatUnknown("No scans found in file %s" % self._filename)

    @property
    def abspath(self):
        return self.absolutePath()

    def absolutePath(self):
        return os.path.abspath(self._filename)

    def update(self):

        currstat = os.stat(self._filename)

        if currstat.st_size > self.st_size:
            self.st_size = currstat.st_size
            self._indexscans()
            modified = True
        else:
            modified = False

        return modified

    @property
    def filename(self):
        return self.getFileName()

    def getFileName(self):
        return self._filename

    def getScanByNumber(self, scanno, scanorder=0):
        if scanno in self.scans:
            if scanorder >= 0 and scanorder < len(self.scans[scanno]):
                scan = self.scans[scanno][scanorder]
                return scan
        else:
            return None

    get_scan_by_number = getScanByNumber

    @property
    def time_created(self):
        return self.getTimeCreated()

    def getTimeCreated(self):
        if self._headers:
            return self._headers[0].getDate()

    @property
    def user(self):
        return self.getUser()

    def getUser(self):
        if self._headers:
            return self._headers[0].getUser()

    @property
    def spec(self):
        return self.getSpec()

    def getSpec(self):
        if self._headers:
            return self._headers[0].getSpec()

    @property
    def time_modified(self):
        return self.getTimeModified()

    def getTimeModified(self):
        if not self._filename:
            return None

        mtime = os.stat(self._filename).st_mtime
        return time.asctime(time.localtime(mtime))

    @property
    def length(self):
        return self.getNumberScans()

    def getNumberScans(self):
        return len(self.scans)

    @property
    def headers(self):
        return self.getNumberHeaders()

    def getNumberHeaders(self):
        return len(self._headers)

    @property
    def info(self):
        return self.getInfo()

    def getInfo(self):
        """Returns user and application"""
        ctime = self.getTimeCreated()
        mtime = self.getTimeModified()
        user = self.getUser()
        spec = self.getSpec()
        return [ctime, mtime, user, spec]

    def _indexscans(self):

        self.fd = open(self._filename, "r")

        if len(self) > 0:
            fb = self[-1]
            self.fd.seek(self.lastpos)
        else:
            fb = None

        data = self.fd.read()

        for lineno, sline in enumerate(data.split("\n#")):

            if not sline.strip():
                continue

            if sline[0] in ["S", "F", "E"]:

                btype = sline[0]

                if btype in ["F", "E"]:
                    # block not followed by space is not a block. ignore line
                    if sline[1] != " ":
                        continue

                blockstart = self.lastpos
                blockline = lineno

                if fb is not None:
                    fb.end()

                if btype in ("F", "E"):
                    if btype == "F":
                        self.origfilename = sline[2:].strip()
                    fb = Header(blockstart, blockline)
                    self.inheader = True
                    self._headers.append(fb)
                elif btype == "S":
                    fb = Scan(blockstart, blockline)
                    fb.addSLine(sline[2:])
                    self.inheader = False
                    self.append(fb)
                    fb._setScanIndex(len(self))
                    if len(self._headers):
                        # Assign last added header to current scan
                        fb._setFileHeader(self._headers[-1])

                if self.origfilename:
                    fb.setFileName(self.origfilename)

            if sline and fb:
                fb.addLine(sline)

            self.lastpos = self.fd.tell()

        # register last block
        if fb is not None:
            fb.end()

        # correct the scan order if necessary
        # assign number in file

        self.scans = {}
        scanidx = 0

        for scan in self:
            scanno = scan.getNumber()
            if scanno not in self.scans:
                self.scans[scanno] = []

            self.scans[scanno].append(scan)
            scan._setOrder(len(self.scans[scanno]) - 1)
            scan._setNumberInFile(scanidx)
            scanidx += 1

        self.fd.close()


class FileBlock:

    respecuser = re.compile(r"(?P<spec>.*?)\s+User\s+=\s+(?P<user>.*?)$")

    def __init__(self, start, firstline):

        self.start = start
        self.firstline = firstline
        self.lines = []
        self._filename = None
        self._contains_error = False
        self._error_messages = []
        self._id = ""

        self.funcs = {
            "S": self.addSLine,
            "E": self.addEpochLine,
            "F": self.addFileLine,
            "D": self.addDateLine,
            "N": self.addColumnsLine,
            "L": self.addLabelLine,
            "O": self.addMotorLabelLine,
            "o": self.addMotorMneLine,
            "J": self.addCounterLabelLine,
            "j": self.addCounterMneLine,
            "U": self.addUserLine,
            "C": self.addCommentLine,
            "P": self.addMotorPositionLine,
            "T": self.addTimeLine,
            "G": self.addGeoLine,
            "Q": self.addQLine,
            "@": self.addExtraLine,
        }

        self.resetParsedData()

    def resetParsedData(self):
        # Default
        self.is_parsed = False

        self._data = []
        self._oneds = []

        # self._number = 0
        # self._command = ""

        self._count_time = 0
        self._filename = ""
        self._epoch = 0
        self._date = ""
        self._columns = 0
        self._labels = None
        self._motor_labels = []
        self._motor_mnes = []
        self._counter_labels = []
        self._counter_mnes = []
        self._motor_positions = []
        self._comment_lines = []
        self._user_lines = []
        self._geo_pars = []
        self._qvalue = 0
        self._extra_lines = []
        self._wrong_lines = []
        self._error_messages = []
        self._contains_error = False
        self._find_oned = True
        self.reading_mca = False

    def addLine(self, line):
        self.lines.append(line)

    def end(self):
        pass

    def parse(self):
        lineno = -1
        oned_idx = 0
        data_line = 0
        comp_line = 2  # The mca data is between 2 data counter lines.

        for line in self.lines:
            for sline in line.split("\n"):

                lineno += 1

                if not sline:
                    continue

                first_char = sline[0]

                if first_char in string.ascii_letters + "@":

                    widx = sline.find(" ")

                    metakey = sline[0]
                    metaval = sline[1:widx].strip()
                    content = sline[widx:].strip()

                    if metakey in self.funcs:
                        try:
                            self.funcs[metakey](content.strip(), metaval)
                        except:
                            self.wrongLine(
                                lineno, sline, "unknown line (%s) " % metakey
                            )
                    else:
                        self.wrongLine(
                            lineno, sline, "unknown header line (%s) " % metakey
                        )

                    if sline[0:2] == "@A":
                        if data_line == 1:
                            comp_line = 1  # The mca data is the first line.

                        sline = sline[2:]
                        self.reading_mca = True

                        if self._find_oned:
                            self._oneds.append(OneD())

                        self.tmpmca = McaData()
                        complete = self.tmpmca._addLine(sline)
                        if complete:
                            self._oneds[oned_idx].append(self.tmpmca)
                            self.reading_mca = False
                            oned_idx += 1
                else:
                    data_line += 1
                    if self.reading_mca:
                        complete = self.tmpmca._addLine(sline)
                        if complete:
                            self._oneds[oned_idx].append(self.tmpmca)
                            self.reading_mca = False
                            oned_idx += 1
                    else:
                        oned_idx = 0
                        try:
                            try:
                                dataline = list(map(float, sline.strip().split()))
                            except BaseException:
                                self.wrongLine(lineno, sline, "wrong data line")
                                continue

                            if len(dataline) != self._columns:
                                self.wrongLine(lineno, sline, "wrong number of columns")
                            else:
                                self._data.append(dataline)
                                if len(self._data) == comp_line:
                                    self._find_oned = False
                        except ValueError:
                            self.wrongLine(lineno, sline, "cannot parse line ")

        self.is_parsed = True

        self.finalizeParsing()

    def finalizeParsing(self):
        pass

    def wrongLine(self, lineno, sline, errmsg):
        self._wrong_lines.append([errmsg, sline])
        line = "%s (%s)" % (lineno + 1, self.firstline + lineno + 1)
        ermsg = "erroneous data / %s " % errmsg
        self._error_messages.append([self._id, line, ermsg])
        self._contains_error = True

    def setFileName(self, filename):
        self._filename = filename

    def addSLine(self, content, keyval=None):
        vals = content.split()
        self._number = int(vals[0])
        self._id = self._number
        self._command = " ".join(vals[1:])

    def addFileLine(self, content, keyval=None):
        self._filename = content

    def addEpochLine(self, content, keyval=None):
        self._epoch = int(content)

    def addDateLine(self, content, keyval=None):
        self._date = content

    def addColumnsLine(self, content, keyval=None):
        if not self._columns:
            self._columns = int(content)
        else:
            pass

    def addLabelLine(self, content, keyval=None):
        if self._labels is None:
            self._labels = re.split(r"\s\s+", content)
            if not self._columns:
                # cope with no N line. get nb columns from _labels
                self._columns = len(self._labels)
        else:
            pass

    def addMotorLabelLine(self, content, keyval=None):
        # Beware of double spacing
        self._motor_labels.extend(re.split(r"\s\s+", content))

    def addMotorMneLine(self, content, keyval=None):
        self._motor_mnes.extend(re.split(r"\s", content))

    def addCounterLabelLine(self, content, keyval=None):
        # Beware of double spacing
        self._counter_labels.extend(re.split(r"\s\s+", content))

    def addCounterMneLine(self, content, keyval=None):
        # Beware of double spacing
        self._counter_mnes.extend(re.split(r"\s", content))

    def addMotorPositionLine(self, content, keyval=None):
        self._motor_positions.extend(content.split(" "))

    def addUserLine(self, content, keyval=None):
        self._user_lines.append(content)

    def addCommentLine(self, content, keyval=None):
        self._comment_lines.append(content)

    def addTimeLine(self, content, keyval=None):
        parts = content.split()
        if len(parts) > 1:
            units = re.sub(r"[\)\(]", "", parts[1])
            self._count_time = [parts[0], units]
        else:
            self._count_time = [content, ""]

    def addGeoLine(self, content, keyval=None):
        self._geo_pars.append(content.split())

    def addQLine(self, content, keyval=None):
        self._qvalue = content

    def addExtraLine(self, content, keyval=None):
        self._extra_lines.append([keyval, content])

    @property
    def date(self):
        return self.getDate()

    def getDate(self):
        """
        Returns the date when the scan was started
        """
        if not self.is_parsed:
            self.parse()
        return self._date

    @property
    def user_spec(self):
        return self.getUserSpec()

    def getUserSpec(self):

        comments = self._comment_lines

        if comments:
            for line in comments:
                mat = self.respecuser.search(line)
                if mat:
                    return [mat.group("user"), mat.group("spec")]

        return [None, None]

    @property
    def spec(self):
        return self.getSpec()

    def getSpec(self):
        """
        Returns the name of the spec application
        from which the file was created
        """
        if not self.is_parsed:
            self.parse()

        return self.getUserSpec()[1]

    @property
    def user(self):
        return self.getUser()

    def getUser(self):
        """
        Returns the name of the unix user that created the file
        """
        if not self.is_parsed:
            self.parse()

        return self.getUserSpec()[0]


class Header(FileBlock):
    """
    Class representing a file header.
    """

    def __init__(self, start, firstline):
        FileBlock.__init__(self, start, firstline)

    def end(self):
        self.parse()


class Scan(FileBlock):
    """
    Scan class documentation
    """

    def __init__(self, start, firstline):
        FileBlock.__init__(self, start, firstline)
        self._fileheader = None
        self._numberinfile = -1
        self._order = 1

    def end(self):
        self.resetParsedData()

    def finalizeParsing(self):

        # prepare motor positions
        labels = self.getMotorNames()
        poss = self._motor_positions
        poserr = False
        self.motor_positions_list = None

        if not labels:
            ermsg = "no motor names"
            self._error_messages.append([self._id, "", ermsg])
            self._contains_error = True
            poserr = True

        elif len(labels) != len(poss):
            ermsg = "number of motor labels and positions are different"
            self._error_messages.append([self._id, "", ermsg])
            self._contains_error = True
            poserr = True

        if not poserr:
            self.motor_positions_list = list(zip(labels, poss))

    def _setFileHeader(self, header):
        self._fileheader = header

    def _setScanIndex(self, idx):
        self._index = idx

    def getScanIndex(self):
        """
        Returns the position of the scan in the file
        """
        return self._index

    @property
    def number(self):
        return self.getNumber()

    def getNumber(self):
        """
        Returns scan number as it appeared in spec.
        Remember that it could be that more than one scan
        in the file will have the same number.
        The scan index is the position of the scan in the file.
        The scan number is the number given by spec
        to the scan at the time it was executed.
        """
        return self._number

    @property
    def order(self):
        return self.getOrder()

    def getOrder(self):
        """
        Returns scan order for the scan. The combination
        of scan number/scan order should be unique for a scan.
        in a file.  The first scan with a certain number in
        the file will have order 1.  If another scan in the file
        uses the same number, it will be associated with order 2 and so on.
        """
        return self._order

    def _setNumberInFile(self, number):
        self._numberinfile = number

    def getNumberInFile(self):
        return self._numberinfile

    @property
    def nb_points(self):
        return self.getLines()

    def getLines(self):
        """
        Returns number of data lines
        """
        return len(self._data)

    @property
    def nb_columns(self):
        return self.getColumns()

    def getColumns(self):
        """
        Returns number of columns from scan header
        """
        if not self.is_parsed:
            self.parse()
        return self._columns

    @property
    def labels(self):
        return self.getLabels()

    def getLabels(self):
        """
        Returns the labels for the data columns
        """
        if not self.is_parsed:
            self.parse()
        return self._labels

    @property
    def command(self):
        return self.getCommand()

    def getCommand(self):
        """
        Returns a string containing the command that
        was run in spec to start the scan
        """
        return self._command

    @property
    def motor_names(self):
        return self.getMotorNames()

    def getMotorNames(self):
        """
        Returns a list with motor names
        """
        if not self.is_parsed:
            self.parse()

        if self._motor_labels:
            return self._motor_labels
        elif self._fileheader and self._fileheader._motor_labels:
            return self._fileheader._motor_labels
        else:
            return None

    @property
    def motors(self):
        return self.getMotorMnemonics()

    def getMotorMnemonics(self):
        """
        Returns a list with motor mnemonics. Motor mnemonics are saved
        in files only since spec version 6.0.10
        """
        if not self.is_parsed:
            self.parse()

        if self._motor_mnes:
            return self._motor_mnes
        elif self._fileheader and self._fileheader._motor_mnes:
            return self._fileheader._motor_mnes
        else:
            return None

    @property
    def counter_names(self):
        return self.getCounterNames()

    def getCounterNames(self):
        """
        Returns a list with counter names. Counter names are saved
        in files only since spec version 6.0.10
        """
        if not self.is_parsed:
            self.parse()

        if self._counter_labels:
            return self._counter_labels
        elif self._fileheader and self._fileheader._counter_labels:
            return self._fileheader._counter_labels
        else:
            return None

    @property
    def counters(self):
        return self.getCounterMnemonics()

    def getCounterMnemonics(self):
        """
        Returns a list with counter mnemonics. Counter mnemonics are saved
        in files only since spec version 6.0.10
        """
        if not self.is_parsed:
            self.parse()

        if self._counter_mnes:
            return self._counter_mnes
        elif self._fileheader and self._fileheader._counter_mnes:
            return self._fileheader._counter_mnes
        else:
            return None

    @property
    def motor_positions(self):
        return self.getMotorPositions()

    def getMotorPositions(self):
        """
        Returns a dictionary with motor names and positions.
        These are the positions of the motors when the scan was started
        """
        if not self.is_parsed:
            self.parse()

        return self.motor_positions_list

    @property
    def user(self):
        return self.getUser()

    def getUser(self):
        if self._fileheader:
            return self._fileheader.getUser()

    @property
    def spec(self):
        return self.getSpec()

    def getSpec(self):
        if self._fileheader:
            return self._fileheader.getSpec()

    @property
    def date(self):
        return self.getDate()

    def getDate(self):
        """
        Returns the date when the scan was started
        """
        if not self.is_parsed:
            self.parse()
        return self._date

    @property
    def file_date(self):
        return self.getFileDate()

    def getFileDate(self):
        """
        Returns the date when the file was created
        """
        if self._fileheader:
            return self._fileheader._date
        else:
            return None

    @property
    def source(self):
        return self.getSource()

    def getSource(self):
        """
        Returns the path of the file as it appears in the file header
        """
        if self._fileheader:
            if self._fileheader._filename:
                return self._fileheader._filename

        return ""

    @property
    def geometry(self):
        return self.getGeometry()

    def getGeometry(self):
        """
        Returns geometry values as saved in the file.
        Check the spec documentation for the meaning of these values
        """
        if not self.is_parsed:
            self.parse()
        return [" ".join(line) for line in self._geo_pars]

    @property
    def hkl(self):
        return self.getHKL()

    def getHKL(self):
        """
        Returns a list with HKL values at the beginning of the scan
        """
        if not self.is_parsed:
            self.parse()
        return self._qvalue

    @property
    def file_epoch(self):
        return self.getFileEpoch()

    def getFileEpoch(self):
        """
        Returns the epoch of the file creation. It is possible to find
        the absolute epoch for any scan time by adding
        the file epoch with the value in the Epoch column of the scan
        """
        if self._fileheader:
            return self._fileheader._epoch
        else:
            return None

    @property
    def count_time(self):
        return self.getCountTime()

    def getCountTime(self):
        """
        Returns a list with two values: counting time and units
        if time units cannot be found in file the units value is left empty
        """
        if not self.is_parsed:
            self.parse()
        return self._count_time

    @property
    def comments(self):
        return self.getComments()

    def getComments(self):
        """
        Returns comments in the scan.
        Aborted termination can be found in this way
        """
        if not self.is_parsed:
            self.parse()
        return self._comment_lines

    @property
    def user_lines(self):
        return self.getUserLines()

    def getUserLines(self):
        if not self.is_parsed:
            self.parse()
        return self._user_lines

    @property
    def extra_lines(self):
        return self.getExtraLines()

    def getExtra(self):
        """
        Returns extra lines starting with "@" character.
        These are normally lines related with MCA data
        """
        if not self.is_parsed:
            self.parse()
        return self.getExtraLines()

    def getExtraLines(self):
        if not self.is_parsed:
            self.parse()
        return [" ".join(line) for line in self._extra_lines]

    @property
    def metadata(self):
        return self.getMeta()

    def getMeta(self):
        """
        Returns a dictionary with the most relevant metdata information
        """
        if not self.is_parsed:
            self.parse()

        meta = {
            "spec": "",
            "user": "",
            "source": "",
            "HKL": "",
            "date": "",
            "scanno": "",
            "motors": None,
            "comments": None,
            "errors": None,
        }

        # spec and user. In fileheader comment line
        meta["spec"] = self.getSpec()
        meta["user"] = self.getUser()
        meta["source"] = self.getSource()
        meta["HKL"] = self.getHKL()
        meta["date"] = self.getDate()
        meta["scanno"] = self.getNumber()
        meta["motors"] = self.getMotorPositions()
        meta["motornames"] = self.getMotorNames()
        meta["comments"] = self.getComments()
        meta["order"] = self.getOrder()
        meta["noinfile"] = self.getNumberInFile()
        meta["points"] = self.getLines()
        meta["columns"] = self.getColumns()
        meta["userlines"] = self.getUserLines()
        meta["geo"] = self.getGeometry()
        meta["extra"] = self.getExtra()

        motmnes = self.getMotorMnemonics()
        if motmnes:
            meta["motormnes"] = self.getMotorMnemonics()

        if self._contains_error:
            meta["errors"] = self._error_messages

        return meta

    @property
    def data(self):
        return self.getData()

    def getData(self):
        """
        Returns a numpy array with all data in the scan
        """
        if not self.is_parsed:
            self.parse()

        if self._data:
            return numpy.array(self._data, dtype=float)
        else:
            return numpy.empty((0, self._columns))

    @property
    def nb_mcas(self):
        return self.getNumberMcas()

    def getNumberMcas(self):
        """
        Returns the number of mcas in the scan
        """
        if not self.is_parsed:
            self.parse()
        return sum(map(len, self._oneds))

    @property
    def mcas(self):
        return self.getMcas()

    def getMcas(self):
        """
        Returns a list of 1D numpy arrays in the scan,
        each of them being a spectrum from a 1D detector
        """
        if not self.is_parsed:
            self.parse()
        result = []
        for mcas in self._oneds:
            result += mcas
        return result

    @property
    def nb_oneds(self):
        return self.getNumberOneD()

    def getNumberOneD(self):
        """
        Returns the number of OneD channels in the scan.
        """
        if not self.is_parsed:
            self.parse()
        return len(self._oneds)

    def getOneD(self, idx):
        if not self.is_parsed:
            self.parse()
        return self._oneds[idx]

    get_mca = getOneD
    get_oned = getOneD

    def _setOrder(self, order):
        self._order = order

    def __str__(self):
        if not self.is_parsed:
            self.parse()
        if self._order > 1:
            return "%s.%s %s" % (self._number, self._order, self._command)
        else:
            return "%s %s" % (self._number, self._command)

    def save(self, outfile, format="spec", append=False, columns=None, mcas=False):
        """scan.save method produces a simple output meant to export scan
        data to format readable by excel and other programs
        """

        data = self.getData()
        meta = {}

        meta["command"] = self.getCommand()
        meta["number"] = self.getNumber()
        meta["columns"] = data.shape[1]

        if append:
            ofd = open(outfile, "a")
        else:
            ofd = open(outfile, "w")

        if format == "tabs":
            labsep = "\t"
            datsep = "\t"
            first = ""
        elif format == "csv":
            labsep = ","
            datsep = ","
            first = ""
        elif format == "spec":
            labsep = "  "
            datsep = " "
            first = (
                """
#S %(number)s %(command)s
#N %(columns)s
#L """
                % meta
            )

        ofd.write(first + labsep.join(self.getLabels()) + "\n")
        for row in range(data.shape[0]):
            outline = datsep.join(["%.12g" % val for val in data[row]]) + "\n"
            ofd.write(outline)
        ofd.write("\n")


class McaData:
    """
    The class MCA data represents 1D data
    """

    def __init__(self):
        self._data = []
        self._calib = None

    @property
    def calib(self):
        return self.getCalib()

    def getCalib(self):
        return self.calib

    @calib.setter
    def calib(self, calib):
        return self.setCalib(calib)

    def setCalib(self, calib):
        self._calib = calib

    @property
    def data(self):
        return self.getData()

    def getData(self, calibrated=False):
        channels = list(range(len(self._data)))

        if calibrated and self._calib:
            a, b, c = self._calib
            indexes = [(a + b * x + c * x**2) for x in channels]
        else:
            indexes = channels

        if self._data:
            return numpy.array([indexes, self._data], dtype=float).transpose()
        else:
            return numpy.empty((0, 1))

    def __len__(self):
        return len(self._data)

    def _addLine(self, line):
        if line.strip()[-1] == "\\":
            dataline = line.strip()[:-1]
            complete = False
        else:
            dataline = line
            complete = True

        self._data.extend(list(map(float, dataline.split())))
        return complete


class OneD(list):
    """
    The class OneD is for the one dimension channels.
    It has a list of McaData objects.
    """

    @property
    def data(self):
        return self.getData()

    def getData(self):
        data = []
        for mcadata in self:
            raw_data = mcadata.getData().transpose()[1].tolist()
            data.append(raw_data)
        return numpy.array(data, dtype=float)


if __name__ == "__main__":
    import sys

    t0 = time.time()

    fs = FileSpec(sys.argv[1])

    print("Time to open file was %s " % (time.time() - t0))
    print("  number of scans: %s" % len(fs))

    print("  file created by user %s" % fs.user)

    for scan in fs:
        print("Scan %d /  " % scan.number)
        print("   count time is %s /  " % str(scan.count_time))
        print("   number of points in scan: %d" % scan.nb_points)
        print("   number of mcas in scan: %d" % scan.nb_mcas)
        for mca in scan.mcas:
            print("     - mca / shape: %s" % str(mca.data.shape))
