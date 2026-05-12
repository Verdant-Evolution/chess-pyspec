import asyncio
import weakref
from collections.abc import Iterable
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncContextManager, Literal, Optional, overload

from pyspec._connection import ClientConnection

from ._remote_property_table import (
    PropertyGroup,
    RemotePropertyTable,
    WritableProperty,
)


class Motor(PropertyGroup):
    """
    The motor properties are used to control the motors.
    The parameters for the commands that are sent from the client and the values in the replies and events that are sent from the server are always transmitted as ASCII strings in the data that follows the packet header.

    Args:
        motor_name (str): The name of the motor.
        client_connection (ClientConnection): The client connection instance.
        remote_property_table (RemotePropertyTable): The remote property table instance.
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

        self.position = self._readonly_property("position", float)
        """
        motor/{mne}/position
            on("update"): Sent when the dial position or user offset updates.
            get: Returns the current motor position in user units.
            set: Sets the user offset on the server.
        """
        self.dial_position = self._property("dial_position", float)
        """
        motor/{mne}/dial_position
            on("update"): Sent when the dial position updates.
            get: Returns the current motor position in dial units.
            set: Sets the dial position on the server by pushing a

                .. code-block:: none

                    set_dial mne data\\n

                onto the command queue, unless the dial position is already set to that value.
        """
        self.offset = self._property("offset", float)
        """
        motor/{mne}/offset
            on("update"): Sent when the offset updates.
            get: Returns the current user offset in dial units.
            set: Sets the user offset by pushing the

                .. code-block:: none

                    set mne value\\n

                command onto the command queue, unless the offset is already at the value.
                The data should contain the offset value in motor units (degrees, mm, etc.).
                The server will calculate `value` for the argument in `set` appropriately.
        """
        self.step_size = self._readonly_property("step_size", float)
        """
        motor/{mne}/step_size
            on("update"): Sent when the steps-per-unit parameter updates.
            get: Returns the current steps-per-unit parameter.
        """
        self.sign = self._readonly_property("sign", int)
        """
        motor/{mne}/sign
            on("update"): Sent when the sign-of-user*dial parameter updates.
            get: Returns the current sign-of-user*dial parameter.
        """
        self.moving = self._readonly_property("move_done", bool)
        """
        motor/{mne}/move_done
            on("update"): Sent when moving starts (True) and stops (False).
            get: True if the motor is busy, otherwise False.

        Note: This does seem a little backwards from the name of the SPEC prop.
        """
        self.high_lim_hit = self._readonly_property("high_lim_hit", bool)
        """
        motor/{mne}/high_lim_hit
            on("update"): Sent when the high-limit switch has been hit.
            get: True if the high-limit switch has been hit.
        """
        self.low_lim_hit = self._readonly_property("low_lim_hit", bool)
        """
        motor/{mne}/low_lim_hit
            on("update"): Sent when the low-limit switch has been hit.
            get: True if the low-limit switch has been hit.
        """
        self.emergency_stop = self._readonly_property("emergency_stop", bool)
        """
        motor/{mne}/emergency_stop
            on("update"): Sent when a motor controller indicates a hardware emergency stop.
            get: True if an emergency-stop switch or condition has been activated.
        """
        self.motor_fault = self._readonly_property("motor_fault", bool)
        """
        motor/{mne}/motor_fault
            on("update"): Sent when a motor controller indicates a hardware motor fault.
            get: True if a motor-fault condition has been activated.
        """
        self.high_limit = self._property("high_limit", float)
        """
        motor/{mne}/high_limit
            on("update"): Sent when the value of the high limit position updates.
            get: Returns the high limit in dial units.
            set: Sets the high limit by pushing

                .. code-block:: none

                    set_lm  mne data user(mne,get_lim(mne,-1))\\n

                onto the server command queue. (The last argument adds the current low limit to the set_lm command line.)

        """
        self.low_limit = self._property("low_limit", float)
        """
        motor/{mne}/low_limit
            on("update"): Sent when the value of the low limit position updates.
            get: Returns the low limit in dial units.
            set: Sets the low limit by pushing

                .. code-block:: none

                    set_lm mne data user(mne,get_lim(mne,+1))\\n

            onto the server command queue. (The last argument adds the current high limit to the set_lm command line.)
        """
        self._limits: WritableProperty[str] = self._writeonly_property("limits")
        """
        motor/{mne}/limits
            set: Sets both motor limits by pushing

                .. code-block:: none

                    set_lm mne data\\n

                onto the server command queue,
                where data should contain the low and high motor limit values in a string.
        """
        self._search: WritableProperty[str] = self._writeonly_property("search")
        """
        motor/{mne}/search
            set: The server starts a home or limit search by pushing a

                .. code-block:: none

                    chg_dial(mne, how)\\n

                or a

                .. code-block:: none

                    chg_dial(mne, how, home_pos)\\n

                onto the command queue, depending on whether the data contains one or two arguments.
                The `how` argument is one of the strings recognized by chg_dial(),
                namely \"home\", \"home+\", \"home-\", \"lim+\" or \"lim-\".
                The optional home_pos is the home position in dial units.
        """
        self.unusable = self._readonly_property("unusable", bool)
        """
        motor/{mne}/unusable
            on("update"): Sent when a "disable" option to motor_par() has updated the enabled/disabled state of a motor on the server.
            get: True if the motor is unusable.
        """

        # Sync check is somewhat complicated.
        # This is effectively a request from the server to resolve a synchronization issue.
        # The server will send an event with the current and expected positions,
        # and then wait for a response from either the server keyboard or SOME client.
        # This is not implemented yet, and probably wont be. The use case here is very niche.

        # self.sync_check = self._property("sync_check", str)

        self._start_one: WritableProperty[float] = self._writeonly_property("start_one")
        """
        motor/mne/start_one
            set: If preceded by a prestart_all, adds a


                .. code-block:: none

                    A[mne]=data;

                to the buffer that will be pushed onto the server command queue. Otherwise, pushes

                .. code-block:: none

                    {get_angles;A[mne]=data;move_em;}\\n

                onto the command queue in order to start the single motor moving.
        """

    async def move(self, position: float):
        """
        Move the motor to the specified position.

        If motor synchronization is enabled, the move will be queued until synchronization is executed.

        Args:
            position (float): The target position to move the motor to.
        """

        if _SYNCHRONIZING_MOTORS.get(self._client_connection, False):
            raise RuntimeError(
                "Cannot start move when synchronizing motors. Use prepare_move instead."
            )

        # Start the tracking before we send the move to avoid race conditions.
        async with self.moving.subscribed(), self.moving.wait_for(False):
            await self._start_one.set(position)

    async def start_move(self, position: float):
        """
        Starts a move to the specified position.
        This will wait for the motor to start moving, and then return a task that can be awaited to wait for the move to complete.

        This is a convenience method that combines move() with waiting for the motor to start moving, which can be useful
        if you want to ensure that the motor is moving before moving on to other tasks.

        Args:
            position (float): The target position to move the motor to.
        """
        async with self.moving.wait_for(True):
            return asyncio.create_task(self.move(position))

    def prepare_move(self, position: float):
        """
        Prepare a move to the specified position without starting it.

        This is used for motor synchronization, where multiple moves are queued and then executed together when synchronization is executed.

        Args:
            position (float): The target position to move the motor to.
        """
        if not _SYNCHRONIZING_MOTORS.get(self._client_connection, False):
            raise RuntimeError("Cannot prepare move when not synchronizing motors")

        pending_motions = _PENDING_MOTIONS.setdefault(self._client_connection, {})
        if self.name in pending_motions:
            raise RuntimeError(
                f"Motor {self.name} already has a pending motion in this synchronization context."
            )
        pending_motions[self.name] = position

    @overload
    async def search(self, how: Literal["home", "home+", "home-"], home_pos: float): ...

    @overload
    async def search(self, how: Literal["lim+", "lim-"], home_pos: None = None): ...
    async def search(
        self,
        how: Literal["home", "home+", "home-", "lim+", "lim-"],
        home_pos: Optional[float] = None,
    ):
        """
        Start a home or limit search.

        Pushes a chg_dial command like:

        .. code-block:: none

            chg_dial(mne, how)\n
                or
            chg_dial(mne, how, home_pos)\n

        Args:
            how (Literal["home", "home+", "home-", "lim+", "lim-"]): The type of search to perform. Must be one of "home", "home+", "home-", "lim+" or "lim-".
            home_pos (Optional[float]): The home position in dial units (required for home searches).
        """

        if how.startswith("home"):
            if home_pos is None:
                raise ValueError("home_pos must be provided for home searches")
            return await self._search.set(f"{how} {home_pos}")

        return await self._search.set(how)

    async def set_limits(self, low_limit: float, high_limit: float):
        """
        Set both motor limits by pushing:

        .. code-block:: none

            set_lm mne data\n

        onto the server command queue, where data should contain the low and high motor limit values in a string.

        Args:
            low_limit (float): The low limit value.
            high_limit (float): The high limit value.
        """
        await self._limits.set(f"{low_limit} {high_limit}")


_SYNCHRONIZING_MOTORS: weakref.WeakKeyDictionary[ClientConnection, bool] = (
    weakref.WeakKeyDictionary()
)
_PENDING_MOTIONS: weakref.WeakKeyDictionary[ClientConnection, dict[str, float]] = (
    weakref.WeakKeyDictionary()
)


@asynccontextmanager
async def enter_all(contexts: Iterable[AsyncContextManager]):
    async with AsyncExitStack() as stack:
        for ctx in contexts:
            await stack.enter_async_context(ctx)
        yield


@asynccontextmanager
async def synchronized_motors(
    client_connection: ClientConnection,
    remote_property_table: RemotePropertyTable,
    *,
    timeout: Optional[float] = None,
):
    """
    Context manager to enable synchronized motor operations for the client.

    While this context is active, motor movements will be held.
    Upon exiting the context, the movements will be initialized simultaneously.

    Example usage:

    .. code-block:: python

        async with client.synchronized_motors():
            # Motor movement will be held in here.
            motor1.prepare_move(position)
            motor2.prepare_move(position)

            # Motors will not start moving yet.
            await asyncio.sleep(1)  # Simulate other operations
            # Motors will start moving simultaneously here.

        # Outside of the context, all motors have completed their movements.

    Args:
        timeout (float, optional): Maximum time to wait for all motors to complete, in seconds.
    Yields:
        None
    Raises:
        RuntimeError: If there are pending motor motions from a previous context.
    """
    assert not _SYNCHRONIZING_MOTORS.get(client_connection, False), (
        "Concurrent synchronized_motors contexts are not allowed."
    )

    motion_started = False
    try:
        if len(_PENDING_MOTIONS.get(client_connection, {})) > 0:
            raise RuntimeError(
                "There are pending motor motions from a previous synchronized_motors context."
            )
        _SYNCHRONIZING_MOTORS[client_connection] = True
        _PENDING_MOTIONS[client_connection] = {}

        # Give control back to user.
        yield

        pending_motions = _PENDING_MOTIONS[client_connection]

        @asynccontextmanager
        async def wait_for_move_done(mne: str):
            moving = remote_property_table.readonly_property(
                f"motor/{mne}/move_done", bool
            )
            async with moving.subscribed(), moving.wait_for(False, timeout=timeout):
                yield

        async with enter_all((wait_for_move_done(mne) for mne in pending_motions)):
            # Start the prestart message
            motion_started = True
            await client_connection.prop_set("motor/../prestart_all", None)

            # Append the individual motor commands
            for mne, position in pending_motions.items():
                client_connection.logger.info(
                    "Starting synchronized move for `%s` to position %s.",
                    mne,
                    position,
                )

                await client_connection.prop_set(f"motor/{mne}/start_one", position)

            # Start all the motors simultaneously
            await client_connection.prop_set("motor/../start_all", None)

    except Exception as e:
        client_connection.logger.error(
            "Error during synchronized motor operations: %s", str(e)
        )
        if motion_started:
            await client_connection.prop_set("motor/../abort_all", None)
        raise
    finally:
        _SYNCHRONIZING_MOTORS.pop(client_connection, None)
        _PENDING_MOTIONS.pop(client_connection, None)
