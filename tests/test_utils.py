"""Shared test utilities."""

from typing import Any, Dict


def build_sample_input(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Build minimal sample input from a JSON Schema object."""
    if not schema or schema.get("type") != "object":
        return {}
    sample: Dict[str, Any] = {}
    for key, spec in schema.get("properties", {}).items():
        t = spec.get("type", "string")
        if t in ("number", "integer"):
            sample[key] = 1
        elif t == "boolean":
            sample[key] = True
        elif t == "array":
            sample[key] = []
        elif t == "object":
            sample[key] = {}
        else:
            sample[key] = "test"
    return sample
