from __future__ import annotations

import ast
import asyncio
import logging
from typing import Any, Callable, Coroutine, TypeVar

from pyspec._connection.data import DataType

LOGGER = logging.getLogger("pyspec.server")

SyncOrAsyncCallable = (
    Callable[..., DataType] | Callable[..., Coroutine[Any, Any, DataType]]
)

F = TypeVar("F", bound=SyncOrAsyncCallable)


def mark_remote_function(function: F) -> F:
    """
    Decorator to mark a function as remotely callable.
    :param function: The function to mark as remote.
    :returns: The same function, marked as remote.
    """
    setattr(function, "_is_remote_function", True)
    setattr(function, "_remote_function_name", function.__name__)
    return function


def is_remote_function(function: SyncOrAsyncCallable) -> bool:
    """
    Check if a function is marked as remotely callable.
    :param function: The function to check.
    :returns: True if the function is marked as remote, False otherwise.
    """
    return getattr(function, "_is_remote_function", False)


def remote_function_name(function: SyncOrAsyncCallable) -> str:
    """
    Get the remote function name for a function.
    :param function: The function to get the name for.
    :returns: The remote function name.
    """
    return getattr(function, "_remote_function_name", function.__name__)


def parse_remote_function_string(function_string: str) -> tuple[str, tuple[str, ...]]:
    """
    Parse a remote function call string into its name and arguments.
    :param function_string: The function call string to parse.
    :returns: Tuple of function name and arguments.
    """
    function_string = function_string.strip()
    if "(" not in function_string or not function_string.endswith(")"):
        raise ValueError(f"Invalid function call string: {function_string}")

    name, args_str = function_string[:-1].split("(", 1)

    args_str = args_str.strip()
    if args_str:
        # Use ast.literal_eval to safely parse the arguments
        # This will handle more complex argument types like strings with commas
        # It is a safer and more constrained alternative to eval
        args = ast.literal_eval(f"({args_str},)")
    else:
        args = ()

    return name, args


def build_remote_function_string(
    function_name: str, args: tuple[str | float | int, ...]
) -> str:
    """
    Build a remote function call string from its name and arguments.
    :param function_name: The function name.
    :param args: The arguments to include in the call string.
    :returns: The remote function call string.
    """
    args_str = ", ".join(repr(arg) for arg in args)
    return f"{function_name}({args_str})"


def remote_function(function: F) -> F:
    # TODO: Need to figure out how to type this properly
    # Since the client will only give you strs.
    """
    Decorator to mark a function as remotely callable.
    """
    mark_remote_function(function)
    if not asyncio.iscoroutinefunction(function):
        LOGGER.warning(
            "Remote function '%s' is not asynchronous. "
            "Consider making it async for better performance.",
            function.__name__,
        )
    return function
