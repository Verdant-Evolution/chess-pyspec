from ._remote_property_table import RemotePropertyTable, PropertyGroup


class Status(PropertyGroup):
    """
    The status properties reflect changes in the server state that may affect the server's ability
    to execute client commands or control hardware.

    Attributes:
        quit (RemotePropertyTable.ReadableProperty[bool]): Whether or not the server is exiting.
        shell (RemotePropertyTable.ReadableProperty[bool]): Whether or not the server is in a subshell.
        ready (RemotePropertyTable.ReadableProperty[bool]): Whether or not the server is ready to execute commands.
        simulate (RemotePropertyTable.ReadableProperty[bool]): Whether or not the server is in simulate mode.
    """

    def __init__(self, remote_property_table: RemotePropertyTable):
        super().__init__("/status", remote_property_table)
        self._remote_property_table = remote_property_table

        self.quit = self._readonly_property("quit", bool)
        """
        status/quit
            on("change"): Sent when the server exits.
            get: Always read back as zero.
        """

        self.shell = self._readonly_property("shell", bool)
        """
        status/shell
            on("change"): Sent when the server enters a subshell (True) or returns from a subshell (False).
            get: True if server command thread is in a subshell, otherwise False.

        Starting with spec release 6.06.01, when entering a subshell,
        the server does not process commands from clients for the first one second of the subshell.
        Prior to spec release 6.06.01, the server did not process commands when in a subshell at all.
        """
        self.ready = self._readonly_property("ready", bool)
        """
        status/ready
            on("change"): Sent when the server is waiting for input at the interactive prompt (True)
                            and after a return has been typed at the interactive prompt (False).
                            The server is available to execute commands from clients when it is ready.
            get: True if the server command thread is busy and unable to immediately process a new command, otherwise False.
        """
        self.simulate = self._readonly_property("simulate", bool)
        """
        status/simulate
            on("change"): Sent when the server enters (True) or leaves (False) simulate mode.
            get: True if server is in simulate mode, otherwise False.
        Note, when in simulate mode, the server will not send commands to hardware devices.
        """
