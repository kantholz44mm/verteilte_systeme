from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Union


Number = Union[int, float]


def addition(a: object, b: object) -> Number:
    return a + b


def subtraction(a: object, b: object) -> Number:
    return a - b


def multiplication(a: object, b: object) -> Number:
    return a * b


def division(a: object, b: object) -> Number:
    return a / b


def factorial(a: object) -> int:
    return math.factorial(a)


def power(a: object, b: object) -> Number:
    return a ** b


DEFAULT_OPERATION_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "addition": {
        "name": "addition",
        "description": "Adds two numbers.",
        "expression": "a + b",
        "default_cost": 2,
        "evaluator": addition,
    },
    "subtraction": {
        "name": "subtraction",
        "description": "Subtracts b from a.",
        "expression": "a - b",
        "default_cost": 3,
        "evaluator": subtraction,
    },
    "multiplication": {
        "name": "multiplication",
        "description": "Multiplies two numbers.",
        "expression": "a * b",
        "default_cost": 25,
        "evaluator": multiplication,
    },
    "division": {
        "name": "division",
        "description": "Divides a by b.",
        "expression": "a / b",
        "default_cost": 50,
        "evaluator": division,
    },
    "factorial": {
        "name": "factorial",
        "description": "Calculates the factorial of a.",
        "expression": "a!",
        "default_cost": 100,
        "evaluator": factorial,
    },
    "power": {
        "name": "power",
        "description": "Raises a to the power of b.",
        "expression": "a^b",
        "default_cost": 1150,
        "evaluator": power,
    },
}


def default_operation_names() -> List[str]:
    return list(DEFAULT_OPERATION_DEFINITIONS.keys())
