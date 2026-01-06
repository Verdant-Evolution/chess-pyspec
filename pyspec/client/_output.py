from contextlib import asynccontextmanager
from pyspec.client._remote_property_table import RemotePropertyTable


class Output:
    def __init__(self, property: RemotePropertyTable.ReadableProperty[str], name: str):
        self._property = property
        self.name = name

    @asynccontextmanager
    async def capture(self):
        """
        Context manager that captures output from the server for the duration of the context.

        Example usage:
            async with client.output("tty").capture() as output:
                await client.exec('print("Hello, world!")')
                assert output[-1] == "Hello, world!\n"
        """
        lines = []
        self._property.on("change", lines.append)
        try:
            async with self._property.subscribed():
                yield lines
        finally:
            self._property.remove_listener("change", lines.append)
