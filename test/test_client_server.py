import asyncio
import multiprocessing

import pytest

from pyspec._connection import ClientConnection
from pyspec.server import Server as PyspecServer

HOST = "127.0.0.1"
PORT = 56789


class Server(PyspecServer):
    @PyspecServer.remote_function
    def sum(self, a: str, b: str):
        return float(a) + float(b)

    def uhh(self):
        return "This is not a remote function"


# Helper to run server in a separate process
def run_server(test_mode=True):
    async def main():
        async with Server(host=HOST, port=PORT, test_mode=test_mode) as server:
            await server.serve_forever()

    asyncio.run(main())


@pytest.fixture()
def server_process():
    proc = multiprocessing.Process(target=run_server)
    proc.start()
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


# @pytest.mark.asyncio
# async def test_property_read_write(server_process):
#     async with ClientConnection(HOST, PORT) as client:
#         await client.prop_set("foo", 123)
#         value = await client.prop_get("foo")
#         assert value == 123


# @pytest.mark.asyncio
# async def test_property_subscribe(server_process):
#     async with ClientConnection(HOST, PORT) as client:
#         # Only works if server has a property 'bar' defined
#         updates = []

#         async def on_update(value):
#             updates.append(value)

#         client.on("property-change", lambda name, value: updates.append((name, value)))
#         try:
#             await client.prop_watch("bar")
#             await client.prop_set("bar", 42)
#             await asyncio.sleep(0.5)
#             assert ("bar", 42) in updates
#         except Exception:
#             pytest.skip("No property 'bar' defined on server.")


# @pytest.mark.asyncio
# async def test_command_and_function_interrupt(server_process):
#     async with ClientConnection(HOST, PORT) as client:
#         # This is a placeholder; actual interruption logic depends on server implementation
#         try:
#             task = asyncio.create_task(client.remote_func("long_running_func"))
#             await asyncio.sleep(0.2)
#             await client.abort()
#             with pytest.raises(asyncio.CancelledError):
#                 await task
#         except Exception:
#             pytest.skip("No long_running_func or abort support on server.")
