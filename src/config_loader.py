"""Load and validate assumptions from YAML config."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "assumptions.yaml"


def load_config(path: Path | None = None) -> dict[str, Any]:
    """Load assumptions YAML and return as dict."""
    config_path = path or DEFAULT_CONFIG_PATH
    with open(config_path) as f:
        return yaml.safe_load(f)


def get_revenue_defaults(config: dict, bedrooms: int) -> tuple[float, float]:
    """Get default ADR and occupancy for a bedroom count.

    Returns (adr, occupancy) using the closest available bedroom tier.
    """
    defaults = config["revenue_defaults"]
    adr_map = defaults["adr_by_bedrooms"]
    occ_map = defaults["occupancy_by_bedrooms"]

    available = sorted(adr_map.keys())
    # Clamp to available range
    bed_key = min(available, key=lambda k: abs(k - bedrooms))

    return float(adr_map[bed_key]), float(occ_map[bed_key])


def get_expense_config(config: dict) -> dict[str, Any]:
    """Return the expenses section."""
    return config["expenses"]


def get_tax_config(config: dict) -> dict[str, Any]:
    """Return the tax section."""
    return config["tax"]


def get_thresholds(config: dict) -> dict[str, Any]:
    """Return the return thresholds section."""
    return config["thresholds"]


def get_projection_config(config: dict) -> dict[str, Any]:
    """Return the appreciation/exit assumptions."""
    return config["projections"]


def get_holding_costs_config(config: dict) -> dict[str, Any]:
    """Return the holding cost reserve section."""
    return config["holding_costs"]
