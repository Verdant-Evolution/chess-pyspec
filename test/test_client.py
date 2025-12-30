import pytest
from pyspec.client import Client
from conftest import HOST, PORT


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
        result = await client.exec_function("sum", 2, 3)
        assert result == 5


@pytest.mark.asyncio
async def test_client_exec_command(server_process):
    async with Client(HOST, PORT) as client:
        result = await client.exec("2+2")
        assert result == 4
