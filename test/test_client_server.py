import asyncio
import multiprocessing
import time

import pytest

from pyspec._connection import ClientConnection
from pyspec._connection.connection import RemoteException
from pyspec.server import Server as PyspecServer

HOST = "127.0.0.1"
PORT = 56789


class Server(PyspecServer):
    @PyspecServer.remote_function
    def sum(self, a: str, b: str):
        return float(a) + float(b)

    @PyspecServer.remote_function
    async def async_sum(self, a: str, b: str):
        return float(a) + float(b)

    foo = PyspecServer.Property[int]("foo", 0)

    ticker = PyspecServer.Property[int]("ticker", 0)

    async def tick(self):
        while True:
            await asyncio.sleep(0.1)
            self.ticker.set(self.ticker.get() + 1)

    @PyspecServer.remote_function
    async def long_running_func(self):
        await asyncio.sleep(5)
        return "done"


# Helper to run server in a separate process
def run_server(test_mode=True):
    async def main():
        async with Server(host=HOST, port=PORT, test_mode=test_mode) as server:
            # Set a ticker task so we can watch a property
            asyncio.create_task(server.tick())
            await server.serve_forever()

    asyncio.run(main())


@pytest.fixture()
def server_process():
    proc = multiprocessing.Process(target=run_server)
    proc.start()
    time.sleep(0.05)
    yield
    proc.terminate()
    proc.join()


@pytest.mark.asyncio
async def test_client_connect(server_process):
    async with ClientConnection(HOST, PORT) as client:
        assert client.host == HOST
        assert client.port == PORT


@pytest.mark.asyncio
async def test_command_execution(server_process):
    async with ClientConnection(HOST, PORT) as client:
        # Only works if server is in test_mode
        result = await client.remote_cmd("1+1")
        assert result == 2


@pytest.mark.asyncio
async def test_function_execution_success(server_process):
    async with ClientConnection(HOST, PORT) as client:
        result = await client.remote_func("sum", 1, 2)
        assert result == 3


@pytest.mark.asyncio
async def test_async_function_execution_success(server_process):
    async with ClientConnection(HOST, PORT) as client:
        result = await client.remote_func("async_sum", 1, 2)
        assert result == 3


@pytest.mark.asyncio
async def test_function_execution_not_found(server_process):
    async with ClientConnection(HOST, PORT) as client:
        with pytest.raises(RemoteException):
            result = await client.remote_func("doesnt-exist-on-server", 1, 2)


@pytest.mark.asyncio
async def test_property_read_write(server_process):
    async with ClientConnection(HOST, PORT) as client:
        await client.prop_set("foo", 123)
        value = await client.prop_get("foo")
        assert value == 123


@pytest.mark.asyncio
async def test_property_not_found(server_process):
    async with ClientConnection(HOST, PORT) as client:
        with pytest.raises(RemoteException):
            await client.prop_get("doesnt-exist-on-server")

        # Doesn't raise
        await client.prop_set("doesnt-exist-on-server", 123)
        await client.prop_watch("doesnt-exist-on-server")
        await client.prop_unwatch("doesnt-exist-on-server")


@pytest.mark.asyncio
async def test_property_subscribe(server_process):
    async with ClientConnection(HOST, PORT) as client:
        updates = []
        client.on("property-change", lambda name, value: updates.append((name, value)))
        await client.prop_watch("ticker")
        await client.prop_set("ticker", 42)
        await asyncio.sleep(0.25)
        assert ("ticker", 42) in updates


@pytest.mark.asyncio
async def test_command_and_function_interrupt(server_process):
    async with ClientConnection(HOST, PORT) as client:
        # This is a placeholder; actual interruption logic depends on server implementation
        task = asyncio.create_task(client.remote_func("long_running_func"))
        await asyncio.sleep(0.2)
        await client.abort()
        with pytest.raises(RemoteException):
            await task
