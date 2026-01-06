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
        async with client.motor("s0v") as s0v:
            await s0v.move(0)
            assert await s0v.position.get() == 0


@pytest.mark.asyncio
async def test_sync_motors():
    async with Client("localhost", SERVER_PORT) as client:
        async with client.motor("s0v") as s0v, client.motor("s1v") as s1v:
            await asyncio.sleep(1)
            async with client.synchronized_motors():
                await s0v.move(1)
                await s1v.move(1)

            assert await s0v.position.get() == 0
            assert await s1v.position.get() == 0
