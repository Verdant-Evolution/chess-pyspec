from contextlib import asynccontextmanager
from pyspec.client._remote_property_table import RemotePropertyTable
import asyncio


class Output:
    def __init__(self, property: RemotePropertyTable.EventStream[str], name: str):
        self._property = property
        self.name = name

    @asynccontextmanager
    async def capture(self, wait_time: float = 0.0):
        """
        Context manager that captures output from the server for the duration of the context.

        Example usage:
            async with client.output("tty").capture() as output:
                await client.exec('print("Hello, world!")')
                assert output[-1] == "Hello, world!\n"
        """
        lines = []
        self._property.on("event", lines.append)
        try:
            async with self._property.subscribed():
                yield lines
                # Wait for any remaining output to be captured before unsubscribing.
                await asyncio.sleep(wait_time)
        finally:
            self._property.remove_listener("event", lines.append)
