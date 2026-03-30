"""Template engine for resolving ``{{ }}`` expressions against runtime data.

Supported namespaces::

    {{ trigger.<path> }}                     - trigger data supplied when execution started
    {{ steps.<step_id>.output }}             - output of a completed step
    {{ steps.<step_id>.output.<key> }}
    {{ context.<key> }}                      - value from the context bus

Condition expressions support:

- Comparisons: ``==``, ``!=``, ``>``, ``<``, ``>=``, ``<=``
- Logical: ``and``, ``or``, ``not``
- Truthiness: bare values evaluated as ``bool()``
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_TEMPLATE_RE = re.compile(r"\{\{\s*(.+?)\s*\}\}")

_COMPARISON_OPS: list[tuple[str, Any]] = [
    (">=", lambda l, r: _numeric_cmp(l, r, lambda a, b: a >= b)),
    ("<=", lambda l, r: _numeric_cmp(l, r, lambda a, b: a <= b)),
    ("!=", lambda l, r: _strip(l) != _strip(r)),
    ("==", lambda l, r: _strip(l) == _strip(r)),
    (">", lambda l, r: _numeric_cmp(l, r, lambda a, b: a > b)),
    ("<", lambda l, r: _numeric_cmp(l, r, lambda a, b: a < b)),
]


def _strip(val: str) -> str:
    return val.strip().strip("'\"")


def _numeric_cmp(left: str, right: str, op: Any) -> bool:
    """Try numeric comparison; fall back to string comparison."""
    l_val, r_val = _strip(left), _strip(right)
    try:
        return op(float(l_val), float(r_val))
    except (ValueError, TypeError):
        return op(l_val, r_val)


@dataclass(frozen=True)
class TemplateContext:
    """Bundles the three runtime data sources available to templates."""

    trigger: dict[str, Any]
    steps: dict[str, Any]
    context: dict[str, Any]


class TemplateEngine:
    """Resolve ``{{ expr }}`` placeholders against a :class:`TemplateContext`."""

    def __init__(self, ctx: TemplateContext) -> None:
        self._ctx = ctx

    def render(self, data: Any) -> Any:
        """Recursively walk *data* and replace every ``{{ expr }}`` with its value."""
        if isinstance(data, str):
            return self._render_string(data)
        if isinstance(data, dict):
            return {k: self.render(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self.render(v) for v in data]
        return data

    def evaluate(self, expr: str) -> bool:
        """Evaluate a condition expression with ``and``/``or``/``not`` support.

        Examples::

            steps.analyze.output.sentiment == 'negative'
            steps.a.output.score > 0.5 and steps.a.output.lang == 'en'
            not steps.a.output.flag
        """
        resolved = self._render_string(expr)
        text = str(resolved) if not isinstance(resolved, str) else resolved
        return self._eval_or(text)

    # -- Recursive-descent parser for boolean expressions ----------------------

    def _eval_or(self, text: str) -> bool:
        parts = _split_logical(text, " or ")
        return any(self._eval_and(p) for p in parts)

    def _eval_and(self, text: str) -> bool:
        parts = _split_logical(text, " and ")
        return all(self._eval_not(p) for p in parts)

    def _eval_not(self, text: str) -> bool:
        stripped = text.strip()
        if stripped.startswith("not "):
            return not self._eval_atom(stripped[4:].strip())
        return self._eval_atom(stripped)

    def _eval_atom(self, text: str) -> bool:
        """Evaluate a single comparison or truthiness check."""
        for op_str, op_fn in _COMPARISON_OPS:
            if op_str in text:
                left, right = text.split(op_str, 1)
                return op_fn(left, right)
        val = text.strip().strip("'\"")
        if val.lower() in ("false", "none", "null", "0", ""):
            return False
        return bool(val)

    # -- Template rendering ----------------------------------------------------

    def _render_string(self, text: str) -> Any:
        full_match = _TEMPLATE_RE.fullmatch(text)
        if full_match:
            return self._resolve(full_match.group(1))

        return _TEMPLATE_RE.sub(
            lambda m: str(v) if (v := self._resolve(m.group(1))) is not None else "",
            text,
        )

    def _resolve(self, expr: str) -> Any:
        """Look up a dotted path like ``trigger.user.name``."""
        parts = expr.strip().split(".")
        if not parts:
            return None

        namespace, path = parts[0], parts[1:]

        if namespace == "trigger":
            return _deep_get(self._ctx.trigger, path)
        if namespace == "steps" and path:
            step_data = self._ctx.steps.get(path[0])
            return _deep_get(step_data, path[1:]) if step_data else None
        if namespace == "context":
            return _deep_get(self._ctx.context, path)

        return None


def _deep_get(data: Any, path: list[str]) -> Any:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
        if data is None:
            return None
    return data


def _split_logical(text: str, keyword: str) -> list[str]:
    """Split on a logical keyword while respecting quoted strings."""
    parts: list[str] = []
    current: list[str] = []
    in_quote: str | None = None

    i = 0
    while i < len(text):
        ch = text[i]
        if ch in ("'", '"'):
            in_quote = None if in_quote == ch else (in_quote or ch)
            current.append(ch)
            i += 1
        elif in_quote is None and text[i:].startswith(keyword):
            parts.append("".join(current))
            current = []
            i += len(keyword)
        else:
            current.append(ch)
            i += 1

    parts.append("".join(current))
    return parts
