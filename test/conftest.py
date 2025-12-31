import asyncio

from pyspec.server import Server as PyspecServer
import multiprocessing
import time
import pytest

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
            await asyncio.sleep(0.01)
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
