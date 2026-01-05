import pytest
from pyspec.client import Client
from conftest import HOST, PORT
import asyncio


@pytest.mark.asyncio
async def test_client_property_read_write(server_process):
    async with Client(HOST, PORT) as client:
        foo = client._property("foo", int)
        await foo.set(123)
        value = await foo.get()
        assert value == 123


@pytest.mark.asyncio
async def test_client_property_get_next(server_process):
    async with (
        Client(HOST, PORT) as client,
        client._property("ticker", int).subscribed() as ticker,
    ):
        current_value = await ticker.get_next()
        next_value = await ticker.get_next()
        assert current_value + 1 == next_value


@pytest.mark.asyncio
async def test_client_exec_function(server_process):
    async with Client(HOST, PORT) as client:
        result = await client.call("sum", 2, 3)
        assert result == 5


@pytest.mark.asyncio
async def test_client_exec_command(server_process):
    async with Client(HOST, PORT) as client:
        result = await client.exec("2+2")
        assert result == 4


@pytest.mark.asyncio
async def test_client_property_wait_for(server_process):
    async with (
        Client(HOST, PORT) as client,
        client._property("ticker", int).subscribed() as ticker,
        client._property("foo", int).subscribed() as foo,
    ):
        await ticker.set(42)
        async with ticker.wait_for(45):
            pass

        assert await ticker.get() == 45
        await ticker.set(99)
        await ticker.wait_for(105)
        assert await ticker.get() == 105

        async with foo.wait_for(10, timeout=1):
            await foo.set(10)

        with pytest.raises(asyncio.TimeoutError):
            async with foo.wait_for(20, timeout=0.1):
                # We won't set foo to 20, so this should timeout
                pass


@pytest.mark.asyncio
async def test_client_property_get_when_subscribed(server_process):
    async with (
        Client(HOST, PORT) as client,
        client._property("foo", int).subscribed() as foo,
    ):
        await foo.set(123)
        value = await foo.get()
        assert value == 123


@pytest.mark.asyncio
async def test_client_property_get_next_when_subscribed(server_process):
    async with (
        Client(HOST, PORT) as client,
        client._property("ticker", int).subscribed() as ticker,
    ):
        current_value = await ticker.get_next()
        next_value = await ticker.get_next()
        assert next_value == current_value + 1
