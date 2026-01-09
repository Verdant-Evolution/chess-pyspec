PySpec package
==============

The PySpec package imploements the communication protocol for SPEC Clients and SPEC Servers described in `spec server/client <https://certif.com/spec_help/server.html>`_. This package is largely inspired by and builds on top of the `certif-pyspec <https://pypi.org/project/certif-pyspec/>`_ package, but is a complete reimplementation.

The project is broken down into two user facing subpackages, ``pyspec.client`` and ``pyspec.server``, which implement the client and server sides of the protocol, respectively. There is also a third subpackage, ``pyspec.file``, which provides utilities for working with SPEC files. The expectation is that most users will only want to interact with the client subpackage as a way to interact with SPEC servers from Python.


Manual
------

* Tutorials

  * :doc:`/getting_started`
  * :doc:`/client_usage`
  * :doc:`/server_usage`




Subpackages
-----------

.. toctree::
   :maxdepth: 1

   
   pyspec.client
   pyspec.server
   pyspec.file

