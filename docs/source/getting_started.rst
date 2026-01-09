Getting Started
===============

This page provides a quick introduction to using the PySpec package. For more detailed information, please refer to the `API documentation <https://pyspec.readthedocs.io/en/latest/>`_ and the `SPEC server/client documentation <https://certif.com/spec_help/server.html>`_.

Installation
----------------
You can install the PySpec package using pip:

.. code-block:: bash

   pip install pyspec


Starting a SPEC Server
----------------------
To start a SPEC server, you can run spec with the ``-s`` flag:

.. code-block:: bash

    # Listen on the default port range (6510-6530)
    spec -S

    # Listen on a specific port
    spec -S 6510

    # Listen on a specific port range
    spec -S 6510-6520

    # Restrict to specific host(s) (version 6.07.01)
    # Allows the server to accept connections from 
    #   192.168.1.*
    #   172.33.20.10
    spec -S 6510-6520 -A 192.168.1.0/24 -A 172.33.20.10

Basic Usage
----------------
To use the PySpec client to connect to a SPEC server, you can do the following:

.. code-block:: python

    from pyspec.client import Client
    
    async def main():
        async with Client(host='localhost', port=6510) as client:
            # Get the current status of the server
            status = await client.get_status()
            print(await status.to_str())


    if __name__ == "__main__":
        import asyncio
        asyncio.run(main())

Moving a Motor
---------------
To move a motor using the PySpec client, you can use the `move` method:

.. code-block:: python

    from pyspec.client import Client
    
    async def main():
        async with (
            Client(host='localhost', port=6510) as client,
            client.motor('m1') as motor
        ):
            # Move motor 'm1' to position 10.0
            await motor.move(10.0)

    if __name__ == "__main__":
        import asyncio
        asyncio.run(main())


For more advanced usage, refer to the :doc:`Client API </pyspec.client>`  or the :doc:`Client Usage </client_usage>` documentation.