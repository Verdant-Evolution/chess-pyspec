from __future__ import annotations

import ast
from typing import Any, Callable, Coroutine, TypeVar

from pyspec._connection.data_types import DataType

SyncOrAsyncCallable = (
    Callable[..., DataType] | Callable[..., Coroutine[Any, Any, DataType]]
)

F = TypeVar("F", bound=SyncOrAsyncCallable)


def mark_remote_function(function: F) -> F:
    """Decorator to mark a function as remotely callable."""
    setattr(function, "_is_remote_function", True)
    setattr(function, "_remote_function_name", function.__name__)
    return function


def is_remote_function(function: SyncOrAsyncCallable) -> bool:
    return getattr(function, "_is_remote_function", False)


def remote_function_name(function: SyncOrAsyncCallable) -> str:
    return getattr(function, "_remote_function_name", function.__name__)


def parse_remote_function_string(function_string: str) -> tuple[str, tuple[str, ...]]:
    """Parse a remote function call string into its name and arguments."""
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
    """Build a remote function call string from its name and arguments."""
    args_str = ", ".join(repr(arg) for arg in args)
    return f"{function_name}({args_str})"
