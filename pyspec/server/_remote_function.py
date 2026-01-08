

import ast
import asyncio
import logging
from typing import Any, Callable, Coroutine, TypeVar, Tuple, Union

from pyspec._connection.data import DataType

LOGGER = logging.getLogger("pyspec.server")

SyncOrAsyncCallable = Union[
    Callable[..., DataType], Callable[..., Coroutine[Any, Any, DataType]]
]

F = TypeVar("F", bound=SyncOrAsyncCallable)


def mark_remote_function(function: F) -> F:
    """
    Decorator to mark a function as remotely callable.

    Args:
        function (F): The function to mark as remote.
    Returns:
        F: The same function, marked as remote.
    """
    setattr(function, "_is_remote_function", True)
    setattr(function, "_remote_function_name", function.__name__)
    return function


def is_remote_function(function: SyncOrAsyncCallable) -> bool:
    """
    Check if a function is marked as remotely callable.

    Args:
        function (SyncOrAsyncCallable): The function to check.
    Returns:
        bool: True if the function is marked as remote, False otherwise.
    """
    return getattr(function, "_is_remote_function", False)


def remote_function_name(function: SyncOrAsyncCallable) -> str:
    """
    Get the remote function name for a function.

    Args:
        function (SyncOrAsyncCallable): The function to get the name for.
    Returns:
        str: The remote function name.
    """
    return getattr(function, "_remote_function_name", function.__name__)


def parse_remote_function_string(function_string: str) -> Tuple[str, Tuple[str, ...]]:
    """
    Parse a remote function call string into its name and arguments.

    Args:
        function_string (str): The function call string to parse.
    Returns:
        tuple: Tuple of function name and arguments.
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
    function_name: str, args: Tuple[Union[str, float, int], ...]
) -> str:
    """
    Build a remote function call string from its name and arguments.

    Args:
        function_name (str): The function name.
        args (tuple): The arguments to include in the call string.
    Returns:
        str: The remote function call string.
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
