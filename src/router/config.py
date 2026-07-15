"""Router configuration: tier/role resolution loaded from `config/litellm_config.yaml`."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import yaml

from src.errors import RouterError

VALID_ROLES = {"architect", "developer", "tester", "reviewer", "system"}


class RouterConfigError(RouterError):
    """Raised when the router config file is missing, malformed, or invalid."""


@dataclass(frozen=True)
class ModelSpec:
    """A fully-resolved provider/model/price combination for one tier."""

    tier: str
    provider: str
    model: str
    input_price_per_1k: float
    output_price_per_1k: float
    api_base: str | None = None
    api_key_env: str | None = None


@dataclass(frozen=True)
class TierConfig:
    """Raw tier configuration as parsed from YAML, before dataclass validation."""

    name: str
    provider: str
    model: str
    input_price_per_1k: float
    output_price_per_1k: float
    api_base: str | None = None
    api_key_env: str | None = None


@dataclass(frozen=True)
class RouterConfig:
    """All tiers and the role -> tier map, ready for `resolve()` lookups."""

    tiers: dict[str, TierConfig] = field(default_factory=dict)
    roles: dict[str, str] = field(default_factory=dict)

    def resolve(self, role_or_tier: str) -> ModelSpec:
        """Resolve a role name or an explicit tier name to a `ModelSpec`.

        Role names (architect/developer/tester/reviewer/system) are looked up
        in `roles` first; anything else is treated as an explicit tier name.
        Raises `RouterConfigError` if neither a matching role nor tier exists.
        """
        tier_name = self.roles.get(role_or_tier, role_or_tier)
        tier = self.tiers.get(tier_name)
        if tier is None:
            raise RouterConfigError(
                f"Unknown role or tier {role_or_tier!r}; known tiers: {sorted(self.tiers)}, "
                f"known roles: {sorted(self.roles)}"
            )
        return ModelSpec(
            tier=tier.name,
            provider=tier.provider,
            model=tier.model,
            input_price_per_1k=tier.input_price_per_1k,
            output_price_per_1k=tier.output_price_per_1k,
            api_base=tier.api_base,
            api_key_env=tier.api_key_env,
        )


def _expand_env(value: str | None) -> str | None:
    """Expand `${VAR}`-style env references; leave non-string values untouched."""
    if value is None:
        return None
    return os.path.expandvars(value)


def load_router_config(path: str) -> RouterConfig:
    """Parse the YAML config at `path`, expand env vars, and validate it.

    Raises `RouterConfigError` on a missing file, malformed YAML, a tier
    missing a required price field, or a role pointing at an undefined tier.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except OSError as exc:
        raise RouterConfigError(f"Could not read router config at {path!r}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise RouterConfigError(f"Invalid YAML in router config at {path!r}: {exc}") from exc

    if not isinstance(raw, dict) or not isinstance(raw.get("tiers"), dict):
        raise RouterConfigError(f"Router config at {path!r} is missing a top-level 'tiers' mapping")

    tiers: dict[str, TierConfig] = {}
    for tier_name, tier_raw in raw["tiers"].items():
        if not isinstance(tier_raw, dict):
            raise RouterConfigError(f"Tier {tier_name!r} must be a mapping")
        for required in ("provider", "model", "input_price_per_1k", "output_price_per_1k"):
            if required not in tier_raw:
                raise RouterConfigError(
                    f"Tier {tier_name!r} is missing required field {required!r}"
                )
        tiers[tier_name] = TierConfig(
            name=tier_name,
            provider=tier_raw["provider"],
            model=tier_raw["model"],
            input_price_per_1k=float(tier_raw["input_price_per_1k"]),
            output_price_per_1k=float(tier_raw["output_price_per_1k"]),
            api_base=_expand_env(tier_raw.get("api_base")),
            api_key_env=tier_raw.get("api_key_env"),
        )

    roles_raw = raw.get("roles") or {}
    if not isinstance(roles_raw, dict):
        raise RouterConfigError(f"Router config at {path!r} has a non-mapping 'roles' section")
    roles: dict[str, str] = roles_raw
    for role_name, tier_name in roles.items():
        if role_name not in VALID_ROLES:
            raise RouterConfigError(
                f"Role {role_name!r} in config is not a recognised agent role: "
                f"{sorted(VALID_ROLES)}"
            )
        if tier_name not in tiers:
            raise RouterConfigError(
                f"Role {role_name!r} maps to unknown tier {tier_name!r}; "
                f"known tiers: {sorted(tiers)}"
            )

    return RouterConfig(tiers=tiers, roles=roles)
