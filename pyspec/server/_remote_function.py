import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional, TypeVar, Tuple, Union

from pyspec._connection.data import DataType
from pyspec._spec_syntax import parse_function_call, parse_function_name

LOGGER = logging.getLogger("pyspec.server")

SyncOrAsyncCallable = Union[
    Callable[..., DataType], Callable[..., Coroutine[Any, Any, DataType]]
]

F = TypeVar("F", bound=SyncOrAsyncCallable)
SymbolResolver = Callable[[str], Any]


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


def parse_remote_function_name(function_string: str) -> str:
    """
    Parse only the function name from a remote function call string.

    Args:
        function_string (str): The function call string to parse.
    Returns:
        str: The function name.
    """
    try:
        return parse_function_name(function_string)
    except ValueError:
        raise ValueError(f"Invalid function call string: {function_string}")


def parse_remote_function_string(
    function_string: str, resolve_symbol: Optional[SymbolResolver] = None
) -> Tuple[str, Tuple[Any, ...]]:
    """
    Parse a remote function call string into its name and arguments.

    Args:
        function_string (str): The function call string to parse.
        resolve_symbol (SymbolResolver | None): Optional resolver for bare symbol
            arguments, such as SPEC variable names.
    Returns:
        tuple: Tuple of function name and arguments.
    """
    try:
        return parse_function_call(function_string, resolve_symbol=resolve_symbol)
    except ValueError as exc:
        raise ValueError(f"Invalid function call string: {function_string}") from exc


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
    """
    Decorator to mark a function as remotely callable.

    Note: All inputs to the function will be received as strings.

    Args:
        function (F): The function to mark as remote.
    Returns:
        F: The same function, marked as remote.
    """
    mark_remote_function(function)
    if not asyncio.iscoroutinefunction(function):
        LOGGER.warning(
            "Remote function '%s' is not asynchronous. "
            "Consider making it async for better performance.",
            function.__name__,
        )
    return function
