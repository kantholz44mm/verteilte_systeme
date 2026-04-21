from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Union


Number = Union[int, float]


class OperationValidationError(ValueError):
    """Raised when operation parameters are invalid."""


@dataclass(frozen=True)
class OperationDefinition:
    name: str
    description: str
    expression: str
    default_cost: int
    evaluator: Callable[..., Number]


def _ensure_number(value: object, argument_name: str) -> Number:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OperationValidationError(f"'{argument_name}' must be a number.")
    return value


def _ensure_integer(value: object, argument_name: str) -> int:
    value = _ensure_number(value, argument_name)
    if isinstance(value, float) and not value.is_integer():
        raise OperationValidationError(f"'{argument_name}' must be an integer.")
    return int(value)


def addition(a: object, b: object) -> Number:
    return _ensure_number(a, "a") + _ensure_number(b, "b")


def subtraction(a: object, b: object) -> Number:
    return _ensure_number(a, "a") - _ensure_number(b, "b")


def multiplication(a: object, b: object) -> Number:
    return _ensure_number(a, "a") * _ensure_number(b, "b")


def division(a: object, b: object) -> Number:
    numerator = _ensure_number(a, "a")
    denominator = _ensure_number(b, "b")
    if denominator == 0:
        raise OperationValidationError("Division by zero is not allowed.")
    return numerator / denominator


def factorial(a: object) -> int:
    number = _ensure_integer(a, "a")
    if number < 0:
        raise OperationValidationError("'a' must not be negative.")
    return math.factorial(number)


def power(a: object, b: object) -> Number:
    base = _ensure_number(a, "a")
    exponent = _ensure_number(b, "b")
    return base ** exponent


DEFAULT_OPERATION_DEFINITIONS: Dict[str, OperationDefinition] = {
    "addition": OperationDefinition(
        name="addition",
        description="Adds two numbers.",
        expression="a + b",
        default_cost=2,
        evaluator=addition,
    ),
    "subtraction": OperationDefinition(
        name="subtraction",
        description="Subtracts b from a.",
        expression="a - b",
        default_cost=3,
        evaluator=subtraction,
    ),
    "multiplication": OperationDefinition(
        name="multiplication",
        description="Multiplies two numbers.",
        expression="a * b",
        default_cost=25,
        evaluator=multiplication,
    ),
    "division": OperationDefinition(
        name="division",
        description="Divides a by b.",
        expression="a / b",
        default_cost=50,
        evaluator=division,
    ),
    "factorial": OperationDefinition(
        name="factorial",
        description="Calculates the factorial of a.",
        expression="a!",
        default_cost=100,
        evaluator=factorial,
    ),
    "power": OperationDefinition(
        name="power",
        description="Raises a to the power of b.",
        expression="a^b",
        default_cost=1150,
        evaluator=power,
    ),
}


def default_operation_names() -> List[str]:
    return list(DEFAULT_OPERATION_DEFINITIONS.keys())

