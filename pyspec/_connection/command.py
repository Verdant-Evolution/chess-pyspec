from enum import Enum


class Command(Enum):
    """
    Enumeration of commands that can be sent between the client and server.

    This enum defines all possible commands for the SPEC protocol.
    """

    ### From Client ###
    CLOSE = 1
    ABORT = 2
    CMD = 3
    CMD_WITH_RETURN = 4

    REGISTER = 6
    UNREGISTER = 7

    FUNC = 9
    FUNC_WITH_RETURN = 10
    CHAN_READ = 11
    CHAN_SEND = 12

    HELLO = 14

    ### From Server ###
    EVENT = 8
    REPLY = 13
    HELLO_REPLY = 15

    ### Unused ###
    RETURN = 5
