import asyncio
from contextlib import suppress

from pyspec.server import Server as PyspecServer, Property, remote_function

import pytest_asyncio
import time
import pytest

HOST = "127.0.0.1"
PORT = 56789


class Server(PyspecServer):
    @remote_function
    def sum(self, a: str, b: str):
        return float(a) + float(b)

    @remote_function
    async def async_sum(self, a: str, b: str):
        return float(a) + float(b)

    foo = Property[int]("foo", 0)

    ticker = Property[int]("ticker", 0)

    flag = Property[int]("flag", 0)

    async def tick(self):
        while True:
            await asyncio.sleep(0.01)
            self.ticker.set(self.ticker.get() + 1)

    @remote_function
    async def long_running_func(self):
        await asyncio.sleep(5)
        return "done"


# Helper to run server in a separate process
async def run_server(test_mode=True):
    async with Server(
        host=HOST, port=PORT, allow_remote_code_execution=test_mode
    ) as server:
        # Set a ticker task so we can watch a property
        asyncio.create_task(server.tick())
        await server.serve_forever()


@pytest_asyncio.fixture()
async def server_process():
    task = asyncio.create_task(run_server())
    await asyncio.sleep(0.01)  # Give the server some time to start up
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
