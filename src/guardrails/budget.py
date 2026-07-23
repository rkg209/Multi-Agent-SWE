"""Per-task token-budget cap (FR-43, NFR-11): halts a run before it becomes runaway-expensive.

`is_budget_exceeded` is a pure function consulted at the top of every
conditional-edge routing function in `src/graph/graph.py` — those functions
cannot mutate `GraphState` (Spec 06's `cap_hit` constraint applies equally
here), so the solver re-derives `budget_exceeded` from the final state after
`graph.invoke()`, exactly like Spec 06's `cap_hit` derivation.
"""

from __future__ import annotations

from dataclasses import dataclass

import yaml

from src.errors import GuardrailError

DEFAULT_CONFIG_PATH = "config/budget.yaml"
DEFAULT_TOKEN_BUDGET = 100_000  # NFR-11: 50-task run stays under ~$5 at `strong`-tier pricing


@dataclass(frozen=True)
class BudgetConfig:
    """The per-task token cap, loaded from `config/budget.yaml`."""

    token_cap_per_task: int


def load_budget_config(path: str = DEFAULT_CONFIG_PATH) -> BudgetConfig:
    """Parse the YAML budget config at `path`.

    Falls back to `DEFAULT_TOKEN_BUDGET` if the file is absent (keeps
    existing solvers/tests working without requiring a new file), but raises
    `GuardrailError` on malformed YAML or an invalid value.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except FileNotFoundError:
        return BudgetConfig(token_cap_per_task=DEFAULT_TOKEN_BUDGET)
    except OSError as exc:
        raise GuardrailError(f"Could not read budget config at {path!r}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise GuardrailError(f"Invalid YAML in budget config at {path!r}: {exc}") from exc

    if not isinstance(raw, dict) or "token_cap_per_task" not in raw:
        raise GuardrailError(f"Budget config at {path!r} is missing 'token_cap_per_task'")

    try:
        token_cap = int(raw["token_cap_per_task"])
    except (TypeError, ValueError) as exc:
        raise GuardrailError(
            f"Budget config at {path!r} has a non-integer 'token_cap_per_task'"
        ) from exc

    return BudgetConfig(token_cap_per_task=token_cap)


def is_budget_exceeded(total_tokens: int, token_budget: int) -> bool:
    """Return whether `total_tokens` has reached or passed `token_budget`."""
    return total_tokens >= token_budget
