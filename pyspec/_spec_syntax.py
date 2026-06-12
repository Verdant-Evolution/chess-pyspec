"""
Shared parser/evaluator for SPEC command strings used by PySpec client/server APIs.

This module intentionally accepts a narrow, Python-parseable subset of expressions:

- scalar literals (`1`, `1.5`, `'abc'`, `True`, `None`)
- container literals (`[1, 2]`, `(1, 2)`, `{'k': 1}`, `{1, 2}`)
- symbol references (`TEMP`)
- indexed symbol access (`NUMBERS[1]`, `LOOKUP['alpha']`)
- function-call form for remote function dispatch (`sum(1, TEMP)`)

This is not a full SPEC parser. In particular, SPEC macro-command syntax that is not
valid Python expression syntax (for example, whitespace-style macro invocation such as
``umv th 1``) is rejected.

References:
- SPEC server/client protocol help: https://certif.com/spec_help/server.html
- SPEC macro language help: https://www.certif.com/spec_help/macros.html
"""

import ast
from typing import Any, Callable, Optional, Tuple


class SpecSyntaxError(ValueError):
    """
    Raised when a SPEC expression cannot be parsed or safely resolved.
    """


SymbolResolver = Callable[[str], Any]


def _format_syntax_error(expression: str, exc: SyntaxError) -> str:
    location = f"line {exc.lineno}, column {exc.offset}" if exc.offset else "unknown location"
    detail = exc.msg or "invalid syntax"
    return f"{detail} at {location}: {expression!r}"


def parse_spec_expression(expression: str) -> ast.Expression:
    text = expression.strip()
    if not text:
        raise SpecSyntaxError("Command cannot be empty.")
    try:
        node = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise SpecSyntaxError(_format_syntax_error(text, exc)) from exc
    return node


def validate_spec_expression(expression: str) -> None:
    parse_spec_expression(expression)


def parse_function_name(expression: str) -> str:
    node = parse_spec_expression(expression)
    call = node.body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        raise SpecSyntaxError(f"Expected a function call expression: {expression!r}")
    return call.func.id


def _evaluate_expression_node(
    node: ast.AST, resolve_symbol: Optional[SymbolResolver] = None
) -> Any:
    if isinstance(node, ast.Constant):
        return node.value

    if isinstance(node, ast.Tuple):
        return tuple(_evaluate_expression_node(elt, resolve_symbol) for elt in node.elts)

    if isinstance(node, ast.List):
        return [_evaluate_expression_node(elt, resolve_symbol) for elt in node.elts]

    if isinstance(node, ast.Set):
        return {_evaluate_expression_node(elt, resolve_symbol) for elt in node.elts}

    if isinstance(node, ast.Dict):
        return {
            _evaluate_expression_node(key, resolve_symbol): _evaluate_expression_node(
                value, resolve_symbol
            )
            for key, value in zip(node.keys, node.values)
        }

    if isinstance(node, ast.Name):
        if resolve_symbol is None:
            raise SpecSyntaxError(f"Unresolved symbol: {node.id!r}")
        return resolve_symbol(node.id)

    if isinstance(node, ast.Subscript):
        value = _evaluate_expression_node(node.value, resolve_symbol)
        key = _evaluate_expression_node(node.slice, resolve_symbol)
        try:
            return value[key]
        except Exception as exc:  # noqa: BLE001
            raise SpecSyntaxError(
                f"Unable to resolve array index {ast.unparse(node)!r}: {exc}"
            ) from exc

    raise SpecSyntaxError(
        f"Unsupported SPEC expression node: {type(node).__name__} in {ast.unparse(node)!r}"
    )


def parse_function_call(
    expression: str, resolve_symbol: Optional[SymbolResolver] = None
) -> Tuple[str, Tuple[Any, ...]]:
    node = parse_spec_expression(expression)
    call = node.body
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        raise SpecSyntaxError(f"Expected a function call expression: {expression!r}")
    if call.keywords:
        raise SpecSyntaxError(
            f"Keyword arguments are not supported in SPEC function calls: {expression!r}"
        )

    args = tuple(_evaluate_expression_node(arg, resolve_symbol) for arg in call.args)
    return call.func.id, args


def evaluate_spec_expression(
    expression: str, resolve_symbol: Optional[SymbolResolver] = None
) -> Any:
    node = parse_spec_expression(expression)
    return _evaluate_expression_node(node.body, resolve_symbol)
