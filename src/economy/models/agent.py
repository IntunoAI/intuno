"""Economy agent model — re-exports wisdom's Agent model.

The economy module no longer maintains its own Agent ORM class.
Wisdom's Agent model (src.models.registry) is the single source of truth
for the ``agents`` table, now including pricing fields
(``pricing_strategy``, ``base_price``).
"""

from src.models.registry import Agent  # noqa: F401
