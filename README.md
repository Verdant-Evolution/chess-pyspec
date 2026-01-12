# Test status badge

![Test](https://github.com/Verdant-Evolution/chess-pyspec/actions/workflows/test.yml/badge.svg)

# PySpec

PySpec is a Python implementation of the [SPEC server and client protocol](https://certif.com/spec_help/server.html), providing tools for remote control, data acquisition, and automation in scientific instrumentation environments. It enables Python-based clients to interact with a SPEC server, control motors, read/write variables, and execute commands or functions remotely.

## Features

-   **Async client-server architecture** for high-performance remote control
-   **Remote property and function access** (read/write variables, call functions)
-   **Motor control** and status monitoring
-   **Associative array and data array support**

## Installation

PySpec requires Python 3.9+ and depends on `cython`, `h5py`, `numpy`, and `pyee`.

```bash
pip install chess-pyspec

# or for development
git clone https://github.com/Verdant-Evolution/chess-pyspec
cd chess-pyspec
pip install -e .[dev]
```

## Quick Start

### Connecting as a Client

```python
import asyncio
from pyspec.client import Client

async def main():
    async with Client("127.0.0.1", 6510) as client:
        # Get a reference to "var/foo" on the server.
        foo = client.var("foo", int)
        await foo.set(42)
        value = await foo.get()
        print("foo:", value) # foo: 42

        result = await client.call("add", 2, 3)
        print("add(2, 3):", result)


        # Wait for properties to be set to specific values
        await foo.wait_for(15, timeout=10)


asyncio.run(main())
```

### Motor Control Example

```python
async with Client("127.0.0.1", 6510) as client:
    motor = client.motor("theta")

    # Read and write motor properties and parameters
    await motor.sign.get()
    await motor.offset.get()
    await motor.position.get()
    ...

    # Move motors on the server
    async with motor:
        await motor.move(10.0)
        pos = await motor.position.get()
        print("Motor position:", pos) # "Motor position: 10.0"
```

### Output Streaming Example

```python
async with Client("127.0.0.1", 6510) as client:
    async with client.output("tty").capture() as lines:
        await client.exec('print("Hello, world!")')
    print(lines[-1])  # Should print 'Hello, world!\n'
```

### Starting a Server

```python
from pyspec.server import Server, Property, remote_function
import asyncio

class MyServer(Server):
    foo = Property[int]("foo", 0)

    @remote_function
    def add(self, a: str, b: str):
        return float(a) + float(b)

async def main():
    async with MyServer(host="127.0.0.1", port=6510, test_mode=True) as server:
        await server.serve_forever()

asyncio.run(main())
```

Hardware servers currently support properties and remote function calls. Connect with a `PySpec` or `spec` client to interface with a `PySpec` server.

Currently unsupported server features:

1. Associative Arrays
2. Motor Protocols (through `../start_one` or `../start_all` )

## Testing

Run the test suite with:

```bash
pytest
```

## Documentation

See the [docs/](docs/) directory for full API documentation and usage details.

## License

See LICENSE or the source headers for license details. Portions copyright Certified Scientific Software.
