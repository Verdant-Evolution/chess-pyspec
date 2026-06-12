import pytest
from pyspec.client import Client
from pyspec._connection.client_connection import build_remote_function_string
from pyspec._connection.client_connection import RemoteException
from conftest import HOST, PORT
import asyncio


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_client_property_read_write(server_process):
    async with Client(HOST, PORT) as client:
        foo = client._property("foo", int)
        await foo.set(123)
        value = await foo.get()
        assert value == 123


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_client_property_get_next(server_process):
    async with (
        Client(HOST, PORT) as client,
        client._property("ticker", int).subscribed() as ticker,
    ):
        current_value = await ticker.get_next()
        next_value = await ticker.get_next()
        assert current_value + 1 == next_value


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_client_exec_function(server_process):
    async with Client(HOST, PORT) as client:
        result = await client.call("sum", 2, 3)
        assert result == 5


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_client_exec_function_with_var_property_reference(server_process):
    async with Client(HOST, PORT) as client:
        temp = client.var("TEMP", int)
        await temp.set(40)
        result = await client.call("sum", temp, 2)
        assert result == 42


def test_remote_function_string_uses_only_var_property_references():
    client = Client(HOST, PORT)
    temp = client.var("TEMP", int)
    foo = client._property("foo", int)

    assert build_remote_function_string("sum", temp, 2) == "sum(TEMP, 2)"
    with pytest.raises(ValueError):
        build_remote_function_string("sum", foo, 2)


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_client_exec_command(server_process):
    async with Client(HOST, PORT) as client:
        result = await client.exec("2+2")
        assert result == 4


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_client_exec_command_invalid_syntax(server_process):
    async with Client(HOST, PORT) as client:
        with pytest.raises(RemoteException, match=r"line 1"):
            await client.exec("sum(1,")


@pytest.mark.asyncio
@pytest.mark.timeout(2)
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
@pytest.mark.timeout(2)
async def test_client_property_get_when_subscribed(server_process):
    async with (
        Client(HOST, PORT) as client,
        client._property("foo", int).subscribed() as foo,
    ):
        await foo.set(123)
        value = await foo.get()
        assert value == 123


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_client_property_get_next_when_subscribed(server_process):
    async with (
        Client(HOST, PORT) as client,
        client._property("ticker", int).subscribed() as ticker,
    ):
        current_value = await ticker.get_next()
        next_value = await ticker.get_next()
        assert next_value == current_value + 1


@pytest.mark.asyncio
@pytest.mark.timeout(2)
async def test_client_boolean_property(server_process):
    async with (
        Client(HOST, PORT) as client,
        client._property("flag", bool).subscribed() as flag,
    ):
        await flag.set(True)
        value = await flag.get()
        assert value is True

        await flag.set(False)
        value = await flag.get()
        assert value is False
