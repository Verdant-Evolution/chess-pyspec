# ******************************************************************************
#
#  @(#)css_logger.py	6.3  12/13/20 CSS
#
#  "pyspec" Release 6
#
#  Copyright (c) 2013,2014,2015,2016,2017,2018,2020
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

import logging
from logging.handlers import RotatingFileHandler

import os
import time


class CSSLogger(logging.Logger):
    def isEnabledFor(self, level):
        return level <= self.getEffectiveLevel()

    def start(self, level=2, filename=None):
        if filename is not None:
            addFileHandler(filename)
        else:
            addStdOutHandler()
        self.setLevel(level)


class StdOutFormatter(logging.Formatter):

    def format(self, record):
        millis = int(round(record.created % 1 * 1000))
        strtime = time.strftime("%H:%M:%S", time.localtime(record.created))
        strtime += ".%03d" % millis
        basefile = os.path.basename(record.pathname)
        level = record.levelname
        levelno = record.levelno
        lineno = record.lineno
        funcname = record.funcName
        msg = record.msg

        fileinfo = "%s:%s (line:%s)" % (basefile, funcname, lineno)
        logline = "%s - %s - %-50s  | %s" % (strtime, levelno, fileinfo, msg)

        return logline


def start_log(level=2, filename=None):
    log.start(level, filename)


def addStdOutHandler():
    stdh = logging.StreamHandler()
    log_formatter = StdOutFormatter()
    stdh.setFormatter(log_formatter)
    log.addHandler(stdh)


def addFileHandler(filename):
    fileh = RotatingFileHandler(filename, maxBytes=2000000, backupCount=5)
    log_formatter = StdOutFormatter()
    fileh.setFormatter(log_formatter)
    log.addHandler(fileh)


def log_exception():
    import traceback

    log = CSSLogger("pyspec")
    log.log(2, traceback.format_exc())


log = CSSLogger("pyspec")
