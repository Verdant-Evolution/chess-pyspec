import asyncio
from multiprocessing import Process
import time

HOST = "127.0.0.1"
PORT = 8888


async def handle_client(reader, writer):
    print(f"Client connected: {writer.get_extra_info('peername')}")
    data = await reader.read(100)
    message = data.decode()
    print(f"Server received: {message}")
    writer.write(data)
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def run_server():
    server = await asyncio.start_server(handle_client, HOST, PORT)
    async with server:
        await server.serve_forever()


async def run_client():
    await asyncio.sleep(0.2)  # Give server time to start
    reader, writer = await asyncio.open_connection(HOST, PORT)
    print(f"Client connected to server at {HOST}:{PORT}")
    message = "Hello, server!"
    print(f"Client sending: {message}")
    writer.write(message.encode())
    await writer.drain()
    data = await reader.read(100)
    print(f"Client received: {data.decode()}")
    writer.close()
    await writer.wait_closed()


def server_process():
    asyncio.run(run_server())


def client_process():
    asyncio.run(run_client())


if __name__ == "__main__":
    server = Process(target=server_process)
    server.start()
    time.sleep(0.5)  # Ensure server is up
    client = Process(target=client_process)
    client.start()
    client.join()
    server.terminate()
    server.join()
