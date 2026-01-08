from enum import Enum


class Flag(Enum):
    """
    Enumeration of flags that can be sent between the client and server.

    This enum defines all possible flags for the SPEC protocol.
    """

    NONE = 0
    DELETED = 0x1000
    """
    Sent when watched variables or associative array elements are deleted.
    the spec client currently does not take any action on receipt of such events.
    """
