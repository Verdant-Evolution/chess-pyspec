

Client Usage
============

This document provides an overview of how to use the PySpec client to interact with a SPEC server.

Overview
--------

The PySpec client allows you to connect to a SPEC server, send commands, interact with remote properties, and subscribe to updates. It is designed for asynchronous and event-driven programming.

Key Concepts
------------

- **Client Class**: The main entry point is the :py:class:`Client <pyspec.client.Client>` class, which manages the connection to the server and provides interfaces for commands, properties, and domains.
- **Domains**: The client exposes domain-specific interfaces such as :py:meth:`status <pyspec.client.Client.status>`, :py:meth:`motor <pyspec.client.Client.motor>`, :py:meth:`count <pyspec.client.Client.count>`, and :py:meth:`output <pyspec.client.Client.output>` for interacting with different parts of the SPEC data model.
- **Remote Functions and Commands**: Use :py:meth:`client.call <pyspec.client.Client.call>` to invoke server functions and :py:meth:`client.exec <pyspec.client.Client.exec>` to execute raw commands.
- **Properties**: Properties can be read, written, and subscribed to for updates. The client provides Pythonic interfaces for all property types.

Example Usage
-------------

.. code-block:: python

    from pyspec.client import Client
    import asyncio

    async def main():
        async with Client(host='localhost', port=6510) as client:
            # The HELLO is sent automatically when connecting.
            # You can now interact with the server:
            result = await client.call('add', 1, 2)
            print("add(1, 2) =", result)

            # Access a SPEC variable
            x = client.var('x')
            await x.set("Hello from client!")
            print(await x.get())

    if __name__ == "__main__":
        asyncio.run(main())

Features
--------

- **Domain Interfaces**: Access server domains via :py:meth:`status <pyspec.client.Client.status>`, :py:meth:`motor <pyspec.client.Client.motor>`, :py:meth:`count <pyspec.client.Client.count>`, and :py:meth:`output <pyspec.client.Client.output>`.
- **Remote Function Calls**: Use `client.call` to invoke server-side functions with arguments.
- **Raw Command Execution**: Use `client.exec` to send complex or multi-line commands to the server.
- **Property Access**: Get, set, and subscribe to properties using Pythonic interfaces.
- **Associative Arrays**: Access and manipulate SPEC associative arrays as Python dictionaries.
- **Event-Driven Programming**: Subscribe to property changes and handle updates asynchronously.

API Reference
-------------

- :py:class:`Client <pyspec.client.Client>` : Main client class for connecting and interacting with the server.
- :py:class:`Property <pyspec.client.Property>` : Represents a property that supports get, set, and subscribe.
- :py:class:`ReadableProperty <pyspec.client.ReadableProperty>` : Represents a read-only property.
- :py:class:`WritableProperty <pyspec.client.WritableProperty>` : Represents a write-only property.
- :py:class:`EventStream <pyspec.client.EventStream>` : Represents an event stream property.
- :py:meth:`client.call(function_name, *args) <pyspec.client.Client.call>` : Call a remote function on the server.
- :py:meth:`client.exec(command) <pyspec.client.Client.exec>` : Execute a raw command on the server.


Connection
----------------

The :py:class:`Client <pyspec.client.Client>` class in the :py:mod:`pyspec.client` subpackage provides an interface for connecting to a SPEC server and sending commands. You can create an instance of the :py:class:`Client <pyspec.client.Client>` class and use it to connect to a server by providing the host and port information. The client uses asynchronous programming, so you will need to use **async** and **await** when working with it.

.. code-block:: python

    from pyspec.client import Client
    
    async def main():
        async with Client(host='localhost', port=6510) as client:
            # The HELLO is sent automatically when connecting.
            # An error will be raised if the server does not respond with a HELLO_REPLY message.


    if __name__ == "__main__":
        import asyncio
        asyncio.run(main())



Properties
----------

The core concept of the SPEC data model is the property. While connected to a SPEC server, there are 3 operations that a property can support:

1. **get**: Get the current value of the property from the server.
2. **set**: Set the value of the property on the server.
3. **subscribe** / **unsubscribe**: Subscribe to updates for the property from the server. Changes will automatically be pushed to the client.

Properties fall into a couple of different categories depending on which interfaces they support. Some properties are `read-only`, meaning that they support **get** and **subscribe**, but not **set**. Some properties are `write-only`, meaning that they support **set**, but not **get** or **subscribe**. Some properties are `event-only`, meaning that they don't represent a single value or state, but instead a stream of events and only implement **subscribe**. Lastly, some properties support all interfaces. When interfacing with the `Client` object, you will encounter these properties through the python types:

- :py:class:`Property <pyspec.client.Property>`: A property that supports **get**, **set**, and **subscribe**.
- :py:class:`ReadableProperty <pyspec.client.ReadableProperty>`: A property that supports **get** and **subscribe**, but not **set**.
- :py:class:`WritableProperty <pyspec.client.WritableProperty>`: A property that supports **set**, but not **get** or **subscribe**.
- :py:class:`EventStream <pyspec.client.EventStream>`: A property that only supports **subscribe**.

Property Types
--------------

Properties in SPEC can be:

- **Read-Write-Subscribe**: Full interface (get, set, subscribe) (ex. **var/x**).
- **Read-Only**: Only get and subscribe (ex. **motor/mne/position**).
- **Write-Only**: Only set (ex. **motor/mne/start_one**).
- **Event-Only**: Only subscribe (stream of events) (ex. **output/tty**).


Working with Variables and Associative Arrays
---------------------------------------------


One of the most common direct interface with properties is when accessing SPEC variables stored under **var/...** on the server. These can be accessed by name through the `client.var` interface. Variables in SPEC will implement the full read-write-subscribe interface.


Example:

.. code-block:: none

    69.SPEC_sim> x = "This is a spec variable"
    x = "This is a spec variable"


.. code-block:: python

    # Get a reference to the variable 'x' on the server. 
    # This does not retrieve the value of x,
    # but instead gives you an interface to interact with it.
    x = client.var('x')

    print(await x.get()) # Output: "This is a spec variable"


Associative arrays are handled similarly:

.. code-block:: spec
    69.SPEC_sim> a["key"] = "Value at key"
    a["key"] = "Value at key"

.. code-block:: python

    a = client.var('a')
    a_key = client.var('a[key]')
    print(await a.get()) # Output: {"key": "Value at key"}
    print(await a_key.get()) # Output: "Value at key"


Writing associative array values back to the server is batched by default, so to update the server, you have to do the following:


.. code-block:: python

    a = client.var('a')
    # Get the current value of the associative array
    associative_array = await a.get()  
    for i in range(10):
        associative_array[i] = f"value at {i}"

    # Write the updated associative array back to the server
    await a.set(associative_array)  

.. note::
   SPEC transforms all associative array keys into strings. Keys like "1" and "1.00000001" will map to the same key.

Event-Based Programming
----------------------

You can subscribe to property changes and handle updates asynchronously:

.. code-block:: python

    x = client.var('x')
    x.on("change", print)
    async with x.subscribed():
        await asyncio.Future()  # Wait forever


.. code-block:: spec

    69.SPEC_sim> x = "Hello"
    x = "Hello"

    # The client will print:
    # "Hello"

To record all changes in a list:

.. code-block:: python

    x = client.var('x')
    async with x.capture() as changes:
        await asyncio.sleep(10)
    # 'changes' is now a list of all values x took during those 10 seconds.
