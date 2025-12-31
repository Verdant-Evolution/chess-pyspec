from pyspec.server._remote_property import Property


class Motor:
    def __init__(self, name: str):
        self.name = name

    position = Property[float]("position", 0.0)
    dial_position = Property[float]("dial_position", 0.0)
    offset = Property[float]("offset", 0.0)
    step_size = Property[float]("step_size", 1.0)

    async def move_to(self, position: float) -> None:
        raise NotImplementedError("This method should be implemented by subclasses.")
