from pyspec._connection import ClientConnection

from ._remote_property_table import PropertyGroup, RemotePropertyTable


class Motor(PropertyGroup):
    """
    The motor properties are used to control the motors.
    The parameters for the commands that are sent from the client and the values in the replies and events that are sent from the server
    are always transmitted as ASCII strings in the data that follows the packet header.
    """

    def __init__(
        self,
        motor_name: str,
        client_connection: ClientConnection,
        remote_property_table: RemotePropertyTable,
    ):
        super().__init__(f"motor/{motor_name}", remote_property_table)
        self.name = motor_name
        self._client_connection = client_connection
        self._remote_property_table = remote_property_table

        self.position = self._readonly_property("position", float, coerce=float)
        """
        motor/{mne}/position
            on("change"): Sent when the dial position or user offset changes.
            get: Returns the current motor position in user units.
            set: Sets the user offset on the server.
        """
        self.dial_position = self._property("dial_position", float, coerce=float)
        """
        motor/{mne}/dial_position
            on("change"): Sent when the dial position changes.
            get: Returns the current motor position in dial units.
            set: Sets the dial position on the server by pushing a

                    set_dial mne data\\n

                onto the command queue, unless the dial position is already set to that value.
        """
        self.offset = self._property("offset", float, coerce=float)
        """
        motor/{mne}/offset
            on("change"): Sent when the offset changes.
            get: Returns the current user offset in dial units.
            set: Sets the user offset by pushing the

                    set mne value\\n

                command onto the command queue, unless the offset is already at the value.
                The data should contain the offset value in motor units (degrees, mm, etc.).
                The server will calculate `value` for the argument in `set` appropriately.
        """
        self.step_size = self._readonly_property("step_size", float, coerce=float)
        """
        motor/{mne}/step_size
            on("change"): Sent when the steps-per-unit parameter changes.
            get: Returns the current steps-per-unit parameter.
        """
        self.sign = self._readonly_property("sign", int, coerce=int)
        """
        motor/{mne}/sign
            on("change"): Sent when the sign-of-user*dial parameter changes.
            get: Returns the current sign-of-user*dial parameter.
        """
        self.moving = self._readonly_property("move_done", bool, coerce=bool)
        """
        motor/{mne}/move_done
            on("change"): Sent when moving starts (True) and stops (False).
            get: True if the motor is busy, otherwise False.

        Note: This does seem a little backwards from the name of the SPEC prop.
        """
        self.high_lim_hit = self._readonly_property("high_lim_hit", bool, coerce=bool)
        """
        motor/{mne}/high_lim_hit
            on("change"): Sent when the high-limit switch has been hit.
            get: True if the high-limit switch has been hit.
        """
        self.low_lim_hit = self._readonly_property("low_lim_hit", bool, coerce=bool)
        """
        motor/{mne}/low_lim_hit
            on("change"): Sent when the low-limit switch has been hit.
            get: True if the low-limit switch has been hit.
        """
        self.emergency_stop = self._readonly_property(
            "emergency_stop", bool, coerce=bool
        )
        """
        motor/{mne}/emergency_stop
            on("change"): Sent when a motor controller indicates a hardware emergency stop.
            get: True if an emergency-stop switch or condition has been activated.
        """
        self.motor_fault = self._readonly_property("motor_fault", bool, coerce=bool)
        """
        motor/{mne}/motor_fault
            on("change"): Sent when a motor controller indicates a hardware motor fault.
            get: True if a motor-fault condition has been activated.
        """
        self.high_limit = self._property("high_limit", float, coerce=float)
        """
        motor/{mne}/high_limit
            on("change"): Sent when the value of the high limit position changes.
            get: Returns the high limit in dial units.
            set: Sets the high limit by pushing

                    set_lm  mne data user(mne,get_lim(mne,-1))\\n

                onto the server command queue. (The last argument adds the current low limit to the set_lm command line.)

        """
        self.low_limit = self._property("low_limit", float, coerce=float)
        """
        motor/{mne}/low_limit
            on("change"): Sent when the value of the low limit position changes.
            get: Returns the low limit in dial units.
            set: Sets the low limit by pushing

                set_lm mne data user(mne,get_lim(mne,+1))\\n

            onto the server command queue. (The last argument adds the current high limit to the set_lm command line.)
        """
        self.limits = self._writeonly_property("limits", str)
        """
        motor/{mne}/limits
            set: Sets both motor limits by pushing

                    set_lm mne data\\n

                onto the server command queue,
                where data should contain the low and high motor limit values in a string.
        """
        self.search = self._writeonly_property("search", str)
        """
        motor/{mne}/search
            set: The server starts a home or limit search by pushing a

                    chg_dial(mne, how)\\n

                or a

                    chg_dial(mne, how, home_pos)\\n

                onto the command queue, depending on whether the data contains one or two arguments.
                The `how` argument is one of the strings recognized by chg_dial(),
                namely \"home\", \"home+\", \"home-\", \"lim+\" or \"lim-\".
                The optional home_pos is the home position in dial units.

                # TODO: It is not clear what it means by sending data with "two arguments" here.
                # Need to check how that is supposed to be formatted.

        """
        self.unusable = self._readonly_property("unusable", bool, coerce=bool)
        """
        motor/{mne}/unusable
            on("change"): Sent when a "disable" option to motor_par() has changed the enabled/disabled state of a motor on the server.
            get: True if the motor is unusable.
        """

        # Sync check is somewhat complicated.
        # This is effectively a request from the server to resolve a synchronization issue.
        # The server will send an event with the current and expected positions,
        # and then wait for a response from either the server keyboard or SOME client.
        # This is not implemented yet, and probably wont be. The use case here is very niche.

        # self.sync_check = self._property("sync_check", str)

        self._start_one = self._writeonly_property("start_one", float)
        """
        motor/mne/start_one
            set: If preceded by a prestart_all, adds a

                    A[mne]=data;

                to the buffer that will be pushed onto the server command queue. Otherwise, pushes

                    {get_angles;A[mne]=data;move_em;}\\n

                onto the command queue in order to start the single motor moving.
        """

    async def _move(self, position: float):
        # Start the tracking before we send the move to avoid race conditions.
        async with self.moving.wait_for(False):
            await self._start_one.set(position)

    async def move(self, position: float):
        """
        Move the motor to the specified position.

        If motor synchronization is enabled, the move will be queued until synchronization is executed.

        Args:
            position (float): The target position to move the motor to.
        """

        if not self._client_connection._synchronizing_motors:
            return await self._move(position)

        self._client_connection._pending_motions[self.name] = position
