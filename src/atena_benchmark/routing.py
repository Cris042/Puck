from __future__ import annotations

from .config import Strategy

ROLE_TO_TIER_HIERARCHICAL = {
    "architect": "strong",
    "planner": "medium",
    "implementer": "weak",
    "repair": "weak",
    "reviewer": "strong",
}


def tier_for_role(strategy: Strategy, role: str) -> str:
    if strategy == "single":
        return "strong"
    return ROLE_TO_TIER_HIERARCHICAL.get(role, "strong")
