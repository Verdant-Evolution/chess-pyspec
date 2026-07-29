Server Usage
================


This document provides an overview of how to use the PySpec server to implement a custom SPEC server.


Overview
--------

The PySpec server allows remote clients to interact with Python objects and functions as if they were part of a SPEC server. It supports remote function calls, property access, and event broadcasting.

Key Concepts
------------

- **Server Class**: The main entry point is the :py:class:`Server <pyspec.server.Server>` class, which manages client connections, remote function calls, and property updates.
- **Remote Functions**: Methods decorated with :py:func:`@remote_function <pyspec.server.remote_function>` are exposed to clients for remote execution.
- **Remote Properties**: Properties defined using the :py:class:`Property <pyspec.server.Property>` class can be accessed and updated remotely.
- **Event Broadcasting**: Property changes are broadcast to subscribed clients.

Example Usage
-------------

.. code-block:: python

    from pyspec.server import Server, Property, remote_function

    class MySpecServer(Server):
        my_property = Property(name="my_property", default=0)

        @remote_function
        def add(self, a: str, b: str):
            return float(a) + float(b)

    async def main():
        async with MySpecServer(host="localhost", port=12345) as server:
            await server.serve_forever()


SPEC Client Side:

.. code-block:: spec

    >> host = "localhost:12345"
    >> remote_par(host, "connect")
    # Now the connection should be established.
    >> property_get(host, "my_property")
    0
    >> property_put(host, "my_property", 42)
    >> property_get(host, "my_property")
    42
    >> remote_cmd(host, "add(1, 2)")
    3.0



PySpec Client Side (Python):

.. code-block:: python

    from pyspec.client import Client
    import asyncio

    async def main():
        async with Client(host='localhost', port=12345) as client:
            print(await client.call('add', 1, 2)) # Should print 3.0
            x = client.var('my_property')
            print(await x.get())  # Should print 0
            await x.set(42)
            print(await x.get())  # Should print 42

    if __name__ == "__main__":
        asyncio.run(main())
Features
--------

- **Remote Function Calls**: Register functions with the :py:func:`@remote_function <pyspec.server.remote_function>` decorator. Clients can call these functions remotely.
- **Remote Properties**: Use the :py:class:`Property <pyspec.server.Property>` class to define properties. Clients can get, set, and subscribe to property changes.
- **Test Mode**: If `test_mode=True`, arbitrary code execution is allowed (for testing only).
- **Abortable Tasks**: Long-running tasks can be aborted by clients.

API Reference
-------------

- :py:class:`Server <pyspec.server.Server>`: Main server class. Handles connections and dispatches remote calls.
- :py:class:`Property <pyspec.server.Property>`: Defines a remotely accessible property.
- :py:func:`@remote_function <pyspec.server.remote_function>`: Decorator to expose methods for remote execution.

Notes
-----

- Always use caution with ``allow_remote_code_execution=True`` as it allows arbitrary code execution. If disabled (default) only literal values through `ast.literal_eval <https://docs.python.org/3/library/ast.html#ast.literal_eval>`_ can be evaluated from client inputs, which is much safer for production use.
- The server uses asyncio for concurrency and can handle multiple clients.


