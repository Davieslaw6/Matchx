"""Lightweight verifier for numeric claims against retrieved tool data."""
import re
from typing import Any

_NUMBER = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?%?(?![A-Za-z])")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")

def _allowed_numbers(value: Any, allowed: set[float]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, (int, float)):
        number = float(value)
        allowed.add(number)
        allowed.add(round(number, 1))
        allowed.add(round(number, 2))
        if 0 <= number <= 1:
            allowed.add(round(number * 100, 1))
            allowed.add(float(round(number * 100)))
        return
    if isinstance(value, str):
        for match in _NUMBER.finditer(value):
            token = match.group().rstrip("%")
            try:
                allowed.add(float(token))
            except ValueError:
                continue
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _allowed_numbers(key, allowed)
            _allowed_numbers(item, allowed)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _allowed_numbers(item, allowed)

def _allowed_dates(value: Any, allowed: set[str]) -> None:
    if isinstance(value, str):
        allowed.update(_DATE.findall(value))
    elif isinstance(value, dict):
        for item in value.values():
            _allowed_dates(item, allowed)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _allowed_dates(item, allowed)

def verify_numeric_grounding(answer: str, tool_results: list[dict[str, Any]]) -> bool:
    """Return false when a numeric/date-like token cannot be matched to retrieved data."""
    allowed: set[float] = set()
    allowed_dates: set[str] = set()
    _allowed_numbers(tool_results, allowed)
    _allowed_dates(tool_results, allowed_dates)
    answer_dates = _DATE.findall(answer)
    if any(value not in allowed_dates for value in answer_dates):
        return False
    answer_without_dates = _DATE.sub("", answer)
    for match in _NUMBER.finditer(answer_without_dates):
        token = match.group()
        is_percent = token.endswith("%")
        try:
            number = float(token.rstrip("%"))
        except ValueError:
            return False
        # Percentages may be rounded to one decimal from probability values.
        tolerance = 0.11 if is_percent else 1e-4
        if not any(abs(number - candidate) <= tolerance for candidate in allowed):
            return False
    return True
