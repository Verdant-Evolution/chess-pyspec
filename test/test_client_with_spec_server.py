import pytest
import os
import pyspec
from pyspec import Client
import asyncio

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
        test_var = client.var("test_var")
        await test_var.set(123)
        value = await test_var.get()
        assert value == 123


@pytest.mark.asyncio
async def test_var_subscribe():
    async with Client("localhost", SERVER_PORT) as client:
        async with client.var("test_var").subscribed() as test_var:
            await test_var.set(10)

            async with test_var.wait_for(123):
                await client.exec("test_var = 123")

            assert await test_var.get() == 123


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
            assert await status.ready.get()
            assert not await status.shell.get()
            assert await status.simulate.get()


@pytest.mark.asyncio
async def test_motor():
    async with Client("localhost", SERVER_PORT) as client:
        s0v = client.motor("s0v")
        async with s0v:
            await asyncio.sleep(1)
            current_position = await s0v.position.get()
            await s0v.move(-current_position)
        assert await s0v.position.get() == -current_position


@pytest.mark.asyncio
async def test_sync_motors():
    """
    Here is a communication log from SPEC when the server is running with REAL motors.
    This is the expected communication pattern for this test.

    Simulation mode behaves differently and sends the position event with the old position.

    sR      1    0.00  2 HELLO
    sW      1    0.00  2 HELLO_REPLY      spec                            spec
    sR      0    0.05  2 REGISTER         motor/xrfx/move_done
    sW      0   56.79  2 EVENT            motor/xrfx/dial_position        -24.40375
    sR      0    0.02  2 REGISTER         motor/xrfx/position
    sW      0    0.00  2 EVENT            motor/xrfx/move_done            0
    sW      0    0.00  2 EVENT            motor/xrfx/position             25.000001373291
    sR      0    0.04  2 REGISTER         motor/xrfz/move_done
    sW      0    0.00  2 EVENT            motor/xrfz/move_done            0
    sR      0    0.04  2 REGISTER         motor/xrfz/position
    sW      0    0.01  2 EVENT            motor/xrfz/position             326.000000610352
    sR      2    0.15  2 CHAN_READ        motor/xrfx/position
    sW      2    0.01  2 REPLY            motor/xrfx/position             25.000001373291
    sR      0  113.65  2 CHAN_SEND        motor/../prestart_all
    sR      0    0.36  2 CHAN_SEND        motor/xrfx/start_one            26
    sR      0    0.12  2 CHAN_SEND        motor/xrfz/start_one            325
    sR      0    0.08  2 CHAN_SEND        motor/../start_all
    sW      0  122.03  2 EVENT            motor/xrfx/move_done            1
    sW      0    1.62  2 EVENT            motor/xrfz/move_done            1
    sW      0    0.02  2 EVENT            motor/xrfx/position             25.000751373291
    sW      0    0.01  2 EVENT            motor/xrfz/position             325.999063110352
    sW      0    0.09  2 EVENT            motor/xrfx/position             26.000001373291
    sW      0    0.00  2 EVENT            motor/xrfx/move_done            0
    sW      0    0.05  2 EVENT            motor/xrfz/position             324.987875610352
    sW      0    0.03  2 EVENT            motor/xrfz/position             325.000000610352
    sW      0    0.02  2 EVENT            motor/xrfz/move_done            0
    """

    async with Client("localhost", SERVER_PORT) as client:
        xrfx = client.motor("xrfx")
        xrfz = client.motor("xrfz")

        xrfx_target = 26
        xrfz_target = 325

        async with xrfx, xrfz:
            async with client.synchronized_motors():
                xrfx_current = await xrfx.position.get()
                xrfz_current = await xrfz.position.get()

                await xrfx.move(xrfx_target)
                await xrfz.move(xrfz_target)

                assert await xrfx.position.get() != xrfx_target
                assert await xrfz.position.get() != xrfz_target

            # Note: There appears to be a bug in server mode simulation where the motor position
            # event doesn't actually get updated. So these tests might fail in with SIMULATION mode on.
            assert pytest.approx(xrfx_target, rel=1e-3) == await xrfx.position.get()
            assert pytest.approx(xrfz_target, rel=1e-3) == await xrfz.position.get()
