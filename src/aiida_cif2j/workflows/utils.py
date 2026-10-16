"""Utility functions for AiiDA CIF2J workflows."""

from aiida.orm import List
from aiida.orm.nodes.data.structure import is_valid_symbol


def validate_chemical_symbols(value: List | None, _) -> str | None:
    """Validate a list of elements."""
    if value is not None:
        if len(value) < 1:
            return "Element list must not be empty."
        if all(is_valid_symbol(symbol) for symbol in value):
            return None
        return f"Invalid element in list: {list(value)}."
    return None
