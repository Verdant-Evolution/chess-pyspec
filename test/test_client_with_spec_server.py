import asyncio
import os

import pytest

import pyspec
from pyspec import Client
from pyspec._connection.associative_array import AssociativeArray
from pyspec.client import Property

SERVER_PORT: int = int(os.environ.get("SPEC_SERVER_PORT", -1))
pytestmark = pytest.mark.skipif(
    SERVER_PORT == -1,
    reason="Requires SPEC_SERVER_PORT environment variable to be set to the port of a running spec server",
)


@pytest.mark.asyncio
async def test_connect():
    from pyspec import Client

    async with Client("localhost", SERVER_PORT) as client:
        assert client._connection is not None


@pytest.mark.asyncio
async def test_var_read_write():
    async with Client("localhost", SERVER_PORT) as client:
        H = client.var("H")
        await H.set(123)
        value = await H.get()
        assert value == 123


@pytest.mark.asyncio
async def test_var_subscribe():
    async with Client("localhost", SERVER_PORT) as client:
        async with client.var("H").subscribed() as H:
            await H.set(10)

            async with H.wait_for(123):
                await client.exec("H = 123")

            assert await H.get() == 123


@pytest.mark.asyncio
async def test_var_read_doesnt_exist():
    async with Client("localhost", SERVER_PORT) as client:
        with pytest.raises(pyspec.RemoteException):
            await client.var("doesnt_exist").get()


@pytest.mark.asyncio
async def test_output():
    async with Client("localhost", SERVER_PORT) as client:
        async with client.output("tty").capture() as lines:
            await client.exec('print("Hello, world!")')
        assert lines[-1] == "Hello, world!\n"


@pytest.mark.asyncio
async def test_status():
    async with Client("localhost", SERVER_PORT) as client:
        status = client.status()
        async with status:
            assert await status.ready.get(), "expected status.ready == True"
            assert not await status.shell.get(), "expected status.shell == False"
            assert not await status.simulate.get(), "expected status.simulate == False"


@pytest.mark.asyncio
async def test_motor():
    async with Client("localhost", SERVER_PORT) as client:
        m0 = client.motor("m0")
        async with m0:
            await asyncio.sleep(1)
            current_position = await m0.position.get()
            await m0.move(-current_position)
        assert await m0.position.get() == -current_position


@pytest.mark.asyncio
async def test_sync_motors():
    """
    Here is a communication log from SPEC when the server is running with REAL motors.
    This is the expected communication pattern for this test.

    Simulation mode behaves differently and sends the position event with the old position.

    sR      1    0.00  2 HELLO
    sW      1    0.00  2 HELLO_REPLY      spec                            spec
    sR      0    0.05  2 REGISTER         motor/m0/move_done
    sW      0   56.79  2 EVENT            motor/m0/dial_position        -24.40375
    sR      0    0.02  2 REGISTER         motor/m0/position
    sW      0    0.00  2 EVENT            motor/m0/move_done            0
    sW      0    0.00  2 EVENT            motor/m0/position             25.000001373291
    sR      0    0.04  2 REGISTER         motor/m1/move_done
    sW      0    0.00  2 EVENT            motor/m1/move_done            0
    sR      0    0.04  2 REGISTER         motor/m1/position
    sW      0    0.01  2 EVENT            motor/m1/position             326.000000610352
    sR      2    0.15  2 CHAN_READ        motor/m0/position
    sW      2    0.01  2 REPLY            motor/m0/position             25.000001373291
    sR      0  113.65  2 CHAN_SEND        motor/../prestart_all
    sR      0    0.36  2 CHAN_SEND        motor/m0/start_one            26
    sR      0    0.12  2 CHAN_SEND        motor/m1/start_one            325
    sR      0    0.08  2 CHAN_SEND        motor/../start_all
    sW      0  122.03  2 EVENT            motor/m0/move_done            1
    sW      0    1.62  2 EVENT            motor/m1/move_done            1
    sW      0    0.02  2 EVENT            motor/m0/position             25.000751373291
    sW      0    0.01  2 EVENT            motor/m1/position             325.999063110352
    sW      0    0.09  2 EVENT            motor/m0/position             26.000001373291
    sW      0    0.00  2 EVENT            motor/m0/move_done            0
    sW      0    0.05  2 EVENT            motor/m1/position             324.987875610352
    sW      0    0.03  2 EVENT            motor/m1/position             325.000000610352
    sW      0    0.02  2 EVENT            motor/m1/move_done            0
    """

    async with Client("localhost", SERVER_PORT) as client:
        m0 = client.motor("m0")
        m1 = client.motor("m1")

        m0_target = 26
        m1_target = 150

        async with m0, m1:
            with pytest.raises(
                RuntimeError, match="Cannot prepare move when not synchronizing motors"
            ):
                m0.prepare_move(m0_target)
                m1.prepare_move(m1_target)

            async with client.synchronized_motors():
                with pytest.raises(
                    RuntimeError, match="Cannot start move when synchronizing motors"
                ):
                    await m0.move(m0_target)
                    await m1.move(m1_target)

                m0.prepare_move(m0_target)
                m1.prepare_move(m1_target)

            # Note: There appears to be a bug in server mode simulation where the motor position
            # event doesn't actually get updated. So these tests might fail in with SIMULATION mode on.
            assert pytest.approx(m0_target, rel=1e-3) == await m0.position.get()
            assert pytest.approx(m1_target, rel=1e-3) == await m1.position.get()


@pytest.mark.asyncio
async def test_associative_array_index():
    async with Client("localhost", SERVER_PORT) as client:
        await client.exec("__X = [ 1:0 ]")
        x = client.var("__X[1]")
        await x.set("one")
        assert await x.get() == "one"
        await x.set("two")
        assert await x.get() == "two"


@pytest.mark.asyncio
async def test_associative_array_multi_index():
    async with Client("localhost", SERVER_PORT) as client:
        await client.exec("__X = [1:2:0]")
        x = client.var("__X[1][2]")
        await x.set("one two")
        assert await x.get() == "one two"
        await x.set("three four")
        assert await x.get() == "three four"


@pytest.mark.asyncio
async def test_associative_array():
    async with Client("localhost", SERVER_PORT) as client:
        x: Property[AssociativeArray] = client.var("__X")
        xv = await x.get()
        assert isinstance(xv, AssociativeArray)

        xv[1, 2] = "three four"
        await x.set(xv)
        assert (await x.get())[1, 2] == "three four"
